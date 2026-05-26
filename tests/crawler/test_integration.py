"""
End-to-end pipeline tests. yt-dlp is mocked so no real network calls are made.
Each test runs main() directly against fixture bookmark files and inspects the
resulting SQLite database.
"""
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from crawler import cli
from crawler.models import VideoMetadata

FIXTURES = Path(__file__).parent / "fixtures"


def _mock_fetch_for(video_id: str) -> VideoMetadata:
    return VideoMetadata(
        video_id=video_id,
        url=f"https://www.youtube.com/watch?v={video_id}",
        title=f"Title for {video_id}",
        channel_name="TestChannel",
        channel_id="UC_test",
        yt_view_count=42000,
        duration_seconds=300,
        thumbnail_url=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        fetch_status="ok",
    )


def _run(args: list[str]) -> int:
    def _fetch(video_id, delay=1.5):
        return _mock_fetch_for(video_id)

    with patch("crawler.cli.fetch_metadata", side_effect=_fetch):
        with patch.object(sys, "argv", ["crawler"] + args):
            try:
                cli.main()
                return 0
            except SystemExit as e:
                return e.code


class TestFullPipelineJson:
    def test_exits_zero(self, tmp_path):
        code = _run(["-i", str(FIXTURES / "sample_bookmarks.json"), "-o", str(tmp_path / "v.db")])
        assert code == 0

    def test_creates_database(self, tmp_path):
        db = tmp_path / "v.db"
        _run(["-i", str(FIXTURES / "sample_bookmarks.json"), "-o", str(db)])
        assert db.exists()

    def test_inserts_correct_row_count(self, tmp_path):
        db = tmp_path / "v.db"
        _run(["-i", str(FIXTURES / "sample_bookmarks.json"), "-o", str(db)])
        conn = sqlite3.connect(str(db))
        # fixture has 3 YouTube URLs: dQw4w9WgXcQ, 9bZkp7q19f0, Ks-_Mh1QhMc
        count = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        conn.close()
        assert count == 3

    def test_row_contains_expected_fields(self, tmp_path):
        db = tmp_path / "v.db"
        _run(["-i", str(FIXTURES / "sample_bookmarks.json"), "-o", str(db)])
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM videos WHERE video_id = ?", ("dQw4w9WgXcQ",)
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["title"] == "Title for dQw4w9WgXcQ"
        assert row["channel_name"] == "TestChannel"
        assert row["yt_view_count"] == 42000
        assert row["personal_view_count"] == 0
        assert row["date_last_viewed"] is None
        assert row["fetch_status"] == "ok"
        assert row["date_added"] is not None  # parsed from bookmark

    def test_non_youtube_urls_excluded(self, tmp_path):
        db = tmp_path / "v.db"
        _run(["-i", str(FIXTURES / "sample_bookmarks.json"), "-o", str(db)])
        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT * FROM videos WHERE url LIKE '%python.org%'"
        ).fetchone()
        conn.close()
        assert row is None


class TestFullPipelineHtml:
    def test_exits_zero(self, tmp_path):
        code = _run(["-i", str(FIXTURES / "sample_bookmarks.html"), "-o", str(tmp_path / "v.db")])
        assert code == 0

    def test_inserts_correct_row_count(self, tmp_path):
        db = tmp_path / "v.db"
        _run(["-i", str(FIXTURES / "sample_bookmarks.html"), "-o", str(db)])
        conn = sqlite3.connect(str(db))
        count = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        conn.close()
        # fixture has 3 YouTube links: dQw4w9WgXcQ, 9bZkp7q19f0, Ks-_Mh1QhMc
        assert count == 3


class TestIncrementalRun:
    def test_does_not_duplicate_rows(self, tmp_path):
        db = tmp_path / "v.db"
        args = ["-i", str(FIXTURES / "sample_bookmarks.json"), "-o", str(db)]
        _run(args)
        _run(args)
        conn = sqlite3.connect(str(db))
        count = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        conn.close()
        assert count == 3

    def test_preserves_personal_view_count(self, tmp_path):
        """Crawler rerun must NOT reset personal_view_count set by the webapp."""
        db = tmp_path / "v.db"
        args = ["-i", str(FIXTURES / "sample_bookmarks.json"), "-o", str(db)]
        _run(args)

        # Simulate webapp recording 7 views for one video
        conn = sqlite3.connect(str(db))
        conn.execute(
            "UPDATE videos SET personal_view_count = 7 WHERE video_id = ?",
            ("dQw4w9WgXcQ",),
        )
        conn.commit()
        conn.close()

        # Crawler reruns with force-refresh
        _run(args + ["--force-refresh"])

        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT personal_view_count FROM videos WHERE video_id = ?",
            ("dQw4w9WgXcQ",),
        ).fetchone()
        conn.close()
        assert row[0] == 7

    def test_preserves_date_last_viewed(self, tmp_path):
        db = tmp_path / "v.db"
        args = ["-i", str(FIXTURES / "sample_bookmarks.json"), "-o", str(db)]
        _run(args)

        conn = sqlite3.connect(str(db))
        conn.execute(
            "UPDATE videos SET date_last_viewed = '2024-09-01T12:00:00' WHERE video_id = ?",
            ("dQw4w9WgXcQ",),
        )
        conn.commit()
        conn.close()

        _run(args + ["--force-refresh"])

        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT date_last_viewed FROM videos WHERE video_id = ?",
            ("dQw4w9WgXcQ",),
        ).fetchone()
        conn.close()
        assert row[0] == "2024-09-01T12:00:00"

    def test_updates_yt_view_count_on_rerun(self, tmp_path):
        db = tmp_path / "v.db"
        args = ["-i", str(FIXTURES / "sample_bookmarks.json"), "-o", str(db), "--force-refresh"]

        def _fetch_v1(video_id, delay=1.5):
            m = _mock_fetch_for(video_id)
            m.yt_view_count = 1000
            return m

        def _fetch_v2(video_id, delay=1.5):
            m = _mock_fetch_for(video_id)
            m.yt_view_count = 2000
            return m

        with patch("crawler.cli.fetch_metadata", side_effect=_fetch_v1):
            with patch.object(sys, "argv", ["crawler"] + args):
                try:
                    cli.main()
                except SystemExit:
                    pass

        with patch("crawler.cli.fetch_metadata", side_effect=_fetch_v2):
            with patch.object(sys, "argv", ["crawler"] + args):
                try:
                    cli.main()
                except SystemExit:
                    pass

        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT yt_view_count FROM videos WHERE video_id = ?", ("dQw4w9WgXcQ",)
        ).fetchone()
        conn.close()
        assert row[0] == 2000

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from crawler import cli
from crawler.models import VideoMetadata

FIXTURES = Path(__file__).parent / "fixtures"

_GOOD_METADATA = VideoMetadata(
    video_id="dQw4w9WgXcQ",
    url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    title="Rick Astley",
    channel_name="RickAstleyVEVO",
    yt_view_count=1_000_000,
    fetch_status="ok",
)


def _run_main(args: list[str], mock_fetch=None):
    if mock_fetch is None:
        mock_fetch = MagicMock(return_value=_GOOD_METADATA)
    with patch("crawler.cli.fetch_metadata", mock_fetch):
        with patch.object(sys, "argv", ["crawler"] + args):
            try:
                cli.main()
                return 0
            except SystemExit as e:
                return e.code


class TestCliExitCodes:
    def test_exits_1_when_input_file_missing(self, tmp_path):
        code = _run_main(["-i", str(tmp_path / "missing.json"), "-o", str(tmp_path / "out.db")])
        assert code == 1

    def test_exits_2_when_input_format_unknown(self, tmp_path):
        bad = tmp_path / "bookmarks.csv"
        bad.write_text("url\nhttps://youtube.com")
        code = _run_main(["-i", str(bad), "-o", str(tmp_path / "out.db")])
        assert code == 2

    def test_exits_0_on_valid_json_input(self, tmp_path):
        code = _run_main([
            "-i", str(FIXTURES / "sample_bookmarks.json"),
            "-o", str(tmp_path / "out.db"),
        ])
        assert code == 0

    def test_exits_0_on_valid_html_input(self, tmp_path):
        code = _run_main([
            "-i", str(FIXTURES / "sample_bookmarks.html"),
            "-o", str(tmp_path / "out.db"),
        ])
        assert code == 0


class TestCliDatabase:
    def test_creates_output_db(self, tmp_path):
        out = tmp_path / "out.db"
        _run_main(["-i", str(FIXTURES / "sample_bookmarks.json"), "-o", str(out)])
        assert out.exists()

    def test_populates_db_with_rows(self, tmp_path):
        out = tmp_path / "out.db"
        _run_main(["-i", str(FIXTURES / "sample_bookmarks.json"), "-o", str(out)])
        conn = sqlite3.connect(str(out))
        count = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        conn.close()
        assert count > 0

    def test_new_rows_have_zero_personal_view_count(self, tmp_path):
        out = tmp_path / "out.db"
        _run_main(["-i", str(FIXTURES / "sample_bookmarks.json"), "-o", str(out)])
        conn = sqlite3.connect(str(out))
        rows = conn.execute("SELECT personal_view_count FROM videos").fetchall()
        conn.close()
        assert all(r[0] == 0 for r in rows)

    def test_new_rows_have_null_date_last_viewed(self, tmp_path):
        out = tmp_path / "out.db"
        _run_main(["-i", str(FIXTURES / "sample_bookmarks.json"), "-o", str(out)])
        conn = sqlite3.connect(str(out))
        rows = conn.execute("SELECT date_last_viewed FROM videos").fetchall()
        conn.close()
        assert all(r[0] is None for r in rows)

    def test_limit_flag_restricts_processing(self, tmp_path):
        out = tmp_path / "out.db"
        _run_main([
            "-i", str(FIXTURES / "sample_bookmarks.json"),
            "-o", str(out),
            "--limit", "1",
        ])
        conn = sqlite3.connect(str(out))
        count = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        conn.close()
        assert count == 1

    def test_skips_already_fetched_by_default(self, tmp_path):
        out = tmp_path / "out.db"
        mock_fetch = MagicMock(return_value=_GOOD_METADATA)
        _run_main([
            "-i", str(FIXTURES / "sample_bookmarks.json"),
            "-o", str(out), "--limit", "1",
        ], mock_fetch=mock_fetch)
        first_call_count = mock_fetch.call_count
        # second run — same video already in DB
        _run_main([
            "-i", str(FIXTURES / "sample_bookmarks.json"),
            "-o", str(out), "--limit", "1",
        ], mock_fetch=mock_fetch)
        assert mock_fetch.call_count == first_call_count  # no additional calls

    def test_force_refresh_re_fetches(self, tmp_path):
        out = tmp_path / "out.db"
        mock_fetch = MagicMock(return_value=_GOOD_METADATA)
        _run_main([
            "-i", str(FIXTURES / "sample_bookmarks.json"),
            "-o", str(out), "--limit", "1",
        ], mock_fetch=mock_fetch)
        first_call_count = mock_fetch.call_count
        _run_main([
            "-i", str(FIXTURES / "sample_bookmarks.json"),
            "-o", str(out), "--limit", "1", "--force-refresh",
        ], mock_fetch=mock_fetch)
        assert mock_fetch.call_count > first_call_count


class TestCliErrorHandling:
    def test_logs_errors_but_continues(self, tmp_path, capsys):
        out = tmp_path / "out.db"
        error_meta = VideoMetadata(
            video_id="dQw4w9WgXcQ",
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            fetch_status="error",
            fetch_error="Network timeout",
        )
        mock_fetch = MagicMock(return_value=error_meta)
        code = _run_main([
            "-i", str(FIXTURES / "sample_bookmarks.json"),
            "-o", str(out),
        ], mock_fetch=mock_fetch)
        assert code == 0  # crawler does not crash on individual video errors

    def test_prints_progress_to_stdout(self, tmp_path, capsys):
        out = tmp_path / "out.db"
        _run_main([
            "-i", str(FIXTURES / "sample_bookmarks.json"),
            "-o", str(out), "--limit", "1",
        ])
        captured = capsys.readouterr()
        assert "[1/" in captured.out

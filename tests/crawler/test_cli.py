import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from crawler import cli
from crawler.models import ChannelMetadata, VideoMetadata

FIXTURES = Path(__file__).parent / "fixtures"

_GOOD_CHANNEL_META = ChannelMetadata(
    channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
    channel_name="RickAstleyVEVO",
    channel_url="https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
    description="The official Rick Astley channel",
    subscriber_count=4_000_000,
    thumbnail_url="https://yt3.ggpht.com/rick.jpg",
)

_GOOD_METADATA = VideoMetadata(
    video_id="dQw4w9WgXcQ",
    url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    title="Rick Astley",
    channel_name="RickAstleyVEVO",
    yt_view_count=1_000_000,
    fetch_status="ok",
)


def _run_main(args: list[str], mock_fetch=None, mock_channel_fetch=None):
    if mock_fetch is None:
        mock_fetch = MagicMock(return_value=_GOOD_METADATA)
    if mock_channel_fetch is None:
        mock_channel_fetch = MagicMock(return_value=_GOOD_CHANNEL_META)
    with patch("crawler.cli.fetch_metadata", mock_fetch):
        with patch("crawler.cli.fetch_channel_metadata", mock_channel_fetch):
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


class TestCliChannelBookmarks:
    def test_channel_bookmark_stored_in_channels_table(self, tmp_path):
        out = tmp_path / "out.db"
        _run_main(["-i", str(FIXTURES / "sample_bookmarks.json"), "-o", str(out)])
        conn = sqlite3.connect(str(out))
        row = conn.execute(
            "SELECT * FROM channels WHERE channel_id = 'UCuAXFkgsw1L7xaCfnd5JJOw'"
        ).fetchone()
        conn.close()
        assert row is not None

    def test_channel_bookmark_has_full_metadata(self, tmp_path):
        out = tmp_path / "out.db"
        _run_main(["-i", str(FIXTURES / "sample_bookmarks.json"), "-o", str(out)])
        conn = sqlite3.connect(str(out))
        row = conn.execute(
            "SELECT description FROM channels WHERE channel_id = 'UCuAXFkgsw1L7xaCfnd5JJOw'"
        ).fetchone()
        conn.close()
        assert row[0] == "The official Rick Astley channel"

    def test_fetch_channel_metadata_called_for_channel_bookmark(self, tmp_path):
        out = tmp_path / "out.db"
        mock_ch = MagicMock(return_value=_GOOD_CHANNEL_META)
        _run_main(["-i", str(FIXTURES / "sample_bookmarks.json"), "-o", str(out)],
                  mock_channel_fetch=mock_ch)
        mock_ch.assert_called()
        called_url = mock_ch.call_args[0][0]
        assert "rickastley" in called_url


class TestCliChannelStubSideEffect:
    def test_video_processing_creates_channel_stub(self, tmp_path):
        out = tmp_path / "out.db"
        video_only_json = tmp_path / "video_only.json"
        video_only_json.write_text("""{
  "guid": "root________", "title": "", "id": 1,
  "dateAdded": 1600000000000000, "lastModified": 1700000000000000,
  "type": "text/x-moz-place-container", "root": "placesRoot",
  "children": [{"guid": "bm1", "title": "V", "id": 2,
    "dateAdded": 1620000000000000, "lastModified": 1700000000000000,
    "type": "text/x-moz-place", "typeCode": 1,
    "uri": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}]
}""")
        meta = MagicMock(return_value=VideoMetadata(
            video_id="dQw4w9WgXcQ",
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            channel_name="RickAstleyVEVO",
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            fetch_status="ok",
        ))
        _run_main(["-i", str(video_only_json), "-o", str(out)], mock_fetch=meta)
        conn = sqlite3.connect(str(out))
        row = conn.execute(
            "SELECT channel_name FROM channels WHERE channel_id = 'UCuAXFkgsw1L7xaCfnd5JJOw'"
        ).fetchone()
        conn.close()
        assert row is not None

    def test_stub_has_no_description(self, tmp_path):
        out = tmp_path / "out.db"
        video_only_json = tmp_path / "video_only.json"
        video_only_json.write_text("""{
  "guid": "root________", "title": "", "id": 1,
  "dateAdded": 1600000000000000, "lastModified": 1700000000000000,
  "type": "text/x-moz-place-container", "root": "placesRoot",
  "children": [{"guid": "bm1", "title": "V", "id": 2,
    "dateAdded": 1620000000000000, "lastModified": 1700000000000000,
    "type": "text/x-moz-place", "typeCode": 1,
    "uri": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}]
}""")
        meta = MagicMock(return_value=VideoMetadata(
            video_id="dQw4w9WgXcQ",
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            channel_name="RickAstleyVEVO",
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            fetch_status="ok",
        ))
        _run_main(["-i", str(video_only_json), "-o", str(out)], mock_fetch=meta)
        conn = sqlite3.connect(str(out))
        row = conn.execute(
            "SELECT description FROM channels WHERE channel_id = 'UCuAXFkgsw1L7xaCfnd5JJOw'"
        ).fetchone()
        conn.close()
        assert row[0] is None


class TestCliBackfillChannels:
    def test_backfill_fetches_full_metadata_for_stubs(self, tmp_path):
        out = tmp_path / "out.db"
        video_only_json = tmp_path / "video_only.json"
        video_only_json.write_text("""{
  "guid": "root________", "title": "", "id": 1,
  "dateAdded": 1600000000000000, "lastModified": 1700000000000000,
  "type": "text/x-moz-place-container", "root": "placesRoot",
  "children": [{"guid": "bm1", "title": "V", "id": 2,
    "dateAdded": 1620000000000000, "lastModified": 1700000000000000,
    "type": "text/x-moz-place", "typeCode": 1,
    "uri": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}]
}""")
        first_meta = MagicMock(return_value=VideoMetadata(
            video_id="dQw4w9WgXcQ",
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            channel_name="RickAstleyVEVO",
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            fetch_status="ok",
        ))
        _run_main(["-i", str(video_only_json), "-o", str(out)], mock_fetch=first_meta)

        mock_ch = MagicMock(return_value=_GOOD_CHANNEL_META)
        _run_main(["-i", str(video_only_json), "-o", str(out), "--backfill-channels"],
                  mock_fetch=MagicMock(return_value=VideoMetadata(
                      video_id="dQw4w9WgXcQ",
                      url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                      fetch_status="ok",
                  )),
                  mock_channel_fetch=mock_ch)
        mock_ch.assert_called()
        conn = sqlite3.connect(str(out))
        row = conn.execute(
            "SELECT description FROM channels WHERE channel_id = 'UCuAXFkgsw1L7xaCfnd5JJOw'"
        ).fetchone()
        conn.close()
        assert row[0] == "The official Rick Astley channel"

    def test_backfill_not_run_without_flag(self, tmp_path):
        out = tmp_path / "out.db"
        video_only_json = tmp_path / "video_only.json"
        video_only_json.write_text("""{
  "guid": "root________", "title": "", "id": 1,
  "dateAdded": 1600000000000000, "lastModified": 1700000000000000,
  "type": "text/x-moz-place-container", "root": "placesRoot",
  "children": [{"guid": "bm1", "title": "V", "id": 2,
    "dateAdded": 1620000000000000, "lastModified": 1700000000000000,
    "type": "text/x-moz-place", "typeCode": 1,
    "uri": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}]
}""")
        first_meta = MagicMock(return_value=VideoMetadata(
            video_id="dQw4w9WgXcQ",
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            channel_name="RickAstleyVEVO",
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            fetch_status="ok",
        ))
        _run_main(["-i", str(video_only_json), "-o", str(out)], mock_fetch=first_meta)

        mock_ch = MagicMock(return_value=_GOOD_CHANNEL_META)
        _run_main(["-i", str(video_only_json), "-o", str(out)],
                  mock_fetch=MagicMock(return_value=VideoMetadata(
                      video_id="dQw4w9WgXcQ",
                      url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                      fetch_status="ok",
                  )),
                  mock_channel_fetch=mock_ch)
        mock_ch.assert_not_called()

import sqlite3
import pytest
from scripts.seed_demo_db import bootstrap_schema, seed_content, VIDEOS, CHANNELS, run


@pytest.fixture
def conn(tmp_path):
    db_path = str(tmp_path / "demo.db")
    bootstrap_schema(db_path)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    yield connection
    connection.close()


class TestSeedContent:
    def test_inserts_all_videos(self, conn):
        seed_content(conn, VIDEOS)
        count = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        assert count == 44

    def test_inserts_all_channels(self, conn):
        seed_content(conn, VIDEOS)
        count = conn.execute("SELECT COUNT(*) FROM channels").fetchone()[0]
        assert count == len(CHANNELS)
        assert count == 12

    def test_video_ids_are_real_youtube_ids(self, conn):
        seed_content(conn, VIDEOS)
        row = conn.execute(
            "SELECT title, channel_name, yt_view_count FROM videos WHERE video_id = ?",
            ("dQw4w9WgXcQ",),
        ).fetchone()
        assert row["channel_name"] == "Rick Astley"
        assert row["yt_view_count"] == 1805594426

    def test_date_added_is_spread_not_all_today(self, conn):
        seed_content(conn, VIDEOS)
        dates = [r[0] for r in conn.execute("SELECT date_added FROM videos").fetchall()]
        assert len(set(dates)) > 1  # not all the same instant


class TestRunCli:
    def test_refuses_to_overwrite_without_force(self, tmp_path):
        db_path = tmp_path / "demo.db"
        db_path.write_text("not a real db")  # simulate an existing file
        with pytest.raises(SystemExit):
            run(["--output", str(db_path)])

    def test_force_overwrites_existing_file(self, tmp_path):
        db_path = tmp_path / "demo.db"
        db_path.write_text("not a real db")
        run(["--output", str(db_path), "--force"])
        connection = sqlite3.connect(str(db_path))
        count = connection.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        connection.close()
        assert count == 44

import sqlite3
from datetime import datetime, timezone
import pytest
from scripts.seed_demo_db import bootstrap_schema, seed_content, seed_tags, seed_engagement, VIDEOS, CHANNELS, run


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
        # Regression test: the newest video must land within the app's own "added in the
        # last 7 days" filter, so a freshly seeded demo isn't empty for that filter.
        parsed_dates = [datetime.fromisoformat(d) for d in dates]
        newest = max(parsed_dates)
        assert (datetime.now(timezone.utc) - newest).days <= 7


class TestSeedTags:
    def test_creates_three_tag_groups(self, conn):
        seed_content(conn, VIDEOS)
        seed_tags(conn)
        count = conn.execute("SELECT COUNT(*) FROM tag_groups").fetchone()[0]
        assert count == 3

    def test_creates_twelve_canonical_tags(self, conn):
        seed_content(conn, VIDEOS)
        seed_tags(conn)
        count = conn.execute(
            "SELECT COUNT(*) FROM tags WHERE is_canonical = 1"
        ).fetchone()[0]
        assert count == 12

    def test_leaves_some_tags_unclassified(self, conn):
        seed_content(conn, VIDEOS)
        seed_tags(conn)
        count = conn.execute(
            "SELECT COUNT(*) FROM tags WHERE is_canonical = 0"
        ).fetchone()[0]
        assert count == 5  # sql, guitar-maintenance, space, woodworking, workshop

    def test_every_video_has_at_least_one_tag(self, conn):
        seed_content(conn, VIDEOS)
        seed_tags(conn)
        untagged = conn.execute("""
            SELECT COUNT(*) FROM videos v
            WHERE NOT EXISTS (
                SELECT 1 FROM video_tags vt WHERE vt.video_id_fk = v.id
            )
        """).fetchone()[0]
        assert untagged == 0


class TestSeedEngagement:
    def test_six_favorites(self, conn):
        seed_content(conn, VIDEOS)
        seed_engagement(conn)
        count = conn.execute(
            "SELECT COUNT(*) FROM videos WHERE is_favorite = 1"
        ).fetchone()[0]
        assert count == 6

    def test_eight_videos_in_watch_later_in_order(self, conn):
        seed_content(conn, VIDEOS)
        seed_engagement(conn)
        rows = conn.execute("""
            SELECT v.video_id FROM watch_later w
            JOIN videos v ON v.id = w.video_id_fk
            ORDER BY w.position
        """).fetchall()
        assert [r[0] for r in rows] == [
            "rfscVS0vtbw", "bMknfKXIFA8", "_QCt3UBTS1Y", "h6fcK_fRYaI",
            "4czjS9h4Fpg", "zfBkJggF9aU", "mvDj7DF1jsk", "iG9CE55wbtY",
        ]

    def test_three_hidden_videos(self, conn):
        seed_content(conn, VIDEOS)
        seed_engagement(conn)
        count = conn.execute(
            "SELECT COUNT(*) FROM videos WHERE is_hidden = 1"
        ).fetchone()[0]
        assert count == 3

    def test_view_history_has_a_real_spread(self, conn):
        seed_content(conn, VIDEOS)
        seed_engagement(conn)
        rows = conn.execute(
            "SELECT date_last_viewed FROM videos WHERE personal_view_count > 0"
        ).fetchall()
        assert len(rows) == 16
        dates = sorted(r[0] for r in rows)
        oldest = datetime.fromisoformat(dates[0])
        newest = datetime.fromisoformat(dates[-1])
        assert (newest - oldest).days > 400  # a real pool, not 1-2 eligible videos


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

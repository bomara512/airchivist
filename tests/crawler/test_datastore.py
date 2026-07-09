import sqlite3
import pytest
from datetime import datetime
from pathlib import Path

from crawler.datastore import Datastore
from crawler.models import Bookmark, VideoMetadata


def _make_metadata(video_id="abc12345678", **kwargs):
    defaults = dict(
        url=f"https://youtube.com/watch?v={video_id}",
        title="Test Video",
        channel_name="Test Channel",
        channel_id="UC123",
        yt_view_count=1000,
        duration_seconds=300,
        thumbnail_url="https://i.ytimg.com/vi/abc/hqdefault.jpg",
        date_published=datetime(2023, 6, 1),
        fetch_status="ok",
        yt_categories=[],
        yt_tags=[],
    )
    defaults.update(kwargs)
    return VideoMetadata(video_id=video_id, **defaults)


def _make_bookmark(video_id="abc12345678"):
    return Bookmark(
        url=f"https://youtube.com/watch?v={video_id}",
        title="Test Video",
        date_added=datetime(2024, 1, 1),
    )


class TestInitDb:
    def test_creates_videos_table(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            tables = ds._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            names = {r[0] for r in tables}
            assert "videos" in names

    def test_creates_tags_table(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            tables = ds._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            assert "tags" in {r[0] for r in tables}

    def test_creates_video_tags_table(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            tables = ds._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            assert "video_tags" in {r[0] for r in tables}

    def test_is_idempotent(self, tmp_path):
        db_path = tmp_path / "test.db"
        with Datastore(db_path):
            pass
        # opening again should not raise
        with Datastore(db_path):
            pass


class TestUpsertVideo:
    def test_inserts_new_row(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_video(_make_metadata(), _make_bookmark())
            count = ds._conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
            assert count == 1

    def test_does_not_duplicate(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_video(_make_metadata(), _make_bookmark())
            ds.upsert_video(_make_metadata(), _make_bookmark())
            count = ds._conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
            assert count == 1

    def test_updates_yt_view_count_on_rerun(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_video(_make_metadata(yt_view_count=1000), _make_bookmark())
            ds.upsert_video(_make_metadata(yt_view_count=2000), _make_bookmark())
            row = ds._conn.execute("SELECT yt_view_count FROM videos").fetchone()
            assert row[0] == 2000

    def test_preserves_personal_view_count_on_rerun(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_video(_make_metadata(), _make_bookmark())
            # simulate webapp incrementing view count
            ds._conn.execute(
                "UPDATE videos SET personal_view_count = 5 WHERE video_id = ?",
                ("abc12345678",),
            )
            ds._conn.commit()
            # re-run crawler
            ds.upsert_video(_make_metadata(yt_view_count=9999), _make_bookmark())
            row = ds._conn.execute("SELECT personal_view_count FROM videos").fetchone()
            assert row[0] == 5

    def test_preserves_date_last_viewed_on_rerun(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_video(_make_metadata(), _make_bookmark())
            ds._conn.execute(
                "UPDATE videos SET date_last_viewed = '2024-06-01T10:00:00' WHERE video_id = ?",
                ("abc12345678",),
            )
            ds._conn.commit()
            ds.upsert_video(_make_metadata(), _make_bookmark())
            row = ds._conn.execute("SELECT date_last_viewed FROM videos").fetchone()
            assert row[0] == "2024-06-01T10:00:00"

    def test_stores_date_added_from_bookmark(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_video(_make_metadata(), _make_bookmark())
            row = ds._conn.execute("SELECT date_added FROM videos").fetchone()
            assert row[0] == "2024-01-01T00:00:00"

    def test_new_row_has_zero_personal_view_count(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_video(_make_metadata(), _make_bookmark())
            row = ds._conn.execute("SELECT personal_view_count FROM videos").fetchone()
            assert row[0] == 0

    def test_new_row_has_null_date_last_viewed(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_video(_make_metadata(), _make_bookmark())
            row = ds._conn.execute("SELECT date_last_viewed FROM videos").fetchone()
            assert row[0] is None


class TestGetVideoById:
    def test_returns_row_for_existing(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_video(_make_metadata(), _make_bookmark())
            row = ds.get_video_by_id("abc12345678")
            assert row is not None
            assert row["video_id"] == "abc12345678"

    def test_returns_none_for_missing(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            assert ds.get_video_by_id("nonexistent") is None

    def test_returns_correct_fields(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_video(_make_metadata(title="My Video", yt_view_count=42000), _make_bookmark())
            row = ds.get_video_by_id("abc12345678")
            assert row["title"] == "My Video"
            assert row["yt_view_count"] == 42000


class TestGetAllVideos:
    def test_returns_list(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            result = ds.get_all_videos()
            assert isinstance(result, list)

    def test_returns_empty_for_empty_db(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            assert ds.get_all_videos() == []

    def test_returns_all_rows(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_video(_make_metadata("vid1111111a"), _make_bookmark("vid1111111a"))
            ds.upsert_video(_make_metadata("vid2222222b"), _make_bookmark("vid2222222b"))
            assert len(ds.get_all_videos()) == 2


class TestTags:
    def test_add_tag_creates_row(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            tag_id = ds.add_tag("guitar tutorials")
            assert isinstance(tag_id, int)
            row = ds._conn.execute("SELECT name FROM tags WHERE id=?", (tag_id,)).fetchone()
            assert row[0] == "guitar tutorials"

    def test_add_tag_is_idempotent(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            id1 = ds.add_tag("cooking")
            id2 = ds.add_tag("cooking")
            assert id1 == id2
            count = ds._conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
            assert count == 1

    def test_tag_video_creates_association(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_video(_make_metadata(), _make_bookmark())
            tag_id = ds.add_tag("music")
            ds.tag_video("abc12345678", tag_id)
            count = ds._conn.execute("SELECT COUNT(*) FROM video_tags").fetchone()[0]
            assert count == 1

    def test_tag_video_is_idempotent(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_video(_make_metadata(), _make_bookmark())
            tag_id = ds.add_tag("music")
            ds.tag_video("abc12345678", tag_id)
            ds.tag_video("abc12345678", tag_id)
            count = ds._conn.execute("SELECT COUNT(*) FROM video_tags").fetchone()[0]
            assert count == 1

    def test_get_tags_for_video(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_video(_make_metadata(), _make_bookmark())
            t1 = ds.add_tag("music")
            t2 = ds.add_tag("classics")
            ds.tag_video("abc12345678", t1)
            ds.tag_video("abc12345678", t2)
            tags = ds.get_tags_for_video("abc12345678")
            assert set(tags) == {"music", "classics"}


class TestAutoTagging:
    def test_upsert_creates_tags_from_yt_categories(self, tmp_path):
        meta = _make_metadata(yt_categories=["Music", "Education"])
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_video(meta, _make_bookmark())
            tags = ds.get_tags_for_video("abc12345678")
        assert "music" in tags
        assert "education" in tags

    def test_upsert_creates_tags_from_yt_tags(self, tmp_path):
        meta = _make_metadata(yt_tags=["guitar", "tutorial", "fingerstyle"])
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_video(meta, _make_bookmark())
            tags = ds.get_tags_for_video("abc12345678")
        assert "guitar" in tags
        assert "tutorial" in tags
        assert "fingerstyle" in tags

    def test_upsert_combines_categories_and_tags(self, tmp_path):
        meta = _make_metadata(yt_categories=["Music"], yt_tags=["pop", "80s"])
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_video(meta, _make_bookmark())
            tags = ds.get_tags_for_video("abc12345678")
        assert set(tags) == {"music", "pop", "80s"}

    def test_upsert_auto_tagging_is_idempotent_on_rerun(self, tmp_path):
        meta = _make_metadata(yt_categories=["Music"], yt_tags=["pop"])
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_video(meta, _make_bookmark())
            ds.upsert_video(meta, _make_bookmark())
            tag_count = ds._conn.execute("SELECT COUNT(*) FROM video_tags").fetchone()[0]
        assert tag_count == 2  # Music + pop, no duplicates

    def test_upsert_skips_empty_tag_names(self, tmp_path):
        meta = _make_metadata(yt_categories=["", "  "], yt_tags=["valid"])
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_video(meta, _make_bookmark())
            tags = ds.get_tags_for_video("abc12345678")
        assert tags == ["valid"]

    def test_upsert_no_tags_when_lists_empty(self, tmp_path):
        meta = _make_metadata(yt_categories=[], yt_tags=[])
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_video(meta, _make_bookmark())
            tags = ds.get_tags_for_video("abc12345678")
        assert tags == []

    def test_shared_tags_across_videos(self, tmp_path):
        """Two videos with the same category share one tags row."""
        m1 = _make_metadata("vid1111111a", yt_categories=["Music"])
        m2 = _make_metadata("vid2222222b", yt_categories=["Music"])
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_video(m1, _make_bookmark("vid1111111a"))
            ds.upsert_video(m2, _make_bookmark("vid2222222b"))
            tag_count = ds._conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
        assert tag_count == 1  # one "Music" tag row shared by both videos


class TestMisc:
    def test_set_fetch_status(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_video(_make_metadata(), _make_bookmark())
            ds.set_fetch_status("abc12345678", "error", "Network timeout")
            row = ds._conn.execute(
                "SELECT fetch_status, fetch_error FROM videos WHERE video_id=?",
                ("abc12345678",),
            ).fetchone()
            assert row[0] == "error"
            assert row[1] == "Network timeout"

    def test_count_videos(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            assert ds.count_videos() == 0
            ds.upsert_video(_make_metadata("vid1111111a"), _make_bookmark("vid1111111a"))
            ds.upsert_video(_make_metadata("vid2222222b"), _make_bookmark("vid2222222b"))
            assert ds.count_videos() == 2


from crawler.models import ChannelMetadata


def _make_channel_meta(channel_id="UCtest123", **kwargs):
    defaults = dict(
        channel_name="Test Channel",
        channel_url=f"https://www.youtube.com/channel/{channel_id}",
        description="A test description",
        subscriber_count=50_000,
        thumbnail_url="https://example.com/thumb.jpg",
        fetch_status="ok",
    )
    defaults.update(kwargs)
    return ChannelMetadata(channel_id=channel_id, **defaults)


class TestChannelsTable:
    def test_creates_channels_table(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            tables = ds._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            assert "channels" in {r[0] for r in tables}


class TestUpsertChannel:
    def test_inserts_all_fields(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_channel(_make_channel_meta())
            row = ds._conn.execute(
                "SELECT * FROM channels WHERE channel_id = 'UCtest123'"
            ).fetchone()
        assert row is not None
        assert row["channel_name"] == "Test Channel"
        assert row["description"] == "A test description"
        assert row["subscriber_count"] == 50_000
        assert row["thumbnail_url"] == "https://example.com/thumb.jpg"

    def test_updates_subscriber_count_on_conflict(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_channel(_make_channel_meta(subscriber_count=100))
            ds.upsert_channel(_make_channel_meta(subscriber_count=200))
            row = ds._conn.execute(
                "SELECT subscriber_count FROM channels WHERE channel_id = 'UCtest123'"
            ).fetchone()
        assert row["subscriber_count"] == 200

    def test_overwrites_description_on_conflict(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_channel(_make_channel_meta(description="Old"))
            ds.upsert_channel(_make_channel_meta(description="New"))
            row = ds._conn.execute(
                "SELECT description FROM channels WHERE channel_id = 'UCtest123'"
            ).fetchone()
        assert row["description"] == "New"


class TestUpsertChannelStub:
    def test_inserts_stub_record(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_channel_stub("UCabc", "My Channel", "https://youtube.com/channel/UCabc")
            row = ds._conn.execute(
                "SELECT * FROM channels WHERE channel_id = 'UCabc'"
            ).fetchone()
        assert row is not None
        assert row["channel_name"] == "My Channel"
        assert row["description"] is None
        assert row["subscriber_count"] is None

    def test_does_not_overwrite_description_after_full_upsert(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_channel(_make_channel_meta(
                channel_id="UCabc", description="Rich description", subscriber_count=999
            ))
            ds.upsert_channel_stub("UCabc", "Updated Name", "https://youtube.com/channel/UCabc")
            row = ds._conn.execute(
                "SELECT * FROM channels WHERE channel_id = 'UCabc'"
            ).fetchone()
        assert row["description"] == "Rich description"
        assert row["subscriber_count"] == 999

    def test_updates_channel_name_on_conflict(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_channel_stub("UCabc", "Old Name", "https://youtube.com/channel/UCabc")
            ds.upsert_channel_stub("UCabc", "New Name", "https://youtube.com/channel/UCabc")
            row = ds._conn.execute(
                "SELECT channel_name FROM channels WHERE channel_id = 'UCabc'"
            ).fetchone()
        assert row["channel_name"] == "New Name"


class TestGetChannelIdsForBackfill:
    def test_returns_channel_id_not_in_channels_table(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            meta = _make_metadata(channel_id="UCabc", channel_name="Test")
            ds.upsert_video(meta, _make_bookmark())
            ids = ds.get_channel_ids_for_backfill()
        assert "UCabc" in ids

    def test_returns_stub_only_channel(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            meta = _make_metadata(channel_id="UCabc", channel_name="Test")
            ds.upsert_video(meta, _make_bookmark())
            ds.upsert_channel_stub("UCabc", "Test", "https://youtube.com/channel/UCabc")
            ids = ds.get_channel_ids_for_backfill()
        assert "UCabc" in ids

    def test_excludes_fully_fetched_channel(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            meta = _make_metadata(channel_id="UCabc", channel_name="Test")
            ds.upsert_video(meta, _make_bookmark())
            ds.upsert_channel(_make_channel_meta(channel_id="UCabc"))
            ids = ds.get_channel_ids_for_backfill()
        assert "UCabc" not in ids

    def test_returns_empty_list_when_no_videos(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ids = ds.get_channel_ids_for_backfill()
        assert ids == []

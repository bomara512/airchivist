import sqlite3
from contextlib import closing
from datetime import datetime

import pytest

from crawler.datastore import Datastore, apply_aliases
from crawler.models import Bookmark, ChannelMetadata, FetchStatus, VideoMetadata
from webapp.db import init_webapp_tables
from webapp.db.tags import remove_video_tag


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
        assert row["thumbnail_url"] == "https://example.com/thumb.jpg"

    def test_updates_channel_name_on_conflict(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_channel_stub("UCabc", "Old Name", "https://youtube.com/channel/UCabc")
            ds.upsert_channel_stub("UCabc", "New Name", "https://youtube.com/channel/UCabc")
            row = ds._conn.execute(
                "SELECT channel_name FROM channels WHERE channel_id = 'UCabc'"
            ).fetchone()
        assert row["channel_name"] == "New Name"


class TestHasFullChannelRecord:
    def test_returns_false_when_no_record(self, tmp_path):
        with Datastore(tmp_path / "db.sqlite") as ds:
            assert ds.has_full_channel_record("https://www.youtube.com/@none") is False

    def test_returns_false_for_stub_only(self, tmp_path):
        with Datastore(tmp_path / "db.sqlite") as ds:
            ds.upsert_channel_stub("UC123", "Chan", "https://www.youtube.com/channel/UC123")
            assert ds.has_full_channel_record("https://www.youtube.com/channel/UC123") is False

    def test_returns_true_when_full_record_matches_channel_url(self, tmp_path):
        with Datastore(tmp_path / "db.sqlite") as ds:
            meta = _make_channel_meta()  # has description set
            ds.upsert_channel(meta)
            assert ds.has_full_channel_record(meta.channel_url) is True

    def test_returns_true_when_full_record_matches_source_url(self, tmp_path):
        with Datastore(tmp_path / "db.sqlite") as ds:
            meta = _make_channel_meta()
            ds.upsert_channel(meta, source_url="https://www.youtube.com/@rickastley")
            assert ds.has_full_channel_record("https://www.youtube.com/@rickastley") is True

    def test_returns_false_for_unrelated_url(self, tmp_path):
        with Datastore(tmp_path / "db.sqlite") as ds:
            meta = _make_channel_meta()
            ds.upsert_channel(meta, source_url="https://www.youtube.com/@rickastley")
            assert ds.has_full_channel_record("https://www.youtube.com/@other") is False


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

    def test_returns_video_channel_with_null_thumbnail(self, tmp_path):
        # Channel has a description but no thumbnail (e.g. fetched before the
        # thumbnail fix) — it needs re-fetching.
        with Datastore(tmp_path / "test.db") as ds:
            meta = _make_metadata(channel_id="UCabc", channel_name="Test")
            ds.upsert_video(meta, _make_bookmark())
            ds.upsert_channel(_make_channel_meta(channel_id="UCabc", thumbnail_url=None))
            ids = ds.get_channel_ids_for_backfill()
        assert "UCabc" in ids

    def test_returns_bookmark_only_channel_with_null_thumbnail(self, tmp_path):
        # A channel with no associated videos (bookmark-only) that lacks a
        # thumbnail must still be reachable for backfill.
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_channel(_make_channel_meta(channel_id="UConly", thumbnail_url=None))
            ids = ds.get_channel_ids_for_backfill()
        assert "UConly" in ids


class TestWalMode:
    """The crawler may be the only thing that ever opens a given database — a
    scheduled refresh on a machine where the webapp was never started — so it
    cannot rely on init_webapp_tables having set the journal mode."""

    def test_datastore_switches_the_database_to_wal(self, tmp_path):
        db_path = tmp_path / "wal.db"
        with Datastore(db_path):
            pass
        with closing(sqlite3.connect(str(db_path))) as conn:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


class TestRefreshVideo:
    """A refresh must never trade a real title for the fact that a video died."""

    def _seed_ok(self, ds):
        ds.upsert_video(
            VideoMetadata(
                video_id="aaaaaaaaaa1",
                url="https://www.youtube.com/watch?v=aaaaaaaaaa1",
                title="Original Title",
                description="Original description",
                channel_name="Original Channel",
                channel_id="UCorig",
                yt_view_count=1000,
                duration_seconds=600,
                thumbnail_url="https://example.test/thumb.jpg",
                fetch_status=FetchStatus.OK,
            ),
            Bookmark(url="https://www.youtube.com/watch?v=aaaaaaaaaa1", title="Original Title"),
        )

    def test_a_deleted_video_keeps_its_last_known_metadata(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            self._seed_ok(ds)
            ds.refresh_video(VideoMetadata(
                video_id="aaaaaaaaaa1",
                url="https://www.youtube.com/watch?v=aaaaaaaaaa1",
                fetch_status=FetchStatus.DELETED,
                fetch_error="Video unavailable",
            ))
            row = ds.get_video_by_id("aaaaaaaaaa1")
        assert row["fetch_status"] == "deleted"
        assert row["fetch_error"] == "Video unavailable"
        assert row["title"] == "Original Title"
        assert row["description"] == "Original description"
        assert row["channel_name"] == "Original Channel"
        assert row["channel_id"] == "UCorig"
        assert row["yt_view_count"] == 1000
        assert row["duration_seconds"] == 600
        assert row["thumbnail_url"] == "https://example.test/thumb.jpg"

    def test_a_private_video_keeps_its_last_known_metadata(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            self._seed_ok(ds)
            ds.refresh_video(VideoMetadata(
                video_id="aaaaaaaaaa1",
                url="https://www.youtube.com/watch?v=aaaaaaaaaa1",
                fetch_status=FetchStatus.PRIVATE,
                fetch_error="Private video",
            ))
            row = ds.get_video_by_id("aaaaaaaaaa1")
        assert row["fetch_status"] == "private"
        assert row["title"] == "Original Title"

    def test_a_successful_refresh_updates_the_metadata(self, tmp_path):
        """Every refreshable column gets a distinct, recognizable value here so a
        positional mix-up between two columns (e.g. description <-> thumbnail_url)
        cannot coincidentally satisfy two assertions at once."""
        with Datastore(tmp_path / "t.db") as ds:
            self._seed_ok(ds)
            ds.refresh_video(VideoMetadata(
                video_id="aaaaaaaaaa1",
                url="https://example.test/new-url",
                title="Renamed Title",
                description="New description",
                channel_name="Renamed Channel",
                channel_id="UCnew",
                yt_view_count=5000,
                duration_seconds=601,
                thumbnail_url="https://example.test/new.jpg",
                date_published=datetime(2025, 3, 4, 5, 6, 7),
                fetch_status=FetchStatus.OK,
            ))
            row = ds.get_video_by_id("aaaaaaaaaa1")
        assert row["url"] == "https://example.test/new-url"
        assert row["title"] == "Renamed Title"
        assert row["description"] == "New description"
        assert row["channel_name"] == "Renamed Channel"
        assert row["channel_id"] == "UCnew"
        assert row["yt_view_count"] == 5000
        assert row["duration_seconds"] == 601
        assert row["thumbnail_url"] == "https://example.test/new.jpg"
        assert row["date_published"] == "2025-03-04T05:06:07"

    def test_a_video_coming_back_to_life_clears_the_stale_error(self, tmp_path):
        """Review Focus #3: deleted -> ok must not leave fetch_error set forever."""
        with Datastore(tmp_path / "t.db") as ds:
            self._seed_ok(ds)
            ds.refresh_video(VideoMetadata(
                video_id="aaaaaaaaaa1", url="u",
                fetch_status=FetchStatus.DELETED, fetch_error="Video unavailable",
            ))
            ds.refresh_video(VideoMetadata(
                video_id="aaaaaaaaaa1", url="u",
                title="Back Again", yt_view_count=7,
                fetch_status=FetchStatus.OK,
            ))
            row = ds.get_video_by_id("aaaaaaaaaa1")
        assert row["fetch_status"] == "ok"
        assert row["fetch_error"] is None
        assert row["title"] == "Back Again"

    def test_last_fetched_at_advances_on_both_outcomes(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            self._seed_ok(ds)
            ds._conn.execute("UPDATE videos SET last_fetched_at = '2020-01-01T00:00:00+00:00'")
            ds._conn.commit()
            ds.refresh_video(VideoMetadata(
                video_id="aaaaaaaaaa1", url="u", fetch_status=FetchStatus.DELETED,
            ))
            after_fail = ds.get_video_by_id("aaaaaaaaaa1")["last_fetched_at"]
            assert after_fail > "2020-01-01T00:00:00+00:00"

            ds._conn.execute("UPDATE videos SET last_fetched_at = '2020-01-01T00:00:00+00:00'")
            ds._conn.commit()
            ds.refresh_video(VideoMetadata(
                video_id="aaaaaaaaaa1", url="u", title="X", fetch_status=FetchStatus.OK,
            ))
            after_ok = ds.get_video_by_id("aaaaaaaaaa1")["last_fetched_at"]
            assert after_ok > "2020-01-01T00:00:00+00:00"

    def test_never_touches_user_owned_columns(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            self._seed_ok(ds)
            ds._conn.execute("""
                UPDATE videos SET personal_view_count = 7, date_last_viewed = '2026-01-01',
                       is_hidden = 1, date_added = '2024-06-01'
            """)
            ds._conn.commit()
            for status in (FetchStatus.OK, FetchStatus.DELETED):
                ds.refresh_video(VideoMetadata(
                    video_id="aaaaaaaaaa1", url="u", title="X", fetch_status=status,
                ))
            row = ds.get_video_by_id("aaaaaaaaaa1")
        assert row["personal_view_count"] == 7
        assert row["date_last_viewed"] == "2026-01-01"
        assert row["is_hidden"] == 1
        assert row["date_added"] == "2024-06-01"

    def test_refreshing_an_unknown_video_id_is_a_no_op(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            ds.refresh_video(VideoMetadata(
                video_id="zzzzzzzzzz9", url="u", fetch_status=FetchStatus.OK, title="T",
            ))
            assert ds.get_video_by_id("zzzzzzzzzz9") is None


class TestRefreshVideoDoesNotBlankAbsentFields:
    """`fetch_status == ok` means `extract_info` did not raise — not that every
    field came back populated.

    Reachable with no upstream bug at all: `duration_seconds` is None for a live
    stream or scheduled premiere, `yt_view_count` is None when the uploader hides
    counts, and `channel_name` comes from `info.get("uploader")`, which yt-dlp has
    drifted on across versions and player clients. `channel_name` is the dangerous
    one — the channel select, /channels, group-by-channel and get_stats all key on
    it, so a blanked value drops the row out of its channel silently.
    """

    _STORED = dict(
        url="https://www.youtube.com/watch?v=aaaaaaaaaa1",
        title="Original Title",
        description="Original description",
        channel_name="Original Channel",
        channel_id="UCorig",
        yt_view_count=1000,
        duration_seconds=600,
        thumbnail_url="https://example.test/thumb.jpg",
        date_published=datetime(2024, 1, 2, 3, 4, 5),
    )

    def _seed(self, ds):
        ds.upsert_video(
            VideoMetadata(video_id="aaaaaaaaaa1", fetch_status=FetchStatus.OK, **self._STORED),
            Bookmark(url=self._STORED["url"], title="T"),
        )

    @pytest.mark.parametrize("field,stored", [
        ("url", "https://www.youtube.com/watch?v=aaaaaaaaaa1"),
        ("channel_name", "Original Channel"),
        ("channel_id", "UCorig"),
        ("yt_view_count", 1000),
        ("duration_seconds", 600),
        ("thumbnail_url", "https://example.test/thumb.jpg"),
        ("date_published", "2024-01-02T03:04:05"),
    ])
    def test_an_ok_fetch_missing_one_field_keeps_the_stored_value(self, tmp_path, field, stored):
        incoming = {**self._STORED, field: None}
        with Datastore(tmp_path / "t.db") as ds:
            self._seed(ds)
            ds.refresh_video(VideoMetadata(
                video_id="aaaaaaaaaa1", fetch_status=FetchStatus.OK, **incoming,
            ))
            row = ds.get_video_by_id("aaaaaaaaaa1")
        assert row[field] == stored

    def test_title_and_description_are_still_clearable(self, tmp_path):
        """The asymmetry is deliberate: for these two, "YouTube says it is empty
        now" is a real thing a successful fetch can report."""
        with Datastore(tmp_path / "t.db") as ds:
            self._seed(ds)
            ds.refresh_video(VideoMetadata(
                video_id="aaaaaaaaaa1", url=self._STORED["url"],
                title=None, description=None, fetch_status=FetchStatus.OK,
            ))
            row = ds.get_video_by_id("aaaaaaaaaa1")
        assert row["title"] is None
        assert row["description"] is None


class TestRefreshDoesNotResurrectRemovedTags:
    """A refresh must never undo the user's own tag curation.

    Before the nightly job existed, `_apply_yt_tags` and `apply_aliases` ran once
    per video, at ingest. On a timer they would re-add every link the user had
    deliberately removed through the webapp, roughly every 15 days — silently
    eroding hand-built editorial state.
    """

    def _seed(self, tmp_path):
        """A video carrying a raw yt-tag plus an alias rule onto a canonical tag."""
        db_path = tmp_path / "t.db"
        ds = Datastore(db_path)
        init_webapp_tables(str(db_path))  # tag_aliases lives in the webapp schema
        ds.upsert_video(
            VideoMetadata(
                video_id="aaaaaaaaaa1",
                url="https://www.youtube.com/watch?v=aaaaaaaaaa1",
                title="Original Title",
                fetch_status=FetchStatus.OK,
                yt_tags=["guitar", "lesson"],
            ),
            Bookmark(url="https://www.youtube.com/watch?v=aaaaaaaaaa1", title="T"),
        )
        canonical_id = ds.add_tag("stringed instruments")
        ds._conn.execute(
            "UPDATE tags SET is_canonical = 1 WHERE id = ?", (canonical_id,)
        )
        ds._conn.execute(
            "INSERT INTO tag_aliases (pattern, match_type, canonical_tag_id) "
            "VALUES ('guitar', 'exact', ?)",
            (canonical_id,),
        )
        ds._conn.commit()
        apply_aliases(ds._conn, "aaaaaaaaaa1")
        return ds, canonical_id

    def _tag_id(self, ds, name):
        return ds._conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()[0]

    def test_a_removed_yt_tag_stays_removed(self, tmp_path):
        ds, _ = self._seed(tmp_path)
        with closing(ds):
            remove_video_tag(ds._conn, "aaaaaaaaaa1", self._tag_id(ds, "lesson"))
            assert "lesson" not in ds.get_tags_for_video("aaaaaaaaaa1")

            ds.refresh_video(VideoMetadata(
                video_id="aaaaaaaaaa1", url="u", title="Original Title",
                fetch_status=FetchStatus.OK, yt_tags=["guitar", "lesson"],
            ))
            assert "lesson" not in ds.get_tags_for_video("aaaaaaaaaa1")

    def test_a_removed_alias_derived_canonical_tag_stays_removed(self, tmp_path):
        ds, canonical_id = self._seed(tmp_path)
        with closing(ds):
            assert "stringed instruments" in ds.get_tags_for_video("aaaaaaaaaa1")
            remove_video_tag(ds._conn, "aaaaaaaaaa1", canonical_id)
            assert "stringed instruments" not in ds.get_tags_for_video("aaaaaaaaaa1")

            ds.refresh_video(VideoMetadata(
                video_id="aaaaaaaaaa1", url="u", title="Original Title",
                fetch_status=FetchStatus.OK, yt_tags=["guitar", "lesson"],
            ))
            assert "stringed instruments" not in ds.get_tags_for_video("aaaaaaaaaa1")


class TestUpsertVideoPreservesOnFailure:
    """Same hazard, older path: `--force-refresh` over a bookmarks file containing a
    since-deleted video would otherwise NULL out its title."""

    def test_a_failed_upsert_keeps_the_existing_title(self, tmp_path):
        bookmark = Bookmark(url="https://www.youtube.com/watch?v=aaaaaaaaaa1", title="T")
        with Datastore(tmp_path / "t.db") as ds:
            ds.upsert_video(VideoMetadata(
                video_id="aaaaaaaaaa1", url="u", title="Original Title",
                channel_name="Original Channel", yt_view_count=10,
                fetch_status=FetchStatus.OK,
            ), bookmark)
            ds.upsert_video(VideoMetadata(
                video_id="aaaaaaaaaa1", url="u",
                fetch_status=FetchStatus.DELETED, fetch_error="Video unavailable",
            ), bookmark)
            row = ds.get_video_by_id("aaaaaaaaaa1")
        assert row["fetch_status"] == "deleted"
        assert row["title"] == "Original Title"
        assert row["channel_name"] == "Original Channel"
        assert row["yt_view_count"] == 10

    def test_a_first_time_failed_insert_still_creates_the_row(self, tmp_path):
        """A brand-new bookmark whose video is already dead has no metadata to
        preserve — the row must still exist, so the user sees they saved something."""
        with Datastore(tmp_path / "t.db") as ds:
            ds.upsert_video(VideoMetadata(
                video_id="aaaaaaaaaa1", url="u",
                fetch_status=FetchStatus.DELETED, fetch_error="Video unavailable",
            ), Bookmark(url="u", title="T"))
            row = ds.get_video_by_id("aaaaaaaaaa1")
        assert row is not None
        assert row["fetch_status"] == "deleted"


class TestGetStaleVideoIds:
    def _seed(self, ds, rows):
        """rows: list of (video_id, last_fetched_at or None)."""
        for video_id, fetched in rows:
            ds._conn.execute(
                "INSERT INTO videos (video_id, url, fetch_status, last_fetched_at) "
                "VALUES (?, ?, 'ok', ?)",
                (video_id, f"https://www.youtube.com/watch?v={video_id}", fetched),
            )
        ds._conn.commit()

    def test_orders_oldest_refreshed_first(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            self._seed(ds, [
                ("newest00001", "2026-09-01T00:00:00+00:00"),
                ("oldest00001", "2026-01-01T00:00:00+00:00"),
                ("middle00001", "2026-05-01T00:00:00+00:00"),
            ])
            assert ds.get_stale_video_ids(10) == ["oldest00001", "middle00001", "newest00001"]

    def test_never_fetched_videos_come_first(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            self._seed(ds, [
                ("fetched0001", "2026-01-01T00:00:00+00:00"),
                ("neverfetch1", None),
            ])
            assert ds.get_stale_video_ids(10)[0] == "neverfetch1"

    def test_honors_the_limit(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            self._seed(ds, [(f"video00000{i}", f"2026-0{i}-01T00:00:00+00:00") for i in range(1, 6)])
            assert len(ds.get_stale_video_ids(2)) == 2

    def test_includes_hidden_and_already_dead_videos(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            ds._conn.execute(
                "INSERT INTO videos (video_id, url, fetch_status, is_hidden, last_fetched_at) "
                "VALUES ('hidden00001', 'u', 'deleted', 1, '2026-01-01T00:00:00+00:00')"
            )
            ds._conn.commit()
            assert ds.get_stale_video_ids(10) == ["hidden00001"]

    def test_a_non_positive_limit_selects_nothing(self, tmp_path):
        """Review Focus #1: SQLite reads LIMIT -1 as *no limit*, so a typo'd
        `--limit -1` would refresh the entire library in one run."""
        with Datastore(tmp_path / "t.db") as ds:
            self._seed(ds, [("video000001", None), ("video000002", None)])
            assert ds.get_stale_video_ids(0) == []
            assert ds.get_stale_video_ids(-1) == []

    def test_empty_library_returns_empty(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            assert ds.get_stale_video_ids(10) == []


class TestCountVideos:
    def test_counts_every_row(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            ds._conn.execute("INSERT INTO videos (video_id, url) VALUES ('a0000000001', 'u')")
            ds._conn.execute("INSERT INTO videos (video_id, url) VALUES ('a0000000002', 'u')")
            ds._conn.commit()
            assert ds.count_videos() == 2

    def test_empty_library_is_zero(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            assert ds.count_videos() == 0

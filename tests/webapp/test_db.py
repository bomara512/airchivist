import sqlite3
import pytest
from webapp.db import (
    get_all_videos, get_video_by_id, get_all_channels, get_all_tags,
    get_tags_with_keywords, get_tag_keywords, get_stats, get_tags_for_video,
    record_visit, create_tag, set_tag_keywords, delete_tag,
    add_video_tag, remove_video_tag, init_webapp_tables, count_videos,
)


class TestGetAllVideos:
    def test_returns_all_rows(self, db_conn):
        rows = get_all_videos(db_conn)
        assert len(rows) == 5

    def test_sorts_by_date_added_desc_by_default(self, db_conn):
        rows = get_all_videos(db_conn)
        dates = [r["date_added"] for r in rows]
        assert dates == sorted(dates, reverse=True)

    def test_sort_by_personal_view_count_asc(self, db_conn):
        rows = get_all_videos(db_conn, sort_by="personal_view_count", sort_dir="asc")
        counts = [r["personal_view_count"] for r in rows]
        assert counts == sorted(counts)

    def test_sort_by_yt_view_count_desc(self, db_conn):
        rows = get_all_videos(db_conn, sort_by="yt_view_count", sort_dir="desc")
        counts = [r["yt_view_count"] for r in rows]
        assert counts == sorted(counts, reverse=True)

    def test_sort_by_title_asc(self, db_conn):
        rows = get_all_videos(db_conn, sort_by="title", sort_dir="asc")
        titles = [r["title"] for r in rows]
        assert titles == sorted(titles)

    def test_filters_by_channel(self, db_conn):
        rows = get_all_videos(db_conn, channel="GuitarChannel")
        assert all(r["channel_name"] == "GuitarChannel" for r in rows)
        assert len(rows) == 2

    def test_filters_by_tag(self, db_conn):
        rows = get_all_videos(db_conn, tag="guitar")
        assert len(rows) == 2
        titles = {r["title"] for r in rows}
        assert "Guitar Lesson 1" in titles
        assert "Advanced Chords" in titles

    def test_filters_by_search_term_in_title(self, db_conn):
        # "Tutorial" appears only in "Pad Thai Tutorial" title and no tag keywords
        rows = get_all_videos(db_conn, search="Tutorial")
        assert len(rows) == 1
        assert rows[0]["title"] == "Pad Thai Tutorial"

    def test_filters_by_search_term_in_description(self, db_conn):
        rows = get_all_videos(db_conn, search="shrimp")
        assert len(rows) == 1
        assert rows[0]["title"] == "Thai Food Recipe"

    def test_filters_by_tag_name(self, db_conn):
        rows = get_all_videos(db_conn, search="thai food")
        titles = {r["title"] for r in rows}
        assert "Thai Food Recipe" in titles
        assert "Pad Thai Tutorial" in titles

    def test_filters_by_tag_keyword(self, db_conn):
        # "lesson" is a keyword of the "guitar" tag; Advanced Chords is tagged guitar
        # but its title/description don't contain "lesson"
        rows = get_all_videos(db_conn, search="lesson")
        titles = {r["title"] for r in rows}
        assert "Advanced Chords" in titles

    def test_search_matches_word_prefix(self, db_conn):
        # "Advanc" is a prefix of "Advanced" — should match
        rows = get_all_videos(db_conn, search="Advanc")
        assert len(rows) > 0

    def test_search_does_not_match_mid_word(self, db_conn):
        # "uitar" appears inside "guitar" but not at a word start — should not match
        rows = get_all_videos(db_conn, search="uitar")
        assert len(rows) == 0

    def test_invalid_sort_by_raises(self, db_conn):
        with pytest.raises(ValueError):
            get_all_videos(db_conn, sort_by="DROP TABLE videos")

    def test_invalid_sort_dir_raises(self, db_conn):
        with pytest.raises(ValueError):
            get_all_videos(db_conn, sort_dir="sideways")

    def test_each_row_includes_tags(self, db_conn):
        rows = get_all_videos(db_conn)
        row = next(r for r in rows if r["video_id"] == "aaaaaaaaaa1")
        assert "guitar" in row["tags"]

    def test_row_with_no_tags_has_empty_tags(self, db_conn):
        rows = get_all_videos(db_conn)
        row = next(r for r in rows if r["video_id"] == "aaaaaaaaaa5")
        assert row["tags"] == ""

    def test_pagination_limits_results(self, db_conn):
        rows = get_all_videos(db_conn, page=1, page_size=2)
        assert len(rows) == 2

    def test_pagination_second_page(self, db_conn):
        page1 = get_all_videos(db_conn, page=1, page_size=2)
        page2 = get_all_videos(db_conn, page=2, page_size=2)
        ids1 = {r["video_id"] for r in page1}
        ids2 = {r["video_id"] for r in page2}
        assert ids1.isdisjoint(ids2)

    def test_pagination_last_page_may_have_fewer(self, db_conn):
        rows = get_all_videos(db_conn, page=3, page_size=2)
        assert len(rows) == 1


class TestCountVideos:
    def test_returns_total_count(self, db_conn):
        assert count_videos(db_conn) == 5

    def test_filters_by_channel(self, db_conn):
        assert count_videos(db_conn, channel="GuitarChannel") == 2

    def test_filters_by_search(self, db_conn):
        assert count_videos(db_conn, search="shrimp") == 1


class TestGetVideoById:
    def test_returns_row_for_existing(self, db_conn):
        row = get_video_by_id(db_conn, "aaaaaaaaaa1")
        assert row is not None
        assert row["title"] == "Guitar Lesson 1"

    def test_returns_none_for_missing(self, db_conn):
        assert get_video_by_id(db_conn, "nonexistent") is None


class TestGetAllChannels:
    def test_returns_distinct_names(self, db_conn):
        channels = get_all_channels(db_conn)
        assert set(channels) == {"GuitarChannel", "ThaiCooking", "OtherChannel"}

    def test_excludes_null_channels(self, db_conn):
        db_conn.execute("INSERT INTO videos (video_id, url) VALUES ('nullchan1', 'http://x.com')")
        channels = get_all_channels(db_conn)
        assert None not in channels


class TestGetAllTags:
    def test_returns_tags_with_video_count(self, db_conn):
        tags = get_all_tags(db_conn)
        guitar = next(t for t in tags if t["name"] == "guitar")
        assert guitar["video_count"] == 2

    def test_returns_all_tags(self, db_conn):
        tags = get_all_tags(db_conn)
        names = {t["name"] for t in tags}
        assert names == {"guitar", "thai food"}


class TestGetTagsWithKeywords:
    def test_returns_tags_with_keywords(self, db_conn):
        result = get_tags_with_keywords(db_conn)
        guitar = next(t for t in result if t["name"] == "guitar")
        assert set(guitar["keywords"]) == {"guitar", "chord", "lesson"}

    def test_tag_with_no_keywords_has_empty_list(self, db_conn):
        db_conn.execute("INSERT INTO tags (name) VALUES ('empty-tag')")
        result = get_tags_with_keywords(db_conn)
        empty = next((t for t in result if t["name"] == "empty-tag"), None)
        assert empty is not None
        assert empty["keywords"] == []


class TestGetTagKeywords:
    def test_returns_keywords_for_tag(self, db_conn):
        kws = get_tag_keywords(db_conn, 1)
        assert set(kws) == {"guitar", "chord", "lesson"}

    def test_returns_empty_for_unknown_tag(self, db_conn):
        assert get_tag_keywords(db_conn, 9999) == []


class TestGetTagsForVideo:
    def test_returns_tag_names(self, db_conn):
        tags = get_tags_for_video(db_conn, "aaaaaaaaaa1")
        assert "guitar" in tags

    def test_returns_empty_for_untagged_video(self, db_conn):
        assert get_tags_for_video(db_conn, "aaaaaaaaaa5") == []


class TestGetStats:
    def test_returns_total_videos(self, db_conn):
        stats = get_stats(db_conn)
        assert stats["total_videos"] == 5

    def test_returns_total_channels(self, db_conn):
        stats = get_stats(db_conn)
        assert stats["total_channels"] == 3

    def test_returns_fetch_errors(self, db_conn):
        stats = get_stats(db_conn)
        assert stats["fetch_errors"] == 1


class TestRecordVisit:
    def test_increments_personal_view_count(self, db_conn):
        record_visit(db_conn, "aaaaaaaaaa1")
        row = db_conn.execute(
            "SELECT personal_view_count FROM videos WHERE video_id=?", ("aaaaaaaaaa1",)
        ).fetchone()
        assert row[0] == 1

    def test_updates_date_last_viewed(self, db_conn):
        record_visit(db_conn, "aaaaaaaaaa1")
        row = db_conn.execute(
            "SELECT date_last_viewed FROM videos WHERE video_id=?", ("aaaaaaaaaa1",)
        ).fetchone()
        assert row[0] is not None

    def test_called_twice_increments_to_two(self, db_conn):
        record_visit(db_conn, "aaaaaaaaaa1")
        record_visit(db_conn, "aaaaaaaaaa1")
        row = db_conn.execute(
            "SELECT personal_view_count FROM videos WHERE video_id=?", ("aaaaaaaaaa1",)
        ).fetchone()
        assert row[0] == 2

    def test_unknown_video_id_does_nothing(self, db_conn):
        record_visit(db_conn, "doesnotexist")  # must not raise


class TestCreateTag:
    def test_creates_tag_row(self, db_conn):
        tag_id = create_tag(db_conn, "coding")
        row = db_conn.execute("SELECT name FROM tags WHERE id=?", (tag_id,)).fetchone()
        assert row[0] == "coding"

    def test_returns_existing_id_for_duplicate(self, db_conn):
        id1 = create_tag(db_conn, "guitar")
        id2 = create_tag(db_conn, "guitar")
        assert id1 == id2


class TestSetTagKeywords:
    def test_replaces_keywords(self, db_conn):
        set_tag_keywords(db_conn, 1, ["new", "keywords"])
        kws = get_tag_keywords(db_conn, 1)
        assert set(kws) == {"new", "keywords"}

    def test_empty_list_clears_keywords(self, db_conn):
        set_tag_keywords(db_conn, 1, [])
        assert get_tag_keywords(db_conn, 1) == []


class TestDeleteTag:
    def test_removes_tag(self, db_conn):
        delete_tag(db_conn, 1)
        row = db_conn.execute("SELECT id FROM tags WHERE id=1").fetchone()
        assert row is None

    def test_removes_video_tag_associations(self, db_conn):
        delete_tag(db_conn, 1)
        count = db_conn.execute(
            "SELECT COUNT(*) FROM video_tags WHERE tag_id_fk=1"
        ).fetchone()[0]
        assert count == 0


class TestVideoTagAssociations:
    def test_add_video_tag(self, db_conn):
        add_video_tag(db_conn, "aaaaaaaaaa5", 1)
        tags = get_tags_for_video(db_conn, "aaaaaaaaaa5")
        assert "guitar" in tags

    def test_add_video_tag_is_idempotent(self, db_conn):
        add_video_tag(db_conn, "aaaaaaaaaa1", 1)
        add_video_tag(db_conn, "aaaaaaaaaa1", 1)
        count = db_conn.execute("SELECT COUNT(*) FROM video_tags").fetchone()[0]
        assert count == 4  # original seed count

    def test_remove_video_tag(self, db_conn):
        remove_video_tag(db_conn, "aaaaaaaaaa1", 1)
        tags = get_tags_for_video(db_conn, "aaaaaaaaaa1")
        assert "guitar" not in tags


class TestInitWebappTables:
    def test_creates_tag_keywords_table(self, tmp_path):
        db_path = str(tmp_path / "fresh.db")
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
        """)
        conn.close()
        init_webapp_tables(db_path)
        conn = sqlite3.connect(db_path)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "tag_keywords" in tables

    def test_is_idempotent(self, tmp_path):
        db_path = str(tmp_path / "fresh.db")
        conn = sqlite3.connect(db_path)
        conn.executescript("CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);")
        conn.close()
        init_webapp_tables(db_path)
        init_webapp_tables(db_path)  # must not raise

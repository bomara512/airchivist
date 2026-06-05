import sqlite3
import pytest
from webapp.db import (
    get_all_videos, get_video_by_id, get_all_channels, get_all_tags,
    get_tags_with_keywords, get_tag_keywords, get_stats, get_tags_for_video,
    record_visit, create_tag, set_tag_keywords, delete_tag,
    add_video_tag, remove_video_tag, init_webapp_tables, count_videos,
    apply_aliases, get_canonical_tags, create_canonical_tag,
    add_alias, delete_alias, retroactive_apply,
    get_unclassified_tags, confirm_suggestion,
    save_llm_suggestions, get_llm_suggestions, dismiss_llm_suggestion,
    is_llm_suggestion_cache_stale,
)


class TestGetAllVideos:
    def test_returns_all_rows(self, db_conn):
        rows = get_all_videos(db_conn)
        assert len(rows) == 4  # aaaaaaaaaa5 excluded (fetch_status='error')

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

    def test_each_row_includes_canonical_tags_only(self, db_conn):
        # promote "guitar" to canonical; non-canonical tags should not appear
        db_conn.execute("UPDATE tags SET is_canonical = 1 WHERE name = 'guitar'")
        db_conn.commit()
        rows = get_all_videos(db_conn)
        guitar_row = next(r for r in rows if r["video_id"] == "aaaaaaaaaa1")
        assert "guitar" in guitar_row["tags"]
        thai_row = next(r for r in rows if r["video_id"] == "aaaaaaaaaa2")
        assert "thai food" not in thai_row["tags"]  # thai food is not canonical

    def test_row_with_no_tags_has_empty_tags(self, db_conn):
        # aaaaaaaaaa4 (Pad Thai Tutorial) is tagged "thai food", not untagged
        # use a video we know has no tags among the ok-status ones — none in seed,
        # so insert a fresh one
        db_conn.execute(
            "INSERT INTO videos (video_id, url, fetch_status) VALUES ('notagvid', 'http://x', 'ok')"
        )
        rows = get_all_videos(db_conn)
        row = next(r for r in rows if r["video_id"] == "notagvid")
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
        # 4 ok-status videos, page_size=3 → page 2 has 1
        rows = get_all_videos(db_conn, page=2, page_size=3)
        assert len(rows) == 1


class TestCountVideos:
    def test_returns_total_count(self, db_conn):
        assert count_videos(db_conn) == 4  # aaaaaaaaaa5 excluded (fetch_status='error')

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


class TestApplyAliases:
    def _add_canonical(self, db_conn, name):
        db_conn.execute("INSERT INTO tags (name, is_canonical) VALUES (?, 1)", (name,))
        db_conn.commit()
        return db_conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()[0]

    def _add_alias(self, db_conn, pattern, canonical_id, match_type="exact"):
        db_conn.execute(
            "INSERT INTO tag_aliases (pattern, match_type, canonical_tag_id) VALUES (?, ?, ?)",
            (pattern, match_type, canonical_id),
        )
        db_conn.commit()

    def test_exact_match_adds_canonical_tag(self, db_conn):
        cid = self._add_canonical(db_conn, "string instrument")
        self._add_alias(db_conn, "guitar", cid)
        apply_aliases(db_conn, "aaaaaaaaaa1")  # aaaaaaaaaa1 is tagged "guitar"
        assert "string instrument" in get_tags_for_video(db_conn, "aaaaaaaaaa1")

    def test_prefix_match_adds_canonical_tag(self, db_conn):
        cid = self._add_canonical(db_conn, "thai cuisine")
        self._add_alias(db_conn, "thai", cid, match_type="prefix")
        apply_aliases(db_conn, "aaaaaaaaaa2")  # aaaaaaaaaa2 is tagged "thai food"
        assert "thai cuisine" in get_tags_for_video(db_conn, "aaaaaaaaaa2")

    def test_contains_match_adds_canonical_tag(self, db_conn):
        cid = self._add_canonical(db_conn, "thai cuisine")
        self._add_alias(db_conn, "food", cid, match_type="contains")
        apply_aliases(db_conn, "aaaaaaaaaa2")  # "thai food" contains "food"
        assert "thai cuisine" in get_tags_for_video(db_conn, "aaaaaaaaaa2")

    def test_no_match_makes_no_change(self, db_conn):
        cid = self._add_canonical(db_conn, "coding")
        self._add_alias(db_conn, "python", cid)
        tags_before = set(get_tags_for_video(db_conn, "aaaaaaaaaa1"))
        apply_aliases(db_conn, "aaaaaaaaaa1")
        assert set(get_tags_for_video(db_conn, "aaaaaaaaaa1")) == tags_before

    def test_is_idempotent(self, db_conn):
        cid = self._add_canonical(db_conn, "string instrument")
        self._add_alias(db_conn, "guitar", cid)
        apply_aliases(db_conn, "aaaaaaaaaa1")
        apply_aliases(db_conn, "aaaaaaaaaa1")
        count = db_conn.execute(
            "SELECT COUNT(*) FROM video_tags vt "
            "JOIN tags t ON t.id = vt.tag_id_fk "
            "WHERE t.name = 'string instrument'"
        ).fetchone()[0]
        assert count == 1

    def test_unknown_video_id_does_nothing(self, db_conn):
        apply_aliases(db_conn, "doesnotexist")  # must not raise

    def test_matching_is_case_insensitive(self, db_conn):
        cid = self._add_canonical(db_conn, "string instrument")
        self._add_alias(db_conn, "GUITAR", cid)
        apply_aliases(db_conn, "aaaaaaaaaa1")
        assert "string instrument" in get_tags_for_video(db_conn, "aaaaaaaaaa1")

    def test_no_alias_rules_makes_no_change(self, db_conn):
        tags_before = set(get_tags_for_video(db_conn, "aaaaaaaaaa1"))
        apply_aliases(db_conn, "aaaaaaaaaa1")
        assert set(get_tags_for_video(db_conn, "aaaaaaaaaa1")) == tags_before


class TestGetUnclassifiedTags:
    def _seed_raw_tag(self, db_conn, name, video_fk=1):
        db_conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
        db_conn.commit()
        tag_row = db_conn.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
        db_conn.execute(
            "INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk) VALUES (?, ?)",
            (video_fk, tag_row[0]),
        )
        db_conn.commit()

    def test_returns_non_canonical_non_aliased_tags(self, db_conn):
        self._seed_raw_tag(db_conn, "meal prep", video_fk=1)
        self._seed_raw_tag(db_conn, "meal prep", video_fk=2)
        tags, _ = get_unclassified_tags(db_conn)
        names = [t["name"] for t in tags]
        assert "meal prep" in names

    def test_excludes_canonical_tags(self, db_conn):
        self._seed_raw_tag(db_conn, "meal prep")
        create_canonical_tag(db_conn, "meal prep")
        tags, _ = get_unclassified_tags(db_conn)
        names = [t["name"] for t in tags]
        assert "meal prep" not in names

    def test_excludes_aliased_tags(self, db_conn):
        self._seed_raw_tag(db_conn, "meal prep")
        tag_id = create_canonical_tag(db_conn, "food prep")
        add_alias(db_conn, tag_id, "meal prep", "exact")
        tags, _ = get_unclassified_tags(db_conn)
        names = [t["name"] for t in tags]
        assert "meal prep" not in names

    def test_returns_total_count(self, db_conn):
        self._seed_raw_tag(db_conn, "meal prep")
        self._seed_raw_tag(db_conn, "meal-prep")
        _, total = get_unclassified_tags(db_conn)
        # seed data also has "guitar" and "thai food" (non-canonical)
        assert total >= 2

    def test_includes_video_count(self, db_conn):
        self._seed_raw_tag(db_conn, "meal prep", video_fk=1)
        self._seed_raw_tag(db_conn, "meal prep", video_fk=2)
        tags, _ = get_unclassified_tags(db_conn)
        meal = next(t for t in tags if t["name"] == "meal prep")
        assert meal["video_count"] == 2

    def test_respects_max_tags(self, db_conn):
        for i in range(10):
            self._seed_raw_tag(db_conn, f"tag-{i:03d}", video_fk=1)
            self._seed_raw_tag(db_conn, f"tag-{i:03d}", video_fk=2)
        tags, total = get_unclassified_tags(db_conn, max_tags=3)
        assert len(tags) == 3
        assert total > 3


class TestConfirmSuggestion:
    def test_creates_canonical_tag_and_aliases(self, db_conn):
        db_conn.execute("INSERT OR IGNORE INTO tags (name) VALUES ('meal prep')")
        db_conn.execute(
            "INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk) VALUES (1, last_insert_rowid())"
        )
        db_conn.commit()
        confirm_suggestion(db_conn, "meal-prep", ["meal prep"])
        row = db_conn.execute("SELECT is_canonical FROM tags WHERE name='meal-prep'").fetchone()
        assert row and row[0] == 1
        alias = db_conn.execute(
            "SELECT id FROM tag_aliases WHERE pattern='meal prep'"
        ).fetchone()
        assert alias is not None

    def test_applies_retroactively(self, db_conn):
        db_conn.execute("INSERT OR IGNORE INTO tags (name) VALUES ('meal prep')")
        db_conn.commit()
        tag_row = db_conn.execute("SELECT id FROM tags WHERE name='meal prep'").fetchone()
        db_conn.execute(
            "INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk) VALUES (1, ?)",
            (tag_row[0],),
        )
        db_conn.commit()
        count = confirm_suggestion(db_conn, "meal-prep", ["meal prep"])
        assert count >= 1
        assert "meal-prep" in get_tags_for_video(db_conn, "aaaaaaaaaa1")

    def test_returns_count_of_new_associations(self, db_conn):
        db_conn.execute("INSERT OR IGNORE INTO tags (name) VALUES ('guitar lesson')")
        db_conn.commit()
        tag_row = db_conn.execute("SELECT id FROM tags WHERE name='guitar lesson'").fetchone()
        # Associate with both guitar videos
        db_conn.execute(
            "INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk) VALUES (1, ?)", (tag_row[0],)
        )
        db_conn.execute(
            "INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk) VALUES (3, ?)", (tag_row[0],)
        )
        db_conn.commit()
        count = confirm_suggestion(db_conn, "guitar-lessons", ["guitar lesson"])
        assert count == 2


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
        assert "tag_aliases" in tables

    def test_adds_is_canonical_column(self, tmp_path):
        db_path = str(tmp_path / "fresh.db")
        conn = sqlite3.connect(db_path)
        conn.executescript("CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);")
        conn.close()
        init_webapp_tables(db_path)
        conn = sqlite3.connect(db_path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(tags)").fetchall()}
        conn.close()
        assert "is_canonical" in cols

    def test_is_idempotent(self, tmp_path):
        db_path = str(tmp_path / "fresh.db")
        conn = sqlite3.connect(db_path)
        conn.executescript("CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);")
        conn.close()
        init_webapp_tables(db_path)
        init_webapp_tables(db_path)  # must not raise


class TestCanonicalTagManagement:
    def test_create_canonical_tag_new(self, db_conn):
        tag_id = create_canonical_tag(db_conn, "cooking")
        row = db_conn.execute("SELECT name, is_canonical FROM tags WHERE id=?", (tag_id,)).fetchone()
        assert row[0] == "cooking"
        assert row[1] == 1

    def test_create_canonical_tag_promotes_existing(self, db_conn):
        tag_id = create_canonical_tag(db_conn, "guitar")  # already exists in seed
        row = db_conn.execute("SELECT is_canonical FROM tags WHERE id=?", (tag_id,)).fetchone()
        assert row[0] == 1

    def test_create_canonical_tag_idempotent(self, db_conn):
        id1 = create_canonical_tag(db_conn, "guitar")
        id2 = create_canonical_tag(db_conn, "guitar")
        assert id1 == id2

    def test_get_canonical_tags_returns_only_canonical(self, db_conn):
        create_canonical_tag(db_conn, "guitar")
        result = get_canonical_tags(db_conn)
        names = {t["name"] for t in result}
        assert "guitar" in names
        assert "thai food" not in names  # not canonical

    def test_get_canonical_tags_includes_video_count(self, db_conn):
        create_canonical_tag(db_conn, "guitar")
        result = get_canonical_tags(db_conn)
        guitar = next(t for t in result if t["name"] == "guitar")
        assert guitar["video_count"] == 2

    def test_get_canonical_tags_includes_aliases(self, db_conn):
        tag_id = create_canonical_tag(db_conn, "guitar")
        add_alias(db_conn, tag_id, "guitar lesson", "prefix")
        result = get_canonical_tags(db_conn)
        guitar = next(t for t in result if t["name"] == "guitar")
        assert any(a["pattern"] == "guitar lesson" for a in guitar["aliases"])

    def test_add_alias_returns_id(self, db_conn):
        tag_id = create_canonical_tag(db_conn, "guitar")
        alias_id = add_alias(db_conn, tag_id, "guitar lesson", "prefix")
        assert isinstance(alias_id, int)

    def test_add_alias_idempotent(self, db_conn):
        tag_id = create_canonical_tag(db_conn, "guitar")
        id1 = add_alias(db_conn, tag_id, "guitar lesson", "prefix")
        id2 = add_alias(db_conn, tag_id, "guitar lesson", "prefix")
        assert id1 == id2

    def test_delete_alias_removes_it(self, db_conn):
        tag_id = create_canonical_tag(db_conn, "guitar")
        alias_id = add_alias(db_conn, tag_id, "guitar lesson", "prefix")
        delete_alias(db_conn, alias_id)
        row = db_conn.execute("SELECT id FROM tag_aliases WHERE id=?", (alias_id,)).fetchone()
        assert row is None


class TestRetroactiveApply:
    def _setup_canonical(self, db_conn, tag_name, pattern, match_type="exact"):
        tag_id = create_canonical_tag(db_conn, tag_name)
        alias_id = add_alias(db_conn, tag_id, pattern, match_type)
        return tag_id, alias_id

    def test_applies_exact_rule_to_all_videos(self, db_conn):
        tag_id, alias_id = self._setup_canonical(db_conn, "string instrument", "guitar")
        count = retroactive_apply(db_conn, alias_id)
        assert count == 2  # aaaaaaaaaa1 and aaaaaaaaaa3 are tagged guitar
        assert "string instrument" in get_tags_for_video(db_conn, "aaaaaaaaaa1")
        assert "string instrument" in get_tags_for_video(db_conn, "aaaaaaaaaa3")

    def test_applies_prefix_rule_to_all_videos(self, db_conn):
        tag_id, alias_id = self._setup_canonical(db_conn, "thai cuisine", "thai", "prefix")
        retroactive_apply(db_conn, alias_id)
        assert "thai cuisine" in get_tags_for_video(db_conn, "aaaaaaaaaa2")
        assert "thai cuisine" in get_tags_for_video(db_conn, "aaaaaaaaaa4")

    def test_applies_contains_rule_to_all_videos(self, db_conn):
        tag_id, alias_id = self._setup_canonical(db_conn, "food content", "food", "contains")
        retroactive_apply(db_conn, alias_id)
        assert "food content" in get_tags_for_video(db_conn, "aaaaaaaaaa2")

    def test_applies_all_rules_when_no_id_given(self, db_conn):
        tag_id1, _ = self._setup_canonical(db_conn, "string instrument", "guitar")
        tag_id2, _ = self._setup_canonical(db_conn, "thai cuisine", "thai", "prefix")
        retroactive_apply(db_conn)
        assert "string instrument" in get_tags_for_video(db_conn, "aaaaaaaaaa1")
        assert "thai cuisine" in get_tags_for_video(db_conn, "aaaaaaaaaa2")

    def test_returns_count_of_new_associations(self, db_conn):
        tag_id, alias_id = self._setup_canonical(db_conn, "string instrument", "guitar")
        count = retroactive_apply(db_conn, alias_id)
        assert count == 2

    def test_is_idempotent(self, db_conn):
        tag_id, alias_id = self._setup_canonical(db_conn, "string instrument", "guitar")
        retroactive_apply(db_conn, alias_id)
        count2 = retroactive_apply(db_conn, alias_id)
        assert count2 == 0


class TestLLMSuggestions:
    _SUGGESTION = {"canonical": "guitar", "members": ["beginner guitar", "guitar lesson"],
                   "confidence": "high", "is_noise": False}

    def test_get_returns_empty_when_none(self, db_conn):
        assert get_llm_suggestions(db_conn) == []

    def test_is_stale_when_no_suggestions(self, db_conn):
        assert is_llm_suggestion_cache_stale(db_conn, "abc123") is True

    def test_save_and_get_roundtrip(self, db_conn):
        save_llm_suggestions(db_conn, [self._SUGGESTION], "abc123")
        result = get_llm_suggestions(db_conn)
        assert len(result) == 1
        assert result[0]["canonical"] == "guitar"
        assert result[0]["members"] == ["beginner guitar", "guitar lesson"]
        assert result[0]["confidence"] == "high"
        assert result[0]["is_noise"] is False
        assert "id" in result[0]

    def test_save_clears_previous_suggestions(self, db_conn):
        save_llm_suggestions(db_conn, [self._SUGGESTION], "hash1")
        save_llm_suggestions(db_conn, [{"canonical": "cooking", "members": ["recipe"],
                                         "confidence": "medium", "is_noise": False}], "hash2")
        result = get_llm_suggestions(db_conn)
        assert len(result) == 1
        assert result[0]["canonical"] == "cooking"

    def test_noise_suggestions_sorted_last(self, db_conn):
        noise = {"canonical": "_noise", "members": ["#ad"], "confidence": "high", "is_noise": True}
        save_llm_suggestions(db_conn, [noise, self._SUGGESTION], "h")
        result = get_llm_suggestions(db_conn)
        assert result[0]["is_noise"] is False
        assert result[-1]["is_noise"] is True

    def test_is_not_stale_when_hash_matches(self, db_conn):
        save_llm_suggestions(db_conn, [self._SUGGESTION], "abc123")
        assert is_llm_suggestion_cache_stale(db_conn, "abc123") is False

    def test_is_stale_when_hash_differs(self, db_conn):
        save_llm_suggestions(db_conn, [self._SUGGESTION], "abc123")
        assert is_llm_suggestion_cache_stale(db_conn, "different") is True

    def test_dismiss_removes_suggestion(self, db_conn):
        save_llm_suggestions(db_conn, [self._SUGGESTION], "abc123")
        suggestion_id = get_llm_suggestions(db_conn)[0]["id"]
        dismiss_llm_suggestion(db_conn, suggestion_id)
        assert get_llm_suggestions(db_conn) == []

    def test_dismiss_unknown_id_is_noop(self, db_conn):
        dismiss_llm_suggestion(db_conn, 9999)  # must not raise

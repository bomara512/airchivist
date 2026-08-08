import pytest
import sqlite3

from crawler.models import ChannelMetadata, FetchStatus


class TestIndexRoute:
    def test_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_lists_video_titles(self, client):
        resp = client.get("/")
        assert b"Guitar Lesson 1" in resp.data

    def test_sort_by_query_param(self, client):
        resp = client.get("/?sort_by=title&sort_dir=asc")
        assert resp.status_code == 200

    def test_channel_filter(self, client):
        resp = client.get("/?channel=GuitarChannel")
        assert resp.status_code == 200
        assert b"Guitar Lesson 1" in resp.data

    def test_tag_filter(self, client):
        resp = client.get("/?tag=guitar")
        assert resp.status_code == 200
        assert b"Guitar Lesson 1" in resp.data

    def test_search_filter(self, client):
        resp = client.get("/?search=shrimp")
        assert resp.status_code == 200
        assert b"Thai Food Recipe" in resp.data

    def test_invalid_sort_returns_400(self, client):
        resp = client.get("/?sort_by=DROP+TABLE")
        assert resp.status_code == 400

    def test_group_by_channel_view(self, client):
        resp = client.get("/?group=channel")
        assert resp.status_code == 200
        assert b"GuitarChannel" in resp.data


class TestIndexFilterQuickWins:
    def _seed(self, client):
        conn = sqlite3.connect(client.application.config["DATABASE"])
        conn.executescript(
            """
            INSERT INTO videos (video_id, url, title, channel_name, personal_view_count,
                                duration_seconds, date_added, fetch_status) VALUES
              ('qwshort0001', 'u', 'QW Short Vid', 'C', 0, 120,  date('now','-1 days'),  'ok'),
              ('qwlong00001', 'u', 'QW Long Vid',  'C', 5, 3600, date('now','-300 days'),'ok');
            UPDATE videos SET is_watched = 1 WHERE personal_view_count > 0;
            """
        )
        conn.commit()
        conn.close()

    def test_unwatched_filter(self, client):
        self._seed(client)
        body = client.get("/?unwatched=1", headers={"HX-Request": "true"}).get_data(as_text=True)
        assert "QW Short Vid" in body      # personal_view_count 0
        assert "QW Long Vid" not in body   # personal_view_count 5

    def test_duration_filter(self, client):
        self._seed(client)
        body = client.get("/?duration=short", headers={"HX-Request": "true"}).get_data(as_text=True)
        assert "QW Short Vid" in body
        assert "QW Long Vid" not in body

    def test_added_within_filter(self, client):
        self._seed(client)
        body = client.get("/?added_within=7", headers={"HX-Request": "true"}).get_data(as_text=True)
        assert "QW Short Vid" in body      # -1 day
        assert "QW Long Vid" not in body   # -300 days

    def test_invalid_duration_returns_400(self, client):
        assert client.get("/?duration=epic").status_code == 400

    def test_invalid_added_within_returns_400(self, client):
        assert client.get("/?added_within=5").status_code == 400

    def test_controls_render_current_state(self, client):
        body = client.get("/?duration=short&unwatched=1").get_data(as_text=True)
        assert 'name="duration"' in body and 'name="unwatched"' in body


class TestVisitRoute:
    def test_redirects_to_youtube(self, client):
        resp = client.get("/visit/aaaaaaaaaa1")
        assert resp.status_code == 302
        assert "youtube.com" in resp.headers["Location"]

    def test_increments_view_count(self, client):
        client.get("/visit/aaaaaaaaaa1")
        resp = client.get("/")
        assert resp.status_code == 200

    def test_unknown_video_returns_404(self, client):
        resp = client.get("/visit/doesnotexist")
        assert resp.status_code == 404


class TestMarkWatchedRoute:
    def test_returns_204(self, client):
        resp = client.post("/videos/aaaaaaaaaa1/mark-watched")
        assert resp.status_code == 204

    def test_increments_personal_view_count(self, client):
        client.post("/videos/aaaaaaaaaa1/mark-watched")
        resp = client.get("/")
        assert b"[1]" in resp.data

    def test_unknown_video_returns_404(self, client):
        resp = client.post("/videos/doesnotexist/mark-watched")
        assert resp.status_code == 404


class TestRemoveFromRediscoverShelfRoute:
    def _shelf_video_ids(self, client):
        import json
        import sqlite3
        conn = sqlite3.connect(client.application.config["DATABASE"])
        row = conn.execute(
            "SELECT video_ids FROM rediscover_shelf ORDER BY generated_at DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return json.loads(row[0])

    def test_returns_204(self, client):
        client.post("/rediscover-shelf/refresh")
        resp = client.post("/videos/aaaaaaaaaa1/rediscover-shelf/remove")
        assert resp.status_code == 204

    def test_removes_video_from_shelf(self, client):
        client.post("/rediscover-shelf/refresh")
        assert "aaaaaaaaaa1" in self._shelf_video_ids(client)
        client.post("/videos/aaaaaaaaaa1/rediscover-shelf/remove")
        assert "aaaaaaaaaa1" not in self._shelf_video_ids(client)

    def test_does_not_increment_personal_view_count(self, client):
        import sqlite3
        client.post("/rediscover-shelf/refresh")
        client.post("/videos/aaaaaaaaaa1/rediscover-shelf/remove")
        conn = sqlite3.connect(client.application.config["DATABASE"])
        row = conn.execute(
            "SELECT personal_view_count, date_last_viewed FROM videos WHERE video_id=?",
            ("aaaaaaaaaa1",),
        ).fetchone()
        conn.close()
        assert row[0] == 0
        assert row[1] is None

    def test_unknown_video_returns_404(self, client):
        resp = client.post("/videos/doesnotexist/rediscover-shelf/remove")
        assert resp.status_code == 404


class TestHideRoute:
    def test_hide_returns_204(self, client):
        resp = client.post("/videos/aaaaaaaaaa1/hide")
        assert resp.status_code == 204

    def test_hide_removes_video_from_index(self, client):
        client.post("/videos/aaaaaaaaaa1/hide")
        resp = client.get("/")
        assert b"Guitar Lesson 1" not in resp.data

    def test_unhide_restores_video(self, client):
        client.post("/videos/aaaaaaaaaa1/hide")
        client.post("/videos/aaaaaaaaaa1/unhide")
        resp = client.get("/")
        assert b"Guitar Lesson 1" in resp.data

    def test_unhide_redirects_to_hidden(self, client):
        client.post("/videos/aaaaaaaaaa1/hide")
        resp = client.post("/videos/aaaaaaaaaa1/unhide")
        assert resp.status_code == 302
        assert "/hidden" in resp.headers["Location"]

    def test_delete_removes_video_permanently(self, client):
        client.post("/videos/aaaaaaaaaa1/hide")
        client.post("/videos/aaaaaaaaaa1/delete")
        resp = client.get("/")
        assert b"Guitar Lesson 1" not in resp.data

    def test_delete_redirects_to_hidden(self, client):
        client.post("/videos/aaaaaaaaaa1/hide")
        resp = client.post("/videos/aaaaaaaaaa1/delete")
        assert resp.status_code == 302
        assert "/hidden" in resp.headers["Location"]


class TestHiddenPage:
    def test_returns_200(self, client):
        resp = client.get("/hidden")
        assert resp.status_code == 200

    def test_shows_hidden_videos(self, client):
        client.post("/videos/aaaaaaaaaa1/hide")
        resp = client.get("/hidden")
        assert b"Guitar Lesson 1" in resp.data

    def test_hidden_video_absent_from_main(self, client):
        client.post("/videos/aaaaaaaaaa1/hide")
        resp = client.get("/")
        assert b"Guitar Lesson 1" not in resp.data

    def test_empty_state(self, client):
        resp = client.get("/hidden")
        assert b"No archived videos" in resp.data

    def test_restore_action(self, client):
        client.post("/videos/aaaaaaaaaa1/hide")
        client.post("/videos/aaaaaaaaaa1/unhide")
        resp = client.get("/hidden")
        assert b"Guitar Lesson 1" not in resp.data

    def test_nav_hidden_link_appears(self, client):
        client.post("/videos/aaaaaaaaaa1/hide")
        resp = client.get("/")
        assert b'nav-hidden' in resp.data

    def test_nav_hidden_link_absent_when_none(self, client):
        resp = client.get("/")
        assert b"Archived" not in resp.data


class TestApiStatus:
    def test_not_found(self, client):
        resp = client.get("/api/status?url=https://www.youtube.com/watch?v=XXXXXXXXXXX")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "not_found"

    def test_exists(self, client):
        resp = client.get("/api/status?url=https://www.youtube.com/watch?v=aaaaaaaaaa1")
        data = resp.get_json()
        assert data["status"] == "exists"
        assert data["title"] == "Guitar Lesson 1"

    def test_hidden(self, client):
        client.post("/videos/aaaaaaaaaa1/hide")
        resp = client.get("/api/status?url=https://www.youtube.com/watch?v=aaaaaaaaaa1")
        data = resp.get_json()
        assert data["status"] == "hidden"
        assert data["video_id"] == "aaaaaaaaaa1"

    def test_invalid_url(self, client):
        resp = client.get("/api/status?url=https://example.com/not-youtube")
        assert resp.status_code == 400
        assert resp.get_json()["status"] == "error"


class TestApiStatusBatch:
    def test_mixed_results(self, client):
        client.post("/videos/aaaaaaaaaa2/hide")
        data = client.post("/api/status/batch", json={
            "ids": ["aaaaaaaaaa1", "aaaaaaaaaa2", "XXXXXXXXXXX"]
        }).get_json()
        assert data["aaaaaaaaaa1"] == "exists"
        assert data["aaaaaaaaaa2"] == "hidden"
        assert data["XXXXXXXXXXX"] == "not_found"

    def test_empty_ids_returns_empty(self, client):
        data = client.post("/api/status/batch", json={"ids": []}).get_json()
        assert data == {}

    def test_missing_ids_key_returns_empty(self, client):
        data = client.post("/api/status/batch", json={}).get_json()
        assert data == {}

    def test_ignores_non_string_ids(self, client):
        data = client.post("/api/status/batch", json={"ids": [1, None, "aaaaaaaaaa1"]}).get_json()
        assert "aaaaaaaaaa1" in data
        assert data["aaaaaaaaaa1"] == "exists"

    def test_cors_header_present(self, client):
        resp = client.post("/api/status/batch", json={"ids": []})
        assert "Access-Control-Allow-Origin" in resp.headers

    def test_options_preflight(self, client):
        resp = client.options("/api/status/batch")
        assert resp.status_code == 204


class TestApiHide:
    def test_hides_video(self, client):
        resp = client.post("/api/hide", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "hidden"
        assert data["title"] == "Guitar Lesson 1"

    def test_unknown_video_returns_error(self, client):
        resp = client.post("/api/hide", json={"url": "https://www.youtube.com/watch?v=XXXXXXXXXXX"})
        assert resp.status_code == 404
        assert resp.get_json()["status"] == "error"

    def test_invalid_url_returns_error(self, client):
        resp = client.post("/api/hide", json={"url": "https://example.com"})
        assert resp.status_code == 400
        assert resp.get_json()["status"] == "error"

    def test_cors_header_present(self, client):
        resp = client.post("/api/hide", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        assert "Access-Control-Allow-Origin" in resp.headers

    def test_options_preflight(self, client):
        resp = client.options("/api/hide")
        assert resp.status_code == 204


class TestFavouriteToggle:
    def test_toggle_on_returns_true(self, client):
        resp = client.post("/videos/aaaaaaaaaa1/favourite")
        assert resp.status_code == 200
        assert resp.get_json()["is_favourite"] is True

    def test_toggle_off_returns_false(self, client):
        client.post("/videos/aaaaaaaaaa1/favourite")
        resp = client.post("/videos/aaaaaaaaaa1/favourite")
        assert resp.get_json()["is_favourite"] is False

    def test_unknown_video_returns_404(self, client):
        resp = client.post("/videos/XXXXXXXXXXX/favourite")
        assert resp.status_code == 404

    def test_favourites_filter_returns_only_favourites(self, client):
        client.post("/videos/aaaaaaaaaa1/favourite")
        resp = client.get("/?favourites=1", headers={"HX-Request": "true"})
        assert b"Guitar Lesson 1" in resp.data
        assert b"Thai Food Recipe" not in resp.data


class TestToggleWatched:
    def test_toggles_watched_on(self, client):
        # aaaaaaaaaa1 seeds unwatched (count 0 → is_watched 0)
        data = client.post("/videos/aaaaaaaaaa1/watched").get_json()
        assert data["is_watched"] is True

    def test_toggle_twice_returns_to_original(self, client):
        first = client.post("/videos/aaaaaaaaaa1/watched").get_json()["is_watched"]
        second = client.post("/videos/aaaaaaaaaa1/watched").get_json()["is_watched"]
        assert first is True and second is False

    def test_unknown_video_returns_404(self, client):
        assert client.post("/videos/doesnotexist/watched").status_code == 404

    def test_toggle_does_not_change_view_count(self, client):
        client.post("/videos/aaaaaaaaaa2/watched")  # was watched (count 3) → unwatched
        conn = sqlite3.connect(client.application.config["DATABASE"])
        count = conn.execute(
            "SELECT personal_view_count FROM videos WHERE video_id = 'aaaaaaaaaa2'"
        ).fetchone()[0]
        conn.close()
        assert count == 3   # history preserved

    def test_unwatched_filter_reflects_toggle(self, client):
        client.post("/videos/aaaaaaaaaa1/watched")  # mark watched
        body = client.get("/?unwatched=1", headers={"HX-Request": "true"}).get_data(as_text=True)
        assert "Guitar Lesson 1" not in body   # aaaaaaaaaa1's title now excluded


class TestWatchLaterReorder:
    def test_reorder_moves_video_and_returns_204(self, client):
        for vid in ("aaaaaaaaaa1", "aaaaaaaaaa2", "aaaaaaaaaa3"):
            client.post("/api/watch-later/add", json={"url": "https://www.youtube.com/watch?v=" + vid})

        resp = client.post("/videos/aaaaaaaaaa1/watch-later/reorder", json={"position": 3})
        assert resp.status_code == 204

        page = client.get("/watch-later")
        ids_in_order = [m for m in ("aaaaaaaaaa1", "aaaaaaaaaa2", "aaaaaaaaaa3")
                         if page.data.find(m.encode()) != -1]
        positions = {vid: page.data.find(vid.encode()) for vid in ids_in_order}
        assert positions["aaaaaaaaaa2"] < positions["aaaaaaaaaa3"] < positions["aaaaaaaaaa1"]

    def test_missing_position_returns_400(self, client):
        client.post("/api/watch-later/add", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        resp = client.post("/videos/aaaaaaaaaa1/watch-later/reorder", json={})
        assert resp.status_code == 400

    def test_video_not_in_queue_returns_404(self, client):
        resp = client.post("/videos/aaaaaaaaaa1/watch-later/reorder", json={"position": 1})
        assert resp.status_code == 404


class TestRediscoverShelfRefresh:
    def test_returns_200_html(self, client):
        resp = client.post("/rediscover-shelf/refresh")
        assert resp.status_code == 200
        assert b"video-card" in resp.data or b"empty-shelf" in resp.data

    def test_returns_html_not_json(self, client):
        resp = client.post("/rediscover-shelf/refresh")
        assert resp.content_type.startswith("text/html")


class TestApiAddHiddenVideo:
    def test_hidden_video_returns_hidden_status(self, client):
        client.post("/videos/aaaaaaaaaa1/hide")
        resp = client.post("/api/add", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        data = resp.get_json()
        assert data["status"] == "hidden"
        assert data["title"] == "Guitar Lesson 1"


class TestWatchLaterPage:
    def test_returns_200(self, client):
        resp = client.get("/watch-later")
        assert resp.status_code == 200

    def test_empty_queue_message(self, client):
        resp = client.get("/watch-later")
        assert b"Your queue is empty" in resp.data

    def test_shows_queued_videos(self, client):
        client.post("/api/watch-later/add", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        resp = client.get("/watch-later")
        assert resp.status_code == 200
        assert b"Guitar Lesson 1" in resp.data

    def test_queue_count_in_title(self, client):
        client.post("/api/watch-later/add", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        resp = client.get("/watch-later")
        assert b"Watch Later (1)" in resp.data


class TestApiWatchLaterAdd:
    def test_add_video_returns_added(self, client):
        resp = client.post("/api/watch-later/add", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        data = resp.get_json()
        assert data["status"] == "added"

    def test_duplicate_add_returns_already_in_queue(self, client):
        client.post("/api/watch-later/add", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        resp = client.post("/api/watch-later/add", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        data = resp.get_json()
        assert data["status"] == "already_in_queue"

    def test_invalid_video_returns_error(self, client):
        resp = client.post("/api/watch-later/add", json={"url": "https://www.youtube.com/watch?v=XXXXXXXXXXX"})
        data = resp.get_json()
        assert data["status"] == "error"

    def test_invalid_url_returns_error(self, client):
        resp = client.post("/api/watch-later/add", json={"url": "https://example.com"})
        data = resp.get_json()
        assert data["status"] == "error"

    def test_cors_header_present(self, client):
        resp = client.post("/api/watch-later/add", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        assert "Access-Control-Allow-Origin" in resp.headers

    def test_options_preflight(self, client):
        resp = client.options("/api/watch-later/add")
        assert resp.status_code == 204


class TestApiWatchLaterRemove:
    def test_remove_video_returns_removed(self, client):
        client.post("/api/watch-later/add", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        resp = client.post("/api/watch-later/remove", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        data = resp.get_json()
        assert data["status"] == "removed"

    def test_remove_nonexistent_video_returns_error(self, client):
        resp = client.post("/api/watch-later/remove", json={"url": "https://www.youtube.com/watch?v=XXXXXXXXXXX"})
        data = resp.get_json()
        assert data["status"] == "error"
        assert resp.status_code == 404

    def test_remove_not_in_queue_returns_error(self, client):
        resp = client.post("/api/watch-later/remove", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        data = resp.get_json()
        assert data["status"] == "error"
        assert resp.status_code == 404

    def test_remove_video_from_queue(self, client):
        client.post("/api/watch-later/add", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        client.post("/api/watch-later/remove", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        resp = client.get("/watch-later")
        assert b"Guitar Lesson 1" not in resp.data
        assert b"Your queue is empty" in resp.data

    def test_cors_header_present(self, client):
        client.post("/api/watch-later/add", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        resp = client.post("/api/watch-later/remove", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        assert "Access-Control-Allow-Origin" in resp.headers

    def test_options_preflight(self, client):
        resp = client.options("/api/watch-later/remove")
        assert resp.status_code == 204


class TestApiWatchLaterStatus:
    def test_status_for_queued_video(self, client):
        client.post("/api/watch-later/add", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        resp = client.post("/api/watch-later/status", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        data = resp.get_json()
        assert data["in_queue"] is True

    def test_status_for_non_queued_video(self, client):
        resp = client.post("/api/watch-later/status", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        data = resp.get_json()
        assert data["in_queue"] is False

    def test_nonexistent_video_returns_error(self, client):
        resp = client.post("/api/watch-later/status", json={"url": "https://www.youtube.com/watch?v=XXXXXXXXXXX"})
        data = resp.get_json()
        assert data["status"] == "error"
        assert resp.status_code == 404

    def test_invalid_url_returns_error(self, client):
        resp = client.post("/api/watch-later/status", json={"url": "https://example.com"})
        data = resp.get_json()
        assert data["status"] == "error"

    def test_cors_header_present(self, client):
        resp = client.post("/api/watch-later/status", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        assert "Access-Control-Allow-Origin" in resp.headers

    def test_options_preflight(self, client):
        resp = client.options("/api/watch-later/status")
        assert resp.status_code == 204


class TestAddTagRoute:
    def _seed_canonical(self, client, name):
        import sqlite3
        conn = sqlite3.connect(client.application.config["DATABASE"])
        conn.execute("INSERT INTO tags (name, is_canonical) VALUES (?, 1)", (name,))
        conn.commit()
        conn.close()

    def test_attach_existing_canonical_tag(self, client):
        self._seed_canonical(client, "music")
        resp = client.post("/videos/aaaaaaaaaa1/tags/add", data={"tag_name": "music"})
        assert resp.status_code == 200
        assert b'data-tag-name="music"' in resp.data

    def test_creates_brand_new_tag(self, client):
        resp = client.post("/videos/aaaaaaaaaa1/tags/add", data={"tag_name": "synthwave"})
        assert resp.status_code == 200
        assert b'data-tag-name="synthwave"' in resp.data

    def test_promotes_existing_raw_tag_and_affects_other_videos(self, client):
        # seed tag 'guitar' (id=1) is raw, used by both aaaaaaaaaa1 and aaaaaaaaaa3
        resp = client.post("/videos/aaaaaaaaaa1/tags/add", data={"tag_name": "guitar"})
        assert resp.status_code == 200
        assert b'data-tag-name="guitar"' in resp.data
        import sqlite3
        conn = sqlite3.connect(client.application.config["DATABASE"])
        rows = conn.execute(
            "SELECT t.name FROM tags t JOIN video_tags vt ON vt.tag_id_fk = t.id "
            "JOIN videos v ON v.id = vt.video_id_fk "
            "WHERE v.video_id = 'aaaaaaaaaa3' AND t.is_canonical = 1"
        ).fetchall()
        conn.close()
        assert ("guitar",) in rows

    def test_idempotent_reattach(self, client):
        self._seed_canonical(client, "music")
        client.post("/videos/aaaaaaaaaa1/tags/add", data={"tag_name": "music"})
        resp = client.post("/videos/aaaaaaaaaa1/tags/add", data={"tag_name": "music"})
        assert resp.status_code == 200
        assert resp.data.count(b'data-tag-name="music"') == 1

    def test_blank_tag_name_returns_400(self, client):
        resp = client.post("/videos/aaaaaaaaaa1/tags/add", data={"tag_name": "   "})
        assert resp.status_code == 400

    def test_unknown_video_returns_404(self, client):
        resp = client.post("/videos/doesnotexist/tags/add", data={"tag_name": "music"})
        assert resp.status_code == 404


class TestApiChannelStatus:
    def _insert_channel(self, client):
        conn = sqlite3.connect(client.application.config["DATABASE"])
        conn.execute(
            "INSERT INTO channels (channel_id, channel_name, channel_url, source_url, "
            "fetch_status) VALUES (?, ?, ?, ?, 'ok')",
            ("UCzzz999", "Tracked Chan",
             "https://www.youtube.com/channel/UCzzz999",
             "https://www.youtube.com/@tracked"),
        )
        conn.commit()
        conn.close()

    def test_not_found_for_untracked(self, client):
        resp = client.get("/api/channel/status?url=https://www.youtube.com/@nobody")
        assert resp.get_json()["status"] == "not_found"

    def test_exists_for_tracked(self, client):
        self._insert_channel(client)
        data = client.get(
            "/api/channel/status?url=https://www.youtube.com/@tracked"
        ).get_json()
        assert data["status"] == "exists"
        assert data["channel_name"] == "Tracked Chan"

    def test_non_channel_url_returns_400(self, client):
        resp = client.get("/api/channel/status?url=https://example.com/foo")
        assert resp.status_code == 400
        assert resp.get_json()["status"] == "error"

    def test_cors_header_present(self, client):
        resp = client.get("/api/channel/status?url=https://www.youtube.com/@nobody")
        assert "Access-Control-Allow-Origin" in resp.headers

    def test_options_preflight(self, client):
        resp = client.options("/api/channel/status")
        assert resp.status_code == 204
        assert "Access-Control-Allow-Origin" in resp.headers


class TestApiChannelAdd:
    def _fake_meta(self):
        return ChannelMetadata(
            channel_id="UCadd777", channel_name="Added Chan",
            channel_url="https://www.youtube.com/channel/UCadd777",
            description="desc", subscriber_count=5,
            thumbnail_url="https://img/y.jpg", fetch_status=FetchStatus.OK,
        )

    def test_adds_new_channel(self, client, monkeypatch):
        monkeypatch.setattr(
            "crawler.metadata_fetcher.fetch_channel_metadata",
            lambda url, delay=0: self._fake_meta(),
        )
        data = client.post(
            "/api/channel/add", json={"url": "https://www.youtube.com/@added"}
        ).get_json()
        assert data["status"] == "added"
        assert data["channel_name"] == "Added Chan"

    def test_second_add_reports_exists(self, client, monkeypatch):
        monkeypatch.setattr(
            "crawler.metadata_fetcher.fetch_channel_metadata",
            lambda url, delay=0: self._fake_meta(),
        )
        client.post("/api/channel/add", json={"url": "https://www.youtube.com/@added"})
        data = client.post(
            "/api/channel/add", json={"url": "https://www.youtube.com/@added"}
        ).get_json()
        assert data["status"] == "exists"

    def test_fetch_error_returns_error(self, client, monkeypatch):
        err = ChannelMetadata(
            channel_id="", channel_name="",
            channel_url="https://www.youtube.com/@broken",
            fetch_status=FetchStatus.PRIVATE, fetch_error="unavailable",
        )
        monkeypatch.setattr(
            "crawler.metadata_fetcher.fetch_channel_metadata",
            lambda url, delay=0: err,
        )
        data = client.post(
            "/api/channel/add", json={"url": "https://www.youtube.com/@broken"}
        ).get_json()
        assert data["status"] == "error"
        assert data["error"] == "unavailable"

    def test_non_channel_url_returns_400(self, client):
        resp = client.post("/api/channel/add", json={"url": "https://example.com/foo"})
        assert resp.status_code == 400

    def test_cors_header_present(self, client, monkeypatch):
        monkeypatch.setattr(
            "crawler.metadata_fetcher.fetch_channel_metadata",
            lambda url, delay=0: self._fake_meta(),
        )
        resp = client.post("/api/channel/add", json={"url": "https://www.youtube.com/@added"})
        assert "Access-Control-Allow-Origin" in resp.headers

    def test_options_preflight(self, client):
        resp = client.options("/api/channel/add")
        assert resp.status_code == 204
        assert "Access-Control-Allow-Origin" in resp.headers


class TestChannelsPage:
    def _seed(self, client):
        conn = sqlite3.connect(client.application.config["DATABASE"])
        conn.executescript(
            """
            INSERT INTO channels (channel_id, channel_name, channel_url, subscriber_count, fetch_status) VALUES
              ('UCaaa', 'AlphaChan',   'https://youtube.com/channel/UCaaa', 1000, 'ok'),
              ('UCbbb', 'BravoChan',   'https://youtube.com/channel/UCbbb', 5000, 'ok'),
              ('UCccc', 'CharlieChan', 'https://youtube.com/channel/UCccc', NULL, 'ok');
            INSERT INTO videos (video_id, url, title, channel_name, channel_id, date_added, fetch_status) VALUES
              ('chrt000001', 'u', 'V1', 'AlphaChan', 'UCaaa', '2024-01-01', 'ok');
            """
        )
        conn.commit()
        conn.close()

    def test_returns_200_and_lists_channels(self, client):
        self._seed(client)
        resp = client.get("/channels")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "AlphaChan" in body and "CharlieChan" in body

    def test_has_videos_filter_hides_zero(self, client):
        self._seed(client)
        body = client.get("/channels?has_videos=1").get_data(as_text=True)
        assert "AlphaChan" in body
        assert "CharlieChan" not in body

    def test_search_filters_by_name(self, client):
        self._seed(client)
        body = client.get("/channels?search=alpha").get_data(as_text=True)
        assert "AlphaChan" in body
        assert "BravoChan" not in body

    def test_invalid_sort_returns_400(self, client):
        self._seed(client)
        assert client.get("/channels?sort=bogus").status_code == 400

    def test_append_fragment_omits_page_chrome(self, client):
        self._seed(client)
        resp = client.get("/channels?append=1", headers={"HX-Request": "true"})
        body = resp.get_data(as_text=True)
        assert "AlphaChan" in body
        assert "<!doctype html>" not in body.lower()



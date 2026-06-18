import pytest


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



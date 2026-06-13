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
        assert b"No hidden videos" in resp.data

    def test_restore_action(self, client):
        client.post("/videos/aaaaaaaaaa1/hide")
        client.post("/videos/aaaaaaaaaa1/unhide")
        resp = client.get("/hidden")
        assert b"Guitar Lesson 1" not in resp.data

    def test_nav_hidden_link_appears(self, client):
        client.post("/videos/aaaaaaaaaa1/hide")
        resp = client.get("/")
        assert b"Hidden (1)" in resp.data

    def test_nav_hidden_link_absent_when_none(self, client):
        resp = client.get("/")
        assert b"Hidden" not in resp.data


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


class TestApiAddHiddenVideo:
    def test_hidden_video_returns_hidden_status(self, client):
        client.post("/videos/aaaaaaaaaa1/hide")
        resp = client.post("/api/add", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        data = resp.get_json()
        assert data["status"] == "hidden"
        assert data["title"] == "Guitar Lesson 1"



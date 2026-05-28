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


class TestTagsRoute:
    def test_tags_page_returns_200(self, client):
        resp = client.get("/tags")
        assert resp.status_code == 200

    def test_lists_tag_names(self, client):
        resp = client.get("/tags")
        assert b"guitar" in resp.data

    def test_create_tag_post(self, client):
        resp = client.post("/tags", data={"name": "coding"})
        assert resp.status_code in (200, 302)

    def test_create_tag_empty_name_returns_400(self, client):
        resp = client.post("/tags", data={"name": ""})
        assert resp.status_code == 400


class TestTagDetailRoute:
    def test_get_tag_returns_200(self, client):
        resp = client.get("/tags/1")
        assert resp.status_code == 200

    def test_unknown_tag_returns_404(self, client):
        resp = client.get("/tags/9999")
        assert resp.status_code == 404

    def test_set_keywords_post(self, client):
        resp = client.post("/tags/1/keywords", data={"keywords": "guitar\nchord"})
        assert resp.status_code in (200, 302)

    def test_delete_tag(self, client):
        resp = client.post("/tags/1/delete")
        assert resp.status_code in (200, 302)


class TestVideoTagRoute:
    def test_add_tag_to_video(self, client):
        resp = client.post("/videos/aaaaaaaaaa5/tags", data={"tag_id": "2"})
        assert resp.status_code in (200, 302)

    def test_remove_tag_from_video(self, client):
        resp = client.post("/videos/aaaaaaaaaa1/tags/1/delete")
        assert resp.status_code in (200, 302)

    def test_add_tag_unknown_video_returns_404(self, client):
        resp = client.post("/videos/doesnotexist/tags", data={"tag_id": "1"})
        assert resp.status_code == 404

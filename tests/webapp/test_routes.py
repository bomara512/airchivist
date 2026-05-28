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



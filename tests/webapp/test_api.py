from webapp.api import ApiStatus


class TestApiStatusEnum:
    def test_members_are_plain_strings(self):
        assert ApiStatus.ADDED == "added"
        assert ApiStatus.REMOVED == "removed"
        assert ApiStatus.EXISTS == "exists"
        assert ApiStatus.NOT_FOUND == "not_found"
        assert ApiStatus.HIDDEN == "hidden"
        assert ApiStatus.ALREADY_IN_QUEUE == "already_in_queue"
        assert ApiStatus.ERROR == "error"


class TestResolveVideoDecorator:
    """Review Focus #3: a malformed or absent JSON body must still be a 400."""

    def test_missing_body_returns_400(self, client):
        resp = client.post("/api/favorite/add")
        assert resp.status_code == 400
        assert resp.get_json()["status"] == "error"

    def test_null_url_returns_400(self, client):
        resp = client.post("/api/favorite/add", json={"url": None})
        assert resp.status_code == 400
        assert resp.get_json()["status"] == "error"

    def test_cors_header_on_400(self, client):
        resp = client.post("/api/favorite/add", json={"url": "https://example.com"})
        assert "Access-Control-Allow-Origin" in resp.headers

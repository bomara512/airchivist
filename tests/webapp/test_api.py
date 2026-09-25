import pytest

from webapp.api import ApiStatus, cors_json, resolve_video, video_api_route


class TestDecoratorOrderIsEnforced:
    """A transposed stack silently strips CORS and lets OPTIONS fall through to
    the view — Flask accepts the (dict, status) tuple either way, so nothing
    fails loudly and `test_client` cannot see the missing header. Make the
    mistake unrepresentable rather than documented."""

    def test_applying_resolve_video_above_cors_json_raises_at_decoration_time(self):
        def view(video):
            return {"ok": True}

        with pytest.raises(TypeError, match="below"):
            resolve_video(cors_json(view))

    def test_correct_order_decorates_without_complaint(self):
        def view(video):
            return {"ok": True}

        assert callable(cors_json(resolve_video(view)))

    def test_video_api_route_composes_them_in_the_right_order(self):
        def view(video):
            return {"ok": True}

        assert callable(video_api_route(view))


class TestEveryApiRouteCarriesCors:
    """Defense in depth for the same failure: whatever decorator a route uses,
    an error response and an OPTIONS preflight must both carry CORS headers.
    Parametrized over the live url_map so a route added later is covered too."""

    def _api_rules(self, app, method):
        return sorted(
            r.rule for r in app.url_map.iter_rules()
            if r.rule.startswith("/api/") and method in r.methods
        )

    def test_options_preflight_is_204_with_cors_everywhere(self, client):
        rules = self._api_rules(client.application, "OPTIONS")
        assert len(rules) >= 12, f"expected all /api/* routes, found {rules}"
        for rule in rules:
            resp = client.open(rule, method="OPTIONS")
            assert resp.status_code == 204, f"{rule} preflight returned {resp.status_code}"
            assert "Access-Control-Allow-Origin" in resp.headers, f"{rule} preflight lost CORS"

    def test_bad_url_error_response_carries_cors_everywhere(self, client):
        # /api/status/batch takes `ids`, not `url`, so a bad url is a 200 with
        # empty results there — still must carry CORS, which is what we assert.
        rules = self._api_rules(client.application, "POST")
        assert rules, "expected at least one POST /api/* route"
        for rule in rules:
            resp = client.post(rule, json={"url": "https://example.com"})
            assert "Access-Control-Allow-Origin" in resp.headers, f"{rule} lost CORS on error"


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


class TestToolingPinsAgree:
    """`.pre-commit-config.yaml` pins a ruff rev and `pyproject.toml` pins a ruff
    version. They agreed only by coincidence until 2026-09-25; a hook running a
    different ruff than the local gate disagrees with it, which is worse than no
    hook. Enforce the agreement instead of commenting about it."""

    def test_precommit_rev_matches_the_dev_extra(self):
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        hook_rev = re.search(
            r"ruff-pre-commit\s*\n\s*rev:\s*v([0-9][^\s]*)",
            (root / ".pre-commit-config.yaml").read_text(),
        )
        pinned = re.search(
            r'"ruff==([^"]+)"', (root / "pyproject.toml").read_text()
        )
        assert hook_rev, "could not find the ruff-pre-commit rev"
        assert pinned, "pyproject's dev extras must pin ruff exactly (ruff==X.Y.Z)"
        assert hook_rev.group(1) == pinned.group(1), (
            f"pre-commit pins ruff v{hook_rev.group(1)} but the dev extras pin "
            f"{pinned.group(1)} — they must match"
        )

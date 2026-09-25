import functools
from enum import StrEnum

from flask import g, jsonify, make_response, request

from crawler.models import extract_video_id
from webapp import db as _db

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST",
    "Access-Control-Allow-Headers": "Content-Type",
}


class ApiStatus(StrEnum):
    """Every `status` value the extension-facing JSON API returns."""

    ADDED = "added"
    REMOVED = "removed"
    EXISTS = "exists"
    NOT_FOUND = "not_found"
    HIDDEN = "hidden"
    ALREADY_IN_QUEUE = "already_in_queue"
    ERROR = "error"


def _request_url() -> str:
    """The `url` the caller sent, from the JSON body or else the query string.

    Body first: every route using this is POST, where the body is authoritative,
    and a GET has no body so it falls through to the query string. Checking both
    rather than branching on `request.method` means a route registered for both
    would not silently ignore one of them.

    A non-string `url` (e.g. `{"url": 123}`) yields "" rather than raising, so it
    reaches the caller's "Not a YouTube URL" 400 instead of a 500.
    """
    body = request.get_json(silent=True) or {}
    from_body = body.get("url")
    if isinstance(from_body, str) and from_body.strip():
        return from_body.strip()
    from_args = request.args.get("url")
    return from_args.strip() if isinstance(from_args, str) else ""


def cors_json(fn):
    """Answer the OPTIONS preflight, JSON-encode the return value, attach CORS headers.

    The wrapped view returns either a body dict (implying 200) or a
    (body, status) tuple.

    Use this alone for routes that must not 404 on an unknown video — see
    `video_api_route` for the ones that must.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if request.method == "OPTIONS":
            return make_response("", 204, CORS_HEADERS)
        result = fn(*args, **kwargs)
        body, status = result if isinstance(result, tuple) else (result, 200)
        resp = jsonify(body)
        resp.headers.update(CORS_HEADERS)
        return resp, status
    wrapper._is_cors_json = True
    return wrapper


def resolve_video(fn):
    """Parse the request's `url` and load its video row, or return the shared errors.

    Passes the row to the view as its first positional argument, and returns
    plain dicts — so it only works *below* `cors_json`, which encodes them.
    Prefer `video_api_route`, which composes the two correctly; this is exported
    for the rare case that needs them apart.
    """
    if getattr(fn, "_is_cors_json", False):
        raise TypeError(
            "resolve_video must be applied below cors_json, not above it. "
            "Transposed, Flask still returns the (dict, status) tuple — but with "
            "no CORS headers, and OPTIONS falls through to the view — so the "
            "mistake is invisible to the test client and surfaces only as an "
            "opaque CORS failure in the extension. Use @video_api_route instead."
        )

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        video_id = extract_video_id(_request_url())
        if video_id is None:
            return {"status": ApiStatus.ERROR, "error": "Not a YouTube URL"}, 400
        video = _db.get_video_by_id(g.db, video_id)
        if not video:
            return {"status": ApiStatus.ERROR, "error": "Video not found"}, 404
        return fn(video, *args, **kwargs)
    return wrapper


def video_api_route(fn):
    """The standard stack for an API route that requires the video to already exist.

    Equivalent to `@cors_json` over `@resolve_video`, as one decorator so the
    order cannot be transposed. The view receives the video row as its first
    argument and returns a dict, or a (dict, status) tuple.
    """
    return cors_json(resolve_video(fn))

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
    """The `url` the caller sent — query string on GET, JSON body otherwise."""
    if request.method == "GET":
        return (request.args.get("url") or "").strip()
    data = request.get_json(silent=True) or {}
    return (data.get("url") or "").strip()


def cors_json(fn):
    """Answer the OPTIONS preflight, JSON-encode the return value, attach CORS headers.

    The wrapped view returns either a body dict (implying 200) or a
    (body, status) tuple.
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
    return wrapper


def resolve_video(fn):
    """Parse the request's `url` and load its video row, or return the shared errors.

    Passes the row to the view as its first positional argument. Must be applied
    *below* `cors_json`, which encodes the error bodies returned here.
    """
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

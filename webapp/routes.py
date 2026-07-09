import math
import os
from datetime import datetime, timezone
from flask import Blueprint, g, request, redirect, abort, render_template, url_for, jsonify, make_response
from webapp import db as _db
from webapp import llm_tagger as _llm
from crawler.models import _YT_ID_RE, FetchStatus
from webapp.db import MatchType

bp = Blueprint("main", __name__)

PAGE_SIZE = 100

_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST",
    "Access-Control-Allow-Headers": "Content-Type",
}


def _shelf_expires_label(expires_at_str: str | None) -> str:
    if not expires_at_str:
        return "—"
    try:
        expires = datetime.fromisoformat(expires_at_str)
        diff = expires - datetime.now(timezone.utc)
        if diff.total_seconds() <= 0:
            return "expired"
        days = diff.days
        hours = diff.seconds // 3600
        if days > 0:
            return f"{days} day{'s' if days != 1 else ''}"
        return f"{hours} hour{'s' if hours != 1 else ''}"
    except Exception:
        return "—"


@bp.route("/")
def index():
    sort_by = request.args.get("sort_by", "date_added")
    sort_dir = request.args.get("sort_dir", "desc")
    channel = request.args.get("channel") or None
    tag = request.args.get("tag") or None
    search = request.args.get("search") or None
    group = request.args.get("group") or None
    favourites_only = request.args.get("favourites") == "1"
    append = request.args.get("append") == "1"
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    try:
        total = _db.count_videos(g.db, channel=channel, tag=tag, search=search, favourites_only=favourites_only)
        videos = _db.get_all_videos(
            g.db, sort_by=sort_by, sort_dir=sort_dir,
            channel=channel, tag=tag, search=search,
            page=page, page_size=PAGE_SIZE,
            group=group, favourites_only=favourites_only,
        )
    except ValueError:
        abort(400)

    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(page, total_pages)

    def page_url(p):
        args = {k: v for k, v in request.args.to_dict().items() if k not in ("page", "append")}
        args["page"] = p
        return url_for("main.index", **args)

    channels = _db.get_video_channel_names(g.db)
    canonical_tags = _db.get_canonical_tags_for_filter_grouped(g.db)

    groups = None
    if group == "channel":
        grouped = {}
        for video in videos:
            ch = video.get("channel_name") or "Unknown"
            grouped.setdefault(ch, []).append(video)
        groups = [{"tag": {"name": ch}, "videos": vids} for ch, vids in grouped.items()]
    elif group == "tag":
        grouped = {}
        untagged = []
        for video in videos:
            tag_names = [t.strip() for t in (video.get("tags") or "").split(",") if t.strip()]
            if tag_names:
                for name in tag_names:
                    grouped.setdefault(name, []).append(video)
            else:
                untagged.append(video)
        groups = [{"tag": {"name": name}, "videos": vids} for name, vids in sorted(grouped.items())]
        if untagged:
            groups.append({"tag": {"name": "Untagged"}, "videos": untagged})

    template_vars = dict(
        videos=videos,
        channels=channels,
        canonical_tags=canonical_tags,
        groups=groups,
        sort_by=sort_by,
        sort_dir=sort_dir,
        current_channel=channel,
        current_tag=tag,
        current_search=search,
        group=group,
        favourites_only=favourites_only,
        page=page,
        total_pages=total_pages,
        total=total,
        prev_url=page_url(page - 1) if page > 1 else None,
        next_url=page_url(page + 1) if page < total_pages else None,
    )

    if request.headers.get("HX-Request"):
        if append:
            return render_template("_load_more.html", **template_vars)
        return render_template("_video_container.html", **template_vars)

    shelf = _db.get_current_rediscover_shelf(g.db)
    template_vars["shelf"] = shelf
    template_vars["expires_label"] = _shelf_expires_label(shelf.get("expires_at"))
    return render_template("index.html", **template_vars)


@bp.route("/videos/<video_id>/tags/remove", methods=["POST"])
def video_remove_tag(video_id):
    tag_name = request.form.get("tag_name", "").strip()
    if tag_name:
        tag_row = g.db.execute("SELECT id FROM tags WHERE name = ?", (tag_name,)).fetchone()
        if tag_row:
            _db.remove_video_tag(g.db, video_id, tag_row["id"])
    return "", 204


@bp.route("/videos/<video_id>/tags/add", methods=["POST"])
def video_add_tag(video_id):
    tag_name = request.form.get("tag_name", "").strip()
    if not tag_name:
        abort(400)
    video = _db.get_video_by_id(g.db, video_id)
    if not video:
        abort(404)
    tag_id = _db.create_canonical_tag(g.db, tag_name)
    _db.add_video_tag(g.db, video_id, tag_id)
    tags = _db.get_canonical_tags_for_video(g.db, video_id)
    return render_template("_tag_pills.html", video={"video_id": video_id, "tags": ",".join(tags)})


@bp.route("/visit/<video_id>")
def visit(video_id):
    row = _db.get_video_by_id(g.db, video_id)
    if row is None:
        abort(404)
    _db.record_visit(g.db, video_id)
    return redirect(row["url"])


@bp.route("/api/add", methods=["POST", "OPTIONS"])
def api_add():
    if request.method == "OPTIONS":
        return make_response("", 204, _CORS_HEADERS)

    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()

    m = _YT_ID_RE.search(url)
    if not m:
        resp = jsonify({"status": "error", "error": "Not a YouTube video URL"})
        resp.headers.update(_CORS_HEADERS)
        return resp, 400

    video_id = m.group(1)
    existing = _db.get_video_by_id(g.db, video_id)
    if existing and existing.get("fetch_status") == FetchStatus.OK:
        if existing.get("is_hidden"):
            resp = jsonify({"status": "hidden", "title": existing.get("title")})
            resp.headers.update(_CORS_HEADERS)
            return resp
        _db.record_visit(g.db, video_id)
        resp = jsonify({"status": "exists", "title": existing.get("title")})
        resp.headers.update(_CORS_HEADERS)
        return resp

    from crawler.metadata_fetcher import fetch_metadata
    meta = fetch_metadata(video_id, delay=0)
    _db.add_video(
        g.db,
        video_id=meta.video_id,
        url=meta.url,
        title=meta.title,
        description=meta.description,
        channel_name=meta.channel_name,
        channel_id=meta.channel_id,
        yt_view_count=meta.yt_view_count,
        duration_seconds=meta.duration_seconds,
        thumbnail_url=meta.thumbnail_url,
        date_published=meta.date_published.isoformat() if meta.date_published else None,
        fetch_status=meta.fetch_status,
        fetch_error=meta.fetch_error,
        yt_tags=[*meta.yt_categories, *meta.yt_tags],
    )

    if meta.fetch_status != FetchStatus.OK:
        resp = jsonify({"status": "error", "error": meta.fetch_error or "fetch failed"})
        resp.headers.update(_CORS_HEADERS)
        return resp, 200

    video_row = _db.get_video_by_id(g.db, video_id)
    if video_row:
        _db.retroactive_apply(g.db, video_id=video_row["id"])
    _db.record_visit(g.db, video_id)
    resp = jsonify({"status": "added", "title": meta.title})
    resp.headers.update(_CORS_HEADERS)
    return resp


@bp.route("/install")
def install():
    return render_template("install.html")


@bp.route("/tags", methods=["GET", "POST"])
def tags():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name:
            _db.create_canonical_tag(g.db, name)
        return redirect(url_for("main.tags"))
    canonical = _db.get_canonical_tags(g.db)
    tag_groups = _db.get_tag_groups(g.db)
    grouped_ids = {m["id"] for grp in tag_groups for m in grp["members"]}
    ungrouped_count = sum(1 for t in canonical if t["id"] not in grouped_ids)
    unclassified, total_unclassified = _db.get_unclassified_tags(g.db)
    pool_hash = _llm.compute_pool_hash(unclassified)
    llm_stale = _db.is_llm_suggestion_cache_stale(g.db, pool_hash)
    llm_suggestions = _db.get_llm_suggestions(g.db)
    return render_template(
        "tags.html",
        canonical_tags=canonical,
        tag_groups=tag_groups,
        ungrouped_count=ungrouped_count,
        unclassified_tags=unclassified,
        total_unclassified=total_unclassified,
        llm_available=_llm.is_available(),
        llm_stale=llm_stale,
        llm_suggestions=llm_suggestions,
        llm_error=request.args.get("llm_error"),
        assigned_groups=request.args.get("assigned_groups", type=int),
    )


@bp.route("/watch-later")
def watch_later():
    queue = _db.get_watch_later_queue(g.db)
    return render_template(
        "watch-later.html",
        queue=queue,
        queue_count=len(queue),
    )


@bp.route("/tags/<int:tag_id>/alias", methods=["POST"])
def tag_add_alias(tag_id):
    pattern = request.form.get("pattern", "").strip()
    match_type = request.form.get("match_type", "exact")
    if pattern and match_type in MatchType:
        _db.add_alias_and_apply(g.db, tag_id, pattern, match_type)
    return redirect(url_for("main.tags"))


@bp.route("/tags/<int:tag_id>/alias/<int:alias_id>/delete", methods=["POST"])
def tag_delete_alias(tag_id, alias_id):
    _db.delete_alias_with_cleanup(g.db, alias_id)
    return redirect(url_for("main.tags"))


@bp.route("/tags/<int:tag_id>/alias/<int:alias_id>/edit", methods=["POST"])
def tag_edit_alias(tag_id, alias_id):
    pattern = request.form.get("pattern", "").strip()
    match_type = request.form.get("match_type", "exact")
    if pattern and match_type in MatchType:
        _db.edit_alias_and_apply(g.db, alias_id, pattern, match_type)
    return redirect(url_for("main.tags"))


@bp.route("/tags/noise", methods=["POST"])
def tag_mark_noise():
    tag_name = request.form.get("tag_name", "").strip()
    if tag_name:
        _db.mark_tag_noise(g.db, tag_name)
    return redirect(url_for("main.tags"))


@bp.route("/tags/pool-videos")
def tag_pool_videos():
    tag_name = request.args.get("tag", "").strip()
    if not tag_name:
        return jsonify([])
    titles = _db.get_video_titles_for_tag(g.db, tag_name)
    return jsonify(titles)


@bp.route("/tags/related")
def tag_related():
    tag_name = request.args.get("tag", "").strip()
    if not tag_name:
        return jsonify([])
    related = _db.get_related_unclassified_tags(g.db, tag_name)
    return jsonify(related)


@bp.route("/tags/groups", methods=["POST"])
def tag_group_create():
    name = request.form.get("name", "").strip()
    if name:
        _db.create_tag_group(g.db, name)
    return redirect(url_for("main.tags"))


@bp.route("/tags/groups/<int:group_id>/delete", methods=["POST"])
def tag_group_delete(group_id):
    _db.delete_tag_group(g.db, group_id)
    return redirect(url_for("main.tags"))


@bp.route("/tags/groups/<int:group_id>/members", methods=["POST"])
def tag_group_add_member(group_id):
    canonical_tag_id = request.form.get("canonical_tag_id", type=int)
    if canonical_tag_id:
        _db.add_canonical_to_group(g.db, group_id, canonical_tag_id)
    return redirect(url_for("main.tags"))


@bp.route("/tags/groups/<int:group_id>/members/<int:tag_id>/delete", methods=["POST"])
def tag_group_remove_member(group_id, tag_id):
    _db.remove_canonical_from_group(g.db, group_id, tag_id)
    return redirect(url_for("main.tags"))


@bp.route("/tags/groups/auto-assign", methods=["POST"])
def tag_groups_auto_assign():
    ungrouped = _db.get_ungrouped_canonicals(g.db)
    if not ungrouped:
        return redirect(url_for("main.tags"))
    groups = _db.get_tag_groups(g.db)
    try:
        assignments = _llm.suggest_group_assignments(ungrouped, groups)
    except EnvironmentError as e:
        return redirect(url_for("main.tags", llm_error=str(e)))
    except ImportError:
        return redirect(url_for("main.tags", llm_error="anthropic package not installed"))
    except Exception as e:
        return redirect(url_for("main.tags", llm_error=f"Auto-assign failed: {e}"))
    for item in assignments:
        _db.add_canonical_to_group(g.db, item["group_id"], item["canonical_id"])
    return redirect(url_for("main.tags", assigned_groups=len(assignments)))


@bp.route("/tags/retroactive", methods=["POST"])
def tags_retroactive():
    count = _db.retroactive_apply(g.db)
    return redirect(url_for("main.tags", applied=count))


@bp.route("/tags/suggest/confirm", methods=["POST"])
def tag_suggest_confirm():
    canonical_name = request.form.get("canonical_name", "").strip()
    members = [m for m in request.form.getlist("member") if m.strip()]
    suggestion_id = request.form.get("suggestion_id", type=int)
    if canonical_name and members:
        if suggestion_id:
            # Confirming from a Smart Suggest — also dismiss the suggestion
            suggestion = _db.get_llm_suggestion_by_id(g.db, suggestion_id)
            all_members = suggestion["members"] if suggestion else members
            _db.confirm_and_dismiss_suggestion(g.db, canonical_name, members, suggestion_id, all_members)
        else:
            # Manual assignment — just create the aliases without a suggestion to dismiss
            _db.confirm_and_dismiss_suggestion(g.db, canonical_name, members, None, members)
    elif suggestion_id:
        _db.dismiss_llm_suggestion(g.db, suggestion_id)
    return redirect(url_for("main.tags"))


@bp.route("/tags/llm-suggest", methods=["POST"])
def tags_llm_suggest():
    canonical = _db.get_canonical_tags(g.db)
    unclassified, _ = _db.get_unclassified_tags(g.db)
    pool_hash = _llm.compute_pool_hash(unclassified)
    try:
        suggestions = _llm.get_suggestions(canonical, unclassified)
    except EnvironmentError as e:
        return redirect(url_for("main.tags", llm_error=str(e)))
    except ImportError:
        return redirect(url_for("main.tags", llm_error="anthropic package not installed"))
    except Exception as e:
        return redirect(url_for("main.tags", llm_error=f"LLM error: {e}"))
    _db.save_llm_suggestions(g.db, suggestions, pool_hash)
    return redirect(url_for("main.tags"))


@bp.route("/tags/llm-suggest/<int:suggestion_id>/dismiss", methods=["POST"])
def tags_llm_suggest_dismiss(suggestion_id):
    _db.dismiss_llm_suggestion(g.db, suggestion_id)
    return redirect(url_for("main.tags"))


@bp.route("/tags/llm-suggest/<int:suggestion_id>/accept-noise", methods=["POST"])
def tags_llm_suggest_accept_noise(suggestion_id):
    members = [m.strip() for m in request.form.getlist("member") if m.strip()]
    suggestion = _db.get_llm_suggestion_by_id(g.db, suggestion_id)
    all_members = suggestion["members"] if suggestion else []
    rejected = [m for m in all_members if m not in set(members)]
    _db.accept_noise_and_dismiss_suggestion(g.db, suggestion_id, members, rejected)
    return redirect(url_for("main.tags"))


@bp.route("/videos/<video_id>/favourite", methods=["POST"])
def video_toggle_favourite(video_id):
    video = _db.get_video_by_id(g.db, video_id)
    if not video:
        abort(404)
    new_value = not video.get("is_favourite")
    _db.set_favourite(g.db, video_id, new_value)
    return jsonify({"is_favourite": new_value})


@bp.route("/videos/<video_id>/mark-watched", methods=["POST"])
def video_mark_watched(video_id):
    video = _db.get_video_by_id(g.db, video_id)
    if not video:
        abort(404)
    _db.record_visit(g.db, video_id)
    return "", 204


@bp.route("/videos/<video_id>/rediscover-shelf/remove", methods=["POST"])
def video_remove_from_rediscover_shelf(video_id):
    video = _db.get_video_by_id(g.db, video_id)
    if not video:
        abort(404)
    _db.remove_from_rediscover_shelf(g.db, video_id)
    return "", 204


@bp.route("/videos/<video_id>/hide", methods=["POST"])
def video_hide(video_id):
    _db.hide_video(g.db, video_id)
    return "", 204


@bp.route("/videos/<video_id>/unhide", methods=["POST"])
def video_unhide(video_id):
    _db.unhide_video(g.db, video_id)
    return redirect(url_for("main.hidden"))


@bp.route("/videos/<video_id>/watch-later/reorder", methods=["POST"])
def watch_later_reorder(video_id):
    data = request.get_json(silent=True) or {}
    position = data.get("position")
    if not isinstance(position, int):
        abort(400)
    moved = _db.reorder_watch_later(g.db, video_id, position)
    if not moved:
        abort(404)
    return "", 204


@bp.route("/videos/<video_id>/delete", methods=["POST"])
def video_delete(video_id):
    _db.delete_video(g.db, video_id)
    return redirect(url_for("main.hidden"))


@bp.route("/hidden")
def hidden():
    sort_by = request.args.get("sort_by", "date_added")
    sort_dir = request.args.get("sort_dir", "desc")
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    total = _db.count_hidden_videos(g.db)
    try:
        videos = _db.get_hidden_videos(g.db, sort_by=sort_by, sort_dir=sort_dir, page=page, page_size=PAGE_SIZE)
    except ValueError:
        abort(400)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(page, total_pages)

    def page_url(p):
        args = {k: v for k, v in request.args.to_dict().items() if k != "page"}
        args["page"] = p
        return url_for("main.hidden", **args)

    return render_template(
        "hidden.html",
        videos=videos,
        total=total,
        page=page,
        total_pages=total_pages,
        sort_by=sort_by,
        sort_dir=sort_dir,
        prev_url=page_url(page - 1) if page > 1 else None,
        next_url=page_url(page + 1) if page < total_pages else None,
    )


@bp.route("/api/status", methods=["GET", "OPTIONS"])
def api_status():
    if request.method == "OPTIONS":
        return make_response("", 204, _CORS_HEADERS)
    url = (request.args.get("url") or "").strip()
    m = _YT_ID_RE.search(url)
    if not m:
        resp = jsonify({"status": "error", "error": "Not a YouTube URL"})
        resp.headers.update(_CORS_HEADERS)
        return resp, 400
    video_id = m.group(1)
    video = _db.get_video_by_id(g.db, video_id)
    if video is None:
        resp = jsonify({"status": "not_found"})
        resp.headers.update(_CORS_HEADERS)
        return resp
    status = "hidden" if video.get("is_hidden") else "exists"
    resp = jsonify({"status": status, "video_id": video_id, "title": video.get("title")})
    resp.headers.update(_CORS_HEADERS)
    return resp


@bp.route("/api/status/batch", methods=["POST", "OPTIONS"])
def api_status_batch():
    if request.method == "OPTIONS":
        return make_response("", 204, _CORS_HEADERS)
    data = request.get_json(silent=True) or {}
    raw_ids = data.get("ids") or []
    ids = [v.strip() for v in raw_ids if isinstance(v, str) and v.strip()][:50]
    found = _db.get_videos_status_batch(g.db, ids)
    result = {vid: found.get(vid, "not_found") for vid in ids}
    resp = jsonify(result)
    resp.headers.update(_CORS_HEADERS)
    return resp


@bp.route("/api/hide", methods=["POST", "OPTIONS"])
def api_hide():
    if request.method == "OPTIONS":
        return make_response("", 204, _CORS_HEADERS)
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    m = _YT_ID_RE.search(url)
    if not m:
        resp = jsonify({"status": "error", "error": "Not a YouTube URL"})
        resp.headers.update(_CORS_HEADERS)
        return resp, 400
    video_id = m.group(1)
    video = _db.get_video_by_id(g.db, video_id)
    if not video:
        resp = jsonify({"status": "error", "error": "Video not found"})
        resp.headers.update(_CORS_HEADERS)
        return resp, 404
    _db.hide_video(g.db, video_id)
    resp = jsonify({"status": "hidden", "title": video.get("title")})
    resp.headers.update(_CORS_HEADERS)
    return resp


@bp.route("/rediscover-shelf/refresh", methods=["POST"])
def rediscover_shelf_refresh():
    shelf = _db.refresh_rediscover_shelf(g.db)
    return render_template("_shelf_cards.html", shelf=shelf)


@bp.route("/api/watch-later/add", methods=["POST", "OPTIONS"])
def api_watch_later_add():
    if request.method == "OPTIONS":
        return make_response("", 204, _CORS_HEADERS)

    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    m = _YT_ID_RE.search(url)
    if not m:
        resp = jsonify({"status": "error", "error": "Not a YouTube URL"})
        resp.headers.update(_CORS_HEADERS)
        return resp, 400

    video_id = m.group(1)
    video = _db.get_video_by_id(g.db, video_id)
    if not video:
        resp = jsonify({"status": "error", "error": "Video not found"})
        resp.headers.update(_CORS_HEADERS)
        return resp, 404

    added = _db.add_to_watch_later(g.db, video_id)
    if not added:
        resp = jsonify({"status": "already_in_queue"})
        resp.headers.update(_CORS_HEADERS)
        return resp, 409

    resp = jsonify({"status": "added"})
    resp.headers.update(_CORS_HEADERS)
    return resp


@bp.route("/api/watch-later/remove", methods=["POST", "OPTIONS"])
def api_watch_later_remove():
    if request.method == "OPTIONS":
        return make_response("", 204, _CORS_HEADERS)

    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    m = _YT_ID_RE.search(url)
    if not m:
        resp = jsonify({"status": "error", "error": "Not a YouTube URL"})
        resp.headers.update(_CORS_HEADERS)
        return resp, 400

    video_id = m.group(1)
    video = _db.get_video_by_id(g.db, video_id)
    if not video:
        resp = jsonify({"status": "error", "error": "Video not found"})
        resp.headers.update(_CORS_HEADERS)
        return resp, 404

    removed = _db.remove_from_watch_later(g.db, video_id)
    if not removed:
        resp = jsonify({"status": "error", "error": "Not in queue"})
        resp.headers.update(_CORS_HEADERS)
        return resp, 404

    resp = jsonify({"status": "removed"})
    resp.headers.update(_CORS_HEADERS)
    return resp


@bp.route("/api/watch-later/status", methods=["POST", "OPTIONS"])
def api_watch_later_status():
    if request.method == "OPTIONS":
        return make_response("", 204, _CORS_HEADERS)

    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    m = _YT_ID_RE.search(url)
    if not m:
        resp = jsonify({"status": "error", "error": "Not a YouTube URL"})
        resp.headers.update(_CORS_HEADERS)
        return resp, 400

    video_id = m.group(1)
    video = _db.get_video_by_id(g.db, video_id)
    if not video:
        resp = jsonify({"status": "error", "error": "Video not found"})
        resp.headers.update(_CORS_HEADERS)
        return resp, 404

    in_queue = _db.is_in_watch_later(g.db, video_id)
    resp = jsonify({"in_queue": in_queue})
    resp.headers.update(_CORS_HEADERS)
    return resp



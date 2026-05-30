import math
from flask import Blueprint, g, request, redirect, abort, render_template, url_for, jsonify, make_response
from webapp import db as _db
from crawler.models import _YT_ID_RE

bp = Blueprint("main", __name__)

PAGE_SIZE = 100


@bp.route("/")
def index():
    sort_by = request.args.get("sort_by", "date_added")
    sort_dir = request.args.get("sort_dir", "desc")
    channel = request.args.get("channel") or None
    tag = request.args.get("tag") or None
    search = request.args.get("search") or None
    group = request.args.get("group") or None
    append = request.args.get("append") == "1"
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    try:
        total = _db.count_videos(g.db, channel=channel, tag=tag, search=search)
        videos = _db.get_all_videos(
            g.db, sort_by=sort_by, sort_dir=sort_dir,
            channel=channel, tag=tag, search=search,
            page=page, page_size=PAGE_SIZE,
            group=group,
        )
    except ValueError:
        abort(400)

    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(page, total_pages)

    def page_url(p):
        args = {k: v for k, v in request.args.to_dict().items() if k not in ("page", "append")}
        args["page"] = p
        return url_for("main.index", **args)

    channels = _db.get_all_channels(g.db)
    canonical_tags = _db.get_canonical_tags_for_filter(g.db)

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

    return render_template("index.html", **template_vars)


@bp.route("/visit/<video_id>")
def visit(video_id):
    row = _db.get_video_by_id(g.db, video_id)
    if row is None:
        abort(404)
    _db.record_visit(g.db, video_id)
    return redirect(row["url"])


@bp.route("/api/add", methods=["POST", "OPTIONS"])
def api_add():
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST",
        "Access-Control-Allow-Headers": "Content-Type",
    }
    if request.method == "OPTIONS":
        return make_response("", 204, cors_headers)

    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()

    m = _YT_ID_RE.search(url)
    if not m:
        resp = jsonify({"status": "error", "error": "Not a YouTube video URL"})
        resp.headers.update(cors_headers)
        return resp, 400

    video_id = m.group(1)
    existing = _db.get_video_by_id(g.db, video_id)
    if existing and existing.get("fetch_status") == "ok":
        _db.record_visit(g.db, video_id)
        resp = jsonify({"status": "exists", "title": existing.get("title")})
        resp.headers.update(cors_headers)
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

    if meta.fetch_status != "ok":
        resp = jsonify({"status": "error", "error": meta.fetch_error or "fetch failed"})
        resp.headers.update(cors_headers)
        return resp, 200

    _db.record_visit(g.db, video_id)
    resp = jsonify({"status": "added", "title": meta.title})
    resp.headers.update(cors_headers)
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
    unclassified, total_unclassified = _db.get_unclassified_tags(g.db)
    return render_template("tags.html", canonical_tags=canonical,
                           unclassified_tags=unclassified, total_unclassified=total_unclassified)


@bp.route("/tags/<int:tag_id>/alias", methods=["POST"])
def tag_add_alias(tag_id):
    pattern = request.form.get("pattern", "").strip()
    match_type = request.form.get("match_type", "exact")
    if pattern and match_type in ("exact", "prefix", "contains"):
        alias_id = _db.add_alias(g.db, tag_id, pattern, match_type)
        _db.retroactive_apply(g.db, alias_id)
    return redirect(url_for("main.tags"))


@bp.route("/tags/<int:tag_id>/alias/<int:alias_id>/delete", methods=["POST"])
def tag_delete_alias(tag_id, alias_id):
    _db.delete_alias(g.db, alias_id)
    return redirect(url_for("main.tags"))


@bp.route("/tags/retroactive", methods=["POST"])
def tags_retroactive():
    count = _db.retroactive_apply(g.db)
    return redirect(url_for("main.tags", applied=count))


@bp.route("/tags/suggest/confirm", methods=["POST"])
def tag_suggest_confirm():
    canonical_name = request.form.get("canonical_name", "").strip()
    members = [m for m in request.form.getlist("member") if m.strip()]
    if canonical_name and members:
        _db.confirm_suggestion(g.db, canonical_name, members)
    return redirect(url_for("main.tags"))



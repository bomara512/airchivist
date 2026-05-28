import math
from flask import Blueprint, g, request, redirect, abort, render_template, url_for
from webapp import db as _db

bp = Blueprint("main", __name__)

PAGE_SIZE = 20


@bp.route("/")
def index():
    sort_by = request.args.get("sort_by", "date_added")
    sort_dir = request.args.get("sort_dir", "desc")
    channel = request.args.get("channel") or None
    tag = request.args.get("tag") or None
    search = request.args.get("search") or None
    group = request.args.get("group") or None
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
        )
    except ValueError:
        abort(400)

    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(page, total_pages)

    def page_url(p):
        args = {**request.args.to_dict(), "page": p}
        return url_for("main.index", **args)

    channels = _db.get_all_channels(g.db)
    stats = _db.get_stats(g.db)

    groups = None
    if group == "channel":
        grouped = {}
        for video in videos:
            ch = video.get("channel_name") or "Unknown"
            grouped.setdefault(ch, []).append(video)
        groups = [{"tag": {"name": ch}, "videos": vids} for ch, vids in grouped.items()]

    template_vars = dict(
        videos=videos,
        channels=channels,
        stats=stats,
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
        return render_template("_video_container.html", **template_vars)

    return render_template("index.html", **template_vars)


@bp.route("/visit/<video_id>")
def visit(video_id):
    row = _db.get_video_by_id(g.db, video_id)
    if row is None:
        abort(404)
    _db.record_visit(g.db, video_id)
    return redirect(row["url"])



from flask import Blueprint, g, request, redirect, abort, render_template, url_for
from webapp import db as _db
from webapp.keyword_matcher import group_videos_by_tags

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    sort_by = request.args.get("sort_by", "date_added")
    sort_dir = request.args.get("sort_dir", "desc")
    channel = request.args.get("channel") or None
    tag = request.args.get("tag") or None
    search = request.args.get("search") or None
    group = request.args.get("group") or None

    try:
        videos = _db.get_all_videos(
            g.db, sort_by=sort_by, sort_dir=sort_dir,
            channel=channel, tag=tag, search=search,
        )
    except ValueError:
        abort(400)

    channels = _db.get_all_channels(g.db)
    tags = _db.get_all_tags(g.db)
    stats = _db.get_stats(g.db)

    groups = None
    if group == "keywords":
        tags_with_kw = _db.get_tags_with_keywords(g.db)
        groups = group_videos_by_tags(videos, tags_with_kw)

    template_vars = dict(
        videos=videos,
        channels=channels,
        tags=tags,
        stats=stats,
        groups=groups,
        sort_by=sort_by,
        sort_dir=sort_dir,
        current_channel=channel,
        current_tag=tag,
        current_search=search,
        group=group,
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


@bp.route("/tags", methods=["GET", "POST"])
def tags():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            abort(400)
        _db.create_tag(g.db, name)
        return redirect(url_for("main.tags"))

    all_tags = _db.get_tags_with_keywords(g.db)
    return render_template("tags.html", tags=all_tags)


@bp.route("/tags/<int:tag_id>")
def tag_detail(tag_id):
    tags_with_kw = _db.get_tags_with_keywords(g.db)
    tag = next((t for t in tags_with_kw if t["id"] == tag_id), None)
    if tag is None:
        abort(404)
    return render_template("tag_detail.html", tag=tag)


@bp.route("/tags/<int:tag_id>/keywords", methods=["POST"])
def set_tag_keywords(tag_id):
    tags_with_kw = _db.get_tags_with_keywords(g.db)
    if not any(t["id"] == tag_id for t in tags_with_kw):
        abort(404)
    raw = request.form.get("keywords") or ""
    keywords = [k.strip() for k in raw.splitlines() if k.strip()]
    _db.set_tag_keywords(g.db, tag_id, keywords)
    return redirect(url_for("main.tag_detail", tag_id=tag_id))


@bp.route("/tags/<int:tag_id>/delete", methods=["POST"])
def delete_tag(tag_id):
    _db.delete_tag(g.db, tag_id)
    return redirect(url_for("main.tags"))


@bp.route("/videos/<video_id>/tags", methods=["POST"])
def add_video_tag(video_id):
    row = _db.get_video_by_id(g.db, video_id)
    if row is None:
        abort(404)
    tag_id = request.form.get("tag_id")
    if tag_id:
        _db.add_video_tag(g.db, video_id, int(tag_id))
    return redirect(url_for("main.index"))


@bp.route("/videos/<video_id>/tags/<int:tag_id>/delete", methods=["POST"])
def remove_video_tag(video_id, tag_id):
    row = _db.get_video_by_id(g.db, video_id)
    if row is None:
        abort(404)
    _db.remove_video_tag(g.db, video_id, tag_id)
    return redirect(url_for("main.index"))

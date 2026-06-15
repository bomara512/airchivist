import json
import random
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from crawler.datastore import apply_aliases
from crawler.models import FetchStatus

ALLOWED_SORT_COLUMNS = frozenset({
    'title', 'channel_name', 'yt_view_count', 'personal_view_count',
    'date_added', 'date_last_viewed', 'date_published',
})
ALLOWED_SORT_DIRS = frozenset({'asc', 'desc'})


def _build_where(channel, tag, search):
    params = []
    clauses = ["v.fetch_status = 'ok'", "v.is_hidden = 0"]
    if channel:
        clauses.append("v.channel_name = ?")
        params.append(channel)
    if tag:
        clauses.append(
            "v.id IN (SELECT vt.video_id_fk FROM video_tags vt "
            "JOIN tags t ON t.id = vt.tag_id_fk WHERE t.name = ?)"
        )
        params.append(tag)
    if search:
        pattern = r'\b' + re.escape(search)
        clauses.append(
            "(REGEXP(?, v.title) OR REGEXP(?, v.description)"
            " OR v.id IN (SELECT vt.video_id_fk FROM video_tags vt"
            "             JOIN tags t ON t.id = vt.tag_id_fk WHERE REGEXP(?, t.name))"
            " OR v.id IN (SELECT vt.video_id_fk FROM video_tags vt"
            "             JOIN tag_keywords tk ON tk.tag_id = vt.tag_id_fk WHERE REGEXP(?, tk.keyword)))"
        )
        params.extend([pattern, pattern, pattern, pattern])
    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where_sql, params


def get_all_videos(
    conn: sqlite3.Connection,
    sort_by: str = 'date_added',
    sort_dir: str = 'desc',
    channel: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: Optional[int] = None,
    group: Optional[str] = None,
) -> list:
    if sort_by not in ALLOWED_SORT_COLUMNS:
        raise ValueError(f"Invalid sort_by: {sort_by!r}")
    if sort_dir not in ALLOWED_SORT_DIRS:
        raise ValueError(f"Invalid sort_dir: {sort_dir!r}")

    where_sql, params = _build_where(channel, tag, search)

    limit_sql = ""
    if page_size is not None:
        limit_sql = "LIMIT ? OFFSET ?"
        params = params + [page_size, (page - 1) * page_size]

    order_sql = f"v.{sort_by} {sort_dir}"
    if group == "channel":
        order_sql = f"v.channel_name ASC, {order_sql}"

    sql = f"""
        SELECT v.*, GROUP_CONCAT(CASE WHEN t.is_canonical = 1 THEN t.name ELSE NULL END) as tags
        FROM videos v
        LEFT JOIN video_tags vt ON vt.video_id_fk = v.id
        LEFT JOIN tags t ON t.id = vt.tag_id_fk
        {where_sql}
        GROUP BY v.id
        ORDER BY {order_sql}
        {limit_sql}
    """
    rows = conn.execute(sql, params).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        if d.get("tags") is None:
            d["tags"] = ""
        result.append(d)
    return result


def count_videos(
    conn: sqlite3.Connection,
    channel: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
) -> int:
    where_sql, params = _build_where(channel, tag, search)
    sql = f"""
        SELECT COUNT(DISTINCT v.id)
        FROM videos v
        {where_sql}
    """
    return conn.execute(sql, params).fetchone()[0]


def get_videos_status_batch(conn: sqlite3.Connection, video_ids: list[str]) -> dict[str, str]:
    """Return {video_id: 'exists'|'hidden'} for IDs present in the DB. Missing IDs are omitted."""
    if not video_ids:
        return {}
    ph = ",".join("?" * len(video_ids))
    rows = conn.execute(
        f"SELECT video_id, is_hidden FROM videos WHERE video_id IN ({ph})",
        video_ids,
    ).fetchall()
    return {r["video_id"]: ("hidden" if r["is_hidden"] else "exists") for r in rows}


def get_video_by_id(conn: sqlite3.Connection, video_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM videos WHERE video_id = ?", (video_id,)
    ).fetchone()
    return dict(row) if row else None


def get_all_channels(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT channel_name FROM videos WHERE channel_name IS NOT NULL ORDER BY channel_name"
    ).fetchall()
    return [r[0] for r in rows]


def get_stats(conn: sqlite3.Connection) -> dict:
    total_videos = conn.execute(
        "SELECT COUNT(*) FROM videos WHERE fetch_status = 'ok' AND is_hidden = 0"
    ).fetchone()[0]
    total_channels = conn.execute(
        "SELECT COUNT(DISTINCT channel_name) FROM videos "
        "WHERE channel_name IS NOT NULL AND fetch_status = 'ok' AND is_hidden = 0"
    ).fetchone()[0]
    fetch_errors = conn.execute(
        "SELECT COUNT(*) FROM videos WHERE fetch_status = 'error'"
    ).fetchone()[0]
    hidden_count = conn.execute(
        "SELECT COUNT(*) FROM videos WHERE is_hidden = 1"
    ).fetchone()[0]
    return {
        "total_videos": total_videos,
        "total_channels": total_channels,
        "fetch_errors": fetch_errors,
        "hidden_count": hidden_count,
    }


def record_visit(conn: sqlite3.Connection, video_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE videos SET personal_view_count = personal_view_count + 1, "
        "date_last_viewed = ? WHERE video_id = ?",
        (now, video_id),
    )
    conn.commit()


def add_video(
    conn: sqlite3.Connection,
    video_id: str,
    url: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    channel_name: Optional[str] = None,
    channel_id: Optional[str] = None,
    yt_view_count: Optional[int] = None,
    duration_seconds: Optional[int] = None,
    thumbnail_url: Optional[str] = None,
    date_published: Optional[str] = None,
    fetch_status: str = FetchStatus.OK,
    fetch_error: Optional[str] = None,
    yt_tags: Optional[list] = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO videos (
            video_id, url, title, description, channel_name, channel_id,
            yt_view_count, duration_seconds, thumbnail_url, date_published,
            fetch_status, fetch_error, date_added
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(video_id) DO UPDATE SET
            url              = excluded.url,
            title            = excluded.title,
            description      = excluded.description,
            channel_name     = excluded.channel_name,
            channel_id       = excluded.channel_id,
            yt_view_count    = excluded.yt_view_count,
            duration_seconds = excluded.duration_seconds,
            thumbnail_url    = excluded.thumbnail_url,
            date_published   = excluded.date_published,
            fetch_status     = excluded.fetch_status,
            fetch_error      = excluded.fetch_error
    """, (
        video_id, url, title, description, channel_name, channel_id,
        yt_view_count, duration_seconds, thumbnail_url, date_published,
        fetch_status, fetch_error, now,
    ))
    conn.commit()

    video_row = conn.execute("SELECT id FROM videos WHERE video_id = ?", (video_id,)).fetchone()
    if video_row and yt_tags:
        for name in yt_tags:
            name = name.strip().lower()
            if not name:
                continue
            conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
            tag_row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
            conn.execute(
                "INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk) VALUES (?, ?)",
                (video_row[0], tag_row[0]),
            )
        conn.commit()

    apply_aliases(conn, video_id)


def hide_video(conn: sqlite3.Connection, video_id: str) -> None:
    conn.execute("UPDATE videos SET is_hidden = 1 WHERE video_id = ?", (video_id,))
    conn.commit()


def unhide_video(conn: sqlite3.Connection, video_id: str) -> None:
    conn.execute("UPDATE videos SET is_hidden = 0 WHERE video_id = ?", (video_id,))
    conn.commit()


def delete_video(conn: sqlite3.Connection, video_id: str) -> None:
    conn.execute("DELETE FROM videos WHERE video_id = ?", (video_id,))
    conn.commit()


def get_hidden_videos(
    conn: sqlite3.Connection,
    sort_by: str = 'date_added',
    sort_dir: str = 'desc',
    page: int = 1,
    page_size: Optional[int] = None,
) -> list:
    if sort_by not in ALLOWED_SORT_COLUMNS:
        raise ValueError(f"Invalid sort_by: {sort_by!r}")
    if sort_dir not in ALLOWED_SORT_DIRS:
        raise ValueError(f"Invalid sort_dir: {sort_dir!r}")
    limit_sql = ""
    params: list = []
    if page_size is not None:
        limit_sql = "LIMIT ? OFFSET ?"
        params = [page_size, (page - 1) * page_size]
    sql = f"""
        SELECT v.*, GROUP_CONCAT(CASE WHEN t.is_canonical = 1 THEN t.name ELSE NULL END) as tags
        FROM videos v
        LEFT JOIN video_tags vt ON vt.video_id_fk = v.id
        LEFT JOIN tags t ON t.id = vt.tag_id_fk
        WHERE v.is_hidden = 1
        GROUP BY v.id
        ORDER BY v.{sort_by} {sort_dir}
        {limit_sql}
    """
    rows = conn.execute(sql, params).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        if d.get("tags") is None:
            d["tags"] = ""
        result.append(d)
    return result


def count_hidden_videos(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM videos WHERE is_hidden = 1").fetchone()[0]


def generate_rediscover_shelf(conn: sqlite3.Connection) -> dict:
    """Generate a new rediscover shelf: 20 random from least-recently-viewed pool.

    Prioritizes unwatched (personal_view_count = 0), then falls back to oldest-viewed.
    Returns dict with video_ids, reasons, generated_at, expires_at.
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=7)

    # Fetch unwatched videos
    unwatched = conn.execute("""
        SELECT id, video_id, title, channel_name, personal_view_count, date_last_viewed
        FROM videos
        WHERE personal_view_count = 0
        ORDER BY date_added ASC
    """).fetchall()

    # Fetch oldest-viewed videos
    viewed = conn.execute("""
        SELECT id, video_id, title, channel_name, personal_view_count, date_last_viewed
        FROM videos
        WHERE personal_view_count > 0
        ORDER BY date_last_viewed ASC
    """).fetchall()

    # Combine pools: unwatched first, then viewed
    pool = [dict(r) for r in unwatched] + [dict(r) for r in viewed]

    if not pool:
        # Empty library — store empty shelf
        conn.execute(
            "DELETE FROM rediscover_shelf"
        )
        conn.execute(
            "INSERT INTO rediscover_shelf (generated_at, expires_at, pool, video_ids) VALUES (?, ?, ?, ?)",
            (now.isoformat(), expires_at.isoformat(), "[]", "[]"),
        )
        conn.commit()
        return {"video_ids": [], "reasons": {}, "generated_at": now.isoformat(), "expires_at": expires_at.isoformat()}

    # Select 20 random from the pool
    selected = random.sample(pool, min(20, len(pool)))
    video_ids = [v["video_id"] for v in selected]
    pool_ids = [v["video_id"] for v in pool]

    # Compute reasons for each video
    reasons = {}
    for video in selected:
        if video["personal_view_count"] == 0:
            reasons[video["video_id"]] = "Never watched"
        else:
            last_viewed = datetime.fromisoformat(video["date_last_viewed"])
            days_ago = (now - last_viewed).days
            if days_ago == 0:
                reasons[video["video_id"]] = "Last viewed today"
            elif days_ago == 1:
                reasons[video["video_id"]] = "Last viewed 1 day ago"
            else:
                reasons[video["video_id"]] = f"Last viewed {days_ago} days ago"

    # Store in DB
    conn.execute("DELETE FROM rediscover_shelf")
    conn.execute(
        "INSERT INTO rediscover_shelf (generated_at, expires_at, pool, video_ids) VALUES (?, ?, ?, ?)",
        (now.isoformat(), expires_at.isoformat(), json.dumps(pool_ids), json.dumps(video_ids)),
    )
    conn.commit()

    return {
        "video_ids": video_ids,
        "reasons": reasons,
        "generated_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }


def get_current_rediscover_shelf(conn: sqlite3.Connection) -> Optional[dict]:
    """Fetch active rediscover shelf if not expired; regenerate if expired or missing."""
    shelf = conn.execute(
        "SELECT video_ids, generated_at, expires_at FROM rediscover_shelf ORDER BY generated_at DESC LIMIT 1"
    ).fetchone()

    if not shelf:
        return generate_rediscover_shelf(conn)

    video_ids = json.loads(shelf["video_ids"])
    expires_at = datetime.fromisoformat(shelf["expires_at"])
    now = datetime.now(timezone.utc)

    if now >= expires_at:
        return generate_rediscover_shelf(conn)

    # Fetch full video data for each ID
    if not video_ids:
        return {
            "videos": [],
            "generated_at": shelf["generated_at"],
            "expires_at": shelf["expires_at"],
        }

    placeholders = ",".join("?" * len(video_ids))
    videos = conn.execute(f"""
        SELECT id, video_id, title, channel_name, thumbnail_url, personal_view_count, date_last_viewed
        FROM videos
        WHERE video_id IN ({placeholders})
    """, video_ids).fetchall()

    # Compute reasons for each video
    reasons = {}
    for video in videos:
        if video["personal_view_count"] == 0:
            reasons[video["video_id"]] = "Never watched"
        else:
            last_viewed = datetime.fromisoformat(video["date_last_viewed"])
            days_ago = (now - last_viewed).days
            if days_ago == 0:
                reasons[video["video_id"]] = "Last viewed today"
            elif days_ago == 1:
                reasons[video["video_id"]] = "Last viewed 1 day ago"
            else:
                reasons[video["video_id"]] = f"Last viewed {days_ago} days ago"

    # Return in the order of video_ids (to preserve order from shelf generation)
    video_dict = {v["video_id"]: dict(v) for v in videos}
    ordered_videos = [video_dict[vid] for vid in video_ids if vid in video_dict]

    return {
        "videos": ordered_videos,
        "reasons": reasons,
        "generated_at": shelf["generated_at"],
        "expires_at": shelf["expires_at"],
    }


def is_rediscover_shelf_expired(conn: sqlite3.Connection) -> bool:
    """Check if current shelf has passed expires_at."""
    shelf = conn.execute(
        "SELECT expires_at FROM rediscover_shelf ORDER BY generated_at DESC LIMIT 1"
    ).fetchone()

    if not shelf:
        return True

    expires_at = datetime.fromisoformat(shelf["expires_at"])
    return datetime.now(timezone.utc) >= expires_at


def refresh_rediscover_shelf(conn: sqlite3.Connection) -> dict:
    """Force regeneration of shelf."""
    return generate_rediscover_shelf(conn)

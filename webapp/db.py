import re
import sqlite3
from datetime import datetime, timezone
from typing import Optional

ALLOWED_SORT_COLUMNS = frozenset({
    'title', 'channel_name', 'yt_view_count', 'personal_view_count',
    'date_added', 'date_last_viewed', 'date_published',
})
ALLOWED_SORT_DIRS = frozenset({'asc', 'desc'})


def _build_where(channel, tag, search):
    params = []
    clauses = []
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
            "(REGEXP(?, v.title) OR REGEXP(?, v.description) OR v.id IN ("
            "SELECT vt.video_id_fk FROM video_tags vt "
            "JOIN tags t ON t.id = vt.tag_id_fk WHERE REGEXP(?, t.name)))"
        )
        params.append(pattern)
        params.append(pattern)
        params.append(pattern)
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

    sql = f"""
        SELECT v.*, GROUP_CONCAT(t.name) as tags
        FROM videos v
        LEFT JOIN video_tags vt ON vt.video_id_fk = v.id
        LEFT JOIN tags t ON t.id = vt.tag_id_fk
        {where_sql}
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


def get_video_by_id(conn: sqlite3.Connection, video_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM videos WHERE video_id = ?", (video_id,)
    ).fetchone()
    return dict(row) if row else None


def get_all_channels(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT channel_name FROM videos WHERE channel_name IS NOT NULL"
    ).fetchall()
    return [r[0] for r in rows]


def get_all_tags(conn: sqlite3.Connection) -> list:
    rows = conn.execute("""
        SELECT t.id, t.name, COUNT(vt.video_id_fk) as video_count
        FROM tags t
        LEFT JOIN video_tags vt ON vt.tag_id_fk = t.id
        GROUP BY t.id, t.name
    """).fetchall()
    return [dict(r) for r in rows]


def get_tags_with_keywords(conn: sqlite3.Connection) -> list:
    tags = conn.execute("SELECT id, name FROM tags").fetchall()
    result = []
    for tag in tags:
        kws = conn.execute(
            "SELECT keyword FROM tag_keywords WHERE tag_id = ?", (tag["id"],)
        ).fetchall()
        result.append({"id": tag["id"], "name": tag["name"], "keywords": [r[0] for r in kws]})
    return result


def get_tag_keywords(conn: sqlite3.Connection, tag_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT keyword FROM tag_keywords WHERE tag_id = ?", (tag_id,)
    ).fetchall()
    return [r[0] for r in rows]


def get_stats(conn: sqlite3.Connection) -> dict:
    total_videos = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    total_channels = conn.execute(
        "SELECT COUNT(DISTINCT channel_name) FROM videos WHERE channel_name IS NOT NULL"
    ).fetchone()[0]
    fetch_errors = conn.execute(
        "SELECT COUNT(*) FROM videos WHERE fetch_status = 'error'"
    ).fetchone()[0]
    return {
        "total_videos": total_videos,
        "total_channels": total_channels,
        "fetch_errors": fetch_errors,
    }


def get_tags_for_video(conn: sqlite3.Connection, video_id: str) -> list[str]:
    rows = conn.execute("""
        SELECT t.name FROM tags t
        JOIN video_tags vt ON vt.tag_id_fk = t.id
        JOIN videos v ON v.id = vt.video_id_fk
        WHERE v.video_id = ?
    """, (video_id,)).fetchall()
    return [r[0] for r in rows]


def record_visit(conn: sqlite3.Connection, video_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE videos SET personal_view_count = personal_view_count + 1, "
        "date_last_viewed = ? WHERE video_id = ?",
        (now, video_id),
    )
    conn.commit()


def create_tag(conn: sqlite3.Connection, name: str) -> int:
    existing = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
    if existing:
        return existing[0]
    cursor = conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
    conn.commit()
    return cursor.lastrowid


def set_tag_keywords(conn: sqlite3.Connection, tag_id: int, keywords: list[str]) -> None:
    conn.execute("DELETE FROM tag_keywords WHERE tag_id = ?", (tag_id,))
    for kw in keywords:
        conn.execute(
            "INSERT INTO tag_keywords (tag_id, keyword) VALUES (?, ?)", (tag_id, kw)
        )
    conn.commit()


def delete_tag(conn: sqlite3.Connection, tag_id: int) -> None:
    conn.execute("DELETE FROM video_tags WHERE tag_id_fk = ?", (tag_id,))
    conn.execute("DELETE FROM tag_keywords WHERE tag_id = ?", (tag_id,))
    conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    conn.commit()


def add_video_tag(conn: sqlite3.Connection, video_id: str, tag_id: int) -> None:
    video_row = conn.execute(
        "SELECT id FROM videos WHERE video_id = ?", (video_id,)
    ).fetchone()
    if not video_row:
        return
    conn.execute(
        "INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk) VALUES (?, ?)",
        (video_row[0], tag_id),
    )
    conn.commit()


def remove_video_tag(conn: sqlite3.Connection, video_id: str, tag_id: int) -> None:
    video_row = conn.execute(
        "SELECT id FROM videos WHERE video_id = ?", (video_id,)
    ).fetchone()
    if not video_row:
        return
    conn.execute(
        "DELETE FROM video_tags WHERE video_id_fk = ? AND tag_id_fk = ?",
        (video_row[0], tag_id),
    )
    conn.commit()


def init_webapp_tables(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tag_keywords (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            tag_id  INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            keyword TEXT NOT NULL,
            UNIQUE(tag_id, keyword)
        );
        CREATE TABLE IF NOT EXISTS video_tags (
            video_id_fk INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
            tag_id_fk   INTEGER NOT NULL REFERENCES tags(id)   ON DELETE CASCADE,
            PRIMARY KEY (video_id_fk, tag_id_fk)
        );
    """)
    conn.commit()
    conn.close()

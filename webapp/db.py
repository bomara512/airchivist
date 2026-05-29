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
    clauses = ["v.fetch_status = 'ok'"]
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
        SELECT v.*, GROUP_CONCAT(t.name) as tags
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
    fetch_status: str = 'ok',
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
            name = name.strip()
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


def apply_aliases(conn: sqlite3.Connection, video_id: str) -> None:
    """Associate video with canonical tags whose alias rules match any of its current tags."""
    video_row = conn.execute("SELECT id FROM videos WHERE video_id = ?", (video_id,)).fetchone()
    if not video_row:
        return

    try:
        rules = conn.execute(
            "SELECT pattern, match_type, canonical_tag_id FROM tag_aliases"
        ).fetchall()
    except sqlite3.OperationalError:
        return  # tag_aliases table not yet created

    if not rules:
        return

    tag_names = [r[0] for r in conn.execute(
        "SELECT t.name FROM tags t JOIN video_tags vt ON vt.tag_id_fk = t.id WHERE vt.video_id_fk = ?",
        (video_row[0],),
    ).fetchall()]

    canonical_ids = set()
    for pattern, match_type, canonical_tag_id in rules:
        p = pattern.lower()
        for name in tag_names:
            n = name.lower()
            if match_type == 'exact' and n == p:
                canonical_ids.add(canonical_tag_id)
            elif match_type == 'prefix' and n.startswith(p):
                canonical_ids.add(canonical_tag_id)
            elif match_type == 'contains' and p in n:
                canonical_ids.add(canonical_tag_id)

    for cid in canonical_ids:
        conn.execute(
            "INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk) VALUES (?, ?)",
            (video_row[0], cid),
        )
    if canonical_ids:
        conn.commit()


def get_canonical_tags(conn: sqlite3.Connection) -> list:
    tags = conn.execute("""
        SELECT t.id, t.name, COUNT(DISTINCT vt.video_id_fk) as video_count
        FROM tags t
        LEFT JOIN video_tags vt ON vt.tag_id_fk = t.id
        WHERE t.is_canonical = 1
        GROUP BY t.id, t.name
        ORDER BY t.name
    """).fetchall()
    result = []
    for tag in tags:
        aliases = conn.execute(
            "SELECT id, pattern, match_type FROM tag_aliases WHERE canonical_tag_id = ? ORDER BY pattern",
            (tag["id"],),
        ).fetchall()
        result.append({
            "id": tag["id"],
            "name": tag["name"],
            "video_count": tag["video_count"],
            "aliases": [dict(a) for a in aliases],
        })
    return result


def create_canonical_tag(conn: sqlite3.Connection, name: str) -> int:
    name = name.strip()
    existing = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
    if existing:
        conn.execute("UPDATE tags SET is_canonical = 1 WHERE id = ?", (existing[0],))
        conn.commit()
        return existing[0]
    cursor = conn.execute("INSERT INTO tags (name, is_canonical) VALUES (?, 1)", (name,))
    conn.commit()
    return cursor.lastrowid


def add_alias(conn: sqlite3.Connection, tag_id: int, pattern: str, match_type: str = "exact") -> int:
    conn.execute(
        "INSERT OR IGNORE INTO tag_aliases (pattern, match_type, canonical_tag_id) VALUES (?, ?, ?)",
        (pattern.strip(), match_type, tag_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM tag_aliases WHERE pattern = ? AND match_type = ? AND canonical_tag_id = ?",
        (pattern.strip(), match_type, tag_id),
    ).fetchone()
    return row[0]


def delete_alias(conn: sqlite3.Connection, alias_id: int) -> None:
    conn.execute("DELETE FROM tag_aliases WHERE id = ?", (alias_id,))
    conn.commit()


def retroactive_apply(conn: sqlite3.Connection, alias_rule_id: Optional[int] = None) -> int:
    """Apply alias rules to all existing videos. Returns number of new associations created."""
    if alias_rule_id is not None:
        rules = conn.execute(
            "SELECT pattern, match_type, canonical_tag_id FROM tag_aliases WHERE id = ?",
            (alias_rule_id,),
        ).fetchall()
    else:
        rules = conn.execute(
            "SELECT pattern, match_type, canonical_tag_id FROM tag_aliases"
        ).fetchall()

    total = 0
    for pattern, match_type, canonical_tag_id in rules:
        p = pattern.lower()
        esc = p.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        if match_type == "exact":
            cur = conn.execute("""
                INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk)
                SELECT DISTINCT vt.video_id_fk, ?
                FROM video_tags vt JOIN tags t ON t.id = vt.tag_id_fk
                WHERE LOWER(t.name) = ?
            """, (canonical_tag_id, p))
        elif match_type == "prefix":
            cur = conn.execute("""
                INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk)
                SELECT DISTINCT vt.video_id_fk, ?
                FROM video_tags vt JOIN tags t ON t.id = vt.tag_id_fk
                WHERE LOWER(t.name) LIKE ? ESCAPE '\\'
            """, (canonical_tag_id, esc + "%"))
        elif match_type == "contains":
            cur = conn.execute("""
                INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk)
                SELECT DISTINCT vt.video_id_fk, ?
                FROM video_tags vt JOIN tags t ON t.id = vt.tag_id_fk
                WHERE LOWER(t.name) LIKE ? ESCAPE '\\'
            """, (canonical_tag_id, "%" + esc + "%"))
        else:
            continue
        total += cur.rowcount
    conn.commit()
    return total


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
        CREATE TABLE IF NOT EXISTS tag_aliases (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern          TEXT    NOT NULL,
            match_type       TEXT    NOT NULL DEFAULT 'exact',
            canonical_tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            UNIQUE(pattern, match_type)
        );
    """)
    try:
        conn.execute("ALTER TABLE tags ADD COLUMN is_canonical BOOLEAN NOT NULL DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.commit()
    conn.close()

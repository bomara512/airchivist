import json
import re
import sqlite3
from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional

from crawler.models import FetchStatus

ALLOWED_SORT_COLUMNS = frozenset({
    'title', 'channel_name', 'yt_view_count', 'personal_view_count',
    'date_added', 'date_last_viewed', 'date_published',
})
ALLOWED_SORT_DIRS = frozenset({'asc', 'desc'})


class MatchType(StrEnum):
    EXACT = 'exact'
    PREFIX = 'prefix'
    CONTAINS = 'contains'


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


def get_canonical_tags_for_filter(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("""
        SELECT t.name
        FROM tags t
        JOIN video_tags vt ON vt.tag_id_fk = t.id
        WHERE t.is_canonical = 1
        GROUP BY t.id, t.name
        ORDER BY t.name
    """).fetchall()
    return [r[0] for r in rows]


def get_canonical_tags_for_filter_grouped(conn: sqlite3.Connection) -> list[dict]:
    """Returns [{name, tags}] for optgroup rendering. Last entry has name=None for ungrouped tags."""
    all_canonical = conn.execute("""
        SELECT t.id, t.name
        FROM tags t
        JOIN video_tags vt ON vt.tag_id_fk = t.id
        WHERE t.is_canonical = 1
        GROUP BY t.id, t.name
        ORDER BY t.name
    """).fetchall()
    id_to_name = {r["id"]: r["name"] for r in all_canonical}
    all_ids = set(id_to_name)

    groups = get_tag_groups(conn)
    grouped_ids: set[int] = set()
    result = []
    for g in groups:
        tag_names = []
        for m in g["members"]:
            if m["id"] in all_ids:
                tag_names.append(m["name"])
                grouped_ids.add(m["id"])
        if tag_names:
            result.append({"name": g["name"], "tags": sorted(tag_names)})

    ungrouped = sorted(id_to_name[tid] for tid in all_ids if tid not in grouped_ids)
    if ungrouped:
        result.append({"name": None, "tags": ungrouped})
    return result


def get_tag_groups(conn: sqlite3.Connection) -> list[dict]:
    groups = conn.execute(
        "SELECT id, name FROM tag_groups ORDER BY sort_order, name"
    ).fetchall()
    result = []
    for g in groups:
        members = conn.execute("""
            SELECT t.id, t.name
            FROM tags t
            JOIN tag_group_members tgm ON tgm.canonical_tag_id = t.id
            WHERE tgm.group_id = ?
            ORDER BY t.name
        """, (g["id"],)).fetchall()
        result.append({"id": g["id"], "name": g["name"], "members": [dict(m) for m in members]})
    return result


def create_tag_group(conn: sqlite3.Connection, name: str) -> int:
    conn.execute("INSERT OR IGNORE INTO tag_groups (name) VALUES (?)", (name.strip(),))
    conn.commit()
    return conn.execute("SELECT id FROM tag_groups WHERE name = ?", (name.strip(),)).fetchone()[0]


def delete_tag_group(conn: sqlite3.Connection, group_id: int) -> None:
    conn.execute("DELETE FROM tag_groups WHERE id = ?", (group_id,))
    conn.commit()


def get_ungrouped_canonicals(conn: sqlite3.Connection) -> list[dict]:
    """Return canonical tags not assigned to any group, with video count and sample aliases."""
    rows = conn.execute("""
        SELECT t.id, t.name, COUNT(DISTINCT vt.video_id_fk) as video_count
        FROM tags t
        LEFT JOIN video_tags vt ON vt.tag_id_fk = t.id
        WHERE t.is_canonical = 1
          AND t.id NOT IN (SELECT canonical_tag_id FROM tag_group_members)
        GROUP BY t.id, t.name
        ORDER BY t.name
    """).fetchall()
    result = []
    for r in rows:
        aliases = conn.execute(
            "SELECT pattern FROM tag_aliases WHERE canonical_tag_id = ? LIMIT 5",
            (r["id"],),
        ).fetchall()
        result.append({
            "id": r["id"],
            "name": r["name"],
            "video_count": r["video_count"],
            "aliases": [a["pattern"] for a in aliases],
        })
    return result


def add_canonical_to_group(conn: sqlite3.Connection, group_id: int, canonical_tag_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO tag_group_members (group_id, canonical_tag_id) VALUES (?, ?)",
        (group_id, canonical_tag_id),
    )
    conn.commit()


def remove_canonical_from_group(conn: sqlite3.Connection, group_id: int, canonical_tag_id: int) -> None:
    conn.execute(
        "DELETE FROM tag_group_members WHERE group_id = ? AND canonical_tag_id = ?",
        (group_id, canonical_tag_id),
    )
    conn.commit()


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
    name = name.strip().lower()
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
            if match_type == MatchType.EXACT and n == p:
                canonical_ids.add(canonical_tag_id)
            elif match_type == MatchType.PREFIX and n.startswith(p):
                canonical_ids.add(canonical_tag_id)
            elif match_type == MatchType.CONTAINS and p in n:
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
    name = name.strip().lower()
    existing = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
    if existing:
        conn.execute("UPDATE tags SET is_canonical = 1 WHERE id = ?", (existing[0],))
        conn.commit()
        return existing[0]
    cursor = conn.execute("INSERT INTO tags (name, is_canonical) VALUES (?, 1)", (name,))
    conn.commit()
    return cursor.lastrowid


def add_alias(conn: sqlite3.Connection, tag_id: int, pattern: str, match_type: str = MatchType.EXACT) -> Optional[int]:
    pattern = pattern.strip().lower()
    conn.execute(
        "INSERT OR IGNORE INTO tag_aliases (pattern, match_type, canonical_tag_id) VALUES (?, ?, ?)",
        (pattern, match_type, tag_id),
    )
    conn.commit()
    # UNIQUE constraint is on (pattern, match_type) only — if another canonical already owns
    # this pattern, the INSERT is ignored and the row belongs to the other canonical.
    row = conn.execute(
        "SELECT id FROM tag_aliases WHERE pattern = ? AND match_type = ?",
        (pattern, match_type),
    ).fetchone()
    return row[0] if row else None


def delete_alias(conn: sqlite3.Connection, alias_id: int) -> None:
    conn.execute("DELETE FROM tag_aliases WHERE id = ?", (alias_id,))
    conn.commit()


def delete_alias_with_cleanup(conn: sqlite3.Connection, alias_id: int) -> int:
    """Delete alias and remove video associations no longer covered by any remaining alias.
    Returns the number of video associations removed."""
    alias = conn.execute(
        "SELECT pattern, match_type, canonical_tag_id FROM tag_aliases WHERE id = ?",
        (alias_id,),
    ).fetchone()
    if not alias:
        return 0

    pattern = alias["pattern"]
    match_type = alias["match_type"]
    canonical_tag_id = alias["canonical_tag_id"]

    def _matching_video_ids(pat: str, mt: str, restrict: list | None = None) -> set[int]:
        """Find video IDs that have a raw tag matching pat/mt, optionally restricted to a list."""
        sql = ("SELECT DISTINCT vt.video_id_fk FROM video_tags vt "
               "JOIN tags t ON t.id = vt.tag_id_fk "
               "WHERE t.id != ? ")  # exclude the canonical tag itself
        params: list = [canonical_tag_id]
        if mt == "exact":
            sql += "AND t.name = ? "
            params.append(pat)
        elif mt == "prefix":
            sql += "AND t.name LIKE ? "
            params.append(pat + "%")
        else:
            sql += "AND t.name LIKE ? "
            params.append("%" + pat + "%")
        if restrict:
            sql += f"AND vt.video_id_fk IN ({','.join('?' * len(restrict))}) "
            params.extend(restrict)
        return {r[0] for r in conn.execute(sql, params).fetchall()}

    matched_ids = _matching_video_ids(pattern, match_type)

    conn.execute("DELETE FROM tag_aliases WHERE id = ?", (alias_id,))

    if not matched_ids:
        conn.commit()
        return 0

    remaining = conn.execute(
        "SELECT pattern, match_type FROM tag_aliases WHERE canonical_tag_id = ?",
        (canonical_tag_id,),
    ).fetchall()

    still_covered: set[int] = set()
    for ra in remaining:
        still_covered |= _matching_video_ids(ra["pattern"], ra["match_type"], restrict=list(matched_ids))

    to_remove = matched_ids - still_covered
    if to_remove:
        placeholders = ",".join("?" * len(to_remove))
        conn.execute(
            f"DELETE FROM video_tags WHERE tag_id_fk = ? AND video_id_fk IN ({placeholders})",
            [canonical_tag_id, *to_remove],
        )

    conn.commit()
    return len(to_remove)


def edit_alias(conn: sqlite3.Connection, alias_id: int, pattern: str, match_type: str) -> None:
    conn.execute(
        "UPDATE tag_aliases SET pattern = ?, match_type = ? WHERE id = ?",
        (pattern.strip().lower(), match_type, alias_id),
    )
    conn.commit()


def retroactive_apply(
    conn: sqlite3.Connection,
    alias_rule_id: Optional[int] = None,
    video_id: Optional[int] = None,
) -> int:
    """Apply alias rules to existing videos. Returns number of new associations created.

    alias_rule_id — scope to a single alias rule (used after adding/editing an alias)
    video_id      — scope to a single video row id (used after adding a new video)
    Both None     — full pass over all rules and all videos
    """
    if alias_rule_id is not None:
        rules = conn.execute(
            "SELECT ta.pattern, ta.match_type, ta.canonical_tag_id "
            "FROM tag_aliases ta JOIN tags t ON t.id = ta.canonical_tag_id "
            "WHERE ta.id = ?",
            (alias_rule_id,),
        ).fetchall()
    else:
        rules = conn.execute(
            "SELECT ta.pattern, ta.match_type, ta.canonical_tag_id "
            "FROM tag_aliases ta JOIN tags t ON t.id = ta.canonical_tag_id"
        ).fetchall()

    video_filter = "AND vt.video_id_fk = ? " if video_id is not None else ""
    total = 0
    for pattern, match_type, canonical_tag_id in rules:
        p = pattern.lower()
        esc = p.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        extra = (video_id,) if video_id is not None else ()
        if match_type == MatchType.EXACT:
            cur = conn.execute(f"""
                INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk)
                SELECT DISTINCT vt.video_id_fk, ?
                FROM video_tags vt JOIN tags t ON t.id = vt.tag_id_fk
                WHERE LOWER(t.name) = ? {video_filter}
            """, (canonical_tag_id, p, *extra))
        elif match_type == MatchType.PREFIX:
            cur = conn.execute(f"""
                INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk)
                SELECT DISTINCT vt.video_id_fk, ?
                FROM video_tags vt JOIN tags t ON t.id = vt.tag_id_fk
                WHERE LOWER(t.name) LIKE ? ESCAPE '\\' {video_filter}
            """, (canonical_tag_id, esc + "%", *extra))
        elif match_type == MatchType.CONTAINS:
            cur = conn.execute(f"""
                INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk)
                SELECT DISTINCT vt.video_id_fk, ?
                FROM video_tags vt JOIN tags t ON t.id = vt.tag_id_fk
                WHERE LOWER(t.name) LIKE ? ESCAPE '\\' {video_filter}
            """, (canonical_tag_id, "%" + esc + "%", *extra))
        else:
            continue
        total += cur.rowcount
    conn.commit()
    return total


def mark_tag_noise(conn: sqlite3.Connection, tag_name: str) -> None:
    conn.execute("UPDATE tags SET is_noise = 1 WHERE name = ?", (tag_name,))
    conn.commit()


def mark_tags_noise_bulk(conn: sqlite3.Connection, tag_names: list[str]) -> int:
    if not tag_names:
        return 0
    ph = ",".join("?" * len(tag_names))
    cur = conn.execute(f"UPDATE tags SET is_noise = 1 WHERE name IN ({ph})", tag_names)
    conn.commit()
    return cur.rowcount


def get_video_titles_for_tag(
    conn: sqlite3.Connection,
    tag_name: str,
    limit: int = 10,
) -> list[str]:
    rows = conn.execute("""
        SELECT v.title
        FROM videos v
        JOIN video_tags vt ON vt.video_id_fk = v.id
        JOIN tags t ON t.id = vt.tag_id_fk
        WHERE t.name = ? AND v.title IS NOT NULL
        ORDER BY v.yt_view_count DESC
        LIMIT ?
    """, (tag_name, limit)).fetchall()
    return [r[0] for r in rows]


def get_related_unclassified_tags(
    conn: sqlite3.Connection,
    tag_name: str,
    limit: int = 20,
) -> list[dict]:
    """Return unclassified tags that co-occur most often with tag_name on the same videos."""
    rows = conn.execute("""
        SELECT t2.name, COUNT(DISTINCT vt2.video_id_fk) AS shared
        FROM video_tags vt1
        JOIN tags t1 ON t1.id = vt1.tag_id_fk
        JOIN video_tags vt2 ON vt2.video_id_fk = vt1.video_id_fk
        JOIN tags t2 ON t2.id = vt2.tag_id_fk
        WHERE t1.name = ?
          AND t2.id != t1.id
          AND t2.is_canonical = 0
          AND t2.is_noise = 0
          AND t2.name NOT IN (SELECT pattern FROM tag_aliases)
        GROUP BY t2.id, t2.name
        ORDER BY shared DESC, t2.name COLLATE NOCASE ASC
        LIMIT ?
    """, (tag_name, limit)).fetchall()
    return [{"name": r["name"], "shared": r["shared"]} for r in rows]


def get_unclassified_tags(
    conn: sqlite3.Connection,
    max_tags: int = 1000,
    min_videos: int = 2,
) -> tuple[list, int]:
    """Return (tags, total_count) for non-canonical, non-aliased, non-noise tags ordered by usage."""
    base = """
        FROM tags t
        JOIN video_tags vt ON vt.tag_id_fk = t.id
        WHERE t.is_canonical = 0
          AND t.is_noise = 0
          AND LOWER(t.name) NOT IN (SELECT LOWER(pattern) FROM tag_aliases)
        GROUP BY t.id, t.name
        HAVING COUNT(vt.video_id_fk) >= ?
    """
    total = conn.execute("SELECT COUNT(*) FROM (" + "SELECT t.id " + base + ")", (min_videos,)).fetchone()[0]
    rows = conn.execute("""
        SELECT t.name, COUNT(vt.video_id_fk) as video_count
    """ + base + """
        ORDER BY video_count DESC, t.name COLLATE NOCASE ASC
        LIMIT ?
    """, (min_videos, max_tags)).fetchall()
    return [{"name": r[0], "video_count": r[1]} for r in rows], total


def confirm_suggestion(conn: sqlite3.Connection, canonical_name: str, member_names: list[str]) -> int:
    """Create a canonical tag, add exact aliases for all members, and retroactively apply."""
    tag_id = create_canonical_tag(conn, canonical_name)
    total = 0
    for name in member_names:
        name = name.strip()
        if name:
            alias_id = add_alias(conn, tag_id, name, "exact")
            if alias_id is not None:
                total += retroactive_apply(conn, alias_id)
    return total


def save_llm_suggestions(conn: sqlite3.Connection, suggestions: list[dict], pool_hash: str) -> None:
    """Replace stored LLM suggestions with a fresh batch.

    Always inserts at least one row (a _run_marker sentinel when suggestions is empty)
    so is_llm_suggestion_cache_stale can distinguish "run happened, nothing to show"
    from "never run".
    """
    conn.execute("DELETE FROM llm_suggestions")
    now = datetime.now(timezone.utc).isoformat()
    for s in suggestions:
        conn.execute(
            "INSERT INTO llm_suggestions (canonical, members, confidence, is_noise, created_at, pool_hash) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                s["canonical"],
                json.dumps(s["members"]),
                s.get("confidence", "medium"),
                1 if s.get("is_noise") else 0,
                now,
                pool_hash,
            ),
        )
    if not suggestions:
        conn.execute(
            "INSERT INTO llm_suggestions (canonical, members, confidence, is_noise, created_at, pool_hash) "
            "VALUES ('_run_marker', '[]', 'high', 0, ?, ?)",
            (now, pool_hash),
        )
    conn.commit()


def get_llm_suggestion_by_id(conn: sqlite3.Connection, suggestion_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT id, canonical, members, confidence, is_noise "
        "FROM llm_suggestions WHERE id = ?",
        (suggestion_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "canonical": row["canonical"],
        "members": json.loads(row["members"]),
        "confidence": row["confidence"],
        "is_noise": bool(row["is_noise"]),
    }


def get_llm_suggestions(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, canonical, members, confidence, is_noise "
        "FROM llm_suggestions WHERE canonical != '_run_marker' ORDER BY is_noise ASC, id ASC"
    ).fetchall()
    rejection_rows = conn.execute(
        "SELECT member_tag, canonical FROM llm_suggestion_rejections"
    ).fetchall()
    rejections: set[tuple[str, str]] = {(r["member_tag"], r["canonical"]) for r in rejection_rows}

    result = []
    for row in rows:
        members = [
            m for m in json.loads(row["members"])
            if (m, row["canonical"]) not in rejections
        ]
        if not members:
            continue
        result.append({
            "id": row["id"],
            "canonical": row["canonical"],
            "members": members,
            "confidence": row["confidence"],
            "is_noise": bool(row["is_noise"]),
        })
    return result


def record_suggestion_rejections(
    conn: sqlite3.Connection, canonical: str, member_tags: list[str]
) -> None:
    for tag in member_tags:
        conn.execute(
            "INSERT OR IGNORE INTO llm_suggestion_rejections (member_tag, canonical) VALUES (?, ?)",
            (tag, canonical),
        )
    conn.commit()


def dismiss_llm_suggestion(conn: sqlite3.Connection, suggestion_id: int) -> None:
    conn.execute("DELETE FROM llm_suggestions WHERE id = ?", (suggestion_id,))
    conn.commit()


def is_llm_suggestion_cache_stale(conn: sqlite3.Connection, current_hash: str) -> bool:
    """True when there are no stored suggestions or the pool has changed since the last run."""
    row = conn.execute(
        "SELECT pool_hash FROM llm_suggestions LIMIT 1"
    ).fetchone()
    if row is None:
        return True
    return row["pool_hash"] != current_hash


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


def collapse_case_variants(conn: sqlite3.Connection) -> int:
    """Merge tag rows that differ only in case into a single lowercase row.

    Winner selection per group: canonical tag > most video associations > lowest id.
    Returns the number of tag rows deleted.
    """
    groups = conn.execute("""
        SELECT LOWER(name) AS low, GROUP_CONCAT(id) AS id_list
        FROM tags
        GROUP BY LOWER(name)
        HAVING COUNT(*) > 1
    """).fetchall()

    if not groups:
        return 0

    deleted = 0
    for group in groups:
        low = group[0]
        ids = [int(x) for x in group[1].split(",")]

        candidates = conn.execute("""
            SELECT t.id, COUNT(vt.video_id_fk) AS vc
            FROM tags t
            LEFT JOIN video_tags vt ON vt.tag_id_fk = t.id
            WHERE t.id IN ({ph})
            GROUP BY t.id
            ORDER BY t.is_canonical DESC, vc DESC, t.id ASC
        """.format(ph=",".join("?" * len(ids))), ids).fetchall()

        winner_id = candidates[0][0]
        loser_ids = [c[0] for c in candidates[1:]]

        for loser_id in loser_ids:
            conn.execute("""
                INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk)
                SELECT video_id_fk, ? FROM video_tags WHERE tag_id_fk = ?
            """, (winner_id, loser_id))
            conn.execute("""
                INSERT OR IGNORE INTO tag_keywords (tag_id, keyword)
                SELECT ?, keyword FROM tag_keywords WHERE tag_id = ?
            """, (winner_id, loser_id))
            conn.execute("""
                UPDATE OR IGNORE tag_aliases SET canonical_tag_id = ?
                WHERE canonical_tag_id = ?
            """, (winner_id, loser_id))
            conn.execute("""
                INSERT OR IGNORE INTO tag_group_members (group_id, canonical_tag_id)
                SELECT group_id, ? FROM tag_group_members WHERE canonical_tag_id = ?
            """, (winner_id, loser_id))
            conn.execute("DELETE FROM tags WHERE id = ?", (loser_id,))
            deleted += 1

        conn.execute("UPDATE tags SET name = ? WHERE id = ?", (low, winner_id))

    # Lowercase any remaining single-variant mixed-case names (safe after dedup above)
    conn.execute("UPDATE tags SET name = LOWER(name) WHERE name != LOWER(name)")
    conn.commit()
    return deleted


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
        CREATE TABLE IF NOT EXISTS llm_suggestions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical  TEXT    NOT NULL,
            members    TEXT    NOT NULL,
            confidence TEXT,
            is_noise   BOOLEAN NOT NULL DEFAULT 0,
            created_at TEXT    NOT NULL,
            pool_hash  TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS llm_suggestion_rejections (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            member_tag TEXT    NOT NULL,
            canonical  TEXT    NOT NULL,
            created_at TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE(member_tag, canonical)
        );
        CREATE TABLE IF NOT EXISTS tag_groups (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT    NOT NULL UNIQUE,
            sort_order INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS tag_group_members (
            group_id         INTEGER NOT NULL REFERENCES tag_groups(id) ON DELETE CASCADE,
            canonical_tag_id INTEGER NOT NULL REFERENCES tags(id)       ON DELETE CASCADE,
            PRIMARY KEY (group_id, canonical_tag_id)
        );
    """)
    for col, ddl in [
        ("is_canonical", "ALTER TABLE tags    ADD COLUMN is_canonical BOOLEAN NOT NULL DEFAULT 0"),
        ("is_noise",     "ALTER TABLE tags    ADD COLUMN is_noise     BOOLEAN NOT NULL DEFAULT 0"),
        ("is_hidden",    "ALTER TABLE videos  ADD COLUMN is_hidden    BOOLEAN NOT NULL DEFAULT 0"),
    ]:
        try:
            conn.execute(ddl)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
    conn.close()

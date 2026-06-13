import sqlite3
from typing import Optional

from webapp.db.groups import get_tag_groups


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


def get_tags_for_video(conn: sqlite3.Connection, video_id: str) -> list[str]:
    rows = conn.execute("""
        SELECT t.name FROM tags t
        JOIN video_tags vt ON vt.tag_id_fk = t.id
        JOIN videos v ON v.id = vt.video_id_fk
        WHERE v.video_id = ?
    """, (video_id,)).fetchall()
    return [r[0] for r in rows]


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

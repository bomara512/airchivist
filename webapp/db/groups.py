import sqlite3


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

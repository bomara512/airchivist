import sqlite3
from typing import Optional

from crawler.models import MatchType


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


def add_alias_and_apply(
    conn: sqlite3.Connection,
    tag_id: int,
    pattern: str,
    match_type: str = MatchType.EXACT,
) -> int:
    """Add alias and retroactively apply in a single transaction. Returns count of new associations."""
    pattern = pattern.strip().lower()

    # Step 1: Insert the alias
    conn.execute(
        "INSERT OR IGNORE INTO tag_aliases (pattern, match_type, canonical_tag_id) VALUES (?, ?, ?)",
        (pattern, match_type, tag_id),
    )

    # Step 2: Retroactively apply
    p = pattern.lower()
    esc = p.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    total = 0

    if match_type == MatchType.EXACT:
        cur = conn.execute(f"""
            INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk)
            SELECT DISTINCT vt.video_id_fk, ?
            FROM video_tags vt JOIN tags t ON t.id = vt.tag_id_fk
            WHERE LOWER(t.name) = ?
        """, (tag_id, p))
    elif match_type == MatchType.PREFIX:
        cur = conn.execute(f"""
            INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk)
            SELECT DISTINCT vt.video_id_fk, ?
            FROM video_tags vt JOIN tags t ON t.id = vt.tag_id_fk
            WHERE LOWER(t.name) LIKE ? ESCAPE '\\'
        """, (tag_id, esc + "%"))
    elif match_type == MatchType.CONTAINS:
        cur = conn.execute(f"""
            INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk)
            SELECT DISTINCT vt.video_id_fk, ?
            FROM video_tags vt JOIN tags t ON t.id = vt.tag_id_fk
            WHERE LOWER(t.name) LIKE ? ESCAPE '\\'
        """, (tag_id, "%" + esc + "%"))
    else:
        cur = None

    total = cur.rowcount if cur else 0
    conn.commit()
    return total


def edit_alias_and_apply(
    conn: sqlite3.Connection,
    alias_id: int,
    pattern: str,
    match_type: str,
) -> int:
    """Edit alias and retroactively apply in a single transaction. Returns count of new associations."""
    pattern = pattern.strip().lower()

    # Fetch the alias to get the canonical tag ID
    alias_row = conn.execute(
        "SELECT canonical_tag_id FROM tag_aliases WHERE id = ?", (alias_id,)
    ).fetchone()
    if not alias_row:
        return 0

    tag_id = alias_row[0]

    # Step 1: Update the alias
    conn.execute(
        "UPDATE tag_aliases SET pattern = ?, match_type = ? WHERE id = ?",
        (pattern, match_type, alias_id),
    )

    # Step 2: Retroactively apply
    p = pattern.lower()
    esc = p.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    total = 0

    if match_type == MatchType.EXACT:
        cur = conn.execute(f"""
            INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk)
            SELECT DISTINCT vt.video_id_fk, ?
            FROM video_tags vt JOIN tags t ON t.id = vt.tag_id_fk
            WHERE LOWER(t.name) = ?
        """, (tag_id, p))
    elif match_type == MatchType.PREFIX:
        cur = conn.execute(f"""
            INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk)
            SELECT DISTINCT vt.video_id_fk, ?
            FROM video_tags vt JOIN tags t ON t.id = vt.tag_id_fk
            WHERE LOWER(t.name) LIKE ? ESCAPE '\\'
        """, (tag_id, esc + "%"))
    elif match_type == MatchType.CONTAINS:
        cur = conn.execute(f"""
            INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk)
            SELECT DISTINCT vt.video_id_fk, ?
            FROM video_tags vt JOIN tags t ON t.id = vt.tag_id_fk
            WHERE LOWER(t.name) LIKE ? ESCAPE '\\'
        """, (tag_id, "%" + esc + "%"))
    else:
        cur = None

    total = cur.rowcount if cur else 0
    conn.commit()
    return total

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from webapp.db.aliases import add_alias, retroactive_apply
from webapp.db.tags import create_canonical_tag


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

    noise_names: set[str] = {
        r["name"] for r in conn.execute("SELECT name FROM tags WHERE is_noise = 1").fetchall()
    }

    result = []
    for row in rows:
        members = [
            m for m in json.loads(row["members"])
            if (m, row["canonical"]) not in rejections
            and m not in noise_names
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


def confirm_and_dismiss_suggestion(
    conn: sqlite3.Connection,
    canonical_name: str,
    accepted_members: list[str],
    suggestion_id: int,
    all_suggestion_members: list[str],
) -> int:
    """Create canonical tag, add exact aliases for accepted members, record rejections, dismiss suggestion.

    Single transaction: creates canonical, adds aliases with retroactive apply, records rejections,
    deletes the suggestion. Returns count of new video-tag associations created.
    """
    canonical_name = canonical_name.strip().lower()

    # Step 1: Create or update canonical tag
    existing = conn.execute("SELECT id FROM tags WHERE name = ?", (canonical_name,)).fetchone()
    if existing:
        conn.execute("UPDATE tags SET is_canonical = 1 WHERE id = ?", (existing[0],))
        tag_id = existing[0]
    else:
        cursor = conn.execute("INSERT INTO tags (name, is_canonical) VALUES (?, 1)", (canonical_name,))
        tag_id = cursor.lastrowid

    # Step 2: Add exact aliases for accepted members and retroactively apply
    total_associations = 0
    accepted_set = set(m.strip() for m in accepted_members if m.strip())

    for name in accepted_set:
        name_lower = name.lower()

        # Add the alias
        conn.execute(
            "INSERT OR IGNORE INTO tag_aliases (pattern, match_type, canonical_tag_id) VALUES (?, ?, ?)",
            (name_lower, "exact", tag_id),
        )

        # Retroactively apply: find videos with this raw tag and link to canonical
        conn.execute(f"""
            INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk)
            SELECT DISTINCT vt.video_id_fk, ?
            FROM video_tags vt JOIN tags t ON t.id = vt.tag_id_fk
            WHERE LOWER(t.name) = ?
        """, (tag_id, name_lower))

        total_associations += conn.execute("SELECT changes()").fetchone()[0]

    # Step 3: Record rejections for members not in accepted set
    rejected = [m.strip() for m in all_suggestion_members if m.strip() not in accepted_set]
    for tag in rejected:
        conn.execute(
            "INSERT OR IGNORE INTO llm_suggestion_rejections (member_tag, canonical) VALUES (?, ?)",
            (tag, canonical_name),
        )

    # Step 4: Dismiss the suggestion
    conn.execute("DELETE FROM llm_suggestions WHERE id = ?", (suggestion_id,))

    conn.commit()
    return total_associations


def accept_noise_and_dismiss_suggestion(
    conn: sqlite3.Connection,
    suggestion_id: int,
    noise_members: list[str],
    rejected_members: list[str],
) -> None:
    """Mark members as noise, record rejections, dismiss suggestion. Single transaction."""
    if noise_members:
        ph = ",".join("?" * len(noise_members))
        conn.execute(f"UPDATE tags SET is_noise = 1 WHERE name IN ({ph})", noise_members)

    for tag in rejected_members:
        conn.execute(
            "INSERT OR IGNORE INTO llm_suggestion_rejections (member_tag, canonical) VALUES (?, ?)",
            (tag, "_noise"),
        )

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

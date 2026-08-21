#!/usr/bin/env python3
"""
Airchivist tag categorization CLI.

Default DB: airchivist-test.db (create with: cp airchivist.db airchivist-test.db)
Writing to the live DB requires explicit --db airchivist.db.

Subcommands:
  stats    Show tag counts and frequency breakdown
  noise    Auto-mark known noise patterns (no LLM, no review)
  suggest  LLM-driven categorization pass → proposals.json
  review   Interactive terminal review → approved.json
  apply    Write approved changes to the DB
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

# Allow importing from the project root (webapp.db, etc.)
sys.path.insert(0, str(Path(__file__).parent.parent))

DEFAULT_DB = "airchivist-test.db"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_MIN_VIDEOS = 5
DEFAULT_BATCH_SIZE = 60
MAX_TITLE_SAMPLES = 5


# ── Noise detection ────────────────────────────────────────────────────────

_YT_CATEGORIES = {
    "howto & style", "entertainment", "people & blogs", "science & technology",
    "gaming", "education", "music", "film & animation", "sports",
    "travel & events", "autos & vehicles", "pets & animals", "news & politics",
    "comedy", "nonprofits & activism",
}

_QUALITY_META = {"hd", "4k", "1080p", "720p", "uhd", "hq", "fhd", "480p", "2160p", "1080"}

_YT_META = {"yt:cc=on", "subscribe", "youtube", "youtube video", "subscribe now"}

_GENERIC_FILLER = {"video", "watch", "new", "latest", "official", "free", "viral"}

_YEAR_RE = re.compile(r"^\d{4}$")
_HASHTAG_RE = re.compile(r"^#[\w]+$")


def _noise_category(name: str) -> str | None:
    """Return the noise category label if the tag is noise, else None."""
    n = name.strip().lower()
    if n in _YT_CATEGORIES:
        return "YouTube category"
    if n in _QUALITY_META:
        return "quality/format"
    if n in _YT_META:
        return "YouTube meta"
    if n in _GENERIC_FILLER:
        return "generic filler"
    if _YEAR_RE.match(n) and 2000 <= int(n) <= 2030:
        return "year number"
    if _HASHTAG_RE.match(name.strip()):
        return "hashtag"
    return None


# ── DB helpers ─────────────────────────────────────────────────────────────

def open_db(db_path: str) -> sqlite3.Connection:
    p = Path(db_path)
    if not p.exists():
        msg = f"Error: {db_path} not found."
        if db_path == DEFAULT_DB:
            msg += f"\nCreate it with: cp airchivist.db {db_path}"
        sys.exit(msg)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_noise_column(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("SELECT is_noise FROM tags LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE tags ADD COLUMN is_noise BOOLEAN NOT NULL DEFAULT 0")
        conn.commit()
        print("Migrated: added is_noise column to tags table.")


# ── Subcommand: stats ──────────────────────────────────────────────────────

def cmd_stats(args: argparse.Namespace) -> None:
    conn = open_db(args.db)
    ensure_noise_column(conn)

    videos = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
    canonical = conn.execute("SELECT COUNT(*) FROM tags WHERE is_canonical = 1").fetchone()[0]
    noise = conn.execute("SELECT COUNT(*) FROM tags WHERE is_noise = 1").fetchone()[0]

    try:
        aliases = conn.execute("SELECT COUNT(*) FROM tag_aliases").fetchone()[0]
        row = conn.execute("""
            SELECT
              SUM(CASE WHEN cnt >= 5           THEN 1 ELSE 0 END) as five_plus,
              SUM(CASE WHEN cnt >= 2 AND cnt < 5 THEN 1 ELSE 0 END) as two_to_four,
              SUM(CASE WHEN cnt = 1            THEN 1 ELSE 0 END) as one_vid
            FROM (
              SELECT COUNT(vt.video_id_fk) as cnt
              FROM tags t
              JOIN video_tags vt ON vt.tag_id_fk = t.id
              WHERE t.is_canonical = 0 AND t.is_noise = 0
                AND t.name NOT IN (SELECT pattern FROM tag_aliases)
              GROUP BY t.id
            )
        """).fetchone()
        five_plus    = row[0] or 0
        two_to_four  = row[1] or 0
        one_vid      = row[2] or 0
    except sqlite3.OperationalError:
        aliases = five_plus = two_to_four = one_vid = 0

    unclassified = five_plus + two_to_four + one_vid

    print(f"\nDB: {args.db}")
    print(f"Videos:            {videos:>8,}")
    print(f"Tags:              {total:>8,}  total")
    print(f"  Canonical:       {canonical:>8,}")
    print(f"  Noise:           {noise:>8,}")
    print(f"  Unclassified:    {unclassified:>8,}")
    print(f"    5+ videos:     {five_plus:>8,}  ← primary categorization target")
    print(f"    2-4 videos:    {two_to_four:>8,}  ← secondary pass (suggest --min-videos 2)")
    print(f"    1 video:       {one_vid:>8,}  ← long tail, leave unclassified")
    print(f"Alias rules:       {aliases:>8,}")
    print()


# ── Subcommand: noise ──────────────────────────────────────────────────────

def cmd_noise(args: argparse.Namespace) -> None:
    conn = open_db(args.db)
    ensure_noise_column(conn)

    rows = conn.execute("SELECT id, name FROM tags WHERE is_noise = 0").fetchall()

    by_category: dict[str, list[str]] = {}
    ids_to_mark: list[int] = []
    for row in rows:
        cat = _noise_category(row["name"])
        if cat:
            by_category.setdefault(cat, []).append(row["name"])
            ids_to_mark.append(row["id"])

    total = len(ids_to_mark)
    prefix = "[dry-run] " if args.dry_run else ""
    print(f"\n{prefix}Found {total:,} noise tags:\n")

    for cat in sorted(by_category):
        names = sorted(by_category[cat])
        print(f"  {cat} ({len(names):,}):")
        for name in names[:8]:
            print(f"    {name}")
        if len(names) > 8:
            print(f"    ... and {len(names) - 8} more")
        print()

    if args.dry_run:
        print("[dry-run] No changes written.")
    elif ids_to_mark:
        conn.executemany("UPDATE tags SET is_noise = 1 WHERE id = ?", [(i,) for i in ids_to_mark])
        conn.commit()
        print(f"Done. {total:,} tags marked as noise in {args.db}.")
    else:
        print("Nothing to mark.")


# ── Subcommand: suggest ────────────────────────────────────────────────────

_SUGGEST_SYSTEM = """\
You are organizing tags from a personal YouTube video library into canonical categories.

For each tag you are given: its name, how many videos use it, and a sample of those \
video titles. Use the video titles as your primary signal for understanding what the tag means.

Rules:
1. Assign to EXISTING canonical tags whenever possible — strongly prefer existing over new ones.
2. Only create a NEW canonical if the concept is genuinely not covered by any existing canonical.
3. Do NOT create canonicals for terms that are too broad to be useful for filtering, such as:
   tutorial, lesson, beginner, easy, guide, how to, tips, diy, learn.
   These apply to too many videos to help narrow down a search.
4. Mark as noise: hashtags, year numbers, video quality descriptors (HD/4K), generic words
   (video, watch, subscribe), creator names, collab tags, YouTube category strings.
5. Leave a tag in unassigned if you are not confident where it belongs.
6. Call the categorize_tags tool with your complete analysis.\
"""

_SUGGEST_TOOL = {
    "name": "categorize_tags",
    "description": "Submit the complete categorization of the provided tags.",
    "input_schema": {
        "type": "object",
        "properties": {
            "assignments": {
                "type": "array",
                "description": "Tags mapped to canonical categories.",
                "items": {
                    "type": "object",
                    "properties": {
                        "canonical": {
                            "type": "string",
                            "description": "Canonical tag name — prefer exact name of an existing canonical.",
                        },
                        "members": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Unclassified tag names that belong to this canonical.",
                        },
                        "confidence": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                        },
                    },
                    "required": ["canonical", "members", "confidence"],
                },
            },
            "noise": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags that are noise and should not be canonicalized.",
            },
            "unassigned": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags that couldn't be confidently categorized.",
            },
        },
        "required": ["assignments", "noise", "unassigned"],
    },
}


def _get_video_titles(conn: sqlite3.Connection, tag_name: str) -> list[str]:
    rows = conn.execute("""
        SELECT v.title
        FROM videos v
        JOIN video_tags vt ON vt.video_id_fk = v.id
        JOIN tags t ON t.id = vt.tag_id_fk
        WHERE t.name = ? AND v.title IS NOT NULL
        ORDER BY v.yt_view_count DESC
        LIMIT ?
    """, (tag_name, MAX_TITLE_SAMPLES)).fetchall()
    return [r[0] for r in rows]


def _build_suggest_prompt(canonical_tags: list[dict], batch: list[dict]) -> str:
    lines: list[str] = []
    if canonical_tags:
        lines.append("Existing canonical tags (assign to these first):")
        for t in canonical_tags:
            lines.append(f"  {t['name']} ({t['video_count']} videos)")
    else:
        lines.append("No canonical tags yet — propose new ones as needed.")
    lines.append("")
    lines.append(f"Tags to categorize ({len(batch)} tags with video context):")
    lines.append("")
    for tag in batch:
        count = tag["video_count"]
        lines.append(f'"{tag["name"]}" ({count} video{"s" if count != 1 else ""})')
        for title in tag.get("titles", []):
            lines.append(f"  • {title}")
        lines.append("")
    return "\n".join(lines)


def cmd_suggest(args: argparse.Namespace) -> None:
    try:
        import anthropic
    except ImportError:
        sys.exit("Error: anthropic package not installed.\nRun: pip install anthropic")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("Error: ANTHROPIC_API_KEY environment variable not set.")

    conn = open_db(args.db)
    ensure_noise_column(conn)

    canonical_rows = conn.execute("""
        SELECT t.name, COUNT(DISTINCT vt.video_id_fk) as video_count
        FROM tags t
        LEFT JOIN video_tags vt ON vt.tag_id_fk = t.id
        WHERE t.is_canonical = 1
        GROUP BY t.id, t.name
        ORDER BY t.name
    """).fetchall()
    canonical_tags = [] if args.fresh else [{"name": r["name"], "video_count": r["video_count"]} for r in canonical_rows]
    canonical_names_lower = set() if args.fresh else {t["name"].lower() for t in canonical_tags}

    tag_rows = conn.execute("""
        SELECT t.name, COUNT(vt.video_id_fk) as cnt
        FROM tags t
        JOIN video_tags vt ON vt.tag_id_fk = t.id
        WHERE t.is_canonical = 0 AND t.is_noise = 0
          AND t.name NOT IN (SELECT pattern FROM tag_aliases)
        GROUP BY t.id, t.name
        HAVING cnt >= ?
        ORDER BY cnt DESC
    """, (args.min_videos,)).fetchall()

    if not tag_rows:
        print(f"No unclassified tags with >= {args.min_videos} videos. Nothing to suggest.")
        return

    print(f"\nFetching video context for {len(tag_rows)} tags (>= {args.min_videos} videos)...")
    tags_with_context = []
    for row in tag_rows:
        tags_with_context.append({
            "name": row["name"],
            "video_count": row["cnt"],
            "titles": _get_video_titles(conn, row["name"]),
        })

    client = anthropic.Anthropic(api_key=api_key)
    batches = [
        tags_with_context[i: i + args.batch_size]
        for i in range(0, len(tags_with_context), args.batch_size)
    ]

    print(f"Running {len(batches)} LLM batch{'es' if len(batches) != 1 else ''} "
          f"(model: {args.model})...\n")

    all_proposals: list[dict] = []

    for i, batch in enumerate(batches, 1):
        print(f"  Batch {i}/{len(batches)} ({len(batch)} tags)...", end=" ", flush=True)
        prompt = _build_suggest_prompt(canonical_tags, batch)
        response = client.messages.create(
            model=args.model,
            max_tokens=args.max_tokens,
            system=_SUGGEST_SYSTEM,
            tools=[_SUGGEST_TOOL],
            tool_choice={"type": "tool", "name": "categorize_tags"},
            messages=[{"role": "user", "content": prompt}],
        )
        tool_use = next((b for b in response.content if b.type == "tool_use"), None)
        if tool_use is None:
            print("WARNING: LLM did not call tool — skipping batch.")
            continue

        result = tool_use.input
        batch_groups = 0

        for item in result.get("assignments", []):
            members = [m.strip() for m in item.get("members", []) if m and m.strip()]
            if not members:
                continue
            canonical_name = item["canonical"].strip()
            all_proposals.append({
                "canonical": canonical_name,
                "members": members,
                "confidence": item.get("confidence", "medium"),
                "is_noise": False,
                "is_existing": canonical_name.lower() in canonical_names_lower,
            })
            batch_groups += 1

        noise = [t.strip() for t in result.get("noise", []) if t and t.strip()]
        if noise:
            all_proposals.append({
                "canonical": "_noise",
                "members": noise,
                "confidence": "high",
                "is_noise": True,
                "is_existing": False,
            })
            batch_groups += 1

        print(f"{batch_groups} groups")

    Path(args.output).write_text(json.dumps(all_proposals, indent=2))
    non_noise = [p for p in all_proposals if not p["is_noise"]]
    noise_tags = sum(len(p["members"]) for p in all_proposals if p["is_noise"])
    print(f"\nWrote {len(non_noise)} canonical groups + {noise_tags} noise tags → {args.output}")


# ── Subcommand: review ─────────────────────────────────────────────────────

def cmd_review(args: argparse.Namespace) -> None:
    src = Path(args.proposals_file)
    if not src.exists():
        sys.exit(f"Error: {src} not found.")

    proposals: list[dict] = json.loads(src.read_text())
    if not proposals:
        print("No proposals to review.")
        return

    canonical_proposals = [p for p in proposals if not p.get("is_noise")]
    noise_proposals     = [p for p in proposals if p.get("is_noise")]
    total = len(canonical_proposals) + (1 if noise_proposals else 0)

    approved: list[dict] = []

    print(f"\nReviewing {len(canonical_proposals)} canonical groups + "
          f"{sum(len(p['members']) for p in noise_proposals)} noise tags")
    print("Commands: [a]pprove  [r] <new-name>  [e]dit members  [s]kip  [q]uit\n")

    for seq, proposal in enumerate(canonical_proposals, 1):
        current = {**proposal}  # mutable copy

        while True:
            _print_proposal(current, seq, total)
            try:
                raw = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                _save_approved(approved, args.output)
                return

            cmd = raw.lower()

            if not cmd or cmd == "a":
                approved.append(current)
                print(f"  ✓ {current['canonical']}")
                break

            elif cmd.startswith("r"):
                parts = raw.split(None, 1)
                new_name = parts[1].strip() if len(parts) > 1 else ""
                if not new_name:
                    try:
                        new_name = input("  New name: ").strip()
                    except (EOFError, KeyboardInterrupt):
                        continue
                if new_name:
                    current["canonical"] = new_name
                    current["is_existing"] = False
                    approved.append(current)
                    print(f"  ✓ {new_name}")
                    break

            elif cmd == "e":
                _edit_members(current)

            elif cmd == "s":
                print("  → skipped")
                break

            elif cmd == "q":
                _save_approved(approved, args.output)
                return

            else:
                print("  ? a / r <name> / e / s / q")

    # Noise group — review as one block
    if noise_proposals:
        all_noise: list[str] = []
        for p in noise_proposals:
            all_noise.extend(p["members"])
        noise_group = {"canonical": "_noise", "members": all_noise,
                       "confidence": "high", "is_noise": True, "is_existing": False}

        print(f"\n{'─' * 60}")
        print(f"[{total}/{total}] NOISE TAGS  ({len(all_noise)} tags)")
        print("  Will be marked is_noise=1 (hidden from UI, video associations kept).")
        for j, name in enumerate(all_noise[:20], 1):
            print(f"  {j:3}. {name}")
        if len(all_noise) > 20:
            print(f"  ... and {len(all_noise) - 20} more")

        try:
            raw = input("\n  [a]pprove all / [e]dit / [s]kip > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            raw = "s"

        if not raw or raw == "a":
            approved.append(noise_group)
            print(f"  ✓ {len(all_noise)} noise tags approved")
        elif raw == "e":
            _edit_members(noise_group)
            if noise_group["members"]:
                approved.append(noise_group)
                print(f"  ✓ {len(noise_group['members'])} noise tags approved")
        else:
            print("  → skipped")

    _save_approved(approved, args.output)


def _print_proposal(p: dict, seq: int, total: int) -> None:
    print(f"\n{'─' * 60}")
    kind = "EXISTING" if p.get("is_existing") else "NEW"
    conf = p.get("confidence", "?")
    print(f"[{seq}/{total}] {kind}: {p['canonical']}  [{conf} confidence]")
    print(f"  Members ({len(p['members'])}):")
    for j, m in enumerate(p["members"], 1):
        print(f"  {j:3}. {m}")


def _edit_members(proposal: dict) -> None:
    print("  Enter numbers to REMOVE (space-separated), or Enter to keep all:")
    try:
        raw = input("  Remove: ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if not raw:
        return
    to_remove: set[int] = set()
    for tok in raw.split():
        try:
            to_remove.add(int(tok) - 1)
        except ValueError:
            pass
    proposal["members"] = [m for j, m in enumerate(proposal["members"]) if j not in to_remove]
    print(f"  {len(proposal['members'])} members remaining.")


def _save_approved(approved: list[dict], output: str) -> None:
    Path(output).write_text(json.dumps(approved, indent=2))
    non_noise = [a for a in approved if not a.get("is_noise")]
    noise_tags = sum(len(a["members"]) for a in approved if a.get("is_noise"))
    print(f"\nSaved: {len(non_noise)} canonical groups + {noise_tags} noise tags → {output}")


# ── Subcommand: apply ──────────────────────────────────────────────────────

def cmd_apply(args: argparse.Namespace) -> None:
    src = Path(args.approved_file)
    if not src.exists():
        sys.exit(f"Error: {src} not found.")

    approved: list[dict] = json.loads(src.read_text())
    if not approved:
        print("Nothing to apply.")
        return

    conn = open_db(args.db)
    ensure_noise_column(conn)

    canonical_items = [a for a in approved if not a.get("is_noise")]
    noise_items     = [a for a in approved if a.get("is_noise")]

    # Mark noise tags
    noise_count = 0
    for item in noise_items:
        for name in item.get("members", []):
            cur = conn.execute(
                "UPDATE tags SET is_noise = 1 WHERE name = ? AND is_noise = 0",
                (name.strip(),),
            )
            noise_count += cur.rowcount
    if noise_count:
        conn.commit()

    # Create canonical tags and alias rules
    new_canonicals = 0
    new_aliases = 0

    for item in canonical_items:
        canonical_name = item["canonical"].strip()
        members = [m.strip() for m in item.get("members", []) if m.strip()]
        if not members:
            continue

        existing = conn.execute(
            "SELECT id, is_canonical FROM tags WHERE name = ?", (canonical_name,)
        ).fetchone()
        if existing:
            tag_id = existing["id"]
            if not existing["is_canonical"]:
                conn.execute("UPDATE tags SET is_canonical = 1 WHERE id = ?", (tag_id,))
                new_canonicals += 1
        else:
            cur = conn.execute(
                "INSERT INTO tags (name, is_canonical) VALUES (?, 1)", (canonical_name,)
            )
            tag_id = cur.lastrowid
            new_canonicals += 1

        for member in members:
            cur = conn.execute(
                "INSERT OR IGNORE INTO tag_aliases (pattern, match_type, canonical_tag_id) "
                "VALUES (?, 'exact', ?)",
                (member, tag_id),
            )
            new_aliases += cur.rowcount

    conn.commit()

    # Retroactive apply — use webapp.db if available, else inline
    print("Running retroactive apply...", end=" ", flush=True)
    try:
        from webapp.db import retroactive_apply
        assoc_count = retroactive_apply(conn)
    except ImportError:
        assoc_count = _retroactive_apply_inline(conn)
    conn.commit()
    print(f"{assoc_count:,} new associations")

    print(f"\nDB: {args.db}")
    print(f"  Canonical tags created/promoted: {new_canonicals:>6,}")
    print(f"  Alias rules added:               {new_aliases:>6,}")
    print(f"  Noise tags marked:               {noise_count:>6,}")
    print(f"  Retroactive associations:        {assoc_count:>6,}")


def _retroactive_apply_inline(conn: sqlite3.Connection) -> int:
    """Fallback if webapp.db is not importable."""
    rules = conn.execute(
        "SELECT ta.pattern, ta.match_type, ta.canonical_tag_id "
        "FROM tag_aliases ta JOIN tags t ON t.id = ta.canonical_tag_id"
    ).fetchall()
    total = 0
    for rule in rules:
        pattern, match_type, ctag_id = rule["pattern"], rule["match_type"], rule["canonical_tag_id"]
        p = pattern.lower()
        esc = p.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        if match_type == "exact":
            cur = conn.execute("""
                INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk)
                SELECT DISTINCT vt.video_id_fk, ?
                FROM video_tags vt JOIN tags t ON t.id = vt.tag_id_fk
                WHERE LOWER(t.name) = ?
            """, (ctag_id, p))
        elif match_type == "prefix":
            cur = conn.execute("""
                INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk)
                SELECT DISTINCT vt.video_id_fk, ?
                FROM video_tags vt JOIN tags t ON t.id = vt.tag_id_fk
                WHERE LOWER(t.name) LIKE ? ESCAPE '\\'
            """, (ctag_id, esc + "%"))
        elif match_type == "contains":
            cur = conn.execute("""
                INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk)
                SELECT DISTINCT vt.video_id_fk, ?
                FROM video_tags vt JOIN tags t ON t.id = vt.tag_id_fk
                WHERE LOWER(t.name) LIKE ? ESCAPE '\\'
            """, (ctag_id, "%" + esc + "%"))
        else:
            continue
        total += cur.rowcount
    return total


# ── Argument parsing ───────────────────────────────────────────────────────

def _db_arg(parser: argparse.ArgumentParser, default: str = DEFAULT_DB) -> None:
    parser.add_argument(
        "--db", default=default, metavar="PATH",
        help=f"SQLite DB path (default: {default})",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tag_categorizer",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_stats = sub.add_parser("stats", help="Show tag counts and frequency breakdown")
    _db_arg(p_stats)

    p_noise = sub.add_parser("noise", help="Auto-mark known noise patterns")
    _db_arg(p_noise)
    p_noise.add_argument("--dry-run", action="store_true", help="Preview without writing")

    p_suggest = sub.add_parser("suggest", help="LLM-driven categorization → proposals.json")
    _db_arg(p_suggest)
    p_suggest.add_argument(
        "--min-videos", type=int, default=DEFAULT_MIN_VIDEOS, metavar="N",
        help=f"Min video count to include a tag (default: {DEFAULT_MIN_VIDEOS})",
    )
    p_suggest.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE, metavar="N",
        help=f"Tags per LLM batch (default: {DEFAULT_BATCH_SIZE})",
    )
    p_suggest.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Anthropic model ID (default: {DEFAULT_MODEL})",
    )
    p_suggest.add_argument(
        "--output", default="proposals.json", metavar="FILE",
        help="Output file (default: proposals.json)",
    )
    p_suggest.add_argument(
        "--fresh", action="store_true",
        help="Ignore existing canonical tags — LLM proposes everything from scratch",
    )
    p_suggest.add_argument(
        "--max-tokens", type=int, default=4096, metavar="N",
        help="Max output tokens per LLM call (default: 4096)",
    )

    p_review = sub.add_parser("review", help="Interactive review of proposals → approved.json")
    p_review.add_argument("proposals_file", metavar="PROPOSALS_FILE")
    p_review.add_argument(
        "--output", default="approved.json", metavar="FILE",
        help="Output file (default: approved.json)",
    )

    p_apply = sub.add_parser("apply", help="Write approved changes to DB")
    p_apply.add_argument("approved_file", metavar="APPROVED_FILE")
    _db_arg(p_apply)

    args = parser.parse_args()

    dispatch = {
        "stats":   cmd_stats,
        "noise":   cmd_noise,
        "suggest": cmd_suggest,
        "review":  cmd_review,
        "apply":   cmd_apply,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()

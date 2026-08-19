# Demo Seed Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give a fresh clone of ViewTube a one-command way to see a fully-populated app —
real public YouTube content, fabricated personal-engagement data — with zero network calls
at seed time.

**Architecture:** A standalone script (`scripts/seed_demo_db.py`) builds a fresh SQLite file
by calling existing, already-tested `webapp.db` functions — no new DB-layer functions, no
new routes. A shell wrapper (`demo.sh`) seeds-if-missing and runs the server. A new README
section documents the one-command path.

**Tech Stack:** Python 3.12+, sqlite3, existing `webapp.db` / `crawler.datastore` /
`crawler.models` modules. No new dependencies.

## Global Constraints

- No new functions in `webapp/db.py` or `webapp/routes.py` — the seed script only calls
  existing public functions, with one documented exception: `date_added`,
  `personal_view_count`, and `date_last_viewed` have no public setter for arbitrary
  (backdated) values — every existing function either uses `datetime.now()` or increments by
  1. The seed script sets these three columns via direct `UPDATE` statements against the
  `sqlite3.Connection` it already holds. This is a deliberate, narrow exception: there is no
  legitimate reason for the real app to ever let something set an arbitrary past view
  count/date, so no public setter should be added for it.
- `demo.db` is never committed — already covered by the `viewtube*.db*` `.gitignore` pattern.
  Only `scripts/seed_demo_db.py` and `demo.sh` are checked in.
- All video/channel content data (IDs, titles, durations, view counts, channel IDs/URLs) is
  real and was verified with `yt-dlp` on 2026-08-19 — see
  `docs/superpowers/specs/2026-08-19-demo-seed-data-design.md` for the source list. Use the
  exact values embedded in the tasks below; do not re-derive or re-fetch them.
- `viewtube-web` itself is not modified — no `--demo` flag, no new CLI surface on the webapp
  side. Running the demo is `viewtube-web --db demo.db --port 8080`, identical to the real
  path.
- Use US spelling throughout (project-wide rule) — e.g. "favorite," "organize," "canonical" —
  matches column names already in the schema.

---

### Task 1: Seed script — schema bootstrap + content layer (channels, videos)

**Files:**
- Create: `scripts/seed_demo_db.py`
- Create: `tests/scripts/__init__.py`
- Test: `tests/scripts/test_seed_demo_db.py`
- Modify: `pyproject.toml` (add `scripts` to the coverage flags, matching the existing
  `tools` entry)

**Interfaces:**
- Produces: `seed_content(conn: sqlite3.Connection, videos: list[dict]) -> None` — inserts
  all channels and videos. Consumed by Task 2's `main()` wiring and by this task's own CLI
  entry point.
- Produces: `CHANNELS: dict[str, tuple[str, str]]` (channel_name → (channel_id, channel_url))
  and `VIDEOS: list[dict]` (44 entries, keys: `video_id`, `title`, `channel_name`,
  `duration_seconds`, `yt_view_count`) — Task 2 imports both to build the engagement layer.
- Produces: `ANCHOR: datetime` — a fixed anchor timestamp (not `datetime.now()`) so seeded
  dates are deterministic and reproducible across runs/tests. Task 2 reuses this same anchor
  for engagement-layer date math so all seeded dates are relative to one fixed point.
- Produces: `bootstrap_schema(db_path: str) -> None` — creates the base tables (via
  `crawler.datastore._SCHEMA`) then the webapp extension tables (via
  `webapp.db.init_webapp_tables`), matching the exact pattern already used in
  `tests/webapp/conftest.py::_setup_db`.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/__init__.py` (empty file, matches the `tests/webapp/__init__.py` /
`tests/crawler/__init__.py` package pattern).

Create `tests/scripts/test_seed_demo_db.py`:

```python
import sqlite3
import pytest
from scripts.seed_demo_db import bootstrap_schema, seed_content, VIDEOS, CHANNELS, run


@pytest.fixture
def conn(tmp_path):
    db_path = str(tmp_path / "demo.db")
    bootstrap_schema(db_path)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    yield connection
    connection.close()


class TestSeedContent:
    def test_inserts_all_videos(self, conn):
        seed_content(conn, VIDEOS)
        count = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        assert count == 44

    def test_inserts_all_channels(self, conn):
        seed_content(conn, VIDEOS)
        count = conn.execute("SELECT COUNT(*) FROM channels").fetchone()[0]
        assert count == len(CHANNELS)
        assert count == 12

    def test_video_ids_are_real_youtube_ids(self, conn):
        seed_content(conn, VIDEOS)
        row = conn.execute(
            "SELECT title, channel_name, yt_view_count FROM videos WHERE video_id = ?",
            ("dQw4w9WgXcQ",),
        ).fetchone()
        assert row["channel_name"] == "Rick Astley"
        assert row["yt_view_count"] == 1805594426

    def test_date_added_is_spread_not_all_today(self, conn):
        seed_content(conn, VIDEOS)
        dates = [r[0] for r in conn.execute("SELECT date_added FROM videos").fetchall()]
        assert len(set(dates)) > 1  # not all the same instant


class TestRunCli:
    def test_refuses_to_overwrite_without_force(self, tmp_path):
        db_path = tmp_path / "demo.db"
        db_path.write_text("not a real db")  # simulate an existing file
        with pytest.raises(SystemExit):
            run(["--output", str(db_path)])

    def test_force_overwrites_existing_file(self, tmp_path):
        db_path = tmp_path / "demo.db"
        db_path.write_text("not a real db")
        run(["--output", str(db_path), "--force"])
        connection = sqlite3.connect(str(db_path))
        count = connection.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        connection.close()
        assert count == 44
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/scripts/test_seed_demo_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts'` (or `No module named
'scripts.seed_demo_db'`) — the module doesn't exist yet.

- [ ] **Step 3: Write the implementation**

Create `scripts/seed_demo_db.py`:

```python
#!/usr/bin/env python3
"""Seed a fresh SQLite file with real public YouTube content and fabricated
personal-engagement data, for a one-command "try it now" ViewTube demo.
"""
import argparse
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crawler.datastore import _SCHEMA as _CRAWLER_SCHEMA
from crawler.models import ChannelMetadata, FetchStatus
from webapp.db import add_video, init_webapp_tables, upsert_channel

ANCHOR = datetime(2026, 8, 19, tzinfo=timezone.utc)

# channel_name -> (channel_id, channel_url). Real, verified via `yt-dlp` on 2026-08-19.
CHANNELS: dict[str, tuple[str, str]] = {
    "freeCodeCamp.org": ("UC8butISFwT-Wl7EV0hUK0BQ", "https://www.youtube.com/@freecodecamp"),
    "Bon Appétit": ("UCbpMy0Fg74eXXkvxJrtEn3w", "https://www.youtube.com/@bonappetit"),
    "JustinGuitar": ("UCBNkm8o5LiEVLxO8w0p2sfQ", "https://www.youtube.com/@justinguitar"),
    "Rick Astley": ("UCuAXFkgsw1L7xaCfnd5JJOw", "https://www.youtube.com/@RickAstleyYT"),
    "officialpsy": ("UCrDkAvwZum-UTjHmzDI2iIw", "https://www.youtube.com/@officialpsy"),
    "TV Norge": ("UCYM3pKj9tFQOXc2XcJmj8Vg", "https://www.youtube.com/@tvnorge"),
    "Kurzgesagt – In a Nutshell": ("UCsXVk37bltHxD1rDPwtNM8Q", "https://www.youtube.com/@kurzgesagt"),
    "TED": ("UCAuUUnT6oDeKwE6v1NGQxug", "https://www.youtube.com/@TED"),
    "NASA": ("UCLA_DiR1FfKNvjuUpBHmylQ", "https://www.youtube.com/@NASA"),
    "NASA Jet Propulsion Laboratory": ("UCryGec9PdUCLjpJW2mgCuLw", "https://www.youtube.com/@NASAJPL"),
    "National Geographic": ("UCpVm7bg6pXKo1Pr6k5kxG9A", "https://www.youtube.com/@NatGeo"),
    "Steve Ramsey - Woodworking for Mere Mortals": ("UCBB7sYb14uBtk8UqSQYc9-w", "https://www.youtube.com/@SteveRamsey"),
}

# 44 real videos. Real, verified via `yt-dlp` on 2026-08-19 — see
# docs/superpowers/specs/2026-08-19-demo-seed-data-design.md for the source table.
VIDEOS: list[dict] = [
    {"video_id": "rfscVS0vtbw", "title": "Learn Python - Full Course for Beginners [Tutorial]", "channel_name": "freeCodeCamp.org", "duration_seconds": 16012, "yt_view_count": 49122814},
    {"video_id": "HXV3zeQKqGY", "title": "SQL Tutorial - Full Database Course for Beginners", "channel_name": "freeCodeCamp.org", "duration_seconds": 15639, "yt_view_count": 20888367},
    {"video_id": "i_LwzRVP7bg", "title": "Machine Learning for Everybody – Full Course", "channel_name": "freeCodeCamp.org", "duration_seconds": 14033, "yt_view_count": 10291171},
    {"video_id": "bMknfKXIFA8", "title": "React Course - Beginner's Tutorial for React JavaScript Library [2022]", "channel_name": "freeCodeCamp.org", "duration_seconds": 42927, "yt_view_count": 4266110},
    {"video_id": "916GWv2Qs08", "title": "HTML Tutorial - Website Crash Course for Beginners", "channel_name": "freeCodeCamp.org", "duration_seconds": 2719, "yt_view_count": 664733},
    {"video_id": "n8mNX2YqkUs", "title": "Learn JavaScript Interactively in NEW freeCodeCamp.org Curriculum", "channel_name": "freeCodeCamp.org", "duration_seconds": 3206, "yt_view_count": 100453},
    {"video_id": "a_iQb1lnAEQ", "title": "Learn HTML & CSS – Full Course for Beginners", "channel_name": "freeCodeCamp.org", "duration_seconds": 19304, "yt_view_count": 932945},
    {"video_id": "OXGznpKZ_sA", "title": "CSS Tutorial – Full Course for Beginners", "channel_name": "freeCodeCamp.org", "duration_seconds": 40090, "yt_view_count": 2945708},
    {"video_id": "g1GFJxVeH9c", "title": "Pastry Chef Attempts to Make Gourmet Instant Ramen | Gourmet Makes | Bon Appétit", "channel_name": "Bon Appétit", "duration_seconds": 1532, "yt_view_count": 12341661},
    {"video_id": "mvDj7DF1jsk", "title": "Pastry Chef Attempts to Make Gourmet M&M's | Gourmet Makes | Bon Appétit", "channel_name": "Bon Appétit", "duration_seconds": 2411, "yt_view_count": 6638849},
    {"video_id": "Xi28pEbMdTw", "title": "Pastry Chef Attempts to Make Gourmet Tater Tots | Gourmet Makes | Bon Appétit", "channel_name": "Bon Appétit", "duration_seconds": 2304, "yt_view_count": 6096692},
    {"video_id": "FyMWRcVTGAI", "title": "Pastry Chef Attempts to Make Gourmet Ben & Jerry's Ice Cream | Bon Appétit", "channel_name": "Bon Appétit", "duration_seconds": 1780, "yt_view_count": 7070664},
    {"video_id": "O1JDBt6WE7A", "title": "6 Pro Chefs Make Their Favorite 15-Minute Meal | Test Kitchen Talks | Bon Appétit", "channel_name": "Bon Appétit", "duration_seconds": 1132, "yt_view_count": 3471143},
    {"video_id": "lF2sKFnuALw", "title": "Pro Chefs Make Their Favorite Sandwiches | Test Kitchen Talks | Bon Appétit", "channel_name": "Bon Appétit", "duration_seconds": 1357, "yt_view_count": 7233139},
    {"video_id": "KUHp3ve4m50", "title": "Brad Makes Fermented Citrus Fruits | It's Alive | Bon Appétit", "channel_name": "Bon Appétit", "duration_seconds": 1468, "yt_view_count": 4015353},
    {"video_id": "YGpK6U56oHM", "title": "Brad Makes Beef Jerky | It's Alive | Bon Appétit", "channel_name": "Bon Appétit", "duration_seconds": 1093, "yt_view_count": 7381390},
    {"video_id": "_QCt3UBTS1Y", "title": "JustinGuitar Beginner Course Grade 1 Introduction", "channel_name": "JustinGuitar", "duration_seconds": 75, "yt_view_count": 1396839},
    {"video_id": "BI3S9xSK8Iw", "title": "How to Pass JustinGuitar Beginners Course Grade 1", "channel_name": "JustinGuitar", "duration_seconds": 483, "yt_view_count": 185267},
    {"video_id": "zfBkJggF9aU", "title": "Welcome to Module 2: Rhythm & Chord Change Essentials + Your First Riff!", "channel_name": "JustinGuitar", "duration_seconds": 169, "yt_view_count": 333147},
    {"video_id": "G-X1RemAzks", "title": "Minor Pentatonic Scale - Stage 7 Guitar Lesson - Guitar For Beginners [BC-176]", "channel_name": "JustinGuitar", "duration_seconds": 327, "yt_view_count": 781016},
    {"video_id": "eaUbs13xBl0", "title": "How to Change Acoustic Guitar Strings (Step-by-Step Guide)", "channel_name": "JustinGuitar", "duration_seconds": 1515, "yt_view_count": 203261},
    {"video_id": "ihlDFZjNM6g", "title": "No Tuner? Learn How to Tune Your Guitar by Ear (using Harmonics!)", "channel_name": "JustinGuitar", "duration_seconds": 355, "yt_view_count": 60135},
    {"video_id": "XiOJRhikCBg", "title": "How often should you REALLY change your guitar strings?", "channel_name": "JustinGuitar", "duration_seconds": 515, "yt_view_count": 52000},
    {"video_id": "y5D3jMuCipk", "title": "How to change strings on electric guitars (PRS/locking tuners/strat-style)", "channel_name": "JustinGuitar", "duration_seconds": 1274, "yt_view_count": 30190},
    {"video_id": "dQw4w9WgXcQ", "title": "Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)", "channel_name": "Rick Astley", "duration_seconds": 213, "yt_view_count": 1805594426},
    {"video_id": "9bZkp7q19f0", "title": "PSY - GANGNAM STYLE(강남스타일) M/V", "channel_name": "officialpsy", "duration_seconds": 252, "yt_view_count": 6032168341},
    {"video_id": "jofNR_WkoCE", "title": "Ylvis - The Fox (What Does The Fox Say?) [Official music video HD]", "channel_name": "TV Norge", "duration_seconds": 225, "yt_view_count": 1206159962},
    {"video_id": "h6fcK_fRYaI", "title": "The Egg - A Short Story", "channel_name": "Kurzgesagt – In a Nutshell", "duration_seconds": 486, "yt_view_count": 36078996},
    {"video_id": "sNhhvQGsMEc", "title": "The Fermi Paradox — Where Are All The Aliens? (1/2)", "channel_name": "Kurzgesagt – In a Nutshell", "duration_seconds": 380, "yt_view_count": 35291620},
    {"video_id": "1fQkVqno-uI", "title": "The Fermi Paradox II — Solutions and Ideas – Where Are All The Aliens?", "channel_name": "Kurzgesagt – In a Nutshell", "duration_seconds": 377, "yt_view_count": 17192728},
    {"video_id": "iG9CE55wbtY", "title": "Do schools kill creativity? | Sir Ken Robinson | TED", "channel_name": "TED", "duration_seconds": 1203, "yt_view_count": 24913231},
    {"video_id": "4czjS9h4Fpg", "title": "Perseverance Rover's Descent and Touchdown on Mars (Official NASA Video)", "channel_name": "NASA", "duration_seconds": 205, "yt_view_count": 17916318},
    {"video_id": "wE-aQO9XD1g", "title": "NASA's Perseverance Rover's First 360 View of Mars (Official)", "channel_name": "NASA Jet Propulsion Laboratory", "duration_seconds": 60, "yt_view_count": 7147132},
    {"video_id": "FlpstXNjImY", "title": "Historic Apollo 11 Moon Landing Footage", "channel_name": "NASA", "duration_seconds": 1746, "yt_view_count": 2586458},
    {"video_id": "l24FBVeu3Z4", "title": "Great White Sharks | National Geographic", "channel_name": "National Geographic", "duration_seconds": 149, "yt_view_count": 78436},
    {"video_id": "JvzoijD2YaY", "title": "A woodworker's guide to installing keyhole hangers. They aren't hard.", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "duration_seconds": 317, "yt_view_count": 29585},
    {"video_id": "QLSYADN_BzM", "title": "2026 BEGINNERS' GUIDE to the TOOLS and SUPPLIES you need to start a woodworking hobby", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "duration_seconds": 921, "yt_view_count": 28953},
    {"video_id": "F5oV9FoAKHM", "title": "Finding simplicity in woodworking. And life.", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "duration_seconds": 818, "yt_view_count": 25153},
    {"video_id": "3lzPv_iHEyQ", "title": "6 Simple Ways to Reset Your Workshop and Enjoy It Even More", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "duration_seconds": 495, "yt_view_count": 58447},
    {"video_id": "V7u78RQxjPg", "title": "The myth of \"fine woodworking\" and joinery", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "duration_seconds": 949, "yt_view_count": 96886},
    {"video_id": "SIzDi6pSD4U", "title": "They Say Not to Do This… But It Works. (Finishing technique.)", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "duration_seconds": 460, "yt_view_count": 155325},
    {"video_id": "JgLVfwRltZY", "title": "Simple, sturdy picture frame with splined corner miters", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "duration_seconds": 776, "yt_view_count": 78157},
    {"video_id": "C28ghmZVvd0", "title": "Modifying my standing workstation", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "duration_seconds": 462, "yt_view_count": 61849},
    {"video_id": "IcQxYrNNDcg", "title": "Simple garden hose storage container. LIMITED TOOLS NEEDED!", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "duration_seconds": 643, "yt_view_count": 89404},
]


def bootstrap_schema(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(_CRAWLER_SCHEMA)  # base tables: videos, tags, video_tags, channels
    conn.close()
    init_webapp_tables(db_path)  # webapp extension tables + column migrations


def _channel_metadata(name: str) -> ChannelMetadata:
    channel_id, channel_url = CHANNELS[name]
    # No avatar image: thumbnail_url stays None so the UI falls back to the existing
    # .no-thumb placeholder, sidestepping the yt3.googleusercontent.com rate-limit risk.
    return ChannelMetadata(
        channel_id=channel_id, channel_name=name, channel_url=channel_url,
        description=None, subscriber_count=None, thumbnail_url=None,
        fetch_status=FetchStatus.OK,
    )


def seed_content(conn: sqlite3.Connection, videos: list[dict]) -> None:
    for name in {v["channel_name"] for v in videos}:
        upsert_channel(conn, _channel_metadata(name))

    for i, v in enumerate(videos):
        add_video(
            conn,
            video_id=v["video_id"],
            url=f"https://www.youtube.com/watch?v={v['video_id']}",
            title=v["title"],
            channel_name=v["channel_name"],
            channel_id=CHANNELS[v["channel_name"]][0],
            yt_view_count=v["yt_view_count"],
            duration_seconds=v["duration_seconds"],
            thumbnail_url=f"https://i.ytimg.com/vi/{v['video_id']}/hqdefault.jpg",
        )
        # add_video always stamps date_added=now(); backdate it here so the library
        # looks like it grew over time rather than everything arriving in one instant.
        # No public setter exists for an arbitrary date_added — see Global Constraints.
        date_added = (ANCHOR - timedelta(days=10 + i * 14)).isoformat()
        conn.execute(
            "UPDATE videos SET date_added = ? WHERE video_id = ?",
            (date_added, v["video_id"]),
        )
    conn.commit()


def run(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Seed a ViewTube demo database.")
    parser.add_argument("--output", required=True, help="Path to write the demo database")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing file")
    args = parser.parse_args(argv)

    output_path = Path(args.output)
    if output_path.exists() and not args.force:
        print(
            f"Error: {output_path} already exists. Pass --force to regenerate it.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if output_path.exists():
        output_path.unlink()

    bootstrap_schema(str(output_path))
    conn = sqlite3.connect(str(output_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    seed_content(conn, VIDEOS)
    conn.close()
    print(f"Seeded {output_path} with {len(VIDEOS)} videos.")


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/scripts/test_seed_demo_db.py -v`
Expected: PASS for `TestSeedContent` and `TestRunCli`.

- [ ] **Step 5: Add `scripts` to coverage config**

In `pyproject.toml`, change:

```toml
addopts = "--cov=crawler --cov=webapp --cov=tools --cov-report=term-missing"
```

to:

```toml
addopts = "--cov=crawler --cov=webapp --cov=tools --cov=scripts --cov-report=term-missing"
```

- [ ] **Step 6: Run the full suite and commit**

Run: `python -m pytest -q`
Expected: all tests pass, including the new ones.

```bash
git add scripts/seed_demo_db.py tests/scripts/__init__.py tests/scripts/test_seed_demo_db.py pyproject.toml
git commit -m "feat: add demo seed script content layer (channels, videos)"
```

---

### Task 2: Seed script — engagement layer (tags, favorites, watch later, hidden, view history)

**Files:**
- Modify: `scripts/seed_demo_db.py`
- Modify: `tests/scripts/test_seed_demo_db.py`

**Interfaces:**
- Consumes: `ANCHOR`, `CHANNELS`, `VIDEOS`, `bootstrap_schema`, `seed_content` from Task 1.
- Produces: `seed_tags(conn: sqlite3.Connection) -> None` — creates the tag groups,
  canonical tags, and unclassified (non-canonical) tags, and associates them with videos.
- Produces: `seed_engagement(conn: sqlite3.Connection) -> None` — sets favorites, watch
  later queue (in order), hidden videos, and view history (`is_watched`,
  `personal_view_count`, `date_last_viewed`).
- Modifies: `run()` to call `seed_tags` and `seed_engagement` after `seed_content`.

- [ ] **Step 1: Write the failing test**

Add to `tests/scripts/test_seed_demo_db.py` (new imports: `seed_tags, seed_engagement`
alongside the existing `from scripts.seed_demo_db import ...` line):

```python
class TestSeedTags:
    def test_creates_three_tag_groups(self, conn):
        seed_content(conn, VIDEOS)
        seed_tags(conn)
        count = conn.execute("SELECT COUNT(*) FROM tag_groups").fetchone()[0]
        assert count == 3

    def test_creates_twelve_canonical_tags(self, conn):
        seed_content(conn, VIDEOS)
        seed_tags(conn)
        count = conn.execute(
            "SELECT COUNT(*) FROM tags WHERE is_canonical = 1"
        ).fetchone()[0]
        assert count == 12

    def test_leaves_some_tags_unclassified(self, conn):
        seed_content(conn, VIDEOS)
        seed_tags(conn)
        count = conn.execute(
            "SELECT COUNT(*) FROM tags WHERE is_canonical = 0"
        ).fetchone()[0]
        assert count == 5  # sql, guitar-maintenance, space, woodworking, workshop

    def test_every_video_has_at_least_one_tag(self, conn):
        seed_content(conn, VIDEOS)
        seed_tags(conn)
        untagged = conn.execute("""
            SELECT COUNT(*) FROM videos v
            WHERE NOT EXISTS (
                SELECT 1 FROM video_tags vt WHERE vt.video_id_fk = v.id
            )
        """).fetchone()[0]
        assert untagged == 0


class TestSeedEngagement:
    def test_six_favorites(self, conn):
        seed_content(conn, VIDEOS)
        seed_engagement(conn)
        count = conn.execute(
            "SELECT COUNT(*) FROM videos WHERE is_favorite = 1"
        ).fetchone()[0]
        assert count == 6

    def test_eight_videos_in_watch_later_in_order(self, conn):
        seed_content(conn, VIDEOS)
        seed_engagement(conn)
        rows = conn.execute("""
            SELECT v.video_id FROM watch_later w
            JOIN videos v ON v.id = w.video_id_fk
            ORDER BY w.position
        """).fetchall()
        assert [r[0] for r in rows] == [
            "rfscVS0vtbw", "g1GFJxVeH9c", "_QCt3UBTS1Y", "h6fcK_fRYaI",
            "4czjS9h4Fpg", "JvzoijD2YaY", "i_LwzRVP7bg", "O1JDBt6WE7A",
        ]

    def test_three_hidden_videos(self, conn):
        seed_content(conn, VIDEOS)
        seed_engagement(conn)
        count = conn.execute(
            "SELECT COUNT(*) FROM videos WHERE is_hidden = 1"
        ).fetchone()[0]
        assert count == 3

    def test_view_history_has_a_real_spread(self, conn):
        seed_content(conn, VIDEOS)
        seed_engagement(conn)
        rows = conn.execute(
            "SELECT date_last_viewed FROM videos WHERE personal_view_count > 0"
        ).fetchall()
        assert len(rows) == 16
        dates = sorted(r[0] for r in rows)
        oldest = datetime.fromisoformat(dates[0])
        newest = datetime.fromisoformat(dates[-1])
        assert (newest - oldest).days > 400  # a real pool, not 1-2 eligible videos
```

Add `from datetime import datetime` to the test file's imports (needed for the last test).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/scripts/test_seed_demo_db.py -v`
Expected: FAIL with `ImportError: cannot import name 'seed_tags'` (and `seed_engagement`).

- [ ] **Step 3: Write the implementation**

Add to `scripts/seed_demo_db.py` (new imports: extend the existing
`from webapp.db import ...` line to add `add_canonical_to_group, add_to_watch_later,
add_video_tag, create_canonical_tag, create_tag, create_tag_group, hide_video, set_favorite,
set_watched`):

```python
# Tag groups -> canonical tag names.
TAG_GROUPS: dict[str, list[str]] = {
    "Coding & Tech": ["python", "machine-learning", "javascript", "web-dev"],
    "Cooking": ["baking", "home-cooking", "chef-technique"],
    "Guitar & Music": ["beginner-guitar", "guitar-technique", "music-video"],
}

# Canonical tags that exist but aren't in any group yet (realistic incremental tagging).
UNGROUPED_CANONICAL_TAGS = ["science-explainer", "nature-documentary"]

# canonical tag name -> video_ids it applies to.
CANONICAL_TAG_VIDEOS: dict[str, list[str]] = {
    "python": ["rfscVS0vtbw"],
    "machine-learning": ["i_LwzRVP7bg"],
    "javascript": ["bMknfKXIFA8", "n8mNX2YqkUs"],
    "web-dev": ["916GWv2Qs08", "a_iQb1lnAEQ", "OXGznpKZ_sA"],
    "baking": ["g1GFJxVeH9c", "mvDj7DF1jsk", "Xi28pEbMdTw", "FyMWRcVTGAI"],
    "home-cooking": ["O1JDBt6WE7A", "lF2sKFnuALw"],
    "chef-technique": ["KUHp3ve4m50", "YGpK6U56oHM"],
    "beginner-guitar": ["_QCt3UBTS1Y", "BI3S9xSK8Iw", "zfBkJggF9aU", "G-X1RemAzks"],
    "guitar-technique": ["eaUbs13xBl0", "ihlDFZjNM6g", "y5D3jMuCipk"],
    "music-video": ["dQw4w9WgXcQ", "9bZkp7q19f0", "jofNR_WkoCE"],
    "science-explainer": ["h6fcK_fRYaI", "sNhhvQGsMEc", "1fQkVqno-uI", "iG9CE55wbtY"],
    "nature-documentary": ["l24FBVeu3Z4"],
}

# Non-canonical tag name -> video_ids it applies to. These sit in the "unclassified" pool
# on the /tags page (real tags, never promoted to canonical) — gives the tagging UI
# something to do, and mirrors how a real library accumulates raw, uncategorized tags.
UNCLASSIFIED_TAG_VIDEOS: dict[str, list[str]] = {
    "sql": ["HXV3zeQKqGY"],
    "guitar-maintenance": ["XiOJRhikCBg"],
    "space": ["4czjS9h4Fpg", "wE-aQO9XD1g", "FlpstXNjImY"],
    "woodworking": ["JvzoijD2YaY", "QLSYADN_BzM", "F5oV9FoAKHM", "V7u78RQxjPg", "JgLVfwRltZY"],
    "workshop": ["3lzPv_iHEyQ", "SIzDi6pSD4U", "C28ghmZVvd0", "IcQxYrNNDcg"],
}

FAVORITE_VIDEO_IDS = [
    "dQw4w9WgXcQ", "h6fcK_fRYaI", "rfscVS0vtbw", "V7u78RQxjPg", "l24FBVeu3Z4", "KUHp3ve4m50",
]

# Order matters: add_to_watch_later assigns position by call order.
WATCH_LATER_VIDEO_IDS = [
    "rfscVS0vtbw", "g1GFJxVeH9c", "_QCt3UBTS1Y", "h6fcK_fRYaI",
    "4czjS9h4Fpg", "JvzoijD2YaY", "i_LwzRVP7bg", "O1JDBt6WE7A",
]

HIDDEN_VIDEO_IDS = ["n8mNX2YqkUs", "YGpK6U56oHM", "XiOJRhikCBg"]

# Previously-watched videos, spread from 2 weeks to ~17 months ago so the Rediscover
# shelf has a real least-recently-viewed pool to draw from, not 1-2 eligible videos.
WATCHED_VIDEO_IDS = [
    "rfscVS0vtbw", "g1GFJxVeH9c", "_QCt3UBTS1Y", "h6fcK_fRYaI", "4czjS9h4Fpg",
    "JvzoijD2YaY", "i_LwzRVP7bg", "O1JDBt6WE7A", "dQw4w9WgXcQ", "9bZkp7q19f0",
    "V7u78RQxjPg", "l24FBVeu3Z4", "KUHp3ve4m50", "eaUbs13xBl0", "sNhhvQGsMEc",
    "3lzPv_iHEyQ",
]


def seed_tags(conn: sqlite3.Connection) -> None:
    for group_name, tag_names in TAG_GROUPS.items():
        group_id = create_tag_group(conn, group_name)
        for tag_name in tag_names:
            tag_id = create_canonical_tag(conn, tag_name)
            add_canonical_to_group(conn, group_id, tag_id)
            for video_id in CANONICAL_TAG_VIDEOS[tag_name]:
                add_video_tag(conn, video_id, tag_id)

    for tag_name in UNGROUPED_CANONICAL_TAGS:
        tag_id = create_canonical_tag(conn, tag_name)
        for video_id in CANONICAL_TAG_VIDEOS[tag_name]:
            add_video_tag(conn, video_id, tag_id)

    for tag_name, video_ids in UNCLASSIFIED_TAG_VIDEOS.items():
        tag_id = create_tag(conn, tag_name)
        for video_id in video_ids:
            add_video_tag(conn, video_id, tag_id)


def seed_engagement(conn: sqlite3.Connection) -> None:
    for video_id in FAVORITE_VIDEO_IDS:
        set_favorite(conn, video_id, True)

    for video_id in WATCH_LATER_VIDEO_IDS:
        add_to_watch_later(conn, video_id)

    for video_id in HIDDEN_VIDEO_IDS:
        hide_video(conn, video_id)

    for j, video_id in enumerate(WATCHED_VIDEO_IDS):
        set_watched(conn, video_id, True)
        view_count = 1 + (j % 4)
        date_last_viewed = (ANCHOR - timedelta(days=14 + j * 33)).isoformat()
        # No public setter for an arbitrary personal_view_count/date_last_viewed —
        # see Global Constraints at the top of this plan.
        conn.execute(
            "UPDATE videos SET personal_view_count = ?, date_last_viewed = ? "
            "WHERE video_id = ?",
            (view_count, date_last_viewed, video_id),
        )
    conn.commit()
```

Update `run()` to call the new functions after `seed_content`:

```python
    seed_content(conn, VIDEOS)
    seed_tags(conn)
    seed_engagement(conn)
    conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/scripts/test_seed_demo_db.py -v`
Expected: PASS for all `TestSeedTags` and `TestSeedEngagement` tests.

- [ ] **Step 5: Run the full suite and commit**

Run: `python -m pytest -q`
Expected: all tests pass.

```bash
git add scripts/seed_demo_db.py tests/scripts/test_seed_demo_db.py
git commit -m "feat: add demo seed script engagement layer (tags, favorites, watch later)"
```

---

### Task 3: `demo.sh` wrapper + README "Try it with sample data" section

**Files:**
- Create: `demo.sh`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `plan-webapp.md`

**Interfaces:**
- Consumes: `scripts/seed_demo_db.py`'s CLI (`--output`, `--force`) from Tasks 1-2, and the
  existing `viewtube-web --db <path> --port <port>` CLI.

This task has no new Python logic to unit-test — `demo.sh` is a thin shell wrapper around
two already-tested pieces (the seed script and `viewtube-web`), and README/changelog edits
are prose. Verification here is manual (Step 3 below), matching how the project has no
existing shell-script test harness (`tools/tag_categorizer.py` is likewise untested by
`pytest` — it's exercised through `webapp/db.py` function tests instead).

- [ ] **Step 1: Write `demo.sh`**

Create `demo.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [ ! -f demo.db ]; then
    echo "No demo.db found — seeding one now..."
    python scripts/seed_demo_db.py --output demo.db
fi

echo "Starting ViewTube demo at http://localhost:8080"
viewtube-web --db demo.db --port 8080
```

Run: `chmod +x demo.sh`

- [ ] **Step 2: Add the README section**

In `README.md`, insert a new section immediately after the "## Setup" section (before
"## Ingest your bookmarks"):

````markdown
## Try it with sample data

Want to see it running before pointing it at your own bookmarks? This seeds a database with
~50 real, public YouTube videos across a mix of topics (coding tutorials, cooking, guitar
lessons, science explainers, and more) — real titles/thumbnails/view counts, but the
favorites/watch-later/tags/watch-history are all fabricated demo data, not anyone's real
activity.

```bash
./demo.sh
```

Open http://localhost:8080. To reset back to a clean demo state:

```bash
python scripts/seed_demo_db.py --output demo.db --force
```
````

- [ ] **Step 3: Manually verify the wrapper end to end**

Run: `./demo.sh`
Expected: prints "No demo.db found — seeding one now...", then "Seeded demo.db with 44
videos.", then starts the server. Visit `http://localhost:8080` and confirm: the main list
shows real video thumbnails/titles, the Watch Later page shows 8 videos in the seeded order,
6 videos show as favorited, the Rediscover shelf is populated, and `/tags` shows the 3 tag
groups plus an unclassified pool. Stop the server (Ctrl-C), then run `./demo.sh` again and
confirm it does NOT reseed (goes straight to "Starting ViewTube demo...").

- [ ] **Step 4: Update `plan-webapp.md`**

Add a short paragraph to `plan-webapp.md` (in whichever section documents onboarding/setup,
or a new "Demo data" subsection if none exists) noting: `scripts/seed_demo_db.py` builds a
demo database from real, hardcoded public YouTube content with a fabricated personal-
engagement layer (favorites, watch-later, tags, view history); `demo.sh` wraps seed-if-
missing + run; `demo.db` is gitignored, only the seed script is committed.

- [ ] **Step 5: Update `CHANGELOG.md`**

Append an entry dated 2026-08-19: added `scripts/seed_demo_db.py` and `demo.sh` for a
one-command demo path with real public YouTube content and a fabricated engagement layer;
trade-off — the video list is a fixed snapshot verified 2026-08-19, so view counts will
drift and any individual video could eventually be taken down (mitigated by the list being
structured as easily-swappable data, not scattered inline literals).

- [ ] **Step 6: Commit**

```bash
git add demo.sh README.md plan-webapp.md CHANGELOG.md
git commit -m "docs: add demo.sh wrapper and README fast-path section"
```

---

## Final verification

- [ ] Run `python -m pytest -q` — full suite passes.
- [ ] Run `./demo.sh` from a clean checkout (no `demo.db` present) and confirm the manual
  verification checklist in Task 3, Step 3.
- [ ] Confirm `git status` shows `demo.db` as untracked/ignored, not staged.

# Airchivist Crawler — Implementation Plan

## Overview

The crawler is a standalone CLI tool that reads a Firefox bookmarks export file (JSON or HTML), extracts every YouTube URL it finds, fetches video metadata from `yt-dlp` (with optional YouTube Data API v3 for faster batch mode), and writes the results to a SQLite datastore. It is designed to be re-run incrementally: videos already stored are updated in-place, not duplicated.

---

## Technology Choices

| Concern | Choice | Rationale |
|---|---|---|
| Language | Python 3.12+ | Required |
| CLI parsing | `argparse` (stdlib) | No extra dependency; well-understood |
| Bookmark HTML parsing | `beautifulsoup4` | Firefox HTML export is Netscape bookmark format; bs4 handles it robustly |
| Bookmark JSON parsing | `json` (stdlib) | Firefox JSON export is straightforward nested structure |
| YouTube metadata | `yt-dlp` (primary) + `google-api-python-client` (optional) | `yt-dlp` requires no API key; Google API used when key is supplied for higher rate limits |
| Datastore | SQLite via `sqlite3` (stdlib) | Zero-configuration, file-based, readable by the web component |
| HTTP requests | `requests` | Simple, widely understood |
| Testing | `pytest` + `pytest-cov` + `pytest-mock` | Standard TDD tooling |
| Date/time | `datetime` (stdlib) | Timestamp handling |

---

## File Structure

```
airchivist/
├── crawler/
│   ├── __init__.py
│   ├── cli.py                  # argparse entry point
│   ├── bookmark_parser.py      # Firefox bookmark file parsing (JSON & HTML)
│   ├── metadata_fetcher.py     # YouTube metadata retrieval (yt-dlp / API)
│   ├── datastore.py            # SQLite schema creation and CRUD
│   └── models.py               # Dataclasses: Bookmark, VideoMetadata
├── tests/
│   └── crawler/
│       ├── __init__.py
│       ├── fixtures/
│       │   ├── sample_bookmarks.json
│       │   ├── sample_bookmarks.html
│       │   └── sample_yt_response.json
│       ├── test_bookmark_parser.py
│       ├── test_metadata_fetcher.py
│       ├── test_datastore.py
│       ├── test_cli.py
│       └── test_integration.py
├── pyproject.toml          # deps, dev extras (`.[dev]`), pytest + ruff + mypy config
└── requirements.txt        # runtime deps plus the optional `anthropic` extra
```

---

## Tooling gates

Three gates, all runnable from a clean `pip install -e ".[dev]"`:
`ruff check .`, `mypy`, and `python -m pytest -q`. `ruff` selects `F` (pyflakes),
`I` (import sorting), and `UP` (pyupgrade), so annotations are PEP 604
(`str | None`, never `Optional[str]`) and `datetime.UTC` replaces
`timezone.utc` — both enforced mechanically rather than by review.

`mypy` runs over `webapp` and `crawler` (not `tests` or `scripts`) with
`warn_redundant_casts`, `warn_unused_ignores`, and `warn_unreachable` rather
than `--strict`: the codebase is partly annotated, and `--strict` would report
hundreds of findings with no path to green. It must print `Success` with **no
notes** — an `annotation-unchecked` note means mypy silently skipped a function
body because it had no annotations, which is a gate that isn't checking.
`anthropic` (optional at runtime) and `yt_dlp` (no published stubs) are declared
in a `[[tool.mypy.overrides]]` block rather than as inline `type: ignore`s, so
the pre-commit hook — whose venv has neither — agrees with a local run that does.

Both linters also run as pre-commit hooks, each pinned to the same version as
the `dev` extras; `tests/webapp/test_api.py::TestToolingPinsAgree` fails if a
pair drifts. The mypy hook runs with `pass_filenames: false` so its scope comes
from `pyproject.toml` rather than from whichever files happen to be staged.

Both connection paths set `journal_mode = WAL` (persistent; applied in `webapp/db/schema.py` and `crawler/datastore.py` so whichever opens a database first converts it).

## Data Model / SQLite Schema

### Table: `videos`

```sql
CREATE TABLE IF NOT EXISTS videos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id            TEXT    NOT NULL UNIQUE,   -- YouTube video ID (e.g. dQw4w9WgXcQ)
    url                 TEXT    NOT NULL,
    title               TEXT,
    description         TEXT,
    channel_name        TEXT,
    channel_id          TEXT,
    yt_view_count       INTEGER,                   -- YouTube's public view count (from crawler)
    personal_view_count INTEGER NOT NULL DEFAULT 0, -- times user clicked the link in the webapp
    duration_seconds    INTEGER,
    thumbnail_url       TEXT,
    date_added          TEXT,                      -- ISO-8601, from bookmark metadata
    date_last_viewed    TEXT,                      -- ISO-8601, set by webapp on each click; NULL until first view
    date_published      TEXT,                      -- ISO-8601, from YouTube metadata
    fetch_status        TEXT    DEFAULT 'pending', -- pending | ok | error | private | deleted
    fetch_error         TEXT,
    last_fetched_at     TEXT                       -- ISO-8601
);
```

### Table: `tags`

```sql
CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
```

### Table: `video_tags`

```sql
CREATE TABLE IF NOT EXISTS video_tags (
    video_id_fk INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    tag_id_fk   INTEGER NOT NULL REFERENCES tags(id)   ON DELETE CASCADE,
    PRIMARY KEY (video_id_fk, tag_id_fk)
);
```

### Design Notes

- `video_id` is the 11-character YouTube ID extracted from the URL — the natural de-duplication key.
- `yt_view_count` is YouTube's public view count, fetched by the crawler and refreshed on each crawler run.
- `personal_view_count` and `date_last_viewed` are owned entirely by the webapp. The crawler inserts them as `0` / `NULL` and **never overwrites them** on subsequent runs. This requires an `INSERT ... ON CONFLICT DO UPDATE SET` upsert (not `INSERT OR REPLACE`, which would delete and reinsert the row, resetting these values).
- `date_added` comes from Firefox bookmark metadata (`ADD_DATE`).
- `fetch_status` tracks the last API attempt so the crawler can skip unreachable videos without crashing.
- The `tags` / `video_tags` tables are populated by the crawler from YouTube's own `categories` and `tags` fields, giving every video a default set of tags on first crawl. The webapp can add further tags on top. Tag names are shared across videos — two videos with the same YouTube category share one `tags` row.

---

## Firefox Bookmark Format Reference

### JSON Export (`bookmarks.json`)

Firefox exports a deeply nested tree. Leaf nodes with `typeCode: 1` are bookmarks:

```json
{
  "type": "text/x-moz-url",
  "uri": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "title": "Rick Astley - Never Gonna Give You Up",
  "dateAdded": 1700000000000000,
  "lastModified": 1700100000000000
}
```

- `dateAdded` is **microseconds** since the Unix epoch.
- The tree is traversed recursively to find all leaf bookmark nodes.

### HTML Export (`bookmarks.html`)

Netscape Bookmark File Format stores bookmarks as `<DT><A>` elements:

```html
<DT><A HREF="https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    ADD_DATE="1700000000">Rick Astley - Never Gonna Give You Up</A>
```

- `ADD_DATE` is **seconds** since the Unix epoch.

---

## YouTube Video ID Extraction

A regex covers all common URL forms:

```
(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})
```

Bookmark URLs that do not match are silently skipped.

---

## Metadata Fetching Strategy

### Primary: `yt-dlp`

`yt-dlp` is invoked as a Python library using `yt_dlp.YoutubeDL`. The returned info dict provides: `title`, `description`, `uploader`, `channel_id`, `view_count` (mapped to `yt_view_count`), `duration`, `thumbnail`, `upload_date`, `categories` (YouTube's category, e.g. `["Music"]`), and `tags` (creator-defined tags, e.g. `["guitar", "tutorial"]`).

Rate limiting: the crawler processes videos sequentially with a configurable `--delay` argument (default 1.5 s) to avoid YouTube bot detection.

**Channel metadata (`fetch_channel_metadata`).** Channels are fetched with `extract_flat` (avoids iterating the channel's videos). Unlike videos, yt-dlp does **not** set the singular `thumbnail` field for a channel — the avatar is in the `thumbnails` list alongside the wide banner. `_pick_channel_thumbnail` selects the avatar (uncropped avatar entry → largest square thumbnail → any thumbnail), never the banner.

**Backfill (`--backfill-channels` / `get_channel_ids_for_backfill`).** Selects channels needing a (re)fetch: video channels with no row or an incomplete row (`description IS NULL OR thumbnail_url IS NULL`), UNIONed with any `channels` row that is itself incomplete. The UNION is what lets backfill reach **bookmark-only** channels (no saved videos), which the video-join half cannot see. Each is re-fetched by constructing `https://www.youtube.com/channel/<id>` and upserting by `channel_id`.

### Optional: YouTube Data API v3

When `--api-key` is supplied, the crawler uses `google-api-python-client` to call `videos.list` with `part=snippet,statistics`. Supports batch requests of up to 50 video IDs per call — significantly faster than `yt-dlp`. `statistics.viewCount` maps to `yt_view_count`.

### Error Handling for Metadata

| Scenario | Behavior |
|---|---|
| Private/deleted video | `DownloadError` caught; `fetch_status` set to `'private'` or `'deleted'` |
| Network error | Caught, logged, `fetch_status = 'error'` with message in `fetch_error` |
| Any single video failure | Crawler always continues to the next video |

---

## Metadata Refresh (Nightly)

**Goal:** keep already-stored videos' YouTube-owned fields (view count,
title, thumbnail, etc.) from going stale forever, without a second full
crawl of the bookmarks file.

`crawler.refresh.run_refresh(ds, limit, delay, fetch=fetch_metadata)` is the
run loop: it asks `Datastore.get_stale_video_ids(limit)` for the least
recently refreshed video IDs (never-fetched rows first), calls `fetch` for
each one, and hands the result to `Datastore.refresh_video`, which applies
the update-or-preserve behavior described under Phase 3 above. It takes no
bookmarks file and no `Bookmark` — every video it touches is already in the
library, so there is nothing new to record about when it was added.

`fetch` is a keyword parameter defaulting to the real `fetch_metadata`
specifically so tests can inject a stub without patching a module global —
the run loop's own logic (selection, exception containment, tallying) is
what needs testing, not yt-dlp or the network.

**One video's failure never aborts the run.** `fetch_metadata` already
converts yt-dlp's own errors into a `fetch_status` (`private`, `deleted`,
`error`), but a bare network or OS error propagates as a real exception.
`run_refresh` catches broad `Exception` around each `fetch` call, logs it,
tallies it under a `"failed"` key (not a `FetchStatus` member — no *status*
is written to that video's row), and moves to the next video. This is a
deliberate trade-off for a job that runs unattended at 3am: a narrower
`except` would be more precise about what it catches, but the failure mode
of catching too little — one transient error stopping the library being
maintained at all, discoverable only by reading a log nobody reads — is far
worse than the failure mode of catching too much.

The failed row is not left completely untouched: `run_refresh` calls
`Datastore.mark_fetch_attempted(video_id)`, which bumps `last_fetched_at`
and deliberately writes neither `fetch_status` nor `fetch_error` (a bare
network error says nothing about the video, so the last status that *was*
determined stays put). Changed 2026-09-26; previously the row was untouched
entirely. `last_fetched_at` is also the selection cursor for
`get_stale_video_ids`, so not bumping it parked a deterministically failing
video — a URL yt-dlp chokes on, a permanent 403 — at the head of the queue
on every run forever. At `limit` such videos the rotation stops completely
and nothing else is ever refreshed again, with the only symptom a summary
line reading `refreshed 200 of 2959 (200 failed)`. The trade-off was ruled
explicitly: not bumping risks unbounded harm (a stalled rotation), bumping
risks a bounded, self-correcting one (an outage spanning one run pushes up
to `limit` videos to the back of a ~15-day rotation, losing no data and
misreporting nothing). There is still no separate retry logic — a failed
video is simply re-examined when its turn comes round again.

The run produces a `RefreshSummary` (`attempted`, `library_total`, `counts`
keyed by `fetch_status` string values plus `"failed"`, `elapsed_seconds`).
Its `line()` method is the entire user interface of this feature — for the
launchd job below, one line in a log file is all anyone will ever see:

```
refreshed 200 of 2958 (196 ok, 3 deleted, 1 private) in 5m12s
```

Elapsed time reads as plain seconds under a minute (`4s`) and as
zero-padded `MmSSs` at a minute or more (`5m12s`), so both a quick spot
check and an overnight run render as one glance-able token instead of a
raw float.

### Scheduling

`scripts/com.airchivist.refresh.plist` is a `launchd` template that runs
`airchivist-crawler refresh --db <path>` daily at 3am. It is opt-in: the
file ships with the repo but is never installed or loaded automatically —
a user copies it to `~/Library/LaunchAgents/`, replaces the two `/REPLACE/`
placeholders (the absolute path to the installed `airchivist-crawler` and
to their database) and the log path, then loads it with `launchctl load`.
`RunAtLoad` is `false` on purpose, so installing the job doesn't
immediately kick off a multi-minute run. `StandardOutPath` and
`StandardErrorPath` both point at the same log file, so `RefreshSummary.line()`
is the entire log — one line per night, no logging framework needed.

Absolute paths are mandatory and non-negotiable: launchd performs no shell
expansion (`~` is a literal directory name) and a launchd job does not
inherit an interactive `PATH` (so a bare `airchivist-crawler` is never
found). Either mistake produces a job that loads without error and simply
never runs. `tests/scripts/test_refresh_plist.py` parses the plist with
`plistlib` and asserts every non-flag `ProgramArguments` entry starts with
`/`, so a regression here is caught by `pytest` rather than by a silent
missed night.

---

## CLI Interface Design

`crawler/cli.py` has two subcommands, `ingest` and `refresh`, plus a
backward-compatibility shim so the bare form documented since before
subcommands existed keeps working verbatim: `-i`/`-o` (and the other ingest
flags) also live on the *top-level* parser, and a command line with no
subcommand token dispatches to `_run_ingest`. `main()` only parses and
dispatches; `_run_ingest(args)` and `_run_refresh(args)` hold the actual work,
extracted so the top-level parser, the `ingest` subparser, and the `refresh`
subparser can each be built from shared `_add_common_args`/`_add_ingest_args`
helpers without duplicating flag definitions.

```
Usage: airchivist-crawler [OPTIONS] [-i FILE -o FILE]          # implicit ingest
       airchivist-crawler ingest [OPTIONS] -i FILE -o FILE     # explicit ingest
       airchivist-crawler refresh [OPTIONS] --db FILE

Common options (all three forms):
  --api-key KEY          YouTube Data API v3 key (enables faster batch mode)
  --delay SECONDS        Seconds between yt-dlp requests (default: 1.5)
  --log-level LEVEL      DEBUG | INFO | WARNING | ERROR (default: INFO)
  -h, --help             Show this message and exit

Ingest-only options (top-level and `ingest`):
  -i, --input FILE       Path to Firefox bookmarks file (.json or .html)
  -o, --output FILE      Path to output SQLite database file
  --limit N              Only process the first N YouTube bookmarks
  --force-refresh        Re-fetch metadata even for already-stored videos
  --backfill-channels    Fetch full metadata for channels that only have stub records

Refresh-only options:
  --db FILE              Path to the existing SQLite database [required]
  --limit N              How many of the stalest videos to refresh (default: 200)

Exit codes:
  0   Success
  1   Input file not found (ingest) / database not found (refresh)
  2   Input file format unrecognized, or -i/-o missing (top-level form: a
      custom guard in `_run_ingest`; explicit `ingest` form: argparse's own
      required-argument error) — same code, different mechanism
  3   Database error (ingest)
```

`-i`/`-o` are `required=False` at the top level so a bare
`airchivist-crawler` with neither flag reaches `_run_ingest` instead of
argparse's own usage error; `_run_ingest` checks for both and exits 2 with
`Error: -i/--input and -o/--output are required for ingest` — the same exit
code argparse itself would have used, so the observable behavior for a typo
is unchanged. The `ingest` and `refresh` subparsers keep their own
`required=True` where it applies (both ingest flags; `--db` for refresh),
so `airchivist-crawler ingest` (or `refresh`) with a flag missing still gets
argparse's own error message and exit 2.

`refresh` takes `--db` rather than `-i`/`-o` because it has one database it
both reads (to pick the stalest videos) and writes (to store what it
fetched) — there is no separate input file to name. Its own `--limit` means
"how many stalest videos to refresh" and is unrelated to ingest's `--limit`
("only process the first N bookmarks"); they are defined once each, on their
own subparser, and never share a definition despite the same flag name.

Example invocations:

```bash
# Firefox JSON export, no API key — implicit ingest, unchanged since before subcommands
airchivist-crawler -i ~/Downloads/bookmarks.json -o ~/airchivist.db

# Same, explicit
airchivist-crawler ingest -i ~/Downloads/bookmarks.json -o ~/airchivist.db

# HTML export with API key
airchivist-crawler -i ~/Downloads/bookmarks.html -o ~/airchivist.db --api-key AIza...

# Dry-run: first 10 videos only
airchivist-crawler -i ~/Downloads/bookmarks.json -o /tmp/test.db --limit 10

# Refresh the 200 stalest videos already in the database
airchivist-crawler refresh --db ~/airchivist.db

# Refresh only the 5 stalest, with no inter-request delay (e.g. in a test)
airchivist-crawler refresh --db ~/airchivist.db --limit 5 --delay 0
```

---

## Implementation Phases

### Phase 0: Project Scaffolding

**Goal:** Directory layout, dependency files, and a working test runner before any feature code.

Steps:
1. Create `pyproject.toml` with project metadata, entry point `airchivist-crawler = "crawler.cli:main"`, and `pytest` config.
2. Create `requirements.txt`: `yt-dlp`, `beautifulsoup4`, `requests`, `google-api-python-client`.
3. Create `requirements-dev.txt`: `pytest`, `pytest-cov`, `pytest-mock`.
4. Create all `__init__.py` files and empty module stubs so imports resolve.
5. Verify `pytest` collects zero tests and exits 0.

---

### Phase 1: Data Models

**Goal:** Define `Bookmark` and `VideoMetadata` dataclasses used across all modules.

#### TDD Step 1.1 — Write failing test

File: `tests/crawler/test_models.py`

- `Bookmark` can be constructed from raw Firefox data with `url`, `title`, `date_added`.
- `Bookmark.youtube_video_id` correctly extracts the 11-char ID from various URL forms and returns `None` for non-YouTube URLs.
- `VideoMetadata` raises `ValueError` if `yt_view_count` is negative.
- `VideoMetadata.yt_categories` and `yt_tags` default to independent empty lists (mutable default safety via `field(default_factory=list)`).

Run `pytest tests/crawler/test_models.py` — fails with `ModuleNotFoundError`.

#### TDD Step 1.2 — Implement

File: `crawler/models.py`

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import re

_YT_ID_RE = re.compile(
    r'(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)'
    r'([A-Za-z0-9_-]{11})'
)

@dataclass
class Bookmark:
    url: str
    title: str
    date_added: Optional[datetime] = None

    @property
    def youtube_video_id(self) -> Optional[str]:
        m = _YT_ID_RE.search(self.url)
        return m.group(1) if m else None

@dataclass
class VideoMetadata:
    video_id: str
    url: str
    title: Optional[str] = None
    description: Optional[str] = None
    channel_name: Optional[str] = None
    channel_id: Optional[str] = None
    yt_view_count: Optional[int] = None       # YouTube's public view count
    duration_seconds: Optional[int] = None
    thumbnail_url: Optional[str] = None
    date_published: Optional[datetime] = None
    yt_categories: list[str] = field(default_factory=list)  # e.g. ["Music"]
    yt_tags: list[str] = field(default_factory=list)        # creator-defined tags
    fetch_status: str = 'pending'
    fetch_error: Optional[str] = None

    def __post_init__(self):
        if self.yt_view_count is not None and self.yt_view_count < 0:
            raise ValueError("yt_view_count must be non-negative")
```

Run `pytest tests/crawler/test_models.py` — all pass.

---

### Phase 2: Firefox Bookmark Parser

**Goal:** Parse both JSON and HTML Firefox exports into a list of `Bookmark` objects.

#### TDD Step 2.1 — Write failing tests

File: `tests/crawler/test_bookmark_parser.py`

Create fixture files:

`tests/crawler/fixtures/sample_bookmarks.json` — nested Firefox JSON with:
- One YouTube URL at depth 3
- One non-YouTube URL (included as `Bookmark` with `youtube_video_id = None`)
- One `youtu.be` shortlink
- Correct `dateAdded` in microseconds

`tests/crawler/fixtures/sample_bookmarks.html` — same three URLs with `ADD_DATE` in seconds.

Tests to write:

```
test_parse_json_returns_bookmark_list
test_parse_json_finds_nested_youtube_urls
test_parse_json_converts_microsecond_timestamps
test_parse_json_handles_missing_dates_gracefully
test_parse_json_handles_shortlink_url
test_parse_html_returns_bookmark_list
test_parse_html_finds_all_youtube_urls
test_parse_html_converts_second_timestamps
test_detect_format_json
test_detect_format_html
test_detect_format_unknown_raises
```

Run `pytest tests/crawler/test_bookmark_parser.py` — fails with `ImportError`.

#### TDD Step 2.2 — Implement

File: `crawler/bookmark_parser.py`

Key decisions:
- `parse(path: Path) -> list[Bookmark]`: detects format by extension; raises `ValueError` for unknown extensions.
- JSON path: recursive `_walk_json(node, results)` checks `typeCode == 1` for leaf nodes, recurses into `children`.
- HTML path: `html.parser.HTMLParser` subclass captures `<a>` tag attributes.
- Timestamp helpers: `_us_to_datetime(us)` (microseconds) and `_s_to_datetime(s)` (seconds).

Run `pytest tests/crawler/test_bookmark_parser.py` — all pass.

---

### Phase 3: SQLite Datastore

**Goal:** Create the database schema and all CRUD operations the crawler needs.

#### TDD Step 3.1 — Write failing tests

File: `tests/crawler/test_datastore.py`

Use `tmp_path` pytest fixture for a temporary database per test.

Tests to write:

```
test_init_db_creates_tables
test_init_db_is_idempotent
test_upsert_video_inserts_new_row
test_upsert_video_updates_yt_view_count_on_rerun
test_upsert_video_does_not_duplicate
test_upsert_video_preserves_personal_view_count_on_rerun
test_upsert_video_preserves_date_last_viewed_on_rerun
test_upsert_creates_tags_from_yt_categories
test_upsert_creates_tags_from_yt_tags
test_upsert_combines_categories_and_tags
test_upsert_auto_tagging_is_idempotent_on_rerun
test_upsert_skips_empty_tag_names
test_upsert_no_tags_when_lists_empty
test_shared_tags_across_videos
test_get_video_by_id_returns_correct_row
test_get_video_by_id_returns_none_for_missing
test_get_all_videos_returns_list
test_get_all_videos_returns_empty_for_empty_db
test_add_tag_creates_tag_row
test_add_tag_is_idempotent
test_tag_video_creates_association
test_tag_video_is_idempotent
test_get_tags_for_video_returns_correct_tags
test_set_fetch_status_updates_row
test_count_videos_returns_correct_count
```

The `test_upsert_video_preserves_*` tests are critical: insert a video, simulate the webapp incrementing `personal_view_count` and setting `date_last_viewed`, then run `upsert_video` again and assert those fields are unchanged. The auto-tagging tests verify that `yt_categories` and `yt_tags` from `VideoMetadata` are written to `tags` / `video_tags` and that repeated upserts do not create duplicate tag associations.

Run `pytest tests/crawler/test_datastore.py` — fails with `ImportError`.

#### TDD Step 3.2 — Implement

File: `crawler/datastore.py`

Key decisions:
- `Datastore` class takes `db_path: Path`, calls `init_db()` in `__init__`.
- `init_db()`: executes `CREATE TABLE IF NOT EXISTS` for all three tables plus an index on `video_id`.
- `upsert_video(metadata, bookmark)`: uses `INSERT INTO ... ON CONFLICT(video_id) DO UPDATE SET` to update only the crawler-owned columns (`url`, `title`, `description`, `channel_name`, `channel_id`, `yt_view_count`, `duration_seconds`, `thumbnail_url`, `date_published`, `fetch_status`, `fetch_error`, `last_fetched_at`). `date_added`, `personal_view_count`, `date_last_viewed`, `is_watched`, `is_favorite`, `is_hidden`, and `date_hidden` are excluded from the `DO UPDATE SET` clause so they are never overwritten by the crawler — those are the user's own data, not YouTube's. Each of the nine descriptive columns (`url`, `title`, `description`, `channel_name`, `channel_id`, `yt_view_count`, `duration_seconds`, `thumbnail_url`, `date_published`) is assigned via `COALESCE(excluded.col, videos.col)` rather than a bare `excluded.col` — `fetch_metadata`'s failure path returns every descriptive field as `None`, so a bare assignment would let a re-run over a bookmarks file containing a since-deleted video NULL out the record of what that video was; a successful fetch always supplies a value, so the `COALESCE` is a no-op on the happy path. (Behavior change, 2026-09-26: previously a failed re-fetch did erase these columns.) After the upsert, `_apply_yt_tags` iterates over `metadata.yt_categories + metadata.yt_tags`, calling `add_tag` (idempotent) and `tag_video` (idempotent) for each non-empty name.
- `refresh_video(metadata)`: the nightly-refresh counterpart to `upsert_video`, used for videos already in the library (no `Bookmark` — there's nothing new to record about when it was added). It is a separate method rather than a call into `upsert_video` because the two have opposite obligations on failure, and because it must not touch tags (below). It branches on `metadata.fetch_status`: anything other than `FetchStatus.OK` writes only `fetch_status`, `fetch_error`, and `last_fetched_at`, leaving every descriptive column untouched. A successful fetch (`FetchStatus.OK`) writes the nine descriptive columns and explicitly clears `fetch_error` to `NULL`, so a video that comes back after being marked deleted doesn't keep a stale error message. Like `upsert_video`, it never touches `date_added`, `personal_view_count`, `date_last_viewed`, `is_watched`, `is_favorite`, `is_hidden`, or `date_hidden` — those are the user's own data. A `video_id` with no matching row is a silent no-op (the `UPDATE` simply matches zero rows).
  - The OK branch splits its columns in two (fixed 2026-09-26; previously it assigned all nine unconditionally). `_COALESCED_COLUMNS` — `url`, `channel_name`, `channel_id`, `yt_view_count`, `duration_seconds`, `thumbnail_url`, `date_published` — go through `COALESCE(?, col)`, because for these "absent" is never meaningful information, so a `None` can only mean the fetch didn't report it. `fetch_status = ok` means `extract_info` did not raise, *not* that every field was populated: `duration_seconds` is `None` for a live stream or scheduled premiere, `yt_view_count` is `None` when the uploader hides counts, and `channel_name` comes from `info.get("uploader")`, which yt-dlp has drifted on across versions and player clients. A blanked `channel_name` is the dangerous case, because the channel `<select>`, `/channels`, group-by-channel and `get_stats` all key on it — the row silently drops out of its channel's filter and count rather than showing as an empty field. `_CLEARABLE_COLUMNS` — `title` and `description` — are assigned through, because those two are exactly the fields a successful fetch can legitimately report as now-empty. So the asymmetry with `upsert_video` narrows to those two fields: `refresh_video` has the fetch's overall status to check first, and `upsert_video` does not.
  - **It deliberately does not apply yt-tags or aliases**, unlike `upsert_video` (fixed 2026-09-26; the original spec called for it and it shipped that way). Tag application is `INSERT OR IGNORE` into `video_tags`, which is idempotent against the database but not against the *user*: the webapp's per-video "remove this tag" action deletes the link, and a re-apply on a ~15-day timer restored every removal — reproduced as `['guitar'] → ['guitar', 'lesson']` after one refresh. Tags belong to ingest, when a video enters the library; picking up genuinely new upstream tags is a separate feature needing its own design (there is deliberately no suppression mechanism).
- All `datetime` values stored as ISO-8601 strings.
- Implements `__enter__`/`__exit__` for context manager usage.
- `get_stale_video_ids(limit)`: the read side of the nightly refresh — the `limit` least-recently-refreshed video IDs, stalest first, ordered by `last_fetched_at ASC`. Never-fetched rows (`last_fetched_at IS NULL`) sort first for free, because SQLite orders `NULL` before any value in an ascending sort — no `NULLS FIRST` needed, and adding it would be redundant with the default. Includes hidden videos and videos already marked `deleted`/`private`: an archived video that gets deleted upstream is exactly the case where keeping the last-known title matters, and a private video can become public again, so nothing is excluded from consideration. A non-positive `limit` returns `[]` before the query runs at all — not defensive boilerplate: SQLite reads `LIMIT -1` as *no limit whatsoever*, so a typo'd or miscomputed negative limit would otherwise refresh the entire library (thousands of videos) in one run instead of nothing.
- `mark_fetch_attempted(video_id)`: writes `last_fetched_at` and deliberately nothing else — not `fetch_status`, not `fetch_error`. Used only by `run_refresh`'s unexpected-exception path, where a bare network or OS error says nothing about the video itself, so the last status that *was* determined must stay put; but `last_fetched_at` is the selection cursor, so it has to move or a repeatably failing video blocks the queue head forever. No-op if the row is absent.
- `count_videos()`: total row count in `videos`, used as the denominator for the refresh run's summary (e.g. "responded to 40 of 2,959").

Run `pytest tests/crawler/test_datastore.py` — all pass.

---

### Phase 4: Metadata Fetcher

**Goal:** Fetch YouTube metadata via `yt-dlp` with graceful handling of unavailable videos.

#### TDD Step 4.1 — Write failing tests

File: `tests/crawler/test_metadata_fetcher.py`

Use `pytest-mock` to patch `yt_dlp.YoutubeDL`.

Tests to write:

```
test_fetch_returns_videometadata_on_success
test_fetch_maps_yt_dlp_fields_correctly        # yt-dlp view_count → yt_view_count
test_fetch_maps_yt_categories                  # info['categories'] → yt_categories
test_fetch_maps_yt_tags                        # info['tags'] → yt_tags
test_yt_categories_defaults_to_empty_list_when_missing
test_yt_tags_defaults_to_empty_list_when_missing
test_yt_categories_handles_none_value
test_fetch_handles_private_video
test_fetch_handles_deleted_video
test_fetch_handles_network_error
test_fetch_sets_fetch_status_ok_on_success
test_fetch_sets_fetch_status_error_on_failure
test_fetch_batch_returns_list_of_metadata
test_fetch_batch_handles_partial_failures
```

Run `pytest tests/crawler/test_metadata_fetcher.py` — fails with `ImportError`.

#### TDD Step 4.2 — Implement

File: `crawler/metadata_fetcher.py`

Key decisions:
- `fetch_metadata(video_id, delay=1.5)`: constructs canonical URL, calls `YoutubeDL.extract_info()`, maps fields (yt-dlp `view_count` → `yt_view_count`, `categories` → `yt_categories`, `tags` → `yt_tags`). Uses `or []` guard so `None` values from yt-dlp become empty lists. Calls `time.sleep(delay)`.
- `upload_date` (yt-dlp YYYYMMDD string) → `datetime.strptime(val, '%Y%m%d')`.
- On `DownloadError`: inspect message for "Private video" → `'private'`, "has been removed" → `'deleted'`, otherwise `'error'`.
- `fetch_metadata_batch(video_ids, api_key)`: maps `statistics.viewCount` → `yt_view_count`; active only when `--api-key` is supplied.

Run `pytest tests/crawler/test_metadata_fetcher.py` — all pass.

---

### Phase 5: CLI Entry Point

**Goal:** Wire all components together behind the `argparse` CLI.

#### TDD Step 5.1 — Write failing tests

File: `tests/crawler/test_cli.py`

Tests to write:

```
test_cli_exits_1_when_input_file_missing
test_cli_exits_2_when_input_format_unknown
test_cli_exits_0_on_valid_json_input
test_cli_exits_0_on_valid_html_input
test_cli_creates_output_db
test_cli_populates_db_with_correct_rows
test_cli_new_rows_have_zero_personal_view_count
test_cli_new_rows_have_null_date_last_viewed
test_cli_limit_flag_restricts_processing
test_cli_force_refresh_flag_re_fetches
test_cli_prints_progress_to_stdout
test_cli_logs_errors_but_continues
```

Run `pytest tests/crawler/test_cli.py` — fails.

#### TDD Step 5.2 — Implement

File: `crawler/cli.py`

```python
def main():
    parser = argparse.ArgumentParser(description='Airchivist Bookmark Crawler')
    parser.add_argument('-i', '--input', required=True, type=Path)
    parser.add_argument('-o', '--output', required=True, type=Path)
    parser.add_argument('--api-key', default=None)
    parser.add_argument('--delay', type=float, default=1.5)
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--force-refresh', action='store_true')
    parser.add_argument('--log-level', default='INFO')
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level)

    if not args.input.exists():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    try:
        bookmarks = parse(args.input)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

    yt_bookmarks = [b for b in bookmarks if b.youtube_video_id]
    if args.limit:
        yt_bookmarks = yt_bookmarks[:args.limit]

    try:
        with Datastore(args.output) as ds:
            for i, bookmark in enumerate(yt_bookmarks, 1):
                print(f"[{i}/{len(yt_bookmarks)}] {bookmark.youtube_video_id}", flush=True)
                vid_id = bookmark.youtube_video_id
                if not args.force_refresh and ds.get_video_by_id(vid_id):
                    logging.info("Skipping already-fetched: %s", vid_id)
                    continue
                if args.api_key:
                    metadata = fetch_metadata_batch([vid_id], args.api_key)[0]
                else:
                    metadata = fetch_metadata(vid_id, delay=args.delay)
                ds.upsert_video(metadata, bookmark)
    except Exception as e:
        logging.error("Database error: %s", e)
        sys.exit(3)
```

Run `pytest tests/crawler/test_cli.py` — all pass.

---

### Phase 6: Integration Test

**Goal:** End-to-end test exercising the full pipeline with a real SQLite file.

File: `tests/crawler/test_integration.py`

```
test_full_pipeline_json_input_produces_correct_db
test_full_pipeline_html_input_produces_correct_db
test_full_pipeline_incremental_run_does_not_duplicate
test_full_pipeline_incremental_run_preserves_personal_view_count
```

Use fixture files, mock `yt-dlp`, call `main()` directly, assert final database row count and field values. The last test simulates a webapp visit (direct DB write), re-runs the crawler, and asserts `personal_view_count` is unchanged.

---

## Error Handling Strategy

| Scenario | Handling |
|---|---|
| Input file not found | `sys.exit(1)` with message to stderr |
| Unknown file extension | `sys.exit(2)` with message to stderr |
| Malformed JSON | Caught, logged, `sys.exit(2)` |
| Malformed HTML | Parser silently skips malformed tags; logged at WARNING |
| Private/deleted video | `fetch_status` set in DB; crawler continues |
| Network timeout | Caught, `fetch_status='error'`, crawler continues |
| DB write failure | Logged, raised to top-level, `sys.exit(3)` |
| API quota exceeded | HTTP 403 detected, logged, graceful stop with partial results |
| Keyboard interrupt | Caught in `main()`, prints "Interrupted. Progress saved." and exits 0 |

---

## `pyproject.toml` Key Sections

```toml
[project]
name = "airchivist"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "yt-dlp",
    "beautifulsoup4",
    "requests",
    "google-api-python-client",
    "flask>=3.0",
]

[project.scripts]
airchivist-crawler = "crawler.cli:main"
airchivist-web = "webapp.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=crawler --cov=webapp --cov-report=term-missing"

[tool.coverage.run]
omit = ["tests/*"]
```

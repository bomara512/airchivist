# ViewTube Crawler — Implementation Plan

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
viewtube/
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
├── pyproject.toml
├── requirements.txt
└── requirements-dev.txt
```

---

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

### Optional: YouTube Data API v3

When `--api-key` is supplied, the crawler uses `google-api-python-client` to call `videos.list` with `part=snippet,statistics`. Supports batch requests of up to 50 video IDs per call — significantly faster than `yt-dlp`. `statistics.viewCount` maps to `yt_view_count`.

### Error Handling for Metadata

| Scenario | Behavior |
|---|---|
| Private/deleted video | `DownloadError` caught; `fetch_status` set to `'private'` or `'deleted'` |
| Network error | Caught, logged, `fetch_status = 'error'` with message in `fetch_error` |
| Any single video failure | Crawler always continues to the next video |

---

## CLI Interface Design

```
Usage: python -m crawler.cli [OPTIONS]

Options:
  -i, --input FILE       Path to Firefox bookmarks file (.json or .html) [required]
  -o, --output FILE      Path to output SQLite database file [required]
  --api-key KEY          YouTube Data API v3 key (enables faster batch mode)
  --delay SECONDS        Seconds between yt-dlp requests (default: 1.5)
  --limit N              Only process the first N YouTube bookmarks
  --force-refresh        Re-fetch metadata even for already-stored videos
  --log-level LEVEL      DEBUG | INFO | WARNING | ERROR (default: INFO)
  -h, --help             Show this message and exit

Exit codes:
  0   Success
  1   Input file not found or unreadable
  2   Input file format unrecognized
  3   Database error
```

Example invocations:

```bash
# Firefox JSON export, no API key
python -m crawler.cli -i ~/Downloads/bookmarks.json -o ~/viewtube.db

# HTML export with API key
python -m crawler.cli -i ~/Downloads/bookmarks.html -o ~/viewtube.db --api-key AIza...

# Dry-run: first 10 videos only
python -m crawler.cli -i ~/Downloads/bookmarks.json -o /tmp/test.db --limit 10
```

---

## Implementation Phases

### Phase 0: Project Scaffolding

**Goal:** Directory layout, dependency files, and a working test runner before any feature code.

Steps:
1. Create `pyproject.toml` with project metadata, entry point `viewtube-crawler = "crawler.cli:main"`, and `pytest` config.
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
- `upsert_video(metadata, bookmark)`: uses `INSERT INTO ... ON CONFLICT(video_id) DO UPDATE SET` to update only the crawler-owned columns (`title`, `description`, `channel_name`, `channel_id`, `yt_view_count`, `duration_seconds`, `thumbnail_url`, `date_published`, `fetch_status`, `fetch_error`, `last_fetched_at`). `personal_view_count` and `date_last_viewed` are excluded from the `DO UPDATE SET` clause so they are never overwritten by the crawler. After the upsert, `_apply_yt_tags` iterates over `metadata.yt_categories + metadata.yt_tags`, calling `add_tag` (idempotent) and `tag_video` (idempotent) for each non-empty name.
- All `datetime` values stored as ISO-8601 strings.
- Implements `__enter__`/`__exit__` for context manager usage.

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
    parser = argparse.ArgumentParser(description='ViewTube Bookmark Crawler')
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
name = "viewtube"
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
viewtube-crawler = "crawler.cli:main"
viewtube-web = "webapp.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=crawler --cov=webapp --cov-report=term-missing"

[tool.coverage.run]
omit = ["tests/*"]
```

# ViewTube Web Interface — Implementation Plan

## Overview

The web interface is a locally-run Flask application that reads from the SQLite datastore produced by the crawler. It presents YouTube bookmarks in a browseable, sortable, filterable, and groupable interface. The app is primarily read-heavy, with two categories of writes: tag management and visit tracking (incrementing personal view count and recording the last viewed date when the user clicks a link).

---

## Technology Choices

| Concern | Choice | Rationale |
|---|---|---|
| Language | Python 3.12+ | Required |
| Web framework | Flask 3.x | Lightweight, excellent Jinja2 integration, trivial to run locally |
| Database access | `sqlite3` (stdlib) | Same file the crawler writes; no ORM needed |
| Frontend interactivity | HTMX | Server-driven partial page updates without a JS framework; no build step |
| HTML templating | Jinja2 (bundled with Flask) | Industry standard for Flask |
| CSS | Plain CSS with CSS custom properties | No build step; responsive grid/flex layout |
| CLI argument | `argparse` (stdlib) | Consistent with the crawler |
| Testing | `pytest` + Flask test client | Flask provides `app.test_client()` for request-level testing without a real server |
| Test coverage | `pytest-cov` | Consistent with the crawler |

---

## File Structure

```
viewtube/
├── webapp/
│   ├── __init__.py
│   ├── app.py                  # Flask application factory
│   ├── cli.py                  # Entry point: parses --db arg, calls create_app()
│   ├── db.py                   # SQLite query and write functions
│   ├── filters.py              # Jinja2 template filters (format_number, format_date)
│   ├── keyword_matcher.py      # Keyword group matching logic
│   └── templates/
│       ├── base.html           # Shared layout, nav, HTMX script tag
│       ├── index.html          # Main bookmarks table/card view
│       ├── _video_row.html     # Partial: single table row (HTMX swap)
│       ├── _video_grid.html    # Partial: card grid view (HTMX swap)
│       ├── _tag_modal.html     # Partial: tag management dialog
│       └── error.html          # Error page (DB not found, etc.)
│   └── static/
│       ├── style.css
│       └── htmx.min.js         # Vendored (no CDN dependency for local use)
├── tests/
│   └── webapp/
│       ├── __init__.py
│       ├── conftest.py          # Fixtures: test Flask app, seeded in-memory SQLite DB
│       ├── test_db.py
│       ├── test_keyword_matcher.py
│       ├── test_routes.py
│       └── test_filters.py
```

---

## Database Layer

`webapp/db.py` contains pure functions — no class, no ORM — that accept a `sqlite3.Connection`. The connection is injected via Flask's `g` object, opened in `before_request` and closed in `teardown_appcontext`.

### Functions in `db.py`

```python
# Read functions
def get_all_videos(conn, sort_by='date_added', sort_dir='desc',
                   channel=None, tag=None, search=None,
                   page=1, page_size=None) -> list[dict]

def count_videos(conn, channel=None, tag=None, search=None) -> int

def get_video_by_id(conn, video_id: str) -> dict | None

def get_all_channels(conn) -> list[str]              # distinct non-null channel_name values, alphabetized

def get_canonical_tags_for_filter(conn) -> list[str] # canonical tag names that have ≥1 video, for the filter dropdown

def get_all_tags(conn) -> list[dict]           # id, name, video_count

def get_tag_keywords(conn, tag_id: int) -> list[str]

def get_tags_with_keywords(conn) -> list[dict]

def get_tags_for_video(conn, video_id: str) -> list[str]

def get_stats(conn) -> dict                    # total_videos, total_channels, fetch_errors, hidden_count

# Write functions
def record_visit(conn, video_id: str) -> None  # increments personal_view_count, sets date_last_viewed

def create_tag(conn, name: str) -> int

def set_tag_keywords(conn, tag_id: int, keywords: list[str]) -> None

def delete_tag(conn, tag_id: int) -> None

def add_video_tag(conn, video_id: str, tag_id: int) -> None

def remove_video_tag(conn, video_id: str, tag_id: int) -> None

def hide_video(conn, video_id: str) -> None
def unhide_video(conn, video_id: str) -> None
def delete_video(conn, video_id: str) -> None        # hard delete; video_tags cascade
def get_hidden_videos(conn, sort_by, sort_dir, page, page_size) -> list[dict]
def count_hidden_videos(conn) -> int

def init_webapp_tables(db_path: str) -> None   # creates webapp extension tables if missing; applies column migrations
def collapse_case_variants(conn) -> int        # one-time admin: merges case-duplicate tags; NOT called at startup

# Constants (enums)
# crawler/models.py: FetchStatus(StrEnum) — PENDING, OK, ERROR, PRIVATE, DELETED
# webapp/db.py:      MatchType(StrEnum)   — EXACT, PREFIX, CONTAINS
```

`get_all_videos` and `count_videos` share a `_build_where` helper that composes the `WHERE` clause and params list from the filter arguments. `fetch_status = 'ok'` and `is_hidden = 0` are always applied as base conditions — hidden videos and videos with any other status are never shown in the main index. `get_all_videos` appends `LIMIT ? OFFSET ?` when `page_size` is not `None`. The `sort_by` column name is validated against `ALLOWED_SORT_COLUMNS` before string interpolation (column names cannot be parameterized in SQLite). `sort_dir` is validated against `{'asc', 'desc'}`.

The `search` filter matches against four sources, all using word-prefix regex (`\bterm`, case-insensitive):
1. `v.title`
2. `v.description`
3. Tag names associated with the video (via `video_tags` → `tags`)
4. Tag keywords associated with the video (via `video_tags` → `tag_keywords`)

So searching "lesson" surfaces videos tagged "guitar" (which has "lesson" as a keyword) even if the word doesn't appear in their title or description. Matching is word-prefix — "prik" will not match "pa**prik**a" (mid-word) but will match "prikling". This requires a Python `regexp` function registered on each SQLite connection via `conn.create_function("regexp", 2, _regexp)` in `app.py`'s `before_request` and in the test fixture's `_make_db`.

```python
ALLOWED_SORT_COLUMNS = frozenset({
    'title', 'channel_name', 'yt_view_count', 'personal_view_count',
    'date_added', 'date_last_viewed', 'date_published'
})
```

`record_visit` is a single atomic SQL statement:

```sql
UPDATE videos
SET personal_view_count = personal_view_count + 1,
    date_last_viewed = ?
WHERE video_id = ?
```

---

## Visit Tracking Flow

When the user clicks a video title or thumbnail in the webapp:

1. The link targets `/visit/<video_id>` (not the YouTube URL directly).
2. The Flask route calls `record_visit(g.db, video_id)`, which increments `personal_view_count` and sets `date_last_viewed` to the current UTC time.
3. The route responds with a `302` redirect to the video's YouTube URL.
4. The browser follows the redirect. Because the link uses `target="_blank"`, YouTube opens in a new tab while the ViewTube page remains open.

This is transparent to the user — the click feels like a direct link — while allowing the app to track every view. The crawler never touches `personal_view_count` or `date_last_viewed`, so re-running the crawler does not reset this data.

---

## Keyword Grouping Design

### How It Works

1. **Tag definitions**: A tag has a name (e.g., "guitar tutorials") and associated keywords (e.g., `["guitar", "tutorial", "lesson", "chord"]`). Tags are stored in the `tags` table shared with the crawler.

2. **Keyword matching**: `keyword_matcher.py` provides `find_matching_tags(video, all_tags_with_keywords)` that checks whether any tag keyword appears in the video's `title` or `description` using word-boundary regex (`\b` + keyword + `\b`, case-insensitive).

3. **Manual override**: The `video_tags` table stores manually confirmed tag associations. The UI offers a "Tag this video" button that opens a modal listing all defined tags.

### Tag Management UI Flow

- **Define tags**: `/tags` page lets the user create tag names with comma-separated keywords.
- **Auto-group view**: `/group/keywords` runs `get_all_videos`, calls `find_matching_tags` for each video, groups results in Python. Videos matching no tags appear in an "Untagged" group.
- **Manual tagging**: POST to `/videos/<video_id>/tags` with `tag_id`; DELETE to `/videos/<video_id>/tags/<tag_id>`.

### `tag_keywords` Table

```sql
CREATE TABLE IF NOT EXISTS tag_keywords (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_id  INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    keyword TEXT    NOT NULL,
    UNIQUE(tag_id, keyword)
);
```

This table is created by the web app on first launch (`init_webapp_tables()`), extending the crawler's schema non-destructively.

---

## Flask Application Factory

`webapp/app.py` exports `create_app(db_path: str) -> Flask`. The factory pattern enables clean test setup.

```python
def create_app(db_path: str) -> Flask:
    app = Flask(__name__)
    app.config['DATABASE'] = db_path

    @app.before_request
    def open_db():
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row

    @app.teardown_appcontext
    def close_db(exc):
        db = g.pop('db', None)
        if db is not None:
            db.close()

    from . import routes
    app.register_blueprint(routes.bp)

    @app.context_processor
    def inject_stats():
        # Makes stats available in all templates (used by base.html header)
        db = g.get("db")
        if db is None:
            return {}
        return {"stats": get_stats(db)}

    from .filters import format_view_count, format_date, format_duration
    app.jinja_env.filters['view_count'] = format_view_count  # compact: 1.5K, 7.65M
    app.jinja_env.filters['date'] = format_date              # compact time-ago: 5d, 2mo, 3yr
    app.jinja_env.filters['duration'] = format_duration

    return app
```

`get_stats` is no longer called in `routes.py` — the context processor handles it globally. The header in `base.html` shows `N videos · N channels` (error count excluded); the toolbar no longer has a summary line.

`sqlite3.Row` as the row factory lets templates access columns by name without converting to dicts.

---

## Routes

All routes are defined in `webapp/routes.py` and registered as a blueprint named `bp`.

| Method | Path | Description |
|---|---|---|
| GET | `/` | Main view: card grid with filter controls; returns `_video_container.html` partial when `HX-Request` header is present |
| GET | `/visit/<video_id>` | Record a view, redirect to YouTube URL |
| GET/POST | `/tags` | Canonical tags admin: create canonical, view/manage aliases, unclassified tag pool, LLM suggestions |
| POST | `/tags/<tag_id>/alias` | Add alias rule to a canonical; runs retroactive apply for that alias only |
| POST | `/tags/<tag_id>/alias/<alias_id>/delete` | Delete an alias rule |
| POST | `/tags/<tag_id>/alias/<alias_id>/edit` | Update alias pattern/match_type; runs retroactive apply for the updated alias |
| POST | `/tags/retroactive` | Re-apply all alias rules to all videos |
| POST | `/tags/suggest/confirm` | Accept LLM suggestion group: create canonical, add aliases, retroactive apply |
| POST | `/tags/llm/suggest` | Trigger LLM suggestion generation |
| POST | `/tags/llm/suggest/<id>/dismiss` | Dismiss a single LLM suggestion card |
| POST | `/videos/<id>/mark-watched` | Calls `record_visit` without redirecting; 404 if video not found; returns 204 |
| POST | `/videos/<id>/rediscover-shelf/remove` | Removes from the active shelf only — does not touch `personal_view_count`/`date_last_viewed`; 404 if video not found; returns 204 |
| POST | `/videos/<id>/hide` | Soft-delete: set `is_hidden = 1`; returns 204 (used by right-click JS and extension) |
| POST | `/videos/<id>/unhide` | Restore hidden video; redirects to `/hidden` |
| POST | `/videos/<id>/delete` | Hard delete; `video_tags` rows cascade; redirects to `/hidden` |
| POST | `/videos/<id>/tags/add` | form `tag_name`; creates or promotes a canonical tag and attaches it to the video; 400 if blank, 404 if video not found; returns rendered tag-pills HTML |
| GET | `/hidden` | Hidden videos management page — Restore and Delete permanently per card |
| GET | `/api/status` | CORS. `?url=<yt_url>` → `{status: not_found\|exists\|hidden, video_id, title}` |
| POST | `/api/hide` | CORS. `{url}` → hides by URL → `{status: "hidden", title}` |
| GET | `/watch-later` | Watch Later queue page, ordered by `position` |
| POST | `/api/watch-later/add` | CORS. `{url}` → adds to end of queue |
| POST | `/api/watch-later/remove` | CORS. `{url}` → removes from queue |
| POST | `/api/watch-later/status` | CORS. `{url}` → `{in_queue: bool}` |
| POST | `/videos/<id>/watch-later/reorder` | `{position}` → moves the video to that 1-indexed position via `reorder_watch_later`; 400 if `position` missing/non-int, 404 if not in queue |

### Tag Groups

A display-only organizational layer stored in `tag_groups` (id, name, sort_order) and `tag_group_members` (group_id, canonical_tag_id). Groups have no effect on video-tag associations or filtering logic — they control only how the canonical tag `<select>` is rendered on the main page.

`get_canonical_tags_for_filter_grouped(conn)` replaces `get_canonical_tags_for_filter` in the index route. It returns `[{name, tags}]` where the last entry has `name=None` for ungrouped canonicals. The index template renders `<optgroup label="…">` for named groups and flat `<option>` elements for the ungrouped tail.

Group management routes (all redirect to `/tags`):
- `POST /tags/groups` — create group
- `POST /tags/groups/<id>/delete` — delete group (cascades to members)
- `POST /tags/groups/<id>/members` — add canonical to group by `canonical_tag_id`
- `POST /tags/groups/<id>/members/<tag_id>/delete` — remove canonical from group

### Tags Admin Page (`tags.html`)

**Canonical tag cards** — each card shows the canonical name, video count, and all alias rules rendered as pills. Alias pills use a right-click context menu (vanilla JS, single shared `<div id="alias-context-menu">`) with two actions:

- **Edit** — replaces the pill inline with an `<input>` + match-type `<select>` + Save/Cancel. Save POSTs to `/tags/<tag_id>/alias/<alias_id>/edit`; page reloads and returns to the top of the canonical list. Cancel restores the pill without a request.
- **Delete** — submits a hidden form POST to `/tags/<tag_id>/alias/<alias_id>/delete`.

Alias pill visual conventions: solid border = prefix match; dashed border = contains match; no border = exact match (most common). Context menu is dismissed on click-outside or Escape.

**Tag groups section** (above canonical tag cards) — create/delete groups; each group card shows member canonical pills with a hover-× remove button and a `<select>` to add a canonical.

**Unclassified tag pool** — tags used on 2+ videos that have no canonical assignment and no alias rule. Rendered as checkbox pills; selecting one or more and typing a canonical name in the assign bar posts to `/tags/suggest/confirm` to create/update the canonical with those aliases.

**LLM suggestions (Smart Suggest)** — grouped suggestion cards above the pool. Each card shows a proposed canonical name (editable) and member tags as checkboxes. Accept posts to `/tags/suggest/confirm`. The unclassified pool's `min_videos` default is 2, hiding the 23K single-video long tail.

---

## UI Design

### Main View (`index.html`)

**Layout**: Responsive card grid. Each card shows thumbnail, title, channel, YT views, date published, and times watched (if > 0). Thumbnail and title both link to `/visit/<video_id>` with `target="_blank" rel="noopener noreferrer"`, opening YouTube in a new tab.

Card layout within `.video-info`:
1. Title (`.video-title`)
2. Channel name (`.video-channel`) — on its own line below the title
3. Metadata row (`.video-meta`) — below the channel: view count · publish date · date added (no labels on either date). Personal view count is shown inline with the YouTube view count as `1,234 [5] views` when > 0, replacing a separate "Watched N×" item.
4. Tag pills (`.video-tags`) — canonical tags only, each linking to `/?tag=<name>` to filter by that tag. Only rendered when the video has at least one canonical tag.

The channel name links to `https://www.youtube.com/channel/<channel_id>` (opens in a new tab); if `channel_id` is absent it renders as plain text. A small funnel icon (`.channel-filter-icon`) sits beside the channel name; clicking it navigates to `/?channel=<name>` (full page load so the channel select in the toolbar reflects the active filter). The icon is dim by default and turns red on hover.

**Duration overlay**: Video duration is displayed as a pill badge in the bottom-right corner of the thumbnail (YouTube-style), using `position: absolute` inside the `position: relative` `.thumb-link`. Only rendered when `duration_seconds` is non-null.

**Filter controls** (above the grid, no Apply button):

All filters live in a single `<form>` wired with HTMX:

```html
<form hx-get="/"
      hx-target="#video-container"
      hx-push-url="true"
      hx-trigger="change from:select, keyup changed delay:300ms from:input[name=search]">
```

- **Search input**: triggers after 300 ms pause in typing (`keyup changed delay:300ms`)
- **Channel / sort-by / sort-dir / group selects**: trigger immediately on `change`
- No Apply button — every change fires automatically
- **Reset link** (`<a href="/">Reset</a>`) outside the form performs a full page navigation to `/`, restoring all controls to their default state

HTMX swaps only `<div id="video-container">`, preserving the toolbar. `hx-push-url="true"` keeps the browser URL in sync so filters are bookmarkable and shareable.

The route returns `_video_container.html` (partial) when the `HX-Request` header is present, or the full `index.html` on a direct load.

The sort select uses human-readable labels (no underscores): Date Added, Title, YouTube Views, Times Watched, Last Viewed, Date Published. Values sent to the server remain the raw column names understood by `get_all_videos`.

A canonical tag `<select name="tag">` is rendered between the channel dropdown and the sort-by dropdown, but only when at least one canonical tag has at least one associated video. Options are populated from `get_canonical_tags_for_filter`. Selecting a tag filters via the existing `?tag=` query param and `_build_where` logic.

**Grouping**: The group select offers "No grouping" (default), "By channel", and "By tag". Both grouped modes use Prev/Next pagination (not Load more).

- **By channel**: `get_all_videos` prepends `channel_name ASC` to the ORDER BY so all same-channel videos are adjacent. The route partitions the page of videos by `channel_name` in Python. Each video belongs to exactly one channel, so groups are clean.
- **By tag**: groups are built in Python from the `tags` field on each video (already limited to canonical tags). A video with multiple canonical tags appears in each relevant section. Groups are sorted alphabetically; videos with no canonical tags appear last in an "Untagged" section. SQL ORDER BY is not modified for tag grouping since one video can belong to many groups.

Both modes produce a list of `{"tag": {"name": label}, "videos": [...]}` dicts consumed by the same `_video_container.html` partial. Pagination is applied at the video level before grouping, so a group may span pages if the library is large.

**Bookmarklet / quick-add**: `POST /api/add` accepts `{"url": "<youtube-url>"}` from any origin (CORS headers included). It extracts the video ID via the same `_YT_ID_RE` regex used by the crawler, checks for an existing `fetch_status='ok'` record, then calls `fetch_metadata(video_id, delay=0)` and persists the result via `add_video` in `webapp/db.py`. Returns `{"status": "added"|"exists"|"hidden"|"error", "title": "..."}`. When the video exists but is hidden, returns `"hidden"` — the extension uses this to show the hidden-state UI without a separate status check. `add_video` uses `ON CONFLICT(video_id) DO UPDATE` but does not overwrite `date_added`, `personal_view_count`, or `date_last_viewed`. `GET /install` renders `install.html`, which shows the bookmarklet as a draggable `<a href="javascript:...">` link. The bookmarklet shows a toast notification on the YouTube page while the fetch runs, then updates it with the result.

**Pagination / Load more**: `PAGE_SIZE = 100`. Flat view uses a "Load more" button; grouped view uses Prev/Next links (appending across channel sections is awkward with HTMX).

- **Flat view**: `_video_container.html` renders an `id="video-grid"` div and an `id="load-more"` div containing the button. The button uses `hx-target="#video-grid"` with `hx-swap="beforeend"` and `?append=1` in its URL. The server returns `_load_more.html`, which is the new cards followed by an OOB `<div id="load-more" hx-swap-oob="true">` that replaces the button (empty when no more pages, new button otherwise).
- **Grouped view**: standard Prev/Next links that swap the entire `#video-container`.
- `page_url()` strips both `page` and `append` from the current query args before building the new URL, so `append=1` never accumulates.
- Filter changes still reset to page 1 (page is not a form field).

### Watch Later Drag-to-Reorder

Cards on `/watch-later` carry `draggable="true"` (set only for `context="watch_later"` in `_video_card.html`). All drag handling is a single delegated listener block in `base.html`, using the native HTML5 drag-and-drop API — no vendored sortable library — consistent with the project's zero-JS-dependency convention.

- `dragstart` is cancelled (`e.preventDefault()`) when the originating target is inside an `<a>` or `<button>`, so clicking the thumbnail link, title, tag pills, or the remove button still works; the rest of the card (meta row, secondary-meta line, whitespace) is the effective drag handle.
- `dragover` reorders the DOM live using **index comparison**, not cursor Y-position-within-target-rect: if the dragged card's current index is before the hovered card's index, it's moved after the hovered card; otherwise moved before it. This is layout-agnostic and works correctly for the CSS grid (`auto-fill` columns) the queue uses — a midpoint-of-target-rect heuristic would only work for single-column lists.
- `dragend` reindexes the `.queue-position-badge` numbers from DOM order and POSTs the final 1-indexed position to `/videos/<id>/watch-later/reorder`, which calls the existing `reorder_watch_later` DB function.
- No optimistic-rollback handling on request failure — same trade-off already accepted elsewhere on this page (e.g. queue-remove).

### Template partials

| File | Purpose |
|---|---|
| `base.html` | Shared layout, nav (includes video/channel count; shows "Hidden (N)" link when hidden_count > 0) |
| `index.html` | Filter toolbar + `#video-container` shell + `#video-card-menu` right-click context menu |
| `_video_container.html` | Swapped by HTMX; renders flat grid or grouped sections |
| `_video_card.html` | Single card; carries `data-video-id` for right-click hide |
| `hidden.html` | Hidden videos management page |

### Accessibility and Usability Notes

- Thumbnail `<img>` tags include `alt` text from the video title with `loading="lazy"`.
- No external fonts or icon libraries. No network dependencies for local use.
- Broken thumbnails fall back to a CSS placeholder `div`.

---

## CLI / Startup Interface

File: `webapp/cli.py`

```
Usage: python -m webapp.cli [OPTIONS]

Options:
  --db FILE     Path to the ViewTube SQLite database [required]
  --host HOST   Host to bind to (default: 127.0.0.1)
  --port PORT   Port to listen on (default: 5000)
  --debug       Enable Flask debug mode (auto-reload)
  -h, --help    Show this message and exit

Exit codes:
  0   Clean shutdown
  1   Database file not found
  2   Port already in use
```

Example invocations:

```bash
python -m webapp.cli --db ~/viewtube.db
python -m webapp.cli --db ~/viewtube.db --port 8080 --debug
```

`main()` flow:
1. Parse args.
2. Check `--db` path exists; exit 1 with message if not.
3. Call `init_webapp_tables(db_path)` to add `tag_keywords` if missing.
4. Call `create_app(db_path)`.
5. Print `ViewTube running at http://<host>:<port>`.
6. Call `app.run(host, port, debug)`.

---

## Implementation Phases

### Phase 0: Project Scaffolding

**Goal:** Flask application skeleton with working test client.

Steps:
1. Add `flask` to `requirements.txt`; vendor `htmx.min.js` into `static/`.
2. Create all `__init__.py` files and empty module stubs.
3. Create `base.html` with minimal HTML5 shell loading `htmx.min.js`.
4. Create `conftest.py` with `db_conn` and `client` fixtures (see below).

Verify: `pytest tests/webapp/` collects zero tests and the fixtures do not raise.

---

### Phase 1: Database Layer

**Goal:** Implement and test all `db.py` functions in isolation, including `record_visit`.

#### TDD Step 1.1 — Write failing tests

File: `tests/webapp/test_db.py`

The `db_conn` fixture provides an in-memory `sqlite3.Connection` pre-populated with 5 video rows across 3 channels and 2 tags.

Tests to write:

```
test_get_all_videos_returns_all_rows
test_get_all_videos_sorts_by_date_added_desc_by_default
test_get_all_videos_sort_by_personal_view_count_asc
test_get_all_videos_sort_by_yt_view_count_desc
test_get_all_videos_sort_by_title_asc
test_get_all_videos_filters_by_channel
test_get_all_videos_filters_by_tag
test_get_all_videos_filters_by_search_term_in_title
test_get_all_videos_filters_by_search_term_in_description
test_get_all_videos_invalid_sort_by_raises_value_error
test_get_all_videos_invalid_sort_dir_raises_value_error
test_get_video_by_id_returns_correct_row
test_get_video_by_id_returns_none_for_missing
test_get_all_channels_returns_distinct_names
test_get_all_channels_excludes_null_channels
test_get_all_tags_returns_with_video_count
test_get_stats_returns_correct_totals
test_record_visit_increments_personal_view_count
test_record_visit_updates_date_last_viewed
test_record_visit_called_twice_increments_to_two
test_record_visit_unknown_video_id_does_nothing
test_init_webapp_tables_creates_tag_keywords_table
test_init_webapp_tables_is_idempotent
```

Run `pytest tests/webapp/test_db.py` — fails with `ImportError`.

#### TDD Step 1.2 — Implement

File: `webapp/db.py`

Key decisions:
- `ALLOWED_SORT_COLUMNS` includes `personal_view_count` and `yt_view_count` (not a generic `view_count`).
- `search` filter: `LIKE '%' || ? || '%'` on both `title` and `description` joined with `OR`.
- `get_stats` returns `{'total_videos': N, 'total_channels': N, 'fetch_errors': N, 'pending': N}`.
- `record_visit(conn, video_id)`: single `UPDATE` statement; uses `datetime.utcnow().isoformat()` for `date_last_viewed`.
- `init_webapp_tables(db_path)` opens its own short-lived connection, creates `tag_keywords` with `CREATE TABLE IF NOT EXISTS`.

Run `pytest tests/webapp/test_db.py` — all pass.

---

### Phase 2: Keyword Matcher

**Goal:** Implement and test keyword-based video grouping.

#### TDD Step 2.1 — Write failing tests

File: `tests/webapp/test_keyword_matcher.py`

Tests to write:

```
test_find_matching_tags_returns_matching_tag_names
test_find_matching_tags_case_insensitive
test_find_matching_tags_matches_in_description
test_find_matching_tags_matches_in_title
test_find_matching_tags_returns_empty_for_no_match
test_find_matching_tags_returns_multiple_matching_tags
test_find_matching_tags_word_boundary_no_partial_match   # "guitar" must not match "aguitar"
test_group_videos_by_tags_produces_correct_structure
test_group_videos_by_tags_includes_untagged_group
test_group_videos_by_tags_video_appears_in_multiple_groups
```

Run `pytest tests/webapp/test_keyword_matcher.py` — fails with `ImportError`.

#### TDD Step 2.2 — Implement

File: `webapp/keyword_matcher.py`

```python
import re

def find_matching_tags(video: dict, tags_with_keywords: list[dict]) -> list[str]:
    text = f"{video.get('title', '')} {video.get('description', '')}".lower()
    matched = []
    for tag in tags_with_keywords:
        for kw in tag['keywords']:
            if re.search(r'\b' + re.escape(kw.lower()) + r'\b', text):
                matched.append(tag['name'])
                break
    return matched


def group_videos_by_tags(videos: list[dict],
                         tags_with_keywords: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {t['name']: [] for t in tags_with_keywords}
    groups['Untagged'] = []
    for video in videos:
        matching = find_matching_tags(video, tags_with_keywords)
        if matching:
            for tag_name in matching:
                groups[tag_name].append(video)
        else:
            groups['Untagged'].append(video)
    return groups
```

Run `pytest tests/webapp/test_keyword_matcher.py` — all pass.

---

### Phase 3: Jinja2 Template Filters

**Goal:** Format numbers and dates cleanly without logic in templates.

#### TDD Step 3.1 — Write failing tests

File: `tests/webapp/test_filters.py`

Tests to write:

```
test_format_view_count_thousands_separator
test_format_view_count_millions_suffix          # 1234567 -> "1.2M"
test_format_view_count_none_returns_dash
test_format_date_iso_to_human_readable          # "2024-01-15" -> "Jan 15, 2024"
test_format_date_none_returns_dash
test_format_date_invalid_returns_raw_string
test_format_duration_seconds_to_mm_ss
test_format_duration_hours_to_hh_mm_ss
test_format_duration_none_returns_dash
```

Run `pytest tests/webapp/test_filters.py` — fails with `ImportError`.

#### TDD Step 3.2 — Implement

File: `webapp/filters.py`

```python
from datetime import datetime

def format_view_count(value):
    if value is None:
        return '—'
    if value >= 1_000_000:
        return f'{value / 1_000_000:.1f}M'
    if value >= 1_000:
        return f'{value:,}'
    return str(value)

def format_date(value):
    if value is None:
        return '—'
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').strftime('%b %d, %Y')
    except ValueError:
        return str(value)

def format_duration(seconds):
    if seconds is None:
        return '—'
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f'{h}:{m:02d}:{s:02d}'
    return f'{m}:{s:02d}'
```

Run `pytest tests/webapp/test_filters.py` — all pass.

---

### Phase 4: Flask Routes

**Goal:** Implement all HTTP routes including the visit-tracking redirect.

#### TDD Step 4.1 — Write failing tests

File: `tests/webapp/test_routes.py`

Tests to write:

```
test_index_returns_200
test_index_renders_video_rows
test_index_sort_by_personal_view_count_asc
test_index_sort_by_yt_view_count_desc
test_index_sort_by_invalid_column_returns_400
test_index_filter_by_channel
test_index_filter_by_tag
test_index_search_filters_results
test_index_htmx_request_returns_partial_not_full_page
test_visit_redirects_to_youtube_url
test_visit_increments_personal_view_count
test_visit_updates_date_last_viewed
test_visit_second_click_increments_to_two
test_visit_unknown_video_id_returns_404
test_group_channel_returns_200
test_group_channel_groups_videos_correctly
test_group_keywords_returns_200
test_group_keywords_groups_by_tag
test_group_keywords_includes_untagged
test_tags_page_returns_200
test_create_tag_redirects_to_tags_page
test_create_tag_with_keywords_persists
test_delete_tag_removes_tag
test_add_video_tag_creates_association
test_remove_video_tag_removes_association
test_stats_endpoint_returns_json
test_missing_db_returns_500_with_message
```

For the HTMX partial test: send `HX-Request: true` header and assert the response body does NOT contain `<html>`.

For the visit tests: call `GET /visit/<video_id>`, assert 302 with `Location` pointing to the YouTube URL, then query the DB directly to assert `personal_view_count == 1` and `date_last_viewed` is set.

Run `pytest tests/webapp/test_routes.py` — fails.

#### TDD Step 4.2 — Implement

File: `webapp/routes.py`

Key decisions:
- `GET /visit/<video_id>`: looks up the video by ID; returns 404 if not found; calls `record_visit(g.db, video_id)`; returns `redirect(video['url'])` with `code=302`.
- `GET /` and `GET /videos` share query logic. `GET /videos` checks `request.headers.get('HX-Request')` and returns only the table/grid partial.
- Sort validation: `sort_by` not in `ALLOWED_SORT_COLUMNS` → return 400.
- Tag creation: receives `name` and `keywords` form fields; calls `db.create_tag()` and `db.set_tag_keywords()`; redirects to `/tags`.
- Tag deletion uses HTMX `hx-delete` with `hx-confirm` (HTML forms only support GET/POST).

Run `pytest tests/webapp/test_routes.py` — all pass.

---

### Phase 5: HTML Templates

**Goal:** Create all Jinja2 templates. Route tests verify string content; templates are also manually verified in the browser.

#### `base.html`

- Standard HTML5 boilerplate
- `<head>`: charset, viewport, `style.css`, HTMX `<script>`
- `<body>`: top nav linking Home, Group by Channel, Group by Keywords, Manage Tags
- `{% block content %}{% endblock %}`

#### `index.html`

- Extends `base.html`
- Filter bar: search input with HTMX debounce, channel select, tag select, view-toggle buttons
- `<div id="video-container">`: contains `_video_row.html` loop (table) or `_video_grid.html` loop (cards)
- Column headers: `<a href="/?sort_by=personal_view_count&sort_dir=desc">Times Watched ↓</a>` pattern; active sort column highlighted

#### `_video_row.html`

Single `<tr>`. Both the thumbnail and the title link to `/visit/{{ video.video_id }}`:

```html
<td>
  <a href="/visit/{{ video.video_id }}">
    <img src="{{ video.thumbnail_url }}" alt="{{ video.title }}"
         loading="lazy" width="120" onerror="this.style.display='none'">
  </a>
</td>
<td>
  <a href="/visit/{{ video.video_id }}">{{ video.title }}</a>
</td>
<td>{{ video.personal_view_count | view_count }}</td>
<td>{{ video.yt_view_count | view_count }}</td>
<td>{{ video.date_added | date }}</td>
<td>{{ video.date_last_viewed | date }}</td>
```

#### `_video_grid.html`

Responsive grid of `<article class="video-card">`. Thumbnail and title both link to `/visit/{{ video.video_id }}`. Shows times watched, YT views, and date added.

#### `style.css`

CSS custom properties for colors, spacing, font sizes. Key sections:

- `:root` variables
- Reset/base styles
- `.video-table`
- `.video-grid` with `grid-template-columns: repeat(auto-fill, minmax(280px, 1fr))`
- `.video-card`
- `.tag-pill` (colored badge)
- `.sort-active` (underline + arrow on active column header)
- `.htmx-indicator` spinner
- Responsive breakpoint at 768px

---

### Phase 6: CLI Entry Point

**Goal:** Wire the Flask app factory to `argparse` for startup.

#### TDD Step 6.1 — Write failing tests

File: `tests/webapp/test_cli.py`

Tests to write:

```
test_cli_exits_1_when_db_not_found
test_cli_creates_flask_app
test_cli_passes_db_path_to_app_config
```

For the last two: mock `app.run` so the test doesn't start a real server.

Run `pytest tests/webapp/test_cli.py` — fails.

#### TDD Step 6.2 — Implement

File: `webapp/cli.py`

```python
def main():
    parser = argparse.ArgumentParser(description='ViewTube Web Interface')
    parser.add_argument('--db', required=True, type=Path)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--normalize-tags', action='store_true',
                        help='Merge case-duplicate tags and exit')
    args = parser.parse_args()

    if not args.db.exists():
        print(f"Error: database not found: {args.db}", file=sys.stderr)
        sys.exit(1)

    if args.normalize_tags:
        deleted = collapse_case_variants(open_conn(str(args.db)))
        print(f"Merged {deleted} duplicate tag row(s).")
        return

    app = create_app(str(args.db))
    app.run(host=args.host, port=args.port, debug=args.debug)
```

Run `pytest tests/webapp/test_cli.py` — all pass.

---

### Phase 7: Integration and Browser Testing

**Goal:** End-to-end verification against a real database generated by the crawler.

Steps:
1. Run the crawler against a small sample bookmarks file to produce a populated `test.db`.
2. Start the web app: `python -m webapp.cli --db test.db --debug`.

Manual verification checklist:
- [ ] All videos appear on the main page with "Times Watched" starting at 0
- [ ] Clicking a thumbnail redirects to YouTube and increments Times Watched to 1
- [ ] Clicking the title redirects to YouTube and increments Times Watched to 2
- [ ] Date Last Viewed updates to current date after each click
- [ ] Sort by Times Watched asc and desc works correctly
- [ ] Sort by YT Views asc and desc works correctly
- [ ] Search filters update the list without full page reload (HTMX)
- [ ] Channel dropdown filters correctly
- [ ] Group by Channel shows correct accordion groupings
- [ ] Create a tag with keywords "guitar, tutorial, lesson"
- [ ] Group by Keywords shows matching videos under the tag
- [ ] Videos with no matching tag appear in "Untagged"
- [ ] Manually tag a video; association is persisted in the database
- [ ] Delete a tag; it disappears from video associations
- [ ] Thumbnails load lazily; broken thumbnails hide gracefully
- [ ] Re-running the crawler does not reset Times Watched or Date Last Viewed

---

## `conftest.py` Design

```python
import pytest
import sqlite3
from webapp.app import create_app

SCHEMA_SQL = """
    CREATE TABLE videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT NOT NULL UNIQUE,
        url TEXT NOT NULL,
        title TEXT,
        description TEXT,
        channel_name TEXT,
        channel_id TEXT,
        yt_view_count INTEGER,
        personal_view_count INTEGER NOT NULL DEFAULT 0,
        duration_seconds INTEGER,
        thumbnail_url TEXT,
        date_added TEXT,
        date_last_viewed TEXT,
        date_published TEXT,
        fetch_status TEXT DEFAULT 'pending',
        fetch_error TEXT,
        last_fetched_at TEXT
    );
    CREATE TABLE tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    );
    CREATE TABLE video_tags (
        video_id_fk INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
        tag_id_fk   INTEGER NOT NULL REFERENCES tags(id)   ON DELETE CASCADE,
        PRIMARY KEY (video_id_fk, tag_id_fk)
    );
    CREATE TABLE tag_keywords (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
        keyword TEXT NOT NULL,
        UNIQUE(tag_id, keyword)
    );
"""

SEED_SQL = """
    INSERT INTO videos (video_id, url, title, channel_name, yt_view_count,
                        personal_view_count, date_added, fetch_status)
    VALUES
        ('aaaaaaaaaa1', 'https://youtube.com/watch?v=aaaaaaaaaa1', 'Guitar Lesson 1',
         'GuitarChannel', 100000, 0, '2024-01-01', 'ok'),
        ('aaaaaaaaaa2', 'https://youtube.com/watch?v=aaaaaaaaaa2', 'Thai Food Recipe',
         'ThaiCooking', 200000, 3, '2024-02-01', 'ok'),
        ('aaaaaaaaaa3', 'https://youtube.com/watch?v=aaaaaaaaaa3', 'Advanced Chords',
         'GuitarChannel', 50000, 1, '2024-03-01', 'ok'),
        ('aaaaaaaaaa4', 'https://youtube.com/watch?v=aaaaaaaaaa4', 'Pad Thai Tutorial',
         'ThaiCooking', 300000, 0, '2024-04-01', 'ok'),
        ('aaaaaaaaaa5', 'https://youtube.com/watch?v=aaaaaaaaaa5', 'Random Video',
         'OtherChannel', 10000, 0, '2024-05-01', 'error');
"""

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL + SEED_SQL)
    yield conn
    conn.close()

@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / 'test.db'
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL + SEED_SQL)
    conn.close()
    app = create_app(str(db_path))
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c
```

---

## Error Handling Strategy

| Scenario | Handling |
|---|---|
| DB file not found at startup | `sys.exit(1)` with message to stderr |
| DB file deleted while running | `sqlite3.OperationalError` caught; 500 response with `error.html` |
| Invalid sort column in query param | `ValueError` from `db.get_all_videos`; route returns 400 |
| Invalid sort direction | Same as above |
| `/visit/<video_id>` for unknown ID | `get_video_by_id` returns `None`; route returns 404 |
| Video with no thumbnail | `onerror="this.style.display='none'"` on `<img>`; CSS placeholder via `background-color` |
| Empty database | Index renders zero-row table with "No bookmarks found. Run the crawler first." |
| Duplicate tag name on creation | `sqlite3.IntegrityError`; route returns 409 with HTMX-swappable error message |
| Port already in use | `OSError` from `app.run()` propagates; Python prints OS error; non-zero exit |

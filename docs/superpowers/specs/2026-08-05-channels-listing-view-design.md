# Channels Listing View — Design

**Date:** 2026-08-05
**Status:** Approved
**Scope:** Creator pages, next slice. A browsable `/channels` page listing all tracked channels from the `channels` table, with sort, search, a "has saved videos" toggle, and pagination. Out of scope (deferred to later slices): channel tagging, a per-channel detail page, and channel-specific stats dashboards.

---

## Summary

The `channels` table holds 1,893 tracked channels with rich metadata (name, URL, description, subscriber count, thumbnail), but there is no page that presents them. The videos page already supports a `?channel=<name>` filter and a `group=channel` view, but nothing surfaces the channels *as entities*.

This adds a `/channels` page: a grid of channel cards styled like the videos grid, each linking to that channel's saved videos and out to YouTube.

---

## Section 1: Backend — DB functions

Two new functions in `webapp/db/channels.py` (with tests in `tests/webapp/test_db.py`):

### `get_channels_page(conn, *, sort_by, sort_dir, search, has_videos, page, page_size)`

Returns a list of channel dicts, each augmented with a computed `video_count` from `channels LEFT JOIN videos ON videos.channel_id = channels.channel_id GROUP BY channels.channel_id`.

- `search` (str | None): case-insensitive substring match on `channel_name`.
- `has_videos` (bool): when true, drop channels whose `video_count` is 0 (`HAVING COUNT(...) > 0`).
- `sort_by` (str): one of `video_count` (default), `subscriber_count`, `channel_name`, `date_added`. An invalid value raises `ValueError` (the route maps this to HTTP 400, mirroring `get_all_videos`).
- `sort_dir` (str): `asc` | `desc`; invalid raises `ValueError`.
- `page`, `page_size`: 1-based pagination via `LIMIT/OFFSET`.
- `NULL` handling: `subscriber_count` may be NULL (1 channel failed its fetch); NULLs sort last regardless of direction.

### `count_channels(conn, *, search, has_videos)`

Returns the total number of channels matching `search` + `has_videos`, for computing total pages. Must apply the same `has_videos`/`search` predicates as `get_channels_page` so page counts line up.

Tests cover: default listing includes `video_count`; `has_videos=True` excludes 0-video channels; `search` filters by name substring; each `sort_by` orders correctly; invalid `sort_by`/`sort_dir` raise `ValueError`; `count_channels` agrees with the number of rows returned across pages.

---

## Section 2: Backend — route

`GET /channels` in `webapp/routes.py` (with tests in `tests/webapp/test_routes.py`). This is a normal server-rendered page, **not** an extension API — no `_CORS_HEADERS`, no OPTIONS.

Query params (all optional): `sort_by` (default `video_count`), `sort_dir` (default `desc`), `search`, `has_videos` (`"1"` to enable), `page` (default 1), `append` (`"1"` for load-more fragments). The route mirrors the index route's structure:

- Calls `count_channels` + `get_channels_page`; wraps `ValueError` → `abort(400)`.
- Computes `total_pages`, clamps `page`.
- When `append=1`, renders just the card-grid + load-more fragment (htmx swaps it in); otherwise renders the full `channels.html`.

Tests: returns 200 and lists channel names; `has_videos=1` filters; `search` filters; invalid `sort_by` → 400; the `append=1` fragment returns only cards (no full page chrome); pagination returns the right page.

---

## Section 3: Frontend

### `channels.html` (extends `base.html`)

Header row with:
- a **search box** (`name="search"`, submits on input via htmx or on enter),
- a **sort `<select>`** with options: Most saved videos (`video_count` desc, default), Most subscribers (`subscriber_count` desc), Name A–Z (`channel_name` asc), Recently added (`date_added` desc),
- a **"Has saved videos" toggle** (checkbox → `has_videos=1`).

Below: a responsive grid of `_channel_card.html`, followed by the load-more control (reusing the existing `_load_more.html` pattern or a channel equivalent) when more pages exist.

### `_channel_card.html` partial

Each card shows:
- channel **thumbnail** (`thumbnail_url`; a neutral placeholder box when NULL),
- channel **name**,
- **subscriber count** rendered via the existing `view_count` Jinja filter (compact, e.g. "5.78M"); omitted when NULL,
- a **saved-video count badge** (`video_count`, e.g. "77 videos" / "0 videos"),
- a **truncated description** snippet.

**Primary click** (card body / name) → the channel's saved videos: `url_for('main.index', channel=channel_name)`. A **secondary link** ("View on YouTube ↗") opens `channel_url` in a new tab (`target="_blank" rel="noopener"`).

### Navigation

Add a **Channels** link to the `<nav>` in `base.html`, alongside Tags / Watch Later.

### Styling

Channel cards live in `static/style.css`. Class names describe the shared purpose (e.g. `.channel-card`, `.channel-grid`) rather than borrowing video-specific names; if a video card class turns out to be a genuine shared abstraction, rename it generically before reuse (per the repo's CSS-naming rule).

---

## Section 4: Decisions & known limitations

- **Card→videos link is by channel name**, reusing the existing `?channel=<name>` filter rather than introducing `channel_id`-based video filtering. Simple and reuses working code. Limitation: two distinct channels that share an exact display name would collapse into one filtered video list. Accepted for now; adding `channel_id` filtering to the index is a future refinement if it proves to matter.
- **0-video channels are shown by default** (with a "0 videos" badge) because they are intentionally tracked; the "Has saved videos" toggle hides them on demand.
- **Pagination reuses the videos load-more pattern** (`append=1`) because 1,893 channels is too many to render at once.
- **No channel tagging, per-channel page, or stats dashboard** in this slice (separate TODO items).

---

## File Map

| File | Action |
|---|---|
| `webapp/db/channels.py` | Add `get_channels_page`, `count_channels` |
| `webapp/db/__init__.py` | Export the two new functions |
| `webapp/routes.py` | Add `GET /channels` route (page + `append=1` fragment) |
| `webapp/templates/channels.html` | **New** — full page: controls + grid + load-more |
| `webapp/templates/_channel_card.html` | **New** — single channel card partial |
| `webapp/templates/base.html` | Add "Channels" nav link |
| `webapp/static/style.css` | Channel card/grid styles |
| `tests/webapp/test_db.py` | Tests for the two new DB functions |
| `tests/webapp/test_routes.py` | Tests for `GET /channels` |
| `CHANGELOG.md` | Append entry |
| `plan-webapp.md` | Document the route, DB functions, and page |
| `TODO.md` | Mark the "UI: channels view" item's listing portion |

---

## Testing Strategy

- **DB** — pytest against the seeded temp SQLite DB (extend conftest seed with a few `channels` rows, some with matching `videos.channel_id`, some without): `video_count` computed correctly, `has_videos` filter, `search`, each sort order, invalid-sort `ValueError`, `count_channels` consistency.
- **Route** — Flask test client: 200 + names listed, filters, invalid sort → 400, `append=1` fragment contains only cards, pagination.
- **Manual** — load `/channels` in a browser against `viewtube.db`: cards render with thumbnails/subs/counts, sort/search/toggle work, card links reach the right filtered video list and YouTube.

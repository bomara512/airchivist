# Extension: Bookmark Channel Action — Design

**Date:** 2026-07-25
**Status:** Approved
**Scope:** Phase 2 of creator pages support. The extension popup gains a "bookmark channel" action on YouTube channel pages (`/@handle`, `/c/name`, `/channel/UCxxx`, `/user/name`), backed by two new webapp API routes and two new webapp DB functions. Out of scope: a channels view/page, tagging channels, channel stats, and any hide/archive/watch-later behaviour for channels.

---

## Summary

The extension popup currently shows "Not a YouTube video." on any non-video tab, including channel pages. This phase teaches it to recognise channel pages and offer a first-class **Add channel to ViewTube** action.

On popup open the flow is:

1. Detect whether the active tab is a video (existing behaviour), a **channel page** (new), or neither.
2. For a channel page, **pre-check** tracking status via a fast, DB-only endpoint and render either "Already tracked: *name*" or an **Add channel to ViewTube** button.
3. On click, fetch channel metadata via yt-dlp, upsert the `channels` row, and — in parallel — create a Firefox bookmark in the ViewTube folder, mirroring the existing video-add flow.

This reuses the `channels` table, `ChannelMetadata`, and `fetch_channel_metadata` delivered in Phase 1 (`docs/superpowers/specs/2026-07-07-creator-pages-schema-crawler-design.md`).

---

## Section 1: Backend — webapp DB functions

Two new functions in `webapp/db/channels.py` (which currently holds only read helpers `get_all_channels`, `get_channel`):

### `upsert_channel(conn, meta, source_url=None)`

Webapp-side write that mirrors the crawler's `Datastore.upsert_channel` DDL and `ON CONFLICT(channel_id) DO UPDATE … COALESCE(...)` semantics. Takes a `ChannelMetadata` (imported from `crawler.models`) and an optional `source_url` (the original URL the user was on, used for later status lookups). `channel_id` is the primary key, so re-adding the same channel under any URL form is idempotent.

### `get_channel_by_source_url(conn, url)`

Returns the channel row matching `channel_url = ? OR source_url = ?` (the same predicate the crawler uses for idempotency), or `None`. Used by the status route to answer "is this channel already tracked?" without a network call.

Both get tests in `tests/webapp/test_db.py` covering the happy path and an edge case (upsert-over-existing preserves non-null fields via COALESCE; source-url lookup miss returns `None`).

---

## Section 2: Backend — webapp API routes

Two new routes in `webapp/routes.py`, both using the module-level `_CORS_HEADERS` constant on the success response **and** the OPTIONS preflight, copying the pattern from `api_status` / `api_add`.

### `GET /api/channel/status?url=…` (+ OPTIONS)

Fast, **no yt-dlp**. Parses `url` with the channel regex; if it isn't a channel URL, returns `{status:"error", error:…}` with 400. Otherwise looks up the channel by source URL:

- Found → `{status:"exists", channel_name: …}`
- Not found → `{status:"not_found"}`

This is the popup's pre-check.

### `POST /api/channel/add` `{url}` (+ OPTIONS)

Parses/validates the channel URL (regex); 400 on non-channel URL. Checks for an existing row by source URL first — if present, returns `{status:"exists", channel_name}` without fetching. Otherwise calls `fetch_channel_metadata(url)` (reused from `crawler.metadata_fetcher`, exactly as `api_add` reuses `fetch_metadata`), then:

- `fetch_status == OK` → `upsert_channel(conn, meta, source_url=url)`; return `{status:"added", channel_name}`.
- otherwise → `{status:"error", error: fetch_error}` with 200 (mirrors `api_add`'s handling of a failed fetch).

Tests in `tests/webapp/test_routes.py` cover, for each route: happy path, a non-channel URL (400/error), the CORS header on the success response, and the OPTIONS preflight. `fetch_channel_metadata` is monkeypatched so tests make no network calls.

---

## Section 3: Extension — `popup.js`

### Channel detection

Add a `YT_CHANNEL_RE` constant mirroring the crawler's Python regex:

```
youtube\.com/(?:channel/(UC[A-Za-z0-9_-]+)|(?:c|user)/([^/?#]+)|@([^/?#]+))
```

Add a `channelUrlFrom(match)` helper that rebuilds the **canonical base** channel URL from the regex match (`https://www.youtube.com/@handle`, `/channel/UC…`, `/c/name`, or `/user/name`). This strips sub-tab suffixes (`/videos`, `/featured`, `/community`, query strings) so the `source_url` sent to the backend is stable regardless of which channel sub-page the user is on.

### `run()` branching

`run()` currently rejects any tab whose URL doesn't match `YT_ID_RE`. Replace the single check with a three-way branch:

1. `YT_ID_RE` matches → existing video flow (`checkStatus` → `renderState`).
2. else `YT_CHANNEL_RE` matches → new channel flow: `GET /api/channel/status` → `renderChannelState`.
3. else → "Not a YouTube video." (unchanged fallback).

### `renderChannelState(root, viewtubeUrl, channelUrl, tabTitle, data)`

- `data.status === "not_found"` → render an **Add channel to ViewTube** button wired to `doAddChannel`.
- `data.status === "exists"` → render "✓ Already tracked: *channel_name*".
- otherwise → error line.

No watch-later checkbox, no archive button — channels have no such concept in this phase.

### `doAddChannel(viewtubeUrl, channelUrl, tabTitle)`

Mirrors `doAdd`: a `Promise.allSettled` of (a) `getOrCreateFolder()` → `browser.bookmarks.create` for the channel URL, and (b) `POST /api/channel/add`. Reports success/partial/error with the same line-based rendering (`✓ channel name`, `✓ Bookmarked in Firefox`, `✗ …`), and auto-closes on full success like `doAdd`.

### No manifest changes

The popup reads `tab.url` via the existing `activeTab` permission; localhost fetch and `bookmarks` are already granted. The content script (matched only to `/watch*`) is unaffected — channel detection lives entirely in the popup, which sees the active tab URL directly.

The extension has no automated test suite (manual testing only), consistent with Phase 1 and the watch-later-on-add feature.

---

## Section 4: Known limitation

The status pre-check is a URL-based DB lookup, not a yt-dlp resolution. A channel first added under one URL form (e.g. a crawler bookmark of `/channel/UC…`) will **not** match when later viewed via its `@handle` (or vice-versa), because neither `channel_url` nor `source_url` will equal the current tab URL. In that case the popup shows **Add channel to ViewTube**, and clicking it fetches, resolves to the canonical `channel_id`, and the upsert's primary-key conflict correctly reports/stores it as the same channel (no duplicate row).

Making the pre-check exact would require a yt-dlp resolve on every popup open (several seconds), which defeats the purpose of a fast pre-check. This is an accepted trade-off for this phase.

---

## File Map

| File | Action |
|---|---|
| `webapp/db/channels.py` | Add `upsert_channel`, `get_channel_by_source_url` |
| `webapp/db/__init__.py` | Export the two new functions |
| `webapp/routes.py` | Add `api_channel_status` (`GET /api/channel/status`) and `api_channel_add` (`POST /api/channel/add`), both with `_CORS_HEADERS` + OPTIONS |
| `extension/popup/popup.js` | Add `YT_CHANNEL_RE`, `channelUrlFrom`, channel branch in `run()`, `renderChannelState`, `doAddChannel` |
| `tests/webapp/test_db.py` | Tests for the two new DB functions |
| `tests/webapp/test_routes.py` | Tests for the two new routes (happy path, error, CORS, OPTIONS) |
| `CHANGELOG.md` | Append entry |
| `plan-webapp.md` | Document the two new API routes and popup channel flow |
| `TODO.md` | Mark the extension "bookmark channel" item complete |

---

## Testing Strategy

- **DB functions** — pytest against an in-memory/temp SQLite DB with the `channels` table initialised: upsert-insert, upsert-update (COALESCE preserves fields), source-url lookup hit and miss.
- **Routes** — Flask test client with `fetch_channel_metadata` monkeypatched: `added`, `exists`, non-channel-URL error, CORS header present, OPTIONS returns 204 with CORS.
- **Extension** — manual testing (no suite): verify Add button on a channel page, "Already tracked" on re-open, Firefox bookmark created, and "Not a YouTube video" still shown on unrelated pages.

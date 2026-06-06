# ViewTube — Hide / Delete Video Feature

## Decisions

- **Soft delete by default**: `is_hidden = 1` flag on `videos`. Hidden videos are excluded from all list views and stats but preserved in the DB with full history (tags, personal view count, watch dates).
- **Hard delete**: available only from the `/hidden` management page — explicit second step, no browser bookmark removal (option 1: accepted limitation).
- **Webapp trigger**: right-click context menu on the video card.
- **Extension trigger**: state-aware popup. On open the popup checks video status first, then shows the appropriate action (Add / Hide / Restore+Delete).
- **Browser unbookmark**: opt-in checkbox in the extension popup when hiding. Only available there — the `/hidden` page has no access to the browser bookmark API.

---

## Phase 1 — Schema + DB Layer

### Schema

```sql
ALTER TABLE videos ADD COLUMN is_hidden BOOLEAN NOT NULL DEFAULT 0;
```

Two places need this:
1. `crawler/datastore.py` `_SCHEMA` — add `is_hidden BOOLEAN NOT NULL DEFAULT 0` to the `CREATE TABLE videos` definition.
2. `webapp/db.py` `init_webapp_tables` — add `ALTER TABLE videos ADD COLUMN is_hidden BOOLEAN NOT NULL DEFAULT 0` migration (wrapped in `try/except OperationalError` like the existing `is_noise` migration).

The crawler's `ON CONFLICT(video_id) DO UPDATE SET` does **not** include `is_hidden`, `personal_view_count`, `date_added`, or `date_last_viewed` — confirmed safe. Re-running the crawler never overwrites the hidden flag.

### `_build_where` change

Add `AND v.is_hidden = 0` to the base conditions alongside `fetch_status = 'ok'`. Hidden videos are invisible everywhere on the main index regardless of filter state.

### New DB functions

```python
def hide_video(conn, video_id: str) -> None
    # UPDATE videos SET is_hidden = 1 WHERE video_id = ?

def unhide_video(conn, video_id: str) -> None
    # UPDATE videos SET is_hidden = 0 WHERE video_id = ?

def delete_video(conn, video_id: str) -> None
    # DELETE FROM videos WHERE video_id = ?
    # video_tags rows cascade-delete automatically (ON DELETE CASCADE)

def get_hidden_videos(conn, sort_by='date_added', sort_dir='desc',
                      page=1, page_size=PAGE_SIZE) -> list[dict]
    # Same shape as get_all_videos but WHERE v.is_hidden = 1
    # Includes tags field (canonical tags) for display

def count_hidden_videos(conn) -> int
    # SELECT COUNT(*) FROM videos WHERE is_hidden = 1
```

### `get_stats` update

Add `hidden_count` to the returned dict so `base.html` can surface a badge when hidden videos exist.

### Tests

Add to `tests/webapp/conftest.py` `SCHEMA_SQL`: `is_hidden BOOLEAN NOT NULL DEFAULT 0` on the videos table.

New tests in `test_db.py`:
```
test_hide_video_sets_flag
test_hidden_video_excluded_from_get_all_videos
test_unhide_video_restores_to_index
test_delete_video_removes_row_and_cascades
test_count_hidden_videos
```

---

## Phase 2 — Routes + Hidden Page

### New routes

| Method | Path | Description |
|---|---|---|
| `POST` | `/videos/<video_id>/hide` | Set `is_hidden = 1`. Returns `204`. Used by right-click fetch() on card. |
| `POST` | `/videos/<video_id>/unhide` | Set `is_hidden = 0`. Redirects to `/hidden`. Used by hidden page form. |
| `POST` | `/videos/<video_id>/delete` | Hard delete. Redirects to `/hidden`. Hidden page only. |
| `GET` | `/hidden` | Hidden videos management page. |
| `GET` | `/api/status` | Extension status check. See API section below. |
| `POST` | `/api/hide` | Extension hide action. See API section below. |

Update `POST /api/add`: when the matched video exists with `is_hidden = 1`, return `{"status": "hidden", "title": "..."}` instead of `"exists"`. This is how the extension detects it needs to show the hidden state.

### `/hidden` page

Same card grid as the main index. No filter toolbar — just a sort control (date hidden would be ideal but `date_hidden` is out of scope; use `date_added` desc as default). Pagination via Prev/Next (consistent with grouped view — simpler than Load More for a management page).

Each card has two action buttons in the `.video-info` area below the metadata row:
- **Restore** — POST form to `/videos/<video_id>/unhide`. Redirects back to `/hidden`.
- **Delete permanently** — POST form to `/videos/<video_id>/delete`. Has an `onclick="return confirm('Permanently delete this video?')"` guard. Redirects back to `/hidden`.

Empty state: "No hidden videos."

Add "Hidden (N)" link to `base.html` nav, shown only when `stats.hidden_count > 0`. This acts as a persistent reminder that hidden videos exist.

### API endpoints for extension

**`GET /api/status?url=<youtube_url>`**

Extracts `video_id` from the URL using `_YT_ID_RE`. Looks up the video.

```json
{ "status": "not_found" }
{ "status": "exists",  "video_id": "abc123", "title": "..." }
{ "status": "hidden",  "video_id": "abc123", "title": "..." }
{ "status": "error",   "error": "Not a YouTube URL" }
```

**`POST /api/hide`**

Same CORS headers as `/api/add`. Body: `{"url": "<youtube_url>"}`.

Extracts `video_id`, calls `hide_video`. Returns:
```json
{ "status": "hidden", "title": "..." }
{ "status": "error",  "error": "Video not found" }
```

Both endpoints use the same CORS header pattern as `/api/add`.

### Tests

New tests in `test_routes.py`:
```
test_hide_route_returns_204
test_hide_route_removes_video_from_index
test_unhide_route_restores_video
test_delete_route_removes_video_permanently
test_hidden_page_returns_200
test_hidden_page_shows_hidden_videos
test_hidden_page_empty_state
test_api_status_not_found
test_api_status_exists
test_api_status_hidden
test_api_status_invalid_url
test_api_hide_hides_video
test_api_hide_unknown_video_returns_error
test_api_add_hidden_video_returns_hidden_status
```

---

## Phase 3 — Webapp Right-Click on Video Card

### Context menu

`index.html` already has a `#tag-pill-menu` context menu for tag pills. Add a second menu `#video-card-menu` for the card itself.

```html
<div id="video-card-menu" class="alias-context-menu">
  <button id="video-card-hide">Hide video</button>
</div>
```

The contextmenu event listener targets `.video-card` but must not fire when the right-click lands on a `.tag-pill` (that menu takes priority). Use the existing pattern — check `e.target.closest()` in order:

```javascript
document.addEventListener('contextmenu', function (e) {
  if (e.target.closest('.tag-pill')) return; // tag-pill menu handles this
  const card = e.target.closest('.video-card');
  if (!card) { hideCardMenu(); return; }
  e.preventDefault();
  // show card menu...
});
```

The `video_id` needs to be on the card element. Add `data-video-id="{{ video.video_id }}"` to the `.video-card` div in `_video_card.html`.

On "Hide video" click:
```javascript
fetch(`/videos/${videoId}/hide`, { method: 'POST' })
  .then(r => { if (r.ok) card.closest('.video-card').remove(); });
```

Optimistic removal — card disappears immediately on success, consistent with the tag-pill removal pattern.

### `_video_card.html` change

```html
<div class="video-card" data-video-id="{{ video.video_id }}">
```

---

## Phase 4 — Extension Popup Redesign

### Current flow
Open → auto-add + auto-bookmark → show result → auto-close 1.5s.

### New flow
Open → "Checking…" → `GET /api/status` → render state-appropriate UI → user clicks action → show result.

### Three states

**State: `not_found`** — video not in ViewTube
```
[ Add to ViewTube ]
```
Clicking Add: calls `POST /api/add` + `browser.bookmarks.create()` in parallel (same as current behavior). On success: show title, auto-close after 1.5s.

**State: `exists`** — video already in ViewTube
```
✓ <title>

[ Hide from ViewTube ]
☐ Also remove browser bookmark
```
Clicking Hide:
1. `POST /api/hide`
2. If checkbox checked: `browser.bookmarks.search({url: tab.url})` → `browser.bookmarks.remove(id)` for each match
3. Show "Hidden: \<title\>" — no auto-close (destructive action, let user see the result)

**State: `hidden`** — video is hidden in ViewTube
```
⊘ Hidden: <title>

[ Restore to ViewTube ]   [ Delete permanently ]
```
- Restore: `POST /videos/<video_id>/unhide` (using `video_id` from status response) → show "Restored"
- Delete: `POST /videos/<video_id>/delete` → show "Deleted"
- No browser bookmark removal on either action (option 1 limitation)

**State: ViewTube unreachable**
Same error message as current. No change.

### `popup.html` changes

Replace the single `<div id="status">` with a richer shell that JS populates:

```html
<body>
  <div id="root"></div>
  <script src="popup.js"></script>
</body>
```

All rendering is JS-driven (`root.innerHTML = ...`) to keep the HTML minimal and avoid a flash of pre-rendered markup.

### `popup.js` structure

```javascript
async function checkStatus(viewtubeUrl, tabUrl) → {status, video_id, title}
async function doAdd(viewtubeUrl, tabUrl, folderId, tabTitle) → void
async function doHide(viewtubeUrl, tabUrl, alsoUnbookmark) → void
async function doRestore(viewtubeUrl, videoId) → void
async function doDelete(viewtubeUrl, videoId) → void
function renderState(status, data) → void   // populates #root
async function run() → void                 // entry point
```

`getOrCreateFolder()` is called lazily (only in `doAdd` and `doHide` with checkbox checked) rather than eagerly on every popup open, since status-check and hide paths don't need it.

### Manifest

No new permissions required. The existing `bookmarks`, `activeTab`, and `storage` permissions cover everything.

---

## File Change Summary

| File | Change |
|---|---|
| `crawler/datastore.py` | Add `is_hidden` to `_SCHEMA` |
| `webapp/db.py` | `_build_where`, `get_stats`, 5 new functions, `init_webapp_tables` migration |
| `webapp/routes.py` | 6 new routes, update `/api/add` |
| `webapp/templates/base.html` | "Hidden (N)" nav link |
| `webapp/templates/hidden.html` | New page |
| `webapp/templates/index.html` | `#video-card-menu` + JS |
| `webapp/templates/_video_card.html` | `data-video-id` on `.video-card` |
| `webapp/static/style.css` | Hidden page card styles, Restore/Delete button styles |
| `extension/popup/popup.html` | Replace static markup with `<div id="root">` |
| `extension/popup/popup.js` | Full rewrite — state-aware, action buttons |
| `tests/webapp/conftest.py` | `is_hidden` in `SCHEMA_SQL` |
| `tests/webapp/test_db.py` | 5 new tests |
| `tests/webapp/test_routes.py` | ~13 new tests |

---

## Implementation Order

1. **Phase 1**: Schema + DB layer (test-driven)
2. **Phase 2**: Routes + `/hidden` page + API endpoints
3. **Phase 3**: Right-click hide on video card
4. **Phase 4**: Extension popup redesign

Each phase is independently shippable — the webapp hide feature works without the extension changes, and vice versa.

# Plan: Unified Video Card

## Goal

Replace three divergent card implementations with a single `_video_card.html` Jinja partial.
Server-render the rediscover shelf (eliminating its JS-rendered DOM). Unify JavaScript handlers.

## Decisions made

| Question | Answer |
|---|---|
| Shelf rendering | Switch to server-rendered (HTMX for refresh button) |
| Watch Later button pre-state | Pre-disable if already queued (via context processor) |
| Tags on all cards | Yes — shelf and watch-later cards show tags too |
| Hide context menu | Available on all cards (main, shelf, watch-later) |

---

## Behavior matrix

| Feature | `main` | `shelf` | `watch_later` |
|---|---|---|---|
| Position badge (queue number) | ❌ | ❌ | ✅ overlay on thumbnail |
| Thumbnail + duration overlay | ✅ | ✅ | ✅ |
| Title → `/visit/{id}` | ✅ | ✅ | ✅ |
| Channel link (YouTube) | ✅ | ✅ | ✅ |
| Channel filter icon (library filter) | ✅ | ❌ too noisy | ❌ |
| Full metadata row (views, dates) | ✅ | ❌ | ✅ (views + queue-added date) |
| "Reason" label (Never watched / X days ago) | ❌ | ✅ | ❌ |
| Tags | ✅ | ✅ | ✅ |
| ⏱ Watch Later button | ✅ disabled if queued | ✅ disabled if queued | ❌ already in queue |
| ✕ Remove from queue button | ❌ | ❌ | ✅ |
| Right-click → Hide video | ✅ | ✅ | ✅ |

---

## Files to change

| File | Change |
|---|---|
| `webapp/db/videos.py` | Expand shelf/queue DB queries; add `get_watch_later_video_ids` |
| `webapp/routes.py` | Add context processor; index route passes shelf; new HTML refresh route; remove JSON shelf routes |
| `webapp/templates/_video_card.html` | Rewrite with context-aware sections |
| `webapp/templates/_shelf_cards.html` | New partial for HTMX shelf refresh swap |
| `webapp/templates/index.html` | Server-rendered shelf loop; remove 130-line JS shelf IIFE |
| `webapp/templates/watch-later.html` | Use `_video_card.html` partial |
| `webapp/templates/base.html` | Move context menu HTML+JS and WL button JS here (applies globally) |
| `webapp/static/style.css` | Remove shelf-specific card CSS (`.shelf-card*`); unify under `.video-card` |
| `tests/webapp/test_routes.py` | Tests for new HTML refresh route; remove tests for deleted JSON routes |

---

## Detailed changes

### 1. `webapp/db/videos.py`

**`get_current_rediscover_shelf`**: Expand SELECT to include all card fields:
- Add: `channel_id`, `yt_view_count`, `duration_seconds`, `date_published`, `date_added`
- Add: `tags` via `GROUP_CONCAT(t.name)` join through `video_tags` + `tags`
- Embed `reason` directly on each video dict (instead of a separate `reasons` dict keyed by video_id)
- Same changes to `generate_rediscover_shelf` where video dicts are built

**`get_watch_later_queue`**: Expand SELECT to include all card fields:
- Add: `channel_id`, `duration_seconds`, `date_published`, `date_added`, `date_last_viewed`
- Add: `tags` via GROUP_CONCAT join
- Rename `added_at` → `queue_added_at` to avoid ambiguity with `date_added` (library date)

**New function `get_watch_later_video_ids(conn) -> set[str]`**: Lightweight query returning just the set of `video_id` strings currently in the queue. Used by the context processor — avoids fetching full video rows on every page load.

---

### 2. `webapp/routes.py`

**New context processor** (applies to every template render):
```python
@bp.app_context_processor
def inject_watch_later_ids():
    ids = _db.get_watch_later_video_ids(g.db)
    return {"watch_later_ids": ids}
```
This injects `watch_later_ids: set[str]` globally so `_video_card.html` can check membership without each route having to pass it explicitly.

**`index` route**: After fetching videos, also fetch shelf data:
```python
shelf = _db.get_current_rediscover_shelf(g.db)
```
Pass `shelf=shelf` to the template. Remove the comment about shelf being JS-populated.

**New route `POST /rediscover-shelf/refresh`** (replaces the old JSON route for UI purposes):
- Calls `_db.refresh_rediscover_shelf(g.db)`
- Returns `render_template("_shelf_cards.html", shelf=data, expires_label=...)` — the HTMX target swaps just the carousel contents

**Remove routes** (no longer needed):
- `GET /api/rediscover-shelf` — was used only by the JS shelf loader
- `POST /api/rediscover-shelf/refresh` — was used only by the JS shelf refresher

---

### 3. `webapp/templates/_video_card.html`

Rewritten with a `context` variable (caller passes `context="shelf"` etc.; defaults to `"main"`).

```
[thumbnail block]
  - always: img with lazy loading
  - always: duration overlay (if duration_seconds)
  - watch_later only: position badge overlay (caller passes `position` variable)

[video-info block]
  - always: title link → /visit/{video_id}
  - always: channel link (YouTube)
  - main only: channel filter icon
  - shelf only: reason label instead of metadata row
  - main + watch_later: metadata row
    - main: views [personal], published, added, last-viewed
    - watch_later: views, queue-added date (queue_added_at)
  - all: tags (if any)
  - main + shelf: ⏱ Watch Later button
    - disabled + aria-label "Already in Watch Later" if video.video_id in watch_later_ids
  - watch_later only: ✕ Remove button (data-video-id attribute for JS)
```

---

### 4. `webapp/templates/_shelf_cards.html` (new)

A minimal partial used by the HTMX refresh swap:
```jinja
{% for video in shelf.videos %}
  {% with context="shelf" %}
    {% include "_video_card.html" %}
  {% endwith %}
{% endfor %}
{% if not shelf.videos %}
<p class="empty-shelf">No videos to rediscover yet.</p>
{% endif %}
```

---

### 5. `webapp/templates/index.html`

**Shelf section** replaces the empty `<div id="shelf-carousel">` + JS loader with:
```jinja
<div class="video-carousel" id="shelf-carousel">
  {% include "_shelf_cards.html" %}
</div>
```

**Shelf expiration**: Computed in the route and passed as a formatted string (`expires_label`). No countdown timer — just a static "Refreshes in X days" rendered at page load.

**Refresh button** gets HTMX attributes instead of a JS listener:
```html
<button hx-post="/rediscover-shelf/refresh"
        hx-target="#shelf-carousel"
        hx-swap="innerHTML">Refresh</button>
```

**JS removed**:
- Entire `// Rediscover shelf` IIFE (~130 lines): `renderShelf`, `updateExpiration`, `loadShelf`, `refreshBtn` listener, `setInterval` expiration timer, shelf watch-later listener
- `// Watch Later queue button (main video list)` event listener (moves to base.html)

**JS kept**:
- Tag pill context menu (moves to base.html)
- Video card context menu (moves to base.html)
- Shelf collapse/expand with localStorage (stays in index.html — shelf-specific behaviour)

---

### 6. `webapp/templates/watch-later.html`

Replace the hand-rolled queue item markup with:
```jinja
{% for video in queue %}
  {% with context="watch_later", position=loop.index %}
    {% include "_video_card.html" %}
  {% endwith %}
{% endfor %}
```

Remove the inline `<script>` for the remove button — that handler moves to base.html.

---

### 7. `webapp/templates/base.html`

Add context menu HTML (currently in `index.html` only):
```html
<div id="tag-pill-menu" class="alias-context-menu">...</div>
<div id="video-card-menu" class="alias-context-menu">...</div>
```

Add a single `<script>` block with:
- Tag pill right-click handler
- Video card right-click handler → Hide video (works on `.video-card` in any page)
- ⏱ Watch Later button click handler (`.watch-later-btn` class, any page)
- ✕ Remove from queue click handler (`.queue-remove-btn` class, any page)

These use event delegation (`document.addEventListener`) so they work on dynamically added elements (HTMX shelf refresh inserts new `.video-card` elements).

---

### 8. `webapp/static/style.css`

**Remove** (replaced by unified `.video-card` rules):
- `.shelf-card` and all `.shelf-card-*` rules
- `.shelf-card-watch-later` overlay button
- `.queue-item`, `.queue-position`, `.queue-thumbnail`, `.queue-info`, `.queue-title`, `.queue-meta`, `.queue-actions`, `.queue-remove-btn` (watch-later page list)
- `.watch-later-header`, `.queue-count`, `.queue-desc`, `.empty-queue`

**Add/modify**:
- `.video-card` in carousel context: use container selector (`.video-carousel .video-card`) to constrain width
- `.queue-position-badge`: absolute overlay on thumbnail for watch_later context
- `.shelf-reason`: label style within `.video-card` info section
- `.queue-remove-btn`: style for the ✕ button within a card
- `.watch-later-header` and page-level styles stay (they're page chrome, not card chrome)

---

### 9. `tests/webapp/test_routes.py`

**Add**:
- `TestRediscoverShelfRefreshRoute`: tests `POST /rediscover-shelf/refresh` returns 200 HTML (not JSON)
- Check that context menu and WL button JS is present on the watch-later page (via base.html)

**Remove/update**:
- Tests for `GET /api/rediscover-shelf` and `POST /api/rediscover-shelf/refresh` (routes being deleted)

---

## What stays JavaScript (not server-rendered)

| Behaviour | Where |
|---|---|
| Context menu show/hide/position | base.html (event delegation) |
| WL button → POST add, disable | base.html (event delegation) |
| Remove button → POST remove, animate out | base.html (event delegation) |
| Shelf collapse/expand (localStorage) | index.html |
| HTMX shelf refresh | HTMX attribute on button (no custom JS needed) |

---

## Explicitly NOT doing

- Drag-to-reorder on watch-later page (would need a JS drag library)
- Rediscover shelf countdown timer (removed; static "expires in X days" is sufficient)
- Infinite scroll on shelf (still capped at 20 cards)
- Paginating the watch-later queue (currently unbounded; not needed unless the queue gets large)

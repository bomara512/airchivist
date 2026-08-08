# Plan: Rediscover Shelf — Least Recently Viewed Videos

## Context

Goal: Surface stale content the user hasn't engaged with in a while. A shelf on the homepage shows 20 randomly selected videos from the least-recently-viewed pool, regenerated once per week. Helps combat the "I forgot I had this" problem when library grows large.

## Design Decisions (Locked In)

**Pool selection:** Prioritize unwatched (`is_watched = 0`), then fall back to videos ordered by oldest `date_last_viewed`. (Originally keyed off `personal_view_count = 0`; redefined to `is_watched = 0` on 2026-08-07 when the watched-toggle feature made "watched" an independent, user-settable flag rather than a value derived from the view-count history — see the 2026-08-07 `CHANGELOG.md` entries.)

**Pool scope:** Completely random across the entire library; no tag/channel/quality bias; no exclusions (include hidden, very short, etc.).

**Stickiness:** Shelf is sticky for 7 days from first load. Manual refresh regenerates the entire pool and resets the 7-day timer.

**UI:** Togglable/collapsible section on homepage. Each video card shows *why* it's there: "Never opened", "Last viewed 6 months ago", etc.

**Interaction:** Clicking a video increments `personal_view_count` and updates `date_last_viewed` (normal viewing behavior). Since 2026-08-07, the same `record_visit` call also sets `is_watched = 1`, which is what actually moves the video out of the unwatched pool above — `personal_view_count`/`date_last_viewed` still update as before but no longer gate pool membership themselves. A user can also set `is_watched` directly via the new per-card watched toggle without opening the video at all.

**Scope:** Launch this shelf only; don't retain "recently added" shelf for now.

---

## Data Model

### Schema Changes

**New table: `rediscover_shelf`**
```
id          INTEGER PRIMARY KEY AUTOINCREMENT
generated_at TEXT NOT NULL             -- ISO timestamp of generation
expires_at  TEXT NOT NULL              -- ISO timestamp (generated_at + 7 days)
pool        TEXT NOT NULL              -- JSON array of video IDs: ["abc123", "def456", ...]
video_ids   TEXT NOT NULL              -- JSON array in display order
```

**Rationale:**
- `pool`: The full set of 50–100 candidates (for future filtering/analytics)
- `video_ids`: The ordered 20 actually displayed (allows pinning, reordering in future)
- `generated_at` / `expires_at`: Determines when to regenerate

### Data Queries

**Unwatched pool** (`is_watched = 0`, as shipped in `generate_rediscover_shelf`):
```sql
SELECT id, video_id, title, channel_name, personal_view_count, date_last_viewed
FROM videos
WHERE is_watched = 0
ORDER BY date_added ASC
```

**Viewed pool (fallback)** (`is_watched = 1`):
```sql
SELECT id, video_id, title, channel_name, personal_view_count, date_last_viewed
FROM videos
WHERE is_watched = 1
ORDER BY date_last_viewed ASC
```

(Both queries originally filtered on `personal_view_count`; redefined to `is_watched` on 2026-08-07 — see Data Model note above. `personal_view_count` and `date_last_viewed` are still selected and still drive the "Last viewed N days ago" reason label; only the pool-membership predicate changed.)

**Selection logic:**
1. Fetch unwatched; if < 20, append oldest-viewed videos until 20+ total
2. Randomly shuffle and select 20
3. Store pool and selected 20 IDs in `rediscover_shelf`

---

## Backend Implementation

### New DB Functions (`webapp/db/videos.py`)

```python
def generate_rediscover_shelf(conn) -> dict:
    """Generate a new rediscover shelf: 20 random videos from least-recently-viewed pool.
    
    Returns:
      {
        'video_ids': [id1, id2, ...],  # ordered list for display
        'reasons': {id1: 'Never opened', id2: 'Last viewed 6 months ago', ...},
        'generated_at': '2026-06-14T...',
        'expires_at': '2026-06-21T...'
      }
    """

def get_current_rediscover_shelf(conn) -> Optional[dict]:
    """Fetch the active rediscover shelf if not expired, else None."""

def is_rediscover_shelf_expired(conn) -> bool:
    """Check if current shelf has passed expires_at."""

def refresh_rediscover_shelf(conn) -> dict:
    """Force regeneration of shelf (delete old, create new)."""
```

### Route: `GET /api/rediscover-shelf`

**Response:**
```json
{
  "shelf": [
    {
      "id": "abc123",
      "title": "...",
      "channel_name": "...",
      "thumbnail_url": "...",
      "reason": "Never opened",
      "days_since_viewed": null
    },
    {
      "id": "def456",
      "title": "...",
      "channel_name": "...",
      "thumbnail_url": "...",
      "reason": "Last viewed 247 days ago",
      "days_since_viewed": 247
    }
  ],
  "expires_at": "2026-06-21T14:30:00Z",
  "is_expired": false
}
```

**Logic:**
1. Check if shelf exists and is not expired
2. If expired (or missing), call `generate_rediscover_shelf` and store
3. Return shelf with "reason" labels computed from `personal_view_count` and `date_last_viewed`

### Route: `POST /api/rediscover-shelf/refresh`

Force regenerate the shelf. Returns same response structure as GET.

---

## Frontend Implementation

### Template/Component Changes

**Location:** Homepage, above main video grid or below header (togglable section).

**Structure:**
```html
<section class="rediscover-shelf" id="rediscover-shelf">
  <div class="shelf-header">
    <h2>Rediscover</h2>
    <button id="refresh-shelf-btn" class="secondary-btn">Refresh</button>
    <button class="toggle-btn" aria-label="Toggle shelf">−</button>
  </div>
  
  <div class="shelf-container">
    <div class="video-carousel">
      <!-- dynamically populated -->
      <div class="shelf-card" data-video-id="abc123">
        <a href="/watch/abc123">
          <img src="..." alt="...">
          <div class="card-info">
            <h3>Title</h3>
            <p class="channel">Channel Name</p>
            <p class="reason">Never opened</p>
          </div>
        </a>
      </div>
      ...
    </div>
  </div>
  
  <div class="shelf-footer">
    <p>Refreshes automatically in <span id="expires-in">6 days, 8 hours</span></p>
  </div>
</section>
```

### JavaScript Logic

**Fetch and render:**
1. `GET /api/rediscover-shelf` on page load
2. Populate carousel with cards; show reason for each video
3. Display countdown to expiration (update every minute or on timer)
4. Set `collapsed = localStorage.getItem('rediscover-shelf-collapsed')` to restore state

**Refresh button:**
1. `POST /api/rediscover-shelf/refresh`
2. Fade out, replace with new shelf, fade in
3. Update expiration countdown

**Click handling:**
- Clicking a card navigates to video page (normal link behavior)
- Viewing the video increments count via normal `record_visit` call

**Toggling:**
- Click header button to collapse/expand
- Store preference in `localStorage`
- Icon/text changes to "+" when collapsed

### Styling

- Horizontal scrollable carousel (similar to "Recently Added" if that existed)
- Responsive: on mobile, may stack vertically or use narrower cards
- "Reason" label styled subtly (grey, smaller font)
- Countdown timer in footer (e.g., "Refreshes in 5 days")

---

## Tests

### DB Layer (`tests/webapp/test_db.py`)

```python
class TestRediscoverShelf:
    def test_generates_shelf_with_20_videos(self, db_conn):
        """Shelf generation creates exactly 20 videos."""
    
    def test_prioritizes_unwatched(self, db_conn):
        """Unwatched videos are selected first."""
    
    def test_falls_back_to_oldest_viewed(self, db_conn):
        """If < 20 unwatched, adds oldest-viewed videos."""
    
    def test_shelf_expires_after_7_days(self, db_conn):
        """is_rediscover_shelf_expired returns True after 7 days."""
    
    def test_get_current_returns_none_when_expired(self, db_conn):
        """get_current_rediscover_shelf returns None if expired."""
    
    def test_refresh_regenerates_pool(self, db_conn):
        """refresh_rediscover_shelf deletes old and creates new."""
```

### API Layer (`tests/webapp/test_routes.py`)

```python
class TestRediscoverShelfAPI:
    def test_get_returns_shelf_with_reasons(self, client):
        """GET /api/rediscover-shelf returns shelf with reason labels."""
    
    def test_get_returns_none_when_expired(self, client):
        """GET when shelf is expired triggers regeneration."""
    
    def test_post_refresh_regenerates_and_resets_timer(self, client):
        """POST /api/rediscover-shelf/refresh regenerates and resets expires_at."""
    
    def test_reason_labels_computed_correctly(self, client):
        """Reason labels reflect personal_view_count and date_last_viewed."""
```

---

## Implementation Order

1. **DB layer:** `rediscover_shelf` table, new functions in `webapp/db/videos.py`
2. **API route:** GET and POST endpoints in `webapp/routes.py`
3. **Tests:** Write tests for DB and routes
4. **Frontend:** Add HTML/CSS/JS to homepage template
5. **Integration:** Wire up click handlers, localStorage for collapsed state
6. **Polish:** Responsiveness, animations, countdown timer

---

## Edge Cases & Considerations

- **Empty library:** If < 20 videos total, show what exists and mark shelf as "incomplete"
- **All videos watched recently:** Still show the 20 oldest-viewed (no bias threshold)
- **Deleted videos:** If a video in the shelf is deleted before refresh, handle gracefully (skip or regenerate)
- **Hidden videos:** Include them in the pool (user can unhide if they want to rediscover)
- **Performance:** Shelf generation is ~O(n) query; cache for 7 days so it's not expensive
- **Timezone issues:** Use UTC for `generated_at` and `expires_at` to avoid ambiguity

---

## Collapsed-State Redesign (2026-06-18)

**Problem:** The original collapsed state (see "Toggling" above) kept the full bordered box, background, padding, and both header buttons (Refresh, toggle) visible — only the carousel and footer were hidden via `display: none`. This gave the collapsed shelf the same visual weight as an active section, and the Refresh button made no sense to show when there was nothing visible to refresh.

**Decision:** Collapsed and expanded states now render structurally different chrome, not just hidden/shown content within the same box:

- **Collapsed:** a single full-width line, no border/background/padding — just a disclosure affordance (e.g. `▸ Rediscover`). No Refresh button (removed entirely from the DOM in this state, not just hidden). The entire line is the click target to re-expand — chosen over a small icon-only target for a larger, easier-to-hit hitbox.
- **Expanded:** unchanged from the original design — bordered box, Refresh + toggle buttons, carousel, footer.
- **Transition:** instant swap between the two, no animation. Considered an animated height/opacity transition, but rejected: the two states have structurally different shapes (box has border/padding/radius, the collapsed row has none), so animating between them smoothly is fiddly and risks introducing a new jarring moment — and the complaint was about the resting collapsed state, not the act of toggling.
- **Persistence:** unchanged — still stored in `localStorage` and restored on page load.

**Implemented as designed** — see the plan below. CSS-only restructuring plus a small toggle-script rewrite; no HTML markup changes were needed.

## Implementation Plan: Collapsed-State Redesign (2026-06-18)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the rediscover shelf's collapsed state a minimal, full-width clickable disclosure row instead of the current bordered box with a hidden carousel.

**Architecture:** CSS-only restructuring of the existing `.rediscover-shelf`/`.shelf-header` markup (no HTML changes needed — `.shelf-header` is already a full-width block element), plus a small rewrite of the existing toggle script in `webapp/templates/index.html` to (a) make the whole header the expand target when collapsed, (b) stop that click from re-triggering on the same gesture that just collapsed it, and (c) drop the now-dead `+`/`−` text-swapping since the toggle button is only ever visible in the expanded state.

**Tech Stack:** Plain CSS, vanilla JS (no build step, no new dependencies — matches the rest of the codebase).

---

### Task 1: Collapsed-state CSS

**Files:**
- Modify: `webapp/static/style.css:293-340`

- [ ] **Step 1: Replace the collapsed hide-rule and add the minimal-row styles**

Find this block (style.css:301-302):
```css
.rediscover-shelf.collapsed .shelf-container,
.rediscover-shelf.collapsed .shelf-footer { display: none; }
```

Replace it with:
```css
.rediscover-shelf.collapsed {
  margin: 0.75rem 0;
  padding: 0;
  background: none;
  border: none;
  border-radius: 0;
}

.rediscover-shelf.collapsed .shelf-container,
.rediscover-shelf.collapsed .shelf-footer,
.rediscover-shelf.collapsed .shelf-controls { display: none; }

.rediscover-shelf.collapsed .shelf-header {
  margin-bottom: 0;
  padding: 0.4rem 0.25rem;
  border-radius: 4px;
  cursor: pointer;
}

.rediscover-shelf.collapsed .shelf-header:hover { background: #1a1a1a; }
```

- [ ] **Step 2: Add the disclosure chevron**

Find this line (style.css:311):
```css
.shelf-header h2 { margin: 0; font-size: 1.1rem; }
```

Replace it with:
```css
.shelf-header h2 { margin: 0; font-size: 1.1rem; }

.shelf-header h2::before {
  content: "\25BE ";
  display: inline-block;
  font-size: 0.75em;
  color: #999;
}

.rediscover-shelf.collapsed .shelf-header h2::before { content: "\25B8 "; }
```

(`\25BE` is `▾`, `\25B8` is `▸` — using CSS escapes instead of literal unicode characters in the stylesheet avoids any source-encoding ambiguity.)

- [ ] **Step 3: Visual sanity check**

Run: `grep -n "rediscover-shelf.collapsed\|shelf-header h2::before" webapp/static/style.css`
Expected: 6 rule blocks total — the box override, the 3-selector hide rule, the header padding/cursor rule, the hover rule, and the two `::before` rules.

---

### Task 2: Toggle script rewrite

**Files:**
- Modify: `webapp/templates/index.html:264-278`

- [ ] **Step 1: Replace the collapse/expand script block**

Find this block (index.html:264-278):
```javascript
  // Shelf collapse/expand
  var shelf = document.getElementById('rediscover-shelf');
  var toggleBtn = document.getElementById('toggle-shelf-btn');
  var COLLAPSED_KEY = 'rediscover-shelf-collapsed';

  toggleBtn.addEventListener('click', function () {
    var isCollapsed = shelf.classList.toggle('collapsed');
    localStorage.setItem(COLLAPSED_KEY, isCollapsed ? 'true' : 'false');
    toggleBtn.textContent = isCollapsed ? '+' : '−';
  });

  if (localStorage.getItem(COLLAPSED_KEY) === 'true') {
    shelf.classList.add('collapsed');
    toggleBtn.textContent = '+';
  }
})();
```

Replace it with:
```javascript
  // Shelf collapse/expand
  var shelf = document.getElementById('rediscover-shelf');
  var shelfHeader = shelf.querySelector('.shelf-header');
  var toggleBtn = document.getElementById('toggle-shelf-btn');
  var COLLAPSED_KEY = 'rediscover-shelf-collapsed';

  function setShelfCollapsed(collapsed) {
    shelf.classList.toggle('collapsed', collapsed);
    localStorage.setItem(COLLAPSED_KEY, collapsed ? 'true' : 'false');
  }

  // Toggle button is only ever visible while expanded — its one job is to collapse.
  toggleBtn.addEventListener('click', function (e) {
    e.stopPropagation(); // don't let this bubble into shelfHeader's expand-on-click listener below
    setShelfCollapsed(true);
  });

  // While collapsed, the whole header row (not just a small button) is the expand target.
  shelfHeader.addEventListener('click', function () {
    if (shelf.classList.contains('collapsed')) setShelfCollapsed(false);
  });

  if (localStorage.getItem(COLLAPSED_KEY) === 'true') {
    setShelfCollapsed(true);
  }
})();
```

**Why `e.stopPropagation()` is required, not optional:** `toggleBtn` is a descendant of `shelfHeader`, so a click on it bubbles up to `shelfHeader`'s own click listener after `toggleBtn`'s handler runs. Without `stopPropagation()`, clicking the toggle button while expanded would: (1) `toggleBtn`'s handler runs first, calling `setShelfCollapsed(true)` — the `collapsed` class is now present; (2) the same click event bubbles to `shelfHeader`'s listener, which checks `classList.contains('collapsed')` — now true — and immediately calls `setShelfCollapsed(false)`, undoing step 1. Net effect without the fix: clicking the toggle button would appear to do nothing. This is a real bug to verify against, not a defensive afterthought — Step 2 below specifically checks for it.

**Why the `+`/`−` text-swap is removed:** in the old design `toggleBtn` stayed visible in both states, so the symbol needed to reflect "what happens next." In the new design `.shelf-controls` (which contains `toggleBtn`) is hidden via CSS whenever `.collapsed` is set (Task 1, Step 1), so `toggleBtn` is only ever visible in the expanded state, where its action is always "collapse." A static `−` (already in the HTML as the button's text content) is correct in every state it's actually shown in — keeping the JS branch would be dead code per the project's "remove old approaches when replacing them" convention.

- [ ] **Step 2: Manual verification in a browser**

There's no JS test framework in this codebase yet (see `TODO.md` tech-debt list), so this is verified by hand:
1. Start the app against a copy of real data: `cp viewtube.db /tmp/viewtube-verify.db && python -m webapp.cli --db /tmp/viewtube-verify.db --port 5099`
2. Open `http://127.0.0.1:5099/` in a browser.
3. Confirm expanded state is pixel-identical to before (box, Refresh button, toggle button, carousel, footer).
4. Click the `−` toggle button. Confirm: box border/background/padding disappear, Refresh button disappears, carousel and footer disappear, only a thin `▸ Rediscover` line remains.
5. Click anywhere on that thin line (not just on the chevron). Confirm it re-expands to the full box.
6. Reload the page while expanded, click `−` again — confirm the toggle button collapse still works on a fresh state (this is the case `stopPropagation()` fixes; without it, clicking `−` would appear to do nothing).
7. Reload the page after leaving it collapsed — confirm it restores collapsed (the thin row), not the box.
8. Stop the server (`kill %1` or equivalent) and remove `/tmp/viewtube-verify.db`.

---

### Task 3: Documentation

**Files:**
- Modify: `plan-rediscover-shelf.md` (this file)
- Modify: `CHANGELOG.md`

- [ ] **Step 1:** In `plan-rediscover-shelf.md`, under "Collapsed-State Redesign (2026-06-18)" (added during brainstorming), add one line confirming implementation landed as designed, or note any deviation found during manual verification (Task 2, Step 2).

- [ ] **Step 2:** Append a `CHANGELOG.md` entry dated 2026-06-18 (or the current date if this lands later) describing the change and at least one trade-off, per the project's "Always update the changelog" convention. Trade-off to mention: the collapsed-state click target is the *entire* header row, but the *expand* affordance is only a static chevron + label with no button styling — slightly less visually obvious as "clickable" than a real button, traded for the requested minimal/quiet look.

- [ ] **Step 3:** Leave all changes staged but **do not run `git commit`** — this project's convention is to only commit when the user explicitly asks (see prior turns in this session).

---

## Header Controls Redesign (2026-06-18, follow-up)

**Problem:** After the collapsed-state redesign above, the header still had two separate interactive elements (Refresh, toggle) plus a click-to-expand zone on the whole row when collapsed — three different click targets across two states.

**Decision:**
- The dedicated toggle button (`#toggle-shelf-btn`) is removed entirely. Refresh (`#refresh-shelf-btn`) takes over that same square slot (2rem × 2rem, red background — same visual treatment the toggle button had), with its label changed from the text "Refresh" to the icon `↻`, plus `aria-label="Refresh shelf"` since it's now icon-only.
- Toggling (both expand and collapse) is now done by clicking the **"Rediscover"** label (the `<h2>`) specifically — not the whole header row, not a separate button. This is a narrower click target than the "whole line clickable" decision from the original collapsed-state redesign, but deliberate: there are now two independent interactive elements sharing the header row (label = toggle, icon = refresh), so the label needs an unambiguous boundary rather than overlapping with a whole-row click zone.
- Because Refresh and the label are siblings (not nested) under `.shelf-header`, the `e.stopPropagation()` workaround from the previous redesign is no longer needed — there's no event-bubbling path between them to defend against. Removed as dead code rather than left in place "just in case."
- Refresh still hides when collapsed (unchanged from the original decision) — confirmed explicitly rather than assumed, since the new layout made it a live question again.
- The chevron (`▾`/`▸`) grows from `0.75em` to `1.3em`.

**Implemented as designed** — see the plan below.

### Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the separate Refresh + toggle buttons with a single icon-only Refresh button (in the toggle button's old square slot) and make the "Rediscover" label itself the expand/collapse control.

**Architecture:** Pure HTML/CSS/JS-in-template change to `webapp/templates/index.html` and `webapp/static/style.css` — no DB/route/Python involved. One button element is deleted, one is restyled and relabeled, one CSS class is renamed for its actual purpose (`.toggle-btn` → `.shelf-icon-btn`, since it now sizes the refresh button, not a toggle button), and the toggle script's two listeners collapse into one.

**Tech Stack:** Plain CSS, vanilla JS, Jinja2 HTML — matches the rest of the codebase, no new dependencies.

---

#### Task 1: Markup — remove the toggle button, restyle Refresh as an icon button

**Files:**
- Modify: `webapp/templates/index.html:106-117`

- [ ] **Step 1: Replace the shelf header markup**

Find (index.html:106-117):
```html
<section class="rediscover-shelf" id="rediscover-shelf">
  <div class="shelf-header">
    <h2>Rediscover</h2>
    <div class="shelf-controls">
      <button id="refresh-shelf-btn"
              class="secondary-btn"
              hx-post="/rediscover-shelf/refresh"
              hx-target="#shelf-carousel"
              hx-swap="innerHTML">Refresh</button>
      <button id="toggle-shelf-btn" class="toggle-btn" aria-label="Toggle shelf">−</button>
    </div>
  </div>
```

Replace with:
```html
<section class="rediscover-shelf" id="rediscover-shelf">
  <div class="shelf-header">
    <h2>Rediscover</h2>
    <div class="shelf-controls">
      <button id="refresh-shelf-btn"
              class="shelf-icon-btn"
              aria-label="Refresh shelf"
              hx-post="/rediscover-shelf/refresh"
              hx-target="#shelf-carousel"
              hx-swap="innerHTML">&#8635;</button>
    </div>
  </div>
```

(`&#8635;` is `↻`, U+21BB CLOCKWISE OPEN CIRCLE ARROW — written as a numeric character reference rather than the literal glyph to avoid any template-file encoding ambiguity, matching the CSS escape approach already used for the chevron in style.css.)

- [ ] **Step 2: Confirm the toggle button is gone and Refresh is icon-only**

Run: `grep -n "toggle-shelf-btn\|refresh-shelf-btn" webapp/templates/index.html`
Expected: one match only, for `refresh-shelf-btn`, with `class="shelf-icon-btn"` and `aria-label="Refresh shelf"` — no `toggle-shelf-btn` anywhere.

---

#### Task 2: CSS — rename `.toggle-btn` to `.shelf-icon-btn`, rework collapsed-header hover, grow the chevron

**Files:**
- Modify: `webapp/static/style.css:301-369` (exact end line for `.toggle-btn` may vary slightly — find the block by content, shown below)

- [ ] **Step 1: Drop the now-dead hover/cursor rules from the collapsed header, keep the layout-only parts**

Find (style.css:313-320):
```css
.rediscover-shelf.collapsed .shelf-header {
  margin-bottom: 0;
  padding: 0.4rem 0.25rem;
  border-radius: 4px;
  cursor: pointer;
}

.rediscover-shelf.collapsed .shelf-header:hover { background: #1a1a1a; }
```

Replace with:
```css
.rediscover-shelf.collapsed .shelf-header {
  margin-bottom: 0;
  padding: 0.4rem 0.25rem;
}
```

- [ ] **Step 2: Move the click affordance onto the label itself, grow the chevron**

Find (style.css, now shifted up ~5 lines from Step 1's removal — find by content):
```css
.shelf-header h2 { margin: 0; font-size: 1.1rem; }

.shelf-header h2::before {
  content: "\25BE ";
  display: inline-block;
  font-size: 0.75em;
  color: #999;
}
```

Replace with:
```css
.shelf-header h2 { margin: 0; font-size: 1.1rem; cursor: pointer; }

.shelf-header h2:hover { color: #fff; }

.shelf-header h2::before {
  content: "\25BE ";
  display: inline-block;
  font-size: 1.3em;
  color: #999;
}
```

- [ ] **Step 3: Rename `.toggle-btn` to `.shelf-icon-btn`**

Find:
```css
.toggle-btn {
  width: 2rem;
  height: 2rem;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1rem;
}
```

Replace with:
```css
.shelf-icon-btn {
  width: 2rem;
  height: 2rem;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1rem;
}
```

- [ ] **Step 4: Confirm no orphaned `.toggle-btn` references remain anywhere**

Run: `grep -rn "toggle-btn" webapp/`
Expected: no matches at all (HTML reference removed in Task 1, CSS rule renamed in this step).

Run: `grep -n "shelf-icon-btn\|shelf-header h2" webapp/static/style.css`
Expected: `.shelf-icon-btn` rule present once; `.shelf-header h2`, `.shelf-header h2:hover`, and `.shelf-header h2::before` all present.

---

#### Task 3: JS — collapse the two toggle listeners into one, on the label

**Files:**
- Modify: `webapp/templates/index.html` (the shelf collapse/expand script block, currently around line 264 — find by content since Tasks 1-2 don't shift this)

- [ ] **Step 1: Replace the toggle script**

Find:
```javascript
  // Shelf collapse/expand
  var shelf = document.getElementById('rediscover-shelf');
  var shelfHeader = shelf.querySelector('.shelf-header');
  var toggleBtn = document.getElementById('toggle-shelf-btn');
  var COLLAPSED_KEY = 'rediscover-shelf-collapsed';

  function setShelfCollapsed(collapsed) {
    shelf.classList.toggle('collapsed', collapsed);
    localStorage.setItem(COLLAPSED_KEY, collapsed ? 'true' : 'false');
  }

  // Toggle button is only ever visible while expanded — its one job is to collapse.
  toggleBtn.addEventListener('click', function (e) {
    e.stopPropagation(); // don't let this bubble into shelfHeader's expand-on-click listener below
    setShelfCollapsed(true);
  });

  // While collapsed, the whole header row (not just a small button) is the expand target.
  shelfHeader.addEventListener('click', function () {
    if (shelf.classList.contains('collapsed')) setShelfCollapsed(false);
  });

  if (localStorage.getItem(COLLAPSED_KEY) === 'true') {
    setShelfCollapsed(true);
  }
```

Replace with:
```javascript
  // Shelf collapse/expand
  var shelf = document.getElementById('rediscover-shelf');
  var shelfLabel = shelf.querySelector('.shelf-header h2');
  var COLLAPSED_KEY = 'rediscover-shelf-collapsed';

  function setShelfCollapsed(collapsed) {
    shelf.classList.toggle('collapsed', collapsed);
    localStorage.setItem(COLLAPSED_KEY, collapsed ? 'true' : 'false');
  }

  // The "Rediscover" label is the only toggle target, in both directions. It's a sibling
  // of the refresh button (not an ancestor), so there's no event-bubbling path between them
  // and no stopPropagation() needed.
  shelfLabel.addEventListener('click', function () {
    setShelfCollapsed(!shelf.classList.contains('collapsed'));
  });

  if (localStorage.getItem(COLLAPSED_KEY) === 'true') {
    setShelfCollapsed(true);
  }
```

- [ ] **Step 2: Confirm the old listener variables and workaround are gone**

Run: `grep -n "toggleBtn\|shelfHeader\|stopPropagation\|shelfLabel" webapp/templates/index.html`
Expected: only `shelfLabel` matches (3 occurrences: declaration, the `querySelector` call, and the `addEventListener` line). No `toggleBtn`, `shelfHeader`, or `stopPropagation`.

---

#### Task 4: Verify and document

**Files:**
- Modify: `plan-rediscover-shelf.md` (this file)
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Run the existing test suite (sanity check — no Python touched)**

Run: `python -m pytest -q`
Expected: `391 passed` (same count as before this change — this redesign touches no Python).

- [ ] **Step 2: Structural verification against a copy of real data**

```bash
cp viewtube.db /tmp/viewtube-verify4.db
python -m webapp.cli --db /tmp/viewtube-verify4.db --port 5096 &
sleep 1.5
curl -s http://127.0.0.1:5096/ | grep -o '<button id="refresh-shelf-btn"[^>]*>.\{0,40\}' 
curl -s http://127.0.0.1:5096/ | grep -c 'toggle-shelf-btn'
curl -s http://127.0.0.1:5096/static/style.css | grep -n "shelf-icon-btn\|toggle-btn"
kill %1
rm -f /tmp/viewtube-verify4.db
```
Expected: the first `curl` shows `class="shelf-icon-btn"` and `aria-label="Refresh shelf"` on the button tag; the second `curl -c` count is `0`; the third shows `shelf-icon-btn` present and zero lines containing the bare token `toggle-btn`.

This only confirms the markup/CSS/JS are structurally correct as served — it does **not** verify the actual click behavior in a real browser (no browser automation tooling available in this environment, consistent with the rest of this session). Flag this explicitly to the user and suggest they manually click-test: clicking the label collapses/expands in both directions, and clicking the refresh icon does not toggle the shelf.

- [ ] **Step 3: Update `plan-rediscover-shelf.md`**

Add one line under "Header Controls Redesign (2026-06-18, follow-up)" confirming it was implemented as designed, or noting any deviation found during verification.

- [ ] **Step 4: Append a `CHANGELOG.md` entry**

Dated 2026-06-18 (or current date if later), describing: toggle button removed, Refresh moved into its slot as an icon button, label is now the single toggle target for both directions, `stopPropagation()` removed as no-longer-needed. Trade-off to note: the toggle action has no visible button affordance at all now (just a label that happens to be clickable) — slightly less discoverable than a dedicated button, traded for the cleaner two-element header layout.

- [ ] **Step 5: Leave changes staged, do not commit**

This project's convention (established throughout this session) is to only run `git commit` when the user explicitly asks.

---

## Fix Header Jump on Toggle (2026-06-18, second follow-up)

**Problem:** `.rediscover-shelf`'s box padding (1rem, expanded) applied to everything inside it, including `.shelf-header`. Collapsing dropped that padding to 0, so the header — and the "Rediscover" label that's now the click target — visually shifted position on every toggle. Jarring specifically because the thing you just clicked moves under your cursor.

**Decision:** Move the box styling (padding, background, border, border-radius) off `.rediscover-shelf` and onto a new wrapper, `.shelf-body`, around just the carousel + footer. `.shelf-header` becomes a sibling of `.shelf-body` rather than a padded child of the box — it renders identically in both states, so it never moves. Collapsing becomes a single `display: none` on `.shelf-body` instead of the previous 4-property override (padding/background/border/border-radius back to none) on `.rediscover-shelf` itself.

**Side effect (intentional improvement, not a regression):** the label now aligns with the toolbar/search bar above it and with `.page-header h1` on other pages (all three sit directly in `main`'s page-level padding) rather than being extra-inset by the box's own 1rem padding. The carousel/footer content keeps its own 1rem inset inside the box — a standard "heading above a card" layout.

**Implemented as designed** — see the plan below.

### Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the header position jump by moving the box's visual chrome onto a new `.shelf-body` wrapper, leaving `.shelf-header` always unboxed.

**Architecture:** One HTML wrap (carousel + footer inside a new `<div class="shelf-body">`) and a CSS move (box properties relocate from `.rediscover-shelf` to `.shelf-body`; collapsed-state override simplifies to one `display: none` instead of four property resets).

**Tech Stack:** Plain CSS, Jinja2 HTML — no JS changes needed this time (the toggle script already just flips the `.collapsed` class; it doesn't know or care what that class affects).

---

#### Task 1: Wrap carousel + footer in `.shelf-body`

**Files:**
- Modify: `webapp/templates/index.html:106-131`

- [ ] **Step 1: Add the wrapper div**

Find (index.html:118-131):
```html
  </div>

  <div class="shelf-container" id="shelf-container">
    <button class="carousel-arrow carousel-arrow--prev" id="shelf-prev" aria-label="Previous">&#8249;</button>
    <div class="shelf-viewport">
      <div class="shelf-track" id="shelf-carousel">
        {% include "_shelf_cards.html" %}
      </div>
    </div>
    <button class="carousel-arrow carousel-arrow--next" id="shelf-next" aria-label="Next">&#8250;</button>
  </div>

  <div class="shelf-footer">
    <p>Refreshes automatically in <span id="expires-in">{{ expires_label }}</span></p>
  </div>
```

Replace with:
```html
  </div>

  <div class="shelf-body">
    <div class="shelf-container" id="shelf-container">
      <button class="carousel-arrow carousel-arrow--prev" id="shelf-prev" aria-label="Previous">&#8249;</button>
      <div class="shelf-viewport">
        <div class="shelf-track" id="shelf-carousel">
          {% include "_shelf_cards.html" %}
        </div>
      </div>
      <button class="carousel-arrow carousel-arrow--next" id="shelf-next" aria-label="Next">&#8250;</button>
    </div>

    <div class="shelf-footer">
      <p>Refreshes automatically in <span id="expires-in">{{ expires_label }}</span></p>
    </div>
  </div>
```

(The closing `</div>` for `.shelf-header` stays exactly where it is — only what comes after it changes.)

- [ ] **Step 2: Confirm the wrapper is in place and nothing else moved**

Run: `grep -n "shelf-body\|shelf-header\|shelf-container\|shelf-footer" webapp/templates/index.html`
Expected: `shelf-body` appears twice (opening div and the closing comment context), `shelf-header` once, `shelf-container` and `shelf-footer` each still appear with their original `id`/class intact, now nested one level deeper.

---

#### Task 2: Move box styling to `.shelf-body`, simplify the collapsed override

**Files:**
- Modify: `webapp/static/style.css:293-317`

- [ ] **Step 1: Strip the box properties off `.rediscover-shelf` and its collapsed override**

Find (style.css:293-317):
```css
.rediscover-shelf {
  margin: 1.5rem 0 2rem;
  padding: 1rem;
  background: #0d0d0d;
  border: 1px solid #333;
  border-radius: 6px;
}

.rediscover-shelf.collapsed {
  margin: 0.75rem 0;
  padding: 0;
  background: none;
  border: none;
  border-radius: 0;
}

.rediscover-shelf.collapsed .shelf-container,
.rediscover-shelf.collapsed .shelf-footer,
.rediscover-shelf.collapsed .shelf-controls { display: none; }

.rediscover-shelf.collapsed .shelf-header {
  margin-bottom: 0;
  padding: 0.4rem 0.25rem;
}
```

Replace with:
```css
.rediscover-shelf {
  margin: 1.5rem 0 2rem;
}

.rediscover-shelf.collapsed {
  margin: 0.75rem 0;
}

.rediscover-shelf.collapsed .shelf-body,
.rediscover-shelf.collapsed .shelf-controls { display: none; }

.rediscover-shelf.collapsed .shelf-header {
  margin-bottom: 0;
}

.shelf-body {
  padding: 1rem;
  background: #0d0d0d;
  border: 1px solid #333;
  border-radius: 6px;
}
```

(`.shelf-header` itself gets no padding in either state now — previously it only had padding in the collapsed case, which was itself a smaller version of the same jump bug. Zero padding in both states means zero position change.)

- [ ] **Step 2: Confirm the box properties moved, not duplicated**

Run: `grep -n "^\.rediscover-shelf\|^\.shelf-body" webapp/static/style.css`
Expected: `.rediscover-shelf { margin: 1.5rem 0 2rem; }` and `.rediscover-shelf.collapsed { margin: 0.75rem 0; }` with no `padding`/`background`/`border` on either — those properties now appear only under `.shelf-body { ... }`.

---

#### Task 3: Verify and document

**Files:**
- Modify: `plan-rediscover-shelf.md` (this file)
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Run the test suite (sanity check, no Python touched)**

Run: `python -m pytest -q`
Expected: `391 passed`.

- [ ] **Step 2: Structural verification against a copy of real data**

```bash
cp viewtube.db /tmp/viewtube-verify5.db
python -m webapp.cli --db /tmp/viewtube-verify5.db --port 5094 &
sleep 1.5
curl -s http://127.0.0.1:5094/ | grep -A2 'class="shelf-header"' | tail -1
curl -s http://127.0.0.1:5094/ | grep -c 'class="shelf-body"'
curl -s http://127.0.0.1:5094/static/style.css | grep -n "^\.rediscover-shelf \|^\.shelf-body"
kill %1
rm -f /tmp/viewtube-verify5.db
```
Expected: the `.shelf-header` div is immediately followed by `<div class="shelf-body">` (count of 1), and the CSS shows box properties under `.shelf-body` only. As before, this confirms structure only — not the actual absence of a visual jump, which needs a real browser. Tell the user this explicitly.

- [ ] **Step 3: Update `plan-rediscover-shelf.md` and `CHANGELOG.md`**

Add a confirmation line under "Fix Header Jump on Toggle" noting it was implemented as designed (or any deviation found). Append a `CHANGELOG.md` entry dated 2026-06-18 describing the `.shelf-body` wrapper, why it fixes the jump, and the alignment side-effect (label now lines up with the toolbar/page headers instead of being box-inset).

- [ ] **Step 4: Leave changes staged, do not commit** — per this project's established convention.

---

## Hide Carousel Arrows When Nothing to Scroll To (2026-06-19)

**Problem:** The carousel always showed prev/next arrows and always built wraparound clones, even when the shelf had fewer real videos than the current viewport's visible slot count (e.g. 2 real videos on a 4-wide desktop layout). There was nothing to scroll to, and worse, the unused slots in the viewport would have shown the *start of the wraparound clone strip* — a duplicate of the first real card — rather than empty space.

**Decision:**
- `initCarousel()` computes `needsCarousel = realCount > visibleCount` (visible count is the existing 4/3/2/1 breakpoint logic, based on viewport width). When false, the function skips building wraparound clones entirely and renders the real cards as a plain static row — no transform, no scroll — and hides both arrow buttons (`display: none`). When the shelf is empty (0 real cards), the arrows are likewise hidden (a pre-existing latent gap: arrows used to stay visible-but-inert when the shelf was empty, since `initCarousel` returned before attaching click handlers in that case — now both empty and under-full cases are unified under the same `needsCarousel` check).
- **Card width in the under-full case:** cards keep the *same per-card width* a full row would use (computed from the breakpoint's visible-count, not the actual real count), rather than stretching to fill the row evenly. Leaves a trailing gap when under-full; chosen for visual consistency over a per-shelf-size-dependent card width.
- **Reactive to resize, not computed once:** visible-count is breakpoint-driven (1200/900/600px), so whether arrows are needed can change as the window is resized, independent of the shelf's video count. The resize handler now checks whether the breakpoint crossed the `needsCarousel` threshold and, if so, calls `initCarousel()` again (full rebuild — clones, handlers, arrow visibility) instead of the lightweight width/position-only resize used when the mode hasn't changed.
- **Practical scope:** the shelf pool is normally up to 20 videos, so in practice this matters mainly for small/new libraries, or once videos have been removed from the current shelf via the remove-from-Rediscover button — i.e. exactly the case it was built to anticipate, not a hypothetical.
- Removed three write-only module state variables (`carouselOffset`, `carouselRealCount`, `carouselVis`) discovered to be dead while rewriting this function — set but never read anywhere in the codebase.

## Future Enhancements (Not in Scope)

- Shuffle/reorder shelf without full refresh (new 20 from same pool)
- Time-based bias (prioritize videos not viewed in 6+ months)
- Tag-based shelf variant (e.g., "Rediscover from Jazz tag")
- "Skip this video" button to exclude from current shelf
- Analytics: track which rediscovered videos actually get watched

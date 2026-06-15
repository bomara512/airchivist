# Plan: Rediscover Shelf — Least Recently Viewed Videos

## Context

Goal: Surface stale content the user hasn't engaged with in a while. A shelf on the homepage shows 20 randomly selected videos from the least-recently-viewed pool, regenerated once per week. Helps combat the "I forgot I had this" problem when library grows large.

## Design Decisions (Locked In)

**Pool selection:** Prioritize unwatched (`personal_view_count = 0`), then fall back to videos ordered by oldest `date_last_viewed`.

**Pool scope:** Completely random across the entire library; no tag/channel/quality bias; no exclusions (include hidden, very short, etc.).

**Stickiness:** Shelf is sticky for 7 days from first load. Manual refresh regenerates the entire pool and resets the 7-day timer.

**UI:** Togglable/collapsible section on homepage. Each video card shows *why* it's there: "Never watched", "Last viewed 6 months ago", etc.

**Interaction:** Clicking a video increments `personal_view_count` and updates `date_last_viewed` (normal viewing behavior).

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

**Unwatched pool:**
```sql
SELECT id, video_id, title, channel_name, personal_view_count, date_last_viewed
FROM videos
WHERE personal_view_count = 0
ORDER BY date_added ASC
```

**Viewed pool (fallback):**
```sql
SELECT id, video_id, title, channel_name, personal_view_count, date_last_viewed
FROM videos
WHERE personal_view_count > 0
ORDER BY date_last_viewed ASC
```

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
        'reasons': {id1: 'Never watched', id2: 'Last viewed 6 months ago', ...},
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
      "reason": "Never watched",
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
            <p class="reason">Never watched</p>
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

## Future Enhancements (Not in Scope)

- Shuffle/reorder shelf without full refresh (new 20 from same pool)
- Time-based bias (prioritize videos not viewed in 6+ months)
- Tag-based shelf variant (e.g., "Rediscover from Jazz tag")
- "Skip this video" button to exclude from current shelf
- Analytics: track which rediscovered videos actually get watched

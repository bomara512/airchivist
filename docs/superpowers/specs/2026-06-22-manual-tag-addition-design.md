# Plan: Manual Tag Addition for a Single Video

## Context

Came up while debugging a video that ended up with zero canonical tags. Root cause turned out to be expected behavior (thin source metadata, the one raw tag it had was already marked noise) — but it surfaced that there's no way to manually give a video a tag directly. The only existing tagging mechanisms are automatic alias-matching at ingest time, and the `/tags` admin page's "unclassified tag pool" flow, which only works on raw tags that already exist on 2+ videos. A video with zero or noise-only raw tags has nothing to select there.

Goal: a lightweight, per-video "add a tag" action, available from wherever video cards already render.

## Design Decisions (Locked In)

> **Implementation confirmation (2026-06-22):** All design decisions below were implemented exactly as written across Tasks 1-4, and Task 5's structural verification (button/datalist singleton counts on `/` and `/hidden`, plus a live `POST /videos/<id>/tags/add`) found no deviation from this plan. The only thing not verified is the actual click/right-click interaction in a real browser (no automation tooling available in this environment) — see the "Manual verification" section below for what's left for the user to click-test.

**Trigger:** right-click context menu (the existing `#video-card-menu`, currently just "Archive video") — not a new visible button on the card. The thumbnail-overlay corner is already crowded (favorite, watch-later, and on the shelf, remove).

**Scope:** available everywhere video cards render, including the Hidden/Archived page. (Archive itself still doesn't show there — see Frontend Implementation for how the two are decoupled.)

**Input flow:** clicking "Add tag…" replaces the context menu with an inline `<input>` — not a modal. Enter submits, Escape or clicking outside cancels, mirroring the existing context-menu dismiss behavior. This matches how this app already handles small inline edits elsewhere (e.g. the `/tags` page's alias-edit flow replaces a pill with an input rather than opening a dialog).

**One tag per action.** No comma-separated multi-tag input. Repeat the action to add a second tag. Keeps the input itself trivial and matches how every other single-purpose card action already works.

**Autocomplete suggestions are canonical tags only**, not all tags. Reasons:
- Mirrors the existing `canonical-datalist` pattern on `/tags`, which is also canonical-only.
- The real database has 26,438 raw (non-canonical) tags vs. a much smaller canonical set — surfacing all of them would be unwieldy and mostly junk.
- Promoting a raw tag to canonical is already a distinct, deliberate workflow on `/tags`'s unclassified pool; this feature shouldn't blur into that.

**Typing a name with no canonical match creates a new canonical tag immediately**, no extra confirmation — matches existing behavior elsewhere in the app (the `/tags` page's "+ New canonical tag" form works the same way).

**Typing a name matching an existing raw (non-canonical) tag promotes it to canonical.** This is pre-existing behavior of `create_canonical_tag` (used today by the `/tags` page), not new risk introduced by this feature. Side effect worth being aware of: every other video that already carries that raw tag will retroactively show it as a canonical pill too, not just the one being tagged. The datalist being canonical-only makes this less likely to happen by accident (you'd have to type a raw tag's exact name by hand), but doesn't prevent it.

**Canonical tag names for the datalist are fetched eagerly**, via the existing global context processor (same pattern as `stats` in `webapp/app.py`), not lazily on first use. The canonical tag set is small, so this is cheap and avoids adding fetch-latency/loading-state handling to the input.

**The server returns rendered HTML (the tag-pills partial), not JSON.** Single source of truth for what a tag pill looks like — the client just swaps in the response, rather than duplicating pill markup in JS.

## Data Model

No schema changes. Uses the existing `tags` and `video_tags` tables.

## Backend Implementation

### New DB function — `webapp/db/tags.py`

```python
def get_canonical_tags_for_video(conn: sqlite3.Connection, video_id: str) -> list[str]:
    """Same as get_tags_for_video, but filtered to canonical tags only —
    matches what _video_card.html actually displays."""
    rows = conn.execute("""
        SELECT t.name FROM tags t
        JOIN video_tags vt ON vt.tag_id_fk = t.id
        JOIN videos v ON v.id = vt.video_id_fk
        WHERE v.video_id = ? AND t.is_canonical = 1
    """, (video_id,)).fetchall()
    return [r[0] for r in rows]
```

`get_tags_for_video` (existing) returns *all* tags including raw/noise ones — wrong shape for re-rendering the card's pill list, hence the new function rather than reusing it.

### Reused existing functions — no changes needed

- `create_canonical_tag(conn, name) -> int` (`webapp/db/tags.py`) — idempotent: creates a new canonical tag, or promotes an existing raw tag to canonical, either way returning its id.
- `add_video_tag(conn, video_id, tag_id) -> None` (`webapp/db/tags.py`) — `INSERT OR IGNORE`, so re-adding a tag the video already has is a harmless no-op.

### New route — `webapp/routes.py`

```python
@bp.route("/videos/<video_id>/tags/add", methods=["POST"])
def video_add_tag(video_id):
    tag_name = request.form.get("tag_name", "").strip()
    if not tag_name:
        abort(400)
    video = _db.get_video_by_id(g.db, video_id)
    if not video:
        abort(404)
    tag_id = _db.create_canonical_tag(g.db, tag_name)
    _db.add_video_tag(g.db, video_id, tag_id)
    tags = _db.get_canonical_tags_for_video(g.db, video_id)
    return render_template("_tag_pills.html", video={"video_id": video_id, "tags": ",".join(tags)})
```

Form-encoded `tag_name`, mirroring the existing `/videos/<id>/tags/remove` exactly (same param name, same encoding). No CORS headers — page-internal route, not extension-facing, consistent with `/tags/remove`.

### New partial — `webapp/templates/_tag_pills.html`

Extracted verbatim from `_video_card.html`'s existing inline tags block — pure refactor, zero behavior change:

```html
{% if video.tags %}
<div class="video-tags" data-video-id="{{ video.video_id }}">
  {% for tag_name in video.tags.split(',') %}
  <a href="{{ url_for('main.index', tag=tag_name) }}" class="tag-pill" data-tag-name="{{ tag_name | e }}">{{ tag_name }}</a>
  {% endfor %}
</div>
{% endif %}
```

`_video_card.html` replaces that inline block with `{% include "_tag_pills.html" %}` — `video` stays in scope via Jinja's default ambient-context include, so this is a no-op change to the existing rendering path. The route above constructs an equivalent `video` dict (`video_id` + comma-joined `tags`) so the same partial renders identically from both call sites.

### Global context processor — `webapp/app.py`

Extend `inject_stats` to also inject canonical tag names (e.g. `canonical_tag_names`), rendered into one global `<datalist id="canonical-tag-datalist">` added once in `base.html` — not duplicated per card.

## Frontend Implementation

### Context menu — `base.html`

Add a new item to the existing `#video-card-menu`:

```html
<button id="video-card-add-tag">Add tag…</button>
```

Change the `contextmenu` handler: remove the `.hidden-videos-grid` early-return exclusion that currently skips showing the menu entirely on the Hidden page. Instead, toggle just the Archive item's visibility right before showing the menu:

```js
document.getElementById('video-card-hide').style.display =
  card.closest('.hidden-videos-grid') ? 'none' : '';
```

`#video-card-add-tag` is unconditional — visible in every context.

### Inline input

Clicking "Add tag…": hide `cardMenu`, create a small `<input list="canonical-tag-datalist">` positioned where the menu was, autofocus it.

- **Enter** → `fetch('/videos/' + videoId + '/tags/add', { method: 'POST', body: new URLSearchParams({ tag_name: input.value }) })`. On success, replace the card's `.video-tags` div with the returned HTML if it exists, or insert it fresh (at the same position `_video_card.html` places it) if this was the video's first tag. Remove the input.
- **Escape / click outside** → remove the input, no request sent.

## Tests

### DB layer — `tests/webapp/test_db.py`

- `get_canonical_tags_for_video` returns only canonical tags, excluding raw and noise tags
- returns `[]` for a video with no canonical tags

### Route layer — `tests/webapp/test_routes.py`

- attaching an existing canonical tag → response includes that pill
- typing a brand-new name → creates it, response includes it
- typing a name matching an existing raw tag → promotes it; verify the cross-video side effect (another video already carrying that raw tag now shows it as canonical too)
- re-adding a tag the video already has → no duplicate, same pills returned
- blank `tag_name` → 400
- unknown `video_id` → 404

### Manual verification

No JS test framework exists in this codebase yet (tracked separately in `TODO.md`'s tech-debt list). The context-menu/inline-input/datalist behavior will be verified structurally via `curl`/`grep` against a copy of real data, consistent with this session's established pattern — actual click-testing in a real browser is left to the user, since no browser automation tooling is available in this environment.

## Edge Cases & Considerations

- Tag name normalization (`.strip().lower()`) is already handled by `create_canonical_tag` — no new validation needed.
- Re-adding an already-attached tag is a harmless no-op.
- Promoting a raw tag to canonical affects every video sharing that raw tag, not just the one being tagged — pre-existing behavior, not a new risk this feature introduces, but worth remembering since it's now reachable from a much more casual, frequent entry point than the `/tags` admin page.

## Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user attach a canonical tag to one specific video via a right-click action, available everywhere video cards render including the Hidden page.

**Architecture:** A new DB function plus two already-existing ones do all the data work; a new route renders a small extracted partial as the response so there's one place that knows what a tag pill looks like; the UI extends the existing video-card context menu with an inline, datalist-backed input rather than a modal.

**Tech Stack:** Flask/Jinja2, plain CSS, vanilla JS — no new dependencies, matches the rest of this codebase.

---

### Task 1: DB layer — `get_canonical_tags_for_video`

**Files:**
- Modify: `webapp/db/tags.py:35-42` (insert right after `get_tags_for_video`)
- Modify: `webapp/db/__init__.py` (export)
- Test: `tests/webapp/test_db.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/webapp/test_db.py` (matches the existing `TestVideoTagAssociations` style two classes above it; seed data has video `aaaaaaaaaa1` with one *raw* tag, `guitar`, id `1` — useful as the "should be excluded" control):

```python
class TestGetCanonicalTagsForVideo:
    def test_excludes_raw_tags(self, db_conn):
        from webapp.db import get_canonical_tags_for_video
        # aaaaaaaaaa1 has seed tag 'guitar' (id=1), which is raw (is_canonical=0)
        tags = get_canonical_tags_for_video(db_conn, "aaaaaaaaaa1")
        assert tags == []

    def test_returns_canonical_tags_only(self, db_conn):
        from webapp.db import get_canonical_tags_for_video, create_canonical_tag, add_video_tag
        canonical_id = create_canonical_tag(db_conn, "music")
        add_video_tag(db_conn, "aaaaaaaaaa1", canonical_id)
        tags = get_canonical_tags_for_video(db_conn, "aaaaaaaaaa1")
        assert tags == ["music"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/webapp/test_db.py -k TestGetCanonicalTagsForVideo -v`
Expected: both FAIL with `ImportError: cannot import name 'get_canonical_tags_for_video'`

- [ ] **Step 3: Implement**

In `webapp/db/tags.py`, immediately after `get_tags_for_video` (ends at line 42):

```python
def get_canonical_tags_for_video(conn: sqlite3.Connection, video_id: str) -> list[str]:
    """Same as get_tags_for_video, but filtered to canonical tags only —
    matches what _video_card.html actually displays."""
    rows = conn.execute("""
        SELECT t.name FROM tags t
        JOIN video_tags vt ON vt.tag_id_fk = t.id
        JOIN videos v ON v.id = vt.video_id_fk
        WHERE v.video_id = ? AND t.is_canonical = 1
    """, (video_id,)).fetchall()
    return [r[0] for r in rows]
```

In `webapp/db/__init__.py`, add `get_canonical_tags_for_video` to both the `from webapp.db.tags import (...)` block and the `__all__` list, in the same alphabetical position pattern the file already uses (next to `get_canonical_tags_for_filter`/`get_canonical_tags`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/webapp/test_db.py -k TestGetCanonicalTagsForVideo -v`
Expected: `2 passed`

---

### Task 2: Route + partial extraction

**Files:**
- Create: `webapp/templates/_tag_pills.html`
- Modify: `webapp/templates/_video_card.html:76-82`
- Modify: `webapp/routes.py` (insert after the existing `video_remove_tag` route, currently at lines 126-133)
- Test: `tests/webapp/test_routes.py`

- [ ] **Step 1: Extract the partial (pure refactor, no behavior change)**

Create `webapp/templates/_tag_pills.html`:

```html
{% if video.tags %}
<div class="video-tags" data-video-id="{{ video.video_id }}">
  {% for tag_name in video.tags.split(',') %}
  <a href="{{ url_for('main.index', tag=tag_name) }}" class="tag-pill" data-tag-name="{{ tag_name | e }}">{{ tag_name }}</a>
  {% endfor %}
</div>
{% endif %}
```

In `webapp/templates/_video_card.html`, replace lines 76-82:

```html
    {% if video.tags %}
    <div class="video-tags" data-video-id="{{ video.video_id }}">
      {% for tag_name in video.tags.split(',') %}
      <a href="{{ url_for('main.index', tag=tag_name) }}" class="tag-pill" data-tag-name="{{ tag_name | e }}">{{ tag_name }}</a>
      {% endfor %}
    </div>
    {% endif %}
```

with:

```html
    {% include "_tag_pills.html" %}
```

(`video` stays in scope automatically — Jinja's `include` shares the calling template's context by default.)

- [ ] **Step 2: Run the full suite to confirm the refactor changed nothing**

Run: `python -m pytest -q`
Expected: same pass count as before this task (this step is a pure extraction; if anything changes, stop and investigate before continuing)

- [ ] **Step 3: Write the failing route tests**

Append to `tests/webapp/test_routes.py` (mirrors the `client.application.config["DATABASE"]` direct-DB-assertion pattern from `TestRemoveFromRediscoverShelfRoute`):

```python
class TestAddTagRoute:
    def _seed_canonical(self, client, name):
        import sqlite3
        conn = sqlite3.connect(client.application.config["DATABASE"])
        conn.execute("INSERT INTO tags (name, is_canonical) VALUES (?, 1)", (name,))
        conn.commit()
        conn.close()

    def test_attach_existing_canonical_tag(self, client):
        self._seed_canonical(client, "music")
        resp = client.post("/videos/aaaaaaaaaa1/tags/add", data={"tag_name": "music"})
        assert resp.status_code == 200
        assert b'data-tag-name="music"' in resp.data

    def test_creates_brand_new_tag(self, client):
        resp = client.post("/videos/aaaaaaaaaa1/tags/add", data={"tag_name": "synthwave"})
        assert resp.status_code == 200
        assert b'data-tag-name="synthwave"' in resp.data

    def test_promotes_existing_raw_tag_and_affects_other_videos(self, client):
        # seed tag 'guitar' (id=1) is raw, used by both aaaaaaaaaa1 and aaaaaaaaaa3
        resp = client.post("/videos/aaaaaaaaaa1/tags/add", data={"tag_name": "guitar"})
        assert resp.status_code == 200
        assert b'data-tag-name="guitar"' in resp.data
        import sqlite3
        conn = sqlite3.connect(client.application.config["DATABASE"])
        rows = conn.execute(
            "SELECT t.name FROM tags t JOIN video_tags vt ON vt.tag_id_fk = t.id "
            "JOIN videos v ON v.id = vt.video_id_fk "
            "WHERE v.video_id = 'aaaaaaaaaa3' AND t.is_canonical = 1"
        ).fetchall()
        conn.close()
        assert ("guitar",) in rows

    def test_idempotent_reattach(self, client):
        self._seed_canonical(client, "music")
        client.post("/videos/aaaaaaaaaa1/tags/add", data={"tag_name": "music"})
        resp = client.post("/videos/aaaaaaaaaa1/tags/add", data={"tag_name": "music"})
        assert resp.status_code == 200
        assert resp.data.count(b'data-tag-name="music"') == 1

    def test_blank_tag_name_returns_400(self, client):
        resp = client.post("/videos/aaaaaaaaaa1/tags/add", data={"tag_name": "   "})
        assert resp.status_code == 400

    def test_unknown_video_returns_404(self, client):
        resp = client.post("/videos/doesnotexist/tags/add", data={"tag_name": "music"})
        assert resp.status_code == 404
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python -m pytest tests/webapp/test_routes.py -k TestAddTagRoute -v`
Expected: all FAIL with 404 (route doesn't exist yet)

- [ ] **Step 5: Implement the route**

In `webapp/routes.py`, immediately after `video_remove_tag` (currently lines 126-133):

```python
@bp.route("/videos/<video_id>/tags/add", methods=["POST"])
def video_add_tag(video_id):
    tag_name = request.form.get("tag_name", "").strip()
    if not tag_name:
        abort(400)
    video = _db.get_video_by_id(g.db, video_id)
    if not video:
        abort(404)
    tag_id = _db.create_canonical_tag(g.db, tag_name)
    _db.add_video_tag(g.db, video_id, tag_id)
    tags = _db.get_canonical_tags_for_video(g.db, video_id)
    return render_template("_tag_pills.html", video={"video_id": video_id, "tags": ",".join(tags)})
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/webapp/test_routes.py -k TestAddTagRoute -v`
Expected: `6 passed`

- [ ] **Step 7: Run the full suite**

Run: `python -m pytest -q`
Expected: all passing, count increased by 8 over this task's start (2 from Task 1 + 6 from this task)

---

### Task 3: Canonical tag names available globally (for the datalist)

**Files:**
- Modify: `webapp/app.py:24-29` (insert a new context processor, following the existing `inject_watch_later_ids` one-processor-per-concern pattern)
- Modify: `webapp/templates/base.html` (add the global `<datalist>`)

- [ ] **Step 1: Add the context processor**

In `webapp/app.py`, add the import and a new context processor, following the exact pattern of the existing `inject_watch_later_ids` (lines 31-36):

Change the import line (line 5):
```python
from webapp.db import init_webapp_tables, get_stats, get_watch_later_video_ids, get_canonical_tags_for_filter
```

Add after `inject_watch_later_ids` (after line 36):
```python
    @app.context_processor
    def inject_canonical_tag_names():
        db = g.get("db")
        if db is None:
            return {"canonical_tag_names": []}
        return {"canonical_tag_names": get_canonical_tags_for_filter(db)}
```

(Reuses the existing `get_canonical_tags_for_filter` — already returns exactly a flat, sorted list of canonical tag names with at least one video, the same function that already powers the main page's tag filter dropdown. No new DB function needed here.)

- [ ] **Step 2: Add the datalist to base.html**

In `webapp/templates/base.html`, immediately after the existing context-menu divs (after line 48, the closing `</div>` of `#video-card-menu`):

```html

  <datalist id="canonical-tag-datalist">
    {% for name in canonical_tag_names %}
    <option value="{{ name }}">
    {% endfor %}
  </datalist>
```

- [ ] **Step 3: Verify the suite still passes (no Python logic changed in a way tests cover yet, but confirms no syntax errors)**

Run: `python -m pytest -q`
Expected: same count as end of Task 2

---

### Task 4: Context menu UI — "Add tag…" item, inline popover, Hidden-page decoupling

**Files:**
- Modify: `webapp/templates/base.html:46-48` (menu markup)
- Modify: `webapp/templates/base.html` (new popover markup, after the datalist added in Task 3)
- Modify: `webapp/templates/base.html:161-170` (contextmenu handler — remove the `.hidden-videos-grid` exclusion)
- Modify: `webapp/templates/base.html:172-179` (generic dismiss-on-outside-click / Escape handlers — extend for the new popover)
- Modify: `webapp/templates/base.html` (new click handler for the add-tag button + input, placed after the existing `video-card-hide` handler, currently ending at line 200)
- Modify: `webapp/static/style.css` (new popover/input styles)

- [ ] **Step 1: Add the menu item**

In `webapp/templates/base.html`, change lines 46-48:

```html
  <div id="video-card-menu" class="context-menu">
    <button id="video-card-hide">Archive video</button>
  </div>
```

to:

```html
  <div id="video-card-menu" class="context-menu">
    <button id="video-card-hide">Archive video</button>
    <button id="video-card-add-tag">Add tag…</button>
  </div>

  <div id="video-card-add-tag-popover" class="context-menu add-tag-popover">
    <input id="video-card-add-tag-input" class="popover-input" list="canonical-tag-datalist" placeholder="Tag name…" autocomplete="off">
  </div>
```

- [ ] **Step 2: Decouple the Hidden-page exclusion from menu visibility**

Change line 162:
```js
      if (!card || card.closest('.hidden-videos-grid')) { hideCardMenu(); return; }
```
to:
```js
      if (!card) { hideCardMenu(); return; }
```

Then, immediately before `cardMenu.style.display = 'block';` (currently line 165), add:
```js
      document.getElementById('video-card-hide').style.display = card.closest('.hidden-videos-grid') ? 'none' : '';
```

So the block (currently lines 161-169) reads:
```js
      var card = e.target.closest('.video-card');
      if (!card) { hideCardMenu(); return; }
      e.preventDefault();
      activeCard = card;
      document.getElementById('video-card-hide').style.display = card.closest('.hidden-videos-grid') ? 'none' : '';
      cardMenu.style.display = 'block';
      var x = Math.min(e.clientX, window.innerWidth - cardMenu.offsetWidth - 8);
      var y = Math.min(e.clientY, window.innerHeight - cardMenu.offsetHeight - 8);
      cardMenu.style.left = x + 'px';
      cardMenu.style.top = y + 'px';
```

- [ ] **Step 3: Extend the generic dismiss handlers**

Change the existing outside-click handler (currently lines 172-175):
```js
    document.addEventListener('click', function (e) {
      if (!pillMenu.contains(e.target)) hidePillMenu();
      if (!cardMenu.contains(e.target)) hideCardMenu();
    });
```
to:
```js
    document.addEventListener('click', function (e) {
      if (!pillMenu.contains(e.target)) hidePillMenu();
      if (!cardMenu.contains(e.target)) hideCardMenu();
      if (!addTagPopover.contains(e.target)) hideAddTagPopover();
    });
```

Change the existing Escape handler (currently lines 177-179):
```js
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { hidePillMenu(); hideCardMenu(); }
    });
```
to:
```js
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { hidePillMenu(); hideCardMenu(); hideAddTagPopover(); }
    });
```

(`addTagPopover` and `hideAddTagPopover` are defined in Step 4 below — since these are `var`/`function` declarations inside the same enclosing IIFE, and the dismiss handlers run only in response to later user events, not at script-load time, declaration order within the IIFE doesn't matter here as long as both are defined before any click/keydown event actually fires.)

- [ ] **Step 4: Add the add-tag click handler and submit logic**

Add this immediately after the existing `video-card-hide` click handler (currently ending at line 200):

```js
    // Add tag to video — inline popover from the card context menu
    var addTagPopover = document.getElementById('video-card-add-tag-popover');
    var addTagInput = document.getElementById('video-card-add-tag-input');
    var addTagVideoId = null;

    function hideAddTagPopover() { addTagPopover.style.display = 'none'; addTagVideoId = null; }

    document.getElementById('video-card-add-tag').addEventListener('click', function (e) {
      e.stopPropagation(); // don't let this bubble into the outside-click handler above and immediately hide the popover it's about to show
      if (!activeCard) return;
      var rect = cardMenu.getBoundingClientRect();
      addTagVideoId = activeCard.dataset.videoId;
      hideCardMenu();
      addTagPopover.style.left = rect.left + 'px';
      addTagPopover.style.top = rect.top + 'px';
      addTagPopover.style.display = 'block';
      addTagInput.value = '';
      addTagInput.focus();
    });

    function submitAddTag() {
      var tagName = addTagInput.value.trim();
      var videoId = addTagVideoId;
      hideAddTagPopover();
      if (!tagName || !videoId) return;
      fetch('/videos/' + videoId + '/tags/add', {
        method: 'POST',
        body: new URLSearchParams({ tag_name: tagName })
      })
        .then(function (r) { return r.ok ? r.text() : null; })
        .then(function (html) {
          if (html === null) return;
          document.querySelectorAll('.video-card[data-video-id="' + videoId + '"]').forEach(function (card) {
            var infoDiv = card.querySelector('.video-info');
            var existingTags = infoDiv.querySelector('.video-tags');
            var hiddenActions = infoDiv.querySelector('.hidden-actions');
            if (existingTags) {
              existingTags.outerHTML = html;
            } else if (hiddenActions) {
              hiddenActions.insertAdjacentHTML('beforebegin', html);
            } else {
              infoDiv.insertAdjacentHTML('beforeend', html);
            }
          });
        });
    }

    addTagInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); submitAddTag(); }
    });
```

**Why `e.stopPropagation()` is required, not optional:** the "Add tag…" button lives inside `#video-card-menu`, not inside `#video-card-add-tag-popover`. Without it, clicking the button would: (1) the button's own handler runs, showing the popover; (2) the same click event bubbles to the document-level outside-click handler (Step 3), which checks `!addTagPopover.contains(e.target)` — true, since the button isn't inside the popover — and immediately calls `hideAddTagPopover()`, undoing step 1. This is the same bubbling failure mode fixed once already this session in the rediscover-shelf toggle button; verify against it specifically when testing.

**Why the three-way branch in `submitAddTag`'s `.forEach`:** `_video_card.html` places the tags block before the Hidden-page's restore/delete buttons (`.hidden-actions`), not after. Appending at the end of `.video-info` unconditionally would put a newly-added first tag visually after those buttons on the Hidden page — wrong position relative to what the server would render. Checking for `.hidden-actions` and inserting `beforebegin` keeps it correct there; both other contexts fall through to a plain append. Also note the result is applied to *every* `.video-card` matching that `data-video-id` (not just the one that was right-clicked), matching the existing favorite-button pattern that updates all instances of the same video.

- [ ] **Step 5: Add CSS**

In `webapp/static/style.css`, add near the existing `.alias-edit-input`/`.context-menu` rules:

```css
.add-tag-popover { padding: 0.4rem; }

.popover-input {
  display: block;
  width: 160px;
  background: #111;
  border: 1px solid #555;
  color: #e8e8e8;
  border-radius: 4px;
  padding: 0.3rem 0.5rem;
  font-size: 0.85rem;
}

.popover-input:focus { outline: none; border-color: #888; }
```

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: same count as end of Task 3 (this task is template/JS/CSS only, no Python changed)

---

### Task 5: Manual verification and docs

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `plan-webapp.md` (routes table)
- Modify: `TODO.md`
- Modify: `plan-manual-tagging.md` (this file — confirmation note)

- [ ] **Step 1: Structural verification against a copy of real data**

```bash
cp viewtube.db /tmp/viewtube-verify-tags.db
python -m webapp.cli --db /tmp/viewtube-verify-tags.db --port 5087 &
sleep 1.5
curl -s http://127.0.0.1:5087/ | grep -c 'id="video-card-add-tag"'
curl -s http://127.0.0.1:5087/ | grep -c 'id="canonical-tag-datalist"'
curl -s http://127.0.0.1:5087/hidden | grep -c 'id="video-card-add-tag"'
curl -s -X POST http://127.0.0.1:5087/videos/$(sqlite3 /tmp/viewtube-verify-tags.db "SELECT video_id FROM videos LIMIT 1;")/tags/add -d "tag_name=plan-test-tag" -w "\nHTTP %{http_code}\n"
kill %1
rm -f /tmp/viewtube-verify-tags.db
```

Expected: the add-tag button and datalist each appear exactly once per page load (singleton elements, not per-card — `video-card-add-tag` is one button shared by the whole context menu, not duplicated per card); the Hidden page also shows the button once; the `POST` returns 200 with the new tag's pill HTML.

This confirms structure and the HTTP contract only — not the actual click/right-click interaction in a real browser (no browser automation tooling available in this environment, consistent with the rest of this session). Flag this explicitly and recommend the user click-test: right-click a card in each context (main, shelf, watch later, hidden), confirm "Add tag…" appears and "Archive video" is hidden specifically on the Hidden page, confirm Enter submits and Escape/outside-click cancels, and confirm the popover doesn't immediately close itself when opened (the `stopPropagation()` case).

- [ ] **Step 2: Update `CHANGELOG.md`**

Add an entry describing: new "Add tag…" context-menu action, the `_tag_pills.html` extraction, canonical-only autocomplete, and the raw-tag-promotion side effect worth knowing about (same wording as the "Edge Cases" section of this plan's design doc). Trade-off to note: no JS test coverage for the new interaction (no framework exists yet).

- [ ] **Step 3: Update `plan-webapp.md`**

Add a row to the routes table: `POST /videos/<id>/tags/add | form tag_name; creates or promotes a canonical tag and attaches it to the video; 400 if blank, 404 if video not found; returns rendered tag-pills HTML`.

- [ ] **Step 4: Update `TODO.md`**

Strike through the "Manually add a tag to a single existing video" item under Organization — this closes it.

- [ ] **Step 5: Update this plan doc**

Add a one-line confirmation under each design-decision section noting it was implemented as designed, or any deviation found during Step 1's verification.

- [ ] **Step 6: Leave changes staged, do not commit**

Per this project's established convention — commit only when the user explicitly asks.

---

## Out of Scope

- Multi-tag input in one action
- Removing tags via this same UI (already exists via the tag-pill right-click menu)
- Any change to automatic alias-matching / `retroactive_apply` behavior

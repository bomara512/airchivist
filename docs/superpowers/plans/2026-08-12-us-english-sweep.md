# US English Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every British-English spelling with its American-English equivalent across the codebase — DB schema, Python, JS, CSS, HTML templates, tests, and current-state prose docs — so the project reads consistently as US English throughout. Confirmed with the user: rename depth includes the DB column and route paths (not just strings), historical documents (`CHANGELOG.md`, `docs/superpowers/specs/*.md`, `docs/superpowers/plans/*.md`) are intentionally left untouched, and "grey" → "gray" is in scope.

**Architecture:** A full audit of the repo (excluding `.git`, `node_modules`, `__pycache__`, `.venv`, `htmlcov`, `.pytest_cache`, `.superpowers`, and the vendored `webapp/static/htmx.min.js`) found British spelling in exactly one place in actual code: **"favourite"** (DB column, DB function, two routes, CSS classes, template strings, JS route string, and their tests). Every other UK spelling found (`colour`, `behaviour`, `organise`, `recognise`, `catalogue`, `grey`, `initialised`) appears only in prose — current-state docs (`CLAUDE.md`, `TODO.md`, several `plan-*.md` files, `docs/feature-sheet.html`) or historical docs (left alone per the user's decision). The "favourite" rename touches a SQLite column, so it needs one new migration step in `webapp/db/schema.py` using `ALTER TABLE ... RENAME COLUMN`, which SQLite supports as a single atomic, data-preserving operation — no manual DB work required from the user; it runs automatically the next time the app starts, via the same `init_webapp_tables` migration mechanism already in place.

**Tech Stack:** Python (Flask, sqlite3), vanilla JS, Jinja2/HTML, CSS, pytest, Jest.

## Global Constraints

- Every "favourite" → "favorite" rename must be applied consistently across all layers touching that identifier — DB column, SQL literals, Python identifiers, route paths, CSS classes, template strings/attributes, JS strings, and test names/assertions. A partial rename (e.g. renaming the CSS class but not the DB column) is not acceptable per the user's explicit choice of full-depth rename.
- `CHANGELOG.md` and everything under `docs/superpowers/specs/` and `docs/superpowers/plans/` are historical records and must NOT be edited for spelling — this is intentional, not an oversight. Task 4 adds an explicit note to `CLAUDE.md` recording this decision so it isn't mistaken for a miss in a future sweep.
- `aria-labelledby` (an HTML/ARIA spec attribute name, `webapp/templates/base.html`) is not a spelling variant and must not be touched.
- The vendored `webapp/static/htmx.min.js` is third-party code; do not edit it (a `cancell`-pattern match inside it is a minified JS identifier, not a spelling issue).
- After the full sweep, `python -m pytest -q` must pass (541+ tests) and `npm test` must pass (17 tests) before any task is considered done.
- Every DB migration must remain idempotent and safe to run against both a fresh database and an existing one with data (matching the existing pattern in `webapp/db/schema.py`).
- Remove any debug logging before finishing any task.
- Append a `CHANGELOG.md` entry (new, forward-looking entry — this doesn't contradict the "leave history alone" rule, since it's *today's* new entry, not an edit to a past one) and update the relevant `plan-*.md` files for the implementation change, per standing project convention.

---

### Task 1: Backend rename — DB migration, `webapp/db/`, `webapp/routes.py`, and backend tests

**Files:**
- Modify: `webapp/db/schema.py`
- Modify: `webapp/db/videos.py`
- Modify: `webapp/db/__init__.py`
- Modify: `webapp/routes.py`
- Modify: `tests/webapp/test_routes.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (first task).
- Produces: DB column `videos.is_favorite` (renamed from `is_favourite`); `_db.set_favorite(conn, video_id, value)` (renamed from `set_favorite`); `favorites_only` as the parameter name on `_build_where`, `get_all_videos`, `count_videos` (renamed from `favourites_only`); routes `POST /videos/<video_id>/favorite` and `POST /api/favorite/add` (renamed from `.../favourite` and `/api/favourite/add`); query param `?favorites=1` (renamed from `?favourites=1`). Task 2 (templates/CSS) and Task 3 (extension) both depend on these exact new names.

- [ ] **Step 1: Add the column-rename migration to `webapp/db/schema.py`**

The current migration loop (lines 79-92) reads:

```python
    for col, ddl in [
        ("is_canonical", "ALTER TABLE tags     ADD COLUMN is_canonical BOOLEAN NOT NULL DEFAULT 0"),
        ("is_noise",     "ALTER TABLE tags     ADD COLUMN is_noise     BOOLEAN NOT NULL DEFAULT 0"),
        ("is_hidden",    "ALTER TABLE videos   ADD COLUMN is_hidden    BOOLEAN NOT NULL DEFAULT 0"),
        ("date_hidden",   "ALTER TABLE videos  ADD COLUMN date_hidden   TEXT"),
        ("is_favourite",  "ALTER TABLE videos  ADD COLUMN is_favourite  BOOLEAN NOT NULL DEFAULT 0"),
        ("source_url",    "ALTER TABLE channels ADD COLUMN source_url   TEXT"),
    ]:
        try:
            conn.execute(ddl)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
```

Replace the `is_favourite` tuple with `is_favorite` (US spelling, for brand-new databases that never had the old column), and add a new rename step **immediately before** this loop so it runs first:

```python
    # One-time rename for pre-existing databases: is_favourite -> is_favorite
    # (US spelling). Runs before the ADD COLUMN loop below so a freshly-renamed
    # column is correctly seen as "already exists" by that loop's is_favorite
    # entry. A database that never had is_favourite (brand new, or already
    # migrated) hits OperationalError here and is skipped — the ADD COLUMN
    # loop creates/no-ops it instead.
    try:
        conn.execute("ALTER TABLE videos RENAME COLUMN is_favourite TO is_favorite")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # already renamed, or fresh DB that never had the old column

    for col, ddl in [
        ("is_canonical", "ALTER TABLE tags     ADD COLUMN is_canonical BOOLEAN NOT NULL DEFAULT 0"),
        ("is_noise",     "ALTER TABLE tags     ADD COLUMN is_noise     BOOLEAN NOT NULL DEFAULT 0"),
        ("is_hidden",    "ALTER TABLE videos   ADD COLUMN is_hidden    BOOLEAN NOT NULL DEFAULT 0"),
        ("date_hidden",   "ALTER TABLE videos  ADD COLUMN date_hidden   TEXT"),
        ("is_favorite",   "ALTER TABLE videos  ADD COLUMN is_favorite   BOOLEAN NOT NULL DEFAULT 0"),
        ("source_url",    "ALTER TABLE channels ADD COLUMN source_url   TEXT"),
    ]:
        try:
            conn.execute(ddl)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
```

- [ ] **Step 2: Rename in `webapp/db/videos.py`**

Three renames in this file:
1. Function `set_favourite` (line 66) → `set_favorite`. Body's SQL: `"UPDATE videos SET is_favourite = ? WHERE video_id = ?"` (line 68) → `"UPDATE videos SET is_favorite = ? WHERE video_id = ?"`.
2. Parameter `favourites_only` → `favorites_only` in `_build_where` (line 26 signature, line 49 usage `if favourites_only:`), `get_all_videos` (line 92 signature, line 103 call site), and `count_videos` (line 140 signature, line 146 call site).
3. SQL literal `"v.is_favourite = 1"` (line 50, inside `_build_where`) → `"v.is_favorite = 1"`.

- [ ] **Step 3: Rename in `webapp/db/__init__.py`**

Line 82: `set_favourite,` (import) → `set_favorite,`.
Line 129: `"set_favourite"` (in the `__all__`-style string list) → `"set_favorite"`.

- [ ] **Step 4: Rename in `webapp/routes.py`**

Five spots:
1. Line 46: `favourites_only = request.args.get("favourites") == "1"` → `favorites_only = request.args.get("favorites") == "1"`.
2. Lines 62, 69, 118: every `favourites_only=favourites_only` keyword-argument pass-through → `favorites_only=favorites_only`, and the bare `favourites_only=favourites_only,` in `template_vars` (line 118) likewise.
3. Lines 537-544 — the same-origin toggle route:

```python
@bp.route("/videos/<video_id>/favourite", methods=["POST"])
def video_toggle_favourite(video_id):
    video = _db.get_video_by_id(g.db, video_id)
    if not video:
        abort(404)
    new_value = not video.get("is_favourite")
    _db.set_favourite(g.db, video_id, new_value)
    return jsonify({"is_favourite": new_value})
```

becomes:

```python
@bp.route("/videos/<video_id>/favorite", methods=["POST"])
def video_toggle_favorite(video_id):
    video = _db.get_video_by_id(g.db, video_id)
    if not video:
        abort(404)
    new_value = not video.get("is_favorite")
    _db.set_favorite(g.db, video_id, new_value)
    return jsonify({"is_favorite": new_value})
```

4. Lines 792-813 — the CORS API route:

```python
@bp.route("/api/favourite/add", methods=["POST", "OPTIONS"])
def api_favourite_add():
    if request.method == "OPTIONS":
        return make_response("", 204, _CORS_HEADERS)

    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    m = _YT_ID_RE.search(url)
    if not m:
        resp = jsonify({"status": "error", "error": "Not a YouTube URL"})
        resp.headers.update(_CORS_HEADERS)
        return resp, 400

    video_id = m.group(1)
    video = _db.get_video_by_id(g.db, video_id)
    if not video:
        resp = jsonify({"status": "error", "error": "Video not found"})
        resp.headers.update(_CORS_HEADERS)
        return resp, 404

    _db.set_favourite(g.db, video_id, True)
    resp = jsonify({"status": "added"})
    resp.headers.update(_CORS_HEADERS)
```

becomes (only the route decorator, function name, and the `set_favourite` call change — everything else is identical):

```python
@bp.route("/api/favorite/add", methods=["POST", "OPTIONS"])
def api_favorite_add():
    if request.method == "OPTIONS":
        return make_response("", 204, _CORS_HEADERS)

    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    m = _YT_ID_RE.search(url)
    if not m:
        resp = jsonify({"status": "error", "error": "Not a YouTube URL"})
        resp.headers.update(_CORS_HEADERS)
        return resp, 400

    video_id = m.group(1)
    video = _db.get_video_by_id(g.db, video_id)
    if not video:
        resp = jsonify({"status": "error", "error": "Video not found"})
        resp.headers.update(_CORS_HEADERS)
        return resp, 404

    _db.set_favorite(g.db, video_id, True)
    resp = jsonify({"status": "added"})
    resp.headers.update(_CORS_HEADERS)
```

- [ ] **Step 5: Rename in `tests/webapp/test_routes.py`**

`TestFavouriteToggle` (line 315) → `TestFavoriteToggle`, and its body:

```python
class TestFavouriteToggle:
    def test_toggle_on_returns_true(self, client):
        resp = client.post("/videos/aaaaaaaaaa1/favourite")
        assert resp.status_code == 200
        assert resp.get_json()["is_favourite"] is True

    def test_toggle_off_returns_false(self, client):
        client.post("/videos/aaaaaaaaaa1/favourite")
        resp = client.post("/videos/aaaaaaaaaa1/favourite")
        assert resp.get_json()["is_favourite"] is False

    def test_unknown_video_returns_404(self, client):
        resp = client.post("/videos/XXXXXXXXXXX/favourite")
        assert resp.status_code == 404

    def test_favourites_filter_returns_only_favourites(self, client):
        client.post("/videos/aaaaaaaaaa1/favourite")
        resp = client.get("/?favourites=1", headers={"HX-Request": "true"})
        assert b"Guitar Lesson 1" in resp.data
        assert b"Thai Food Recipe" not in resp.data
```

becomes:

```python
class TestFavoriteToggle:
    def test_toggle_on_returns_true(self, client):
        resp = client.post("/videos/aaaaaaaaaa1/favorite")
        assert resp.status_code == 200
        assert resp.get_json()["is_favorite"] is True

    def test_toggle_off_returns_false(self, client):
        client.post("/videos/aaaaaaaaaa1/favorite")
        resp = client.post("/videos/aaaaaaaaaa1/favorite")
        assert resp.get_json()["is_favorite"] is False

    def test_unknown_video_returns_404(self, client):
        resp = client.post("/videos/XXXXXXXXXXX/favorite")
        assert resp.status_code == 404

    def test_favorites_filter_returns_only_favorites(self, client):
        client.post("/videos/aaaaaaaaaa1/favorite")
        resp = client.get("/?favorites=1", headers={"HX-Request": "true"})
        assert b"Guitar Lesson 1" in resp.data
        assert b"Thai Food Recipe" not in resp.data
```

`TestApiFavouriteAdd` (line 530) → `TestApiFavoriteAdd`, and within it: every `/api/favourite/add` URL string (6 occurrences: `test_add_video_returns_added`, `test_video_is_marked_favourite`, `test_idempotent_reAdd_still_returns_added` ×2, `test_invalid_video_returns_error`, `test_invalid_url_returns_error`, `test_cors_header_present`, `test_options_preflight`) → `/api/favorite/add`; the test method `test_video_is_marked_favourite` → `test_video_is_marked_favorite`, and inside it the SQL `"SELECT is_favourite FROM videos WHERE video_id = ?"` → `"SELECT is_favorite FROM videos WHERE video_id = ?"`.

- [ ] **Step 6: Run the backend tests**

Run: `python -m pytest tests/webapp/test_routes.py -q`
Expected: PASS, same test count as before this task (renamed classes/tests, not removed or added).

Run: `python -m pytest -q`
Expected: PASS, full suite (541+ tests) — this also exercises `schema.py`'s migration against the test fixture DB, confirming the rename migration works.

- [ ] **Step 7: Commit**

```bash
git add webapp/db/schema.py webapp/db/videos.py webapp/db/__init__.py webapp/routes.py tests/webapp/test_routes.py
git commit -m "refactor(webapp): rename is_favourite/favourite routes to US spelling"
```

---

### Task 2: Frontend rename — CSS and templates

**Files:**
- Modify: `webapp/static/style.css`
- Modify: `webapp/templates/index.html`
- Modify: `webapp/templates/_video_card.html`
- Modify: `webapp/templates/base.html`

**Interfaces:**
- Consumes: the renamed route (`/videos/<id>/favorite`), renamed JSON key (`is_favorite`), and renamed template variable (`favorites_only`) from Task 1 — this task cannot run correctly against the old backend, so it must land after Task 1's commit.
- Produces: CSS classes `.favorite-btn` / `.favorite-btn--active` (renamed from `.favourite-btn` / `.favourite-btn--active`) that Task 3 does not depend on (extension has no CSS), but which must be renamed consistently across all three template files in this task together, since they share the same class names.

- [ ] **Step 1: Rename in `webapp/static/style.css`**

Lines 468-492:

```css
/* Favourite button — thumbnail overlay (top-left corner) */
.favourite-btn {
```
→
```css
/* Favorite button — thumbnail overlay (top-left corner) */
.favorite-btn {
```

```css
.thumb-wrap:hover .favourite-btn { opacity: 1; }
.favourite-btn--active { opacity: 1 !important; color: #f5c518; }
.favourite-btn:hover { color: #f5c518; }

/* Watched button — thumbnail overlay, next to favourite button */
```
→
```css
.thumb-wrap:hover .favorite-btn { opacity: 1; }
.favorite-btn--active { opacity: 1 !important; color: #f5c518; }
.favorite-btn:hover { color: #f5c518; }

/* Watched button — thumbnail overlay, next to favorite button */
```

Line 519 comment: `/* Filter toggle (favourites checkbox in toolbar) */` → `/* Filter toggle (favorites checkbox in toolbar) */`.

- [ ] **Step 2: Rename in `webapp/templates/index.html`**

Line 10: `+ favourites_only | int` → `+ favorites_only | int`.

Lines 78-81:
```html
      <label class="filter-toggle">
        <input type="checkbox" name="favourites" value="1" {% if favourites_only %}checked{% endif %}>
        Favourites
      </label>
```
→
```html
      <label class="filter-toggle">
        <input type="checkbox" name="favorites" value="1" {% if favorites_only %}checked{% endif %}>
        Favorites
      </label>
```

- [ ] **Step 3: Rename in `webapp/templates/_video_card.html`**

Lines 33-35:
```html
    <button class="favourite-btn {% if video.is_favourite %}favourite-btn--active{% endif %}"
            data-video-id="{{ video.video_id }}"
            title="{{ 'Remove from favourites' if video.is_favourite else 'Add to favourites' }}">★</button>
```
→
```html
    <button class="favorite-btn {% if video.is_favorite %}favorite-btn--active{% endif %}"
            data-video-id="{{ video.video_id }}"
            title="{{ 'Remove from favorites' if video.is_favorite else 'Add to favorites' }}">★</button>
```

- [ ] **Step 4: Rename in `webapp/templates/base.html`**

Lines 270-288 (the favourite-toggle click handler):

```javascript
    // Favourite toggle button — update all cards with same video_id (handles carousel clones)
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('.favourite-btn');
      if (!btn) return;
      var videoId = btn.dataset.videoId;
      fetch('/videos/' + videoId + '/favourite', { method: 'POST' })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          document.querySelectorAll('.favourite-btn[data-video-id="' + videoId + '"]').forEach(function (b) {
            if (data.is_favourite) {
              b.classList.add('favourite-btn--active');
              b.title = 'Remove from favourites';
            } else {
              b.classList.remove('favourite-btn--active');
              b.title = 'Add to favourites';
            }
          });

          if (!data.is_favourite) return;
```

becomes:

```javascript
    // Favorite toggle button — update all cards with same video_id (handles carousel clones)
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('.favorite-btn');
      if (!btn) return;
      var videoId = btn.dataset.videoId;
      fetch('/videos/' + videoId + '/favorite', { method: 'POST' })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          document.querySelectorAll('.favorite-btn[data-video-id="' + videoId + '"]').forEach(function (b) {
            if (data.is_favorite) {
              b.classList.add('favorite-btn--active');
              b.title = 'Remove from favorites';
            } else {
              b.classList.remove('favorite-btn--active');
              b.title = 'Add to favorites';
            }
          });

          if (!data.is_favorite) return;
```

Line 290-291 comment:
```javascript
          // Favouriting from the rediscover shelf or watch later implies you've
          // watched it — mark it watched and drop it from whichever list it came from.
```
→
```javascript
          // Favoriting from the rediscover shelf or watch later implies you've
          // watched it — mark it watched and drop it from whichever list it came from.
```

- [ ] **Step 5: Manual verification**

Start the webapp (`python -m webapp.cli` or however it's normally run locally) and confirm: the ★ favorite button on a video card still toggles on click (both directions), the "Favorites" filter checkbox in the toolbar still filters correctly, and favoriting a card on the Rediscover shelf or Watch Later page still marks it watched and removes it from that list (the side-effect wired in `base.html`'s handler).

- [ ] **Step 6: Run the full test suite**

Run: `python -m pytest -q`
Expected: PASS (541+ tests) — no Python logic changed in this task, but this confirms nothing else broke.

- [ ] **Step 7: Commit**

```bash
git add webapp/static/style.css webapp/templates/index.html webapp/templates/_video_card.html webapp/templates/base.html
git commit -m "refactor(webapp): rename favourite CSS classes and template strings to US spelling"
```

---

### Task 3: Extension rename — `popup.js` and its tests

**Files:**
- Modify: `extension/popup/popup.js`
- Modify: `tests/extension/popup.test.js`

**Interfaces:**
- Consumes: the renamed route `/api/favorite/add` from Task 1. This task cannot run correctly against the old backend, so it must land after Task 1's commit (independent of Task 2, which touches unrelated files).
- Produces: nothing further tasks depend on.

- [ ] **Step 1: Rename in `extension/popup/popup.js`**

Line 86 — the only "favourite" in this file (everything else, `alsoFavorite`/`favoriteOk`/`chk-favorite`/"Also mark as favorite", already uses US spelling from when this feature was built):

```javascript
        ? postJson(`${viewtubeUrl}/api/favourite/add`, { url: tabUrl })
```
→
```javascript
        ? postJson(`${viewtubeUrl}/api/favorite/add`, { url: tabUrl })
```

- [ ] **Step 2: Rename in `tests/extension/popup.test.js`**

Eight occurrences of the string `/api/favourite/add`, all in the `doAdd` describe block's `mockFetchRouter` route arrays or `fetch.mock.calls.some(...)` assertions — change every one to `/api/favorite/add`. (No test names or variable names in this file use "favourite" — only the URL string literal.)

- [ ] **Step 3: Run the JS test suite**

Run: `npm test`
Expected: PASS (17 tests) — no test logic changed, only the route string literal.

- [ ] **Step 4: Manual verification**

Load the extension in Firefox (`about:debugging` → temporary add-on) with the webapp running, add a brand-new video with "Also mark as favorite" checked, and confirm it actually lands as a favorite (check the web UI's ★ state) — this proves the extension's new route string matches the backend's Task 1 rename.

- [ ] **Step 5: Commit**

```bash
git add extension/popup/popup.js tests/extension/popup.test.js
git commit -m "refactor(extension): call renamed /api/favorite/add route"
```

---

### Task 4: Prose sweep — current-state docs, CLAUDE.md guardrail, changelog

**Files:**
- Modify: `CLAUDE.md`
- Modify: `TODO.md`
- Modify: `plan-webapp.md`
- Modify: `plan-extension.md`
- Modify: `plan-manual-tagging.md`
- Modify: `plan-rediscover-shelf.md`
- Modify: `plan-unified-video-card.md`
- Modify: `plan-llm-tagger.md`
- Modify: `docs/feature-sheet.html`
- Modify: `CHANGELOG.md` (new entry only — no historical edits)

**Interfaces:**
- Consumes: the renamed route paths/CSS classes from Tasks 1-3, since several of these docs describe those routes/classes by name and must describe the new names, not the old ones.
- Produces: nothing further tasks depend on — last task in this plan.

- [ ] **Step 1: `CLAUDE.md` — fix prose, then add the US-English guardrail rule**

Six word-level fixes (`behaviour` → `behavior`, `catalogued` → `cataloged`), each preserving the surrounding sentence exactly:
- Line 14: `Reflect current behaviour, not just the delta.` → `Reflect current behavior, not just the delta.`
- Line 17: `is non-obvious (e.g. scroll behaviour on filter changes vs. pagination).` → `is non-obvious (e.g. scroll behavior on filter changes vs. pagination).`
- Line 47: `Exception: logging that is part of the intended production behaviour (e.g. a` → `Exception: logging that is part of the intended production behavior (e.g. a`
- Line 125: `Keep the stat line (\`N areas catalogued · N features shipped · N queued\`)` → `Keep the stat line (\`N areas cataloged · N features shipped · N queued\`)`
- Line 167: `New feature, component, or behaviour change → \`superpowers:brainstorming\`` → `New feature, component, or behavior change → \`superpowers:brainstorming\``
- Line 170: `Bug, test failure, or unexpected behaviour → \`superpowers:systematic-debugging\`` → `Bug, test failure, or unexpected behavior → \`superpowers:systematic-debugging\``

Then add a new rule section (matching this file's existing section style — see e.g. "Remove old approaches when replacing them"). Place it after the "Keep the feature sheet current" section and before "Keep test-lifecycle state in shared hooks, not inline":

```markdown
## Write US English, not British English

This project uses American spelling throughout — code identifiers, UI
copy, comments, and docs. Write "favorite," "color," "behavior,"
"organize," "catalog," "gray," etc., never their British equivalents
("favourite," "colour," "behaviour," "organise," "catalogue," "grey").

- This applies to everything: DB columns, function/route names, CSS
  classes, template strings, JS, and prose in `CLAUDE.md`, `TODO.md`,
  `plan-*.md`, and `docs/feature-sheet.html`.
- Exception: `CHANGELOG.md` and everything under `docs/superpowers/`
  (specs and plans) are historical records. A past entry that used
  British spelling when it was written stays as-is — do not "fix" old
  entries. Only new entries going forward need to follow this rule.
- Exception: don't touch spec-mandated identifiers that happen to
  contain a double-L or similar pattern that looks British but isn't
  (e.g. `aria-labelledby` is the correct HTML/ARIA attribute name in
  every dialect — never "fix" it).
```

- [ ] **Step 2: `TODO.md`**

Line 49: `- ~~Rating system for videos — favourite toggle (★) on video cards with filter~~` → `- ~~Rating system for videos — favorite toggle (★) on video cards with filter~~` (keep the strikethrough — this item is already done, only the spelling changes).

- [ ] **Step 3: `plan-webapp.md`**

Six spots (this is the file documenting current webapp behavior in most depth, so it has the most references to the renamed route/column):
- Line 137 comment: `# favourite star in shape/wiring.` → `# favorite star in shape/wiring.`
- Line 147: `` `_build_where` also accepts three quick-filter params, alongside the existing `favourites_only`: `` → `` `_build_where` also accepts three quick-filter params, alongside the existing `favorites_only`: ``
- Line 358: `` | POST | `/videos/<id>/favourite` | Toggles `videos.is_favourite` via `set_favourite`; 404 if video not found; returns `{"is_favourite": bool}` | `` → `` | POST | `/videos/<id>/favorite` | Toggles `videos.is_favorite` via `set_favorite`; 404 if video not found; returns `{"is_favorite": bool}` | ``
- Line 416: replace `.favourite-btn` (×2), `favouriting` with `.favorite-btn` (×2), `Favoriting` — full sentence: `` top-left corner holds `.favourite-btn` (★, `#f5c518` when active) `` → `` top-left corner holds `.favorite-btn` (★, `#f5c518` when active) ``; and `` updates every `.favourite-btn`/`.watched-btn` sharing `` → `` updates every `.favorite-btn`/`.watched-btn` sharing ``; and `Favouriting from the rediscover shelf or watch-later list additionally calls` → `Favoriting from the rediscover shelf or watch-later list additionally calls`
- Line 444: `Three quick-filter controls sit alongside the favourites checkbox,` → `Three quick-filter controls sit alongside the favorites checkbox,`
- Line 459: two spots — `` fire after the main add (via `Promise.allSettled` ... POST /api/favourite/add`) `` → `` .../api/favorite/add` ``; and `` since `is_favourite` is a plain boolean. `` → `` since `is_favorite` is a plain boolean. ``

- [ ] **Step 4: `plan-extension.md`**

- Line 173: `a coloured pill shows:` → `a colored pill shows:`
- Line 235: `Should saves go into a date-organised subfolder` → `Should saves go into a date-organized subfolder`

- [ ] **Step 5: `plan-manual-tagging.md`**

- Line 13: `The thumbnail-overlay corner is already crowded (favourite, watch-later, and on the shelf, remove).` → `The thumbnail-overlay corner is already crowded (favorite, watch-later, and on the shelf, remove).`
- Line 563: `matching the existing favourite-button pattern that updates all instances of the same video.` → `matching the existing favorite-button pattern that updates all instances of the same video.`

- [ ] **Step 6: `plan-rediscover-shelf.md`**

- Line 17: `mirroring the ✕ and favourite→shelf-drop flows.` → `mirroring the ✕ and favorite→shelf-drop flows.`
- Line 198: `"Reason" label styled subtly (grey, smaller font)` → `"Reason" label styled subtly (gray, smaller font)`

- [ ] **Step 7: `plan-unified-video-card.md`**

- Line 166: `Shelf collapse/expand with localStorage (stays in index.html — shelf-specific behaviour)` → `Shelf collapse/expand with localStorage (stays in index.html — shelf-specific behavior)`
- Line 233: `| Behaviour | Where |` → `| Behavior | Where |` (table header — check the table's separator row and any other cells in that column aren't affected, only the header text changes)

- [ ] **Step 8: `plan-llm-tagger.md`**

- Line 223: `confidence badge colours (green/amber/grey for high/medium/low);` → `confidence badge colors (green/amber/gray for high/medium/low);`

- [ ] **Step 9: `docs/feature-sheet.html`**

Six spots (per the standing "Keep the feature sheet current" rule, and since this file describes the now-renamed favorite feature and filter):
- Line 312: `<span><strong>10</strong> areas catalogued</span>` → `<span><strong>10</strong> areas cataloged</span>`
- Line 325: `favourites-only, unwatched-only, date-added range,` → `favorites-only, unwatched-only, date-added range,`
- Line 344: `<h2>Favourites &amp; watched state</h2>` → `<h2>Favorites &amp; watched state</h2>`
- Line 346: `★ Favourite toggle on any video, with a favourites-only filter` → `★ Favorite toggle on any video, with a favorites-only filter`
- Line 393: (already says "mark a favourite" — check exact current wording) `optionally also queue for Watch Later and/or mark a favourite in the same click` → `optionally also queue for Watch Later and/or mark a favorite in the same click`
- Line 395: `Video titles on YouTube itself are colour-coded as you browse` → `Video titles on YouTube itself are color-coded as you browse`

- [ ] **Step 10: `CHANGELOG.md` — new entry only**

Append a dated entry (today's date) describing this sweep: renamed the `is_favourite` DB column, `/videos/<id>/favourite` and `/api/favourite/add` routes, `set_favourite` function, `.favourite-btn`/`.favourite-btn--active` CSS classes, and all related test/template/JS references to US spelling (`is_favorite`, `/favorite`, `set_favorite`, `.favorite-btn`); swept `colour`/`behaviour`/`organise`/`catalogue`/`grey`/`initialised` out of current-state prose docs; added a `CLAUDE.md` rule requiring US English going forward. Implication (pro): the codebase and its own docs now consistently use one dialect, matching the user's locale, and a new migration makes the DB rename automatic and lossless for existing installs; (con): historical `CHANGELOG.md` entries and `docs/superpowers/` specs/plans below this one still contain British spelling by design (a deliberate exception, not an inconsistency) — a reader skimming project history will see both spellings depending on how far back they scroll.

- [ ] **Step 11: Final verification**

Run: `python -m pytest -q` — expect 541+ passing.
Run: `npm test` — expect 17 passing.
Run: `grep -rIn -i "favourite\|colour\|behaviour\|organise\|catalogue\|grey\|initialised" CLAUDE.md TODO.md plan-*.md docs/feature-sheet.html webapp/ extension/ tests/` — expect zero matches (confirms the sweep is complete across every file this plan touched).

- [ ] **Step 12: Commit**

```bash
git add CLAUDE.md TODO.md plan-webapp.md plan-extension.md plan-manual-tagging.md plan-rediscover-shelf.md plan-unified-video-card.md plan-llm-tagger.md docs/feature-sheet.html CHANGELOG.md
git commit -m "docs: sweep British spellings from current docs, add US English rule"
```

---

## Self-Review Notes

- **Spec coverage:** full-depth "favourite" rename (DB, routes, functions, CSS, templates, tests, extension) ← user's "Full rename incl. DB + routes" decision, covered across Tasks 1-3; historical docs left untouched with an explicit recorded reason ← user's "leave historical docs untouched, but note somewhere that this is intentional" decision, satisfied by the new `CLAUDE.md` rule's "Exception" bullet in Task 4 Step 1 (this is the "somewhere" — a durable, discoverable place future sessions will actually read, rather than a one-off comment); `grey` → `gray` ← user's "include it" decision, covered in Task 4 Steps 1, 6, 8; every other UK spelling found in the initial audit (`colour`, `behaviour`, `organise`, `recognise`, `catalogue`, `initialised`) ← covered across Task 4's per-file steps, cross-checked against the actual grep inventory gathered before writing this plan, not from memory.
- **Placeholder scan:** every step gives literal before/after text or an exact line-number + old-string/new-string pair — no "and so on," no "similar changes elsewhere" without naming the elsewhere.
- **Type consistency:** `set_favorite(conn, video_id, value)` signature is identical everywhere it's called across Task 1 (routes.py ×2 call sites) after the rename; `favorites_only` parameter name is consistent across `_build_where`/`get_all_videos`/`count_videos`/`routes.py`/`index.html` (Tasks 1-2); `.favorite-btn`/`.favorite-btn--active` class names are identical across `style.css`, `_video_card.html`, and `base.html` (Task 2); route path `/api/favorite/add` is identical between `routes.py` (Task 1), `popup.js`, and `popup.test.js` (Task 3).
- **Verified against codebase, not memory:** every file/line reference in this plan was confirmed via direct `grep`/`Read` immediately before writing the corresponding task, including a full-repo audit (excluding vendored/build/history dirs) that confirmed "favourite" is the *only* UK spelling appearing in actual code, and that the vendored `htmx.min.js` and `aria-labelledby` are false positives correctly excluded from scope.

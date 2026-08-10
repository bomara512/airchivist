# Extension: Mark Favorite at Capture Time Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user mark a video as a favorite (★) at the moment they capture it to ViewTube via the extension popup, via a second opt-in checkbox alongside the existing "Also add to Watch Later" checkbox.

**Architecture:** One new CORS-enabled Flask route (`POST /api/favourite/add`) that reuses the existing `set_favourite(conn, video_id, value)` DB function — no new DB layer code. The extension's `doAdd`/`renderState` gain a second checkbox and a parallel follow-up call, refactoring the existing sequential watch-later follow-up into a small `postJson` helper plus a `Promise.allSettled` batch so watch-later and favorite fire independently of each other (both still gated on the main ViewTube add having already succeeded).

**Tech Stack:** Python, Flask, SQLite, pytest; vanilla-JS Firefox WebExtension (no build, no JS test suite).

## Global Constraints

- Every API route returning JSON to the extension MUST use the module-level `_CORS_HEADERS` constant on both the success response and the OPTIONS preflight — never a locally-defined dict.
- New/changed public functions in `webapp/db/*.py` and routes in `webapp/routes.py` require tests in the same change (happy path + one edge case; routes also CORS header + OPTIONS). This task adds a route but no new DB function (`set_favourite` already exists and is already exercised indirectly by `tests/webapp/test_routes.py` via `/videos/<id>/favourite` — the new route needs its own direct tests).
- Never use `rowid` with `sqlite3.Row`; select and reference the named primary key (`video_id`).
- Remove any debug logging before finishing.
- Append a `CHANGELOG.md` entry and update `plan-webapp.md` for the implementation change.
- Run `python -m pytest -q` at the end; all tests must pass.
- No JS test framework exists for the extension — `popup.js` changes are verified manually, consistent with every other extension feature so far.
- Favorite is a plain boolean column (`is_favourite`), not a queue like watch-later — there is no 409/"already" case for it. Do not add one.

---

### Task 1: Route — `POST /api/favourite/add`

**Files:**
- Modify: `webapp/routes.py`
- Test: `tests/webapp/test_routes.py`

**Interfaces:**
- Consumes: `_db.get_video_by_id(conn, video_id)`, `_db.set_favourite(conn, video_id, value: bool)` (`webapp/db/videos.py:66`, already exported from `webapp/db/__init__.py`); `_YT_ID_RE` (already imported at `routes.py:7`); `_CORS_HEADERS`, `g.db`.
- Produces: route `POST/OPTIONS /api/favourite/add` with JSON body `{url}`, returning `{"status": "added"}` (200) on success, `{"status": "error", "error": "Not a YouTube URL"}` (400), or `{"status": "error", "error": "Video not found"}` (404). No task depends on this beyond Task 2, which calls this exact URL/body/response shape.

- [ ] **Step 1: Write the failing tests**

Add to `tests/webapp/test_routes.py`, immediately after the `TestApiWatchLaterStatus` class (the file already seeds a video with `video_id='aaaaaaaaaa1'` via conftest, used identically by the watch-later tests above):

```python
class TestApiFavouriteAdd:
    def test_add_video_returns_added(self, client):
        resp = client.post("/api/favourite/add", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        data = resp.get_json()
        assert data["status"] == "added"

    def test_video_is_marked_favourite(self, client):
        client.post("/api/favourite/add", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        conn = sqlite3.connect(client.application.config["DATABASE"])
        row = conn.execute(
            "SELECT is_favourite FROM videos WHERE video_id = ?", ("aaaaaaaaaa1",)
        ).fetchone()
        conn.close()
        assert row[0] == 1

    def test_idempotent_reAdd_still_returns_added(self, client):
        client.post("/api/favourite/add", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        resp = client.post("/api/favourite/add", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        data = resp.get_json()
        assert data["status"] == "added"

    def test_invalid_video_returns_error(self, client):
        resp = client.post("/api/favourite/add", json={"url": "https://www.youtube.com/watch?v=XXXXXXXXXXX"})
        data = resp.get_json()
        assert data["status"] == "error"
        assert resp.status_code == 404

    def test_invalid_url_returns_error(self, client):
        resp = client.post("/api/favourite/add", json={"url": "https://example.com"})
        data = resp.get_json()
        assert data["status"] == "error"
        assert resp.status_code == 400

    def test_cors_header_present(self, client):
        resp = client.post("/api/favourite/add", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaa1"})
        assert "Access-Control-Allow-Origin" in resp.headers

    def test_options_preflight(self, client):
        resp = client.options("/api/favourite/add")
        assert resp.status_code == 204
        assert "Access-Control-Allow-Origin" in resp.headers
```

Check the top of `tests/webapp/test_routes.py` for an existing `import sqlite3` (the channel tests already use `sqlite3.connect(client.application.config["DATABASE"])` per the codebase's established pattern) — reuse it, don't re-import if already present.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/webapp/test_routes.py::TestApiFavouriteAdd -q`
Expected: FAIL — 404 responses (route not registered) for the first few, and a `sqlite3` reference error only if `import sqlite3` truly isn't already present (it is — no action needed, just confirming assumption before Step 3).

- [ ] **Step 3: Implement the route**

In `webapp/routes.py`, add immediately after `api_watch_later_status` (after line 789, before the two blank lines that currently precede the next route):

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
    return resp
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/webapp/test_routes.py::TestApiFavouriteAdd -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add webapp/routes.py tests/webapp/test_routes.py
git commit -m "feat(webapp): add POST /api/favourite/add route"
```

---

### Task 2: Extension popup — "Also mark as favorite" checkbox

**Files:**
- Modify: `extension/popup/popup.js:52-102` (the `not_found` branch of `renderState` at `extension/popup/popup.js:230-243`, and `doAdd`)
- Modify: `CHANGELOG.md`, `plan-webapp.md`

**Interfaces:**
- Consumes: `POST /api/favourite/add` (Task 1) → `{status: "added"}` on success, `{status: "error", error}` on failure (400/404); existing `POST /api/watch-later/add` → `{status: "added"|"already_in_queue"}`; existing helpers `esc`, `getOrCreateFolder`.
- Produces: a new `postJson(url, body)` helper used by the refactored `doAdd`. No other task depends on this — it's the last task in this plan.

- [ ] **Step 1: Add the `postJson` helper**

In `extension/popup/popup.js`, add this function directly above `doAdd` (currently at line 52):

```javascript
async function postJson(url, body) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return resp.json();
}
```

- [ ] **Step 2: Refactor `doAdd` to accept `alsoFavorite` and run follow-ups in parallel**

The current `doAdd` (lines 52-102) reads:

```javascript
async function doAdd(viewtubeUrl, tabUrl, tabTitle, alsoWatchLater = false) {
  const root = document.getElementById('root');
  root.innerHTML = working('Adding…');
  const [bookmarkResult, vtResult] = await Promise.allSettled([
    getOrCreateFolder().then(id =>
      browser.bookmarks.create({ title: tabTitle, url: tabUrl, parentId: id })
    ),
    fetch(`${viewtubeUrl}/api/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: tabUrl }),
    }).then(r => r.json()),
  ]);
  const bookmarkOk = bookmarkResult.status === 'fulfilled';
  const vtData = vtResult.status === 'fulfilled' ? vtResult.value : null;
  const viewtubeOk = vtData && ['added', 'exists'].includes(vtData.status);

  let watchLaterOk = null;
  if (alsoWatchLater && viewtubeOk) {
    try {
      const wlResp = await fetch(`${viewtubeUrl}/api/watch-later/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: tabUrl }),
      });
      const wlData = await wlResp.json();
      watchLaterOk = ['added', 'already_in_queue'].includes(wlData.status);
    } catch {
      watchLaterOk = false;
    }
  }

  if (bookmarkOk && viewtubeOk) {
    const lines = [`&#10003; ${esc(vtData.title || tabTitle)}`];
    if (watchLaterOk === true) lines.push('&#10003; Added to Watch Later');
    if (watchLaterOk === false) lines.push('&#10007; Watch Later failed');
    root.innerHTML = `<div class="status success">${lines.map(l => `<div>${l}</div>`).join('')}</div>`;
    setTimeout(() => window.close(), 1500);
    return;
  }
  const lines = [];
  if (bookmarkOk) lines.push('&#10003; Bookmarked in Firefox');
  else lines.push(`&#10007; Bookmark failed: ${esc(bookmarkResult.reason?.message || 'unknown')}`);
  if (viewtubeOk) lines.push('&#10003; Added to ViewTube');
  else if (vtResult.status === 'rejected') lines.push(`&#10007; ViewTube unreachable`);
  else lines.push(`&#10007; ViewTube: ${esc(vtData?.error || 'unknown error')}`);
  if (alsoWatchLater && watchLaterOk === true) lines.push('&#10003; Added to Watch Later');
  if (alsoWatchLater && watchLaterOk === false) lines.push('&#10007; Watch Later failed');
  const cls = (bookmarkOk || viewtubeOk) ? 'partial' : 'error';
  root.innerHTML = `<div class="status ${cls}">${lines.map(l => `<div>${l}</div>`).join('')}</div>`;
}
```

Replace the whole function with:

```javascript
async function doAdd(viewtubeUrl, tabUrl, tabTitle, alsoWatchLater = false, alsoFavorite = false) {
  const root = document.getElementById('root');
  root.innerHTML = working('Adding…');
  const [bookmarkResult, vtResult] = await Promise.allSettled([
    getOrCreateFolder().then(id =>
      browser.bookmarks.create({ title: tabTitle, url: tabUrl, parentId: id })
    ),
    fetch(`${viewtubeUrl}/api/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: tabUrl }),
    }).then(r => r.json()),
  ]);
  const bookmarkOk = bookmarkResult.status === 'fulfilled';
  const vtData = vtResult.status === 'fulfilled' ? vtResult.value : null;
  const viewtubeOk = vtData && ['added', 'exists'].includes(vtData.status);

  let watchLaterOk = null;
  let favoriteOk = null;
  if (viewtubeOk) {
    const [wlResult, favResult] = await Promise.allSettled([
      alsoWatchLater
        ? postJson(`${viewtubeUrl}/api/watch-later/add`, { url: tabUrl })
        : Promise.resolve(null),
      alsoFavorite
        ? postJson(`${viewtubeUrl}/api/favourite/add`, { url: tabUrl })
        : Promise.resolve(null),
    ]);
    if (alsoWatchLater) {
      watchLaterOk = wlResult.status === 'fulfilled'
        && ['added', 'already_in_queue'].includes(wlResult.value?.status);
    }
    if (alsoFavorite) {
      favoriteOk = favResult.status === 'fulfilled' && favResult.value?.status === 'added';
    }
  }

  if (bookmarkOk && viewtubeOk) {
    const lines = [`&#10003; ${esc(vtData.title || tabTitle)}`];
    if (watchLaterOk === true) lines.push('&#10003; Added to Watch Later');
    if (watchLaterOk === false) lines.push('&#10007; Watch Later failed');
    if (favoriteOk === true) lines.push('&#9733; Marked as favorite');
    if (favoriteOk === false) lines.push('&#10007; Favorite failed');
    root.innerHTML = `<div class="status success">${lines.map(l => `<div>${l}</div>`).join('')}</div>`;
    setTimeout(() => window.close(), 1500);
    return;
  }
  const lines = [];
  if (bookmarkOk) lines.push('&#10003; Bookmarked in Firefox');
  else lines.push(`&#10007; Bookmark failed: ${esc(bookmarkResult.reason?.message || 'unknown')}`);
  if (viewtubeOk) lines.push('&#10003; Added to ViewTube');
  else if (vtResult.status === 'rejected') lines.push(`&#10007; ViewTube unreachable`);
  else lines.push(`&#10007; ViewTube: ${esc(vtData?.error || 'unknown error')}`);
  if (alsoWatchLater && watchLaterOk === true) lines.push('&#10003; Added to Watch Later');
  if (alsoWatchLater && watchLaterOk === false) lines.push('&#10007; Watch Later failed');
  if (alsoFavorite && favoriteOk === true) lines.push('&#9733; Marked as favorite');
  if (alsoFavorite && favoriteOk === false) lines.push('&#10007; Favorite failed');
  const cls = (bookmarkOk || viewtubeOk) ? 'partial' : 'error';
  root.innerHTML = `<div class="status ${cls}">${lines.map(l => `<div>${l}</div>`).join('')}</div>`;
}
```

Note: `&#9733;` is the HTML entity for ★, consistent with this file's existing use of numeric entities (`&#10003;`, `&#10007;`, `&#8856;`) inside `innerHTML` strings rather than raw UTF-8 characters.

- [ ] **Step 3: Add the checkbox to the `not_found` branch**

In `extension/popup/popup.js`, the `not_found` branch of `renderState` (currently lines 230-243) reads:

```javascript
  if (data.status === 'not_found') {
    root.innerHTML = `
      <button id="btn-add" class="action-btn">Add to ViewTube</button>
      <label style="display:block;margin-top:0.4rem;font-size:0.8rem;cursor:pointer;color:#aaa">
        <input type="checkbox" id="chk-watch-later" style="margin-right:0.3rem">
        Also add to Watch Later
      </label>
    `;
    document.getElementById('btn-add').addEventListener('click', () => {
      const alsoWatchLater = document.getElementById('chk-watch-later').checked;
      doAdd(viewtubeUrl, tabUrl, tabTitle, alsoWatchLater);
    });
    return;
  }
```

Replace it with:

```javascript
  if (data.status === 'not_found') {
    root.innerHTML = `
      <button id="btn-add" class="action-btn">Add to ViewTube</button>
      <label style="display:block;margin-top:0.4rem;font-size:0.8rem;cursor:pointer;color:#aaa">
        <input type="checkbox" id="chk-watch-later" style="margin-right:0.3rem">
        Also add to Watch Later
      </label>
      <label style="display:block;margin-top:0.4rem;font-size:0.8rem;cursor:pointer;color:#aaa">
        <input type="checkbox" id="chk-favorite" style="margin-right:0.3rem">
        Also mark as favorite (&#9733;)
      </label>
    `;
    document.getElementById('btn-add').addEventListener('click', () => {
      const alsoWatchLater = document.getElementById('chk-watch-later').checked;
      const alsoFavorite = document.getElementById('chk-favorite').checked;
      doAdd(viewtubeUrl, tabUrl, tabTitle, alsoWatchLater, alsoFavorite);
    });
    return;
  }
```

This branch is the only place `doAdd` is invoked with user-controlled checkbox state — the `exists` and `hidden` branches don't call `doAdd` at all, so they're unaffected by this change.

- [ ] **Step 4: Manual verification**

Load the extension in Firefox (`about:debugging` → temporary add-on) with the webapp running at `http://localhost:8080`, using a video not yet in ViewTube:

- Open the popup: both "Also add to Watch Later" and "Also mark as favorite (★)" checkboxes appear, unchecked.
- Check only "Also mark as favorite", click "Add to ViewTube": popup shows `✓ <title>` then `★ Marked as favorite`, closes after 1.5s. Confirm on the web UI (`/`) that the video's ★ button shows the active/favourited state.
- Check only "Also add to Watch Later" (leave favorite unchecked): behavior unchanged from before this task — confirm no `★ Marked as favorite` line appears and the video is not favourited on the web UI.
- Check both boxes: both `✓ Added to Watch Later` and `★ Marked as favorite` lines appear; confirm both states landed (video on `/watch-later` and favourited).
- Check neither box: existing add-only behavior unchanged.
- Stop the webapp server, open the popup on a brand-new video with the favorite box checked, click Add: bookmark-only partial-failure state is unaffected in shape (favorite/watch-later simply don't fire since `viewtubeOk` is false); popup doesn't crash.
- The `exists`-state popup (video already in ViewTube) is unaffected — no favorite checkbox appears there (out of scope, tracked separately in `TODO.md`).

- [ ] **Step 5: Update docs**

- `CHANGELOG.md`: append a dated entry (today's date) — extension popup gained an "Also mark as favorite" checkbox on the add-new-video screen, alongside the existing watch-later checkbox; backed by a new `POST /api/favourite/add` route reusing the existing `set_favourite` DB function. Implication (pro): a standout video can be starred the instant it's captured, no trip back to the web UI needed; (con): favoriting is capture-time only for now — toggling favorite status on an already-added video is a separate deferred TODO item, same as watch-later's own history.
- `plan-webapp.md`: in the `**Bookmarklet / quick-add**` paragraph (the same sentence already documenting the `not_found`-state watch-later checkbox), add a clause describing the sibling "Also mark as favorite" checkbox and `POST /api/favourite/add`: no 409/already-case (unlike watch-later) since `is_favourite` is a plain boolean, and the follow-up calls for watch-later and favorite now run in parallel via `Promise.allSettled` rather than sequentially, since neither depends on the other (both only depend on the video already existing in the DB, which the main add call guarantees before either fires).

- [ ] **Step 6: Run the full test suite**

Run: `python -m pytest -q`
Expected: PASS (all tests, including Task 1's new route tests).

- [ ] **Step 7: Commit**

```bash
git add extension/popup/popup.js CHANGELOG.md plan-webapp.md
git commit -m "feat(extension): mark video as favorite at capture time"
```

---

## Self-Review Notes

- **Spec coverage:** `POST /api/favourite/add` (Task 1) ← spec's "Backend" section, including the no-409 design decision (explicitly enforced via Global Constraints and the idempotent-re-add test); `postJson` helper + parallel `doAdd` refactor + new checkbox (Task 2) ← spec's "Extension" section, including the exact success/partial-failure line behavior from the spec's two sub-sections; manual verification ← spec's "Testing" section, expanded into the spec's own edge-case table (both/either/neither checked, server down); doc bookkeeping ← CLAUDE.md's always-update-plans/changelog/TODO instructions, plus the lesson from the watch-later-toggle plan's final review (that plan's own review caught a missed `TODO.md` update — this plan's Task 2 Step 5 deliberately does not touch `TODO.md` because the capture-time item was already struck through when this plan was written, and the anytime-toggle item stays open by design since it's out of scope here).
- **Type consistency:** `postJson(url, body)` signature used identically in both call sites inside `doAdd`; `doAdd(viewtubeUrl, tabUrl, tabTitle, alsoWatchLater = false, alsoFavorite = false)` signature matches its only call site (Task 2 Step 3); `favoriteOk` tri-state (`null`/`true`/`false`) mirrors the existing `watchLaterOk` pattern exactly, including how both branches of the success/partial-failure `if` blocks read it.
- **Verified against codebase:** `set_favourite(conn, video_id, value)` exists at `webapp/db/videos.py:66` and is already exported via `webapp/db/__init__.py`; `_YT_ID_RE` already imported at `routes.py:7`; the `not_found` branch of `renderState` and the full `doAdd` function were read directly from the current file before drafting the diffs above (lines cited match the current file as of this plan's writing); `tests/webapp/test_routes.py` already has `sqlite3` usage and a seeded `aaaaaaaaaa1` video fixture via conftest, confirmed by reading the existing `TestApiWatchLaterAdd`/`TestApiWatchLaterRemove` classes.

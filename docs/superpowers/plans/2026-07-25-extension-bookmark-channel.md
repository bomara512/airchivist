# Extension: Bookmark Channel Action Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the extension popup detect a YouTube channel page, pre-check whether ViewTube already tracks it, and add it (ViewTube row + Firefox bookmark) on click.

**Architecture:** Two new webapp DB functions in `webapp/db/channels.py` (a write `upsert_channel` and a `get_channel_by_source_url` lookup), two new CORS-enabled routes in `webapp/routes.py` (`GET /api/channel/status` for the fast pre-check, `POST /api/channel/add` for the yt-dlp fetch + upsert), and popup changes in `extension/popup/popup.js` that branch on channel URLs. The routes reuse `fetch_channel_metadata` and `ChannelMetadata` from the crawler exactly as the existing `/api/add` reuses `fetch_metadata`.

**Tech Stack:** Python, Flask, SQLite, yt-dlp (via crawler), pytest; vanilla-JS Firefox WebExtension (no build, no JS test suite).

## Global Constraints

- Every API route returning JSON to the extension MUST use the module-level `_CORS_HEADERS` constant on both the success response and the OPTIONS preflight — never a locally-defined dict.
- New/changed public functions in `webapp/db/*.py` and routes in `webapp/routes.py` require tests in the same change (happy path + one edge case; routes also CORS header + OPTIONS).
- Never use `rowid` with `sqlite3.Row`; select and reference the named primary key (`channel_id`).
- Webapp DB write functions commit internally (see `webapp/db/aliases.py`).
- Remove any debug logging before finishing.
- Append a `CHANGELOG.md` entry and update `plan-webapp.md` for the implementation change; mark the extension "bookmark channel" item in `TODO.md`.
- Run `python -m pytest -q` at the end; all tests must pass.

---

### Task 1: Webapp DB functions — `upsert_channel` and `get_channel_by_source_url`

**Files:**
- Modify: `webapp/db/channels.py`
- Modify: `webapp/db/__init__.py` (export the two new functions)
- Test: `tests/webapp/test_db.py`

**Interfaces:**
- Consumes: `ChannelMetadata` from `crawler.models` (fields: `channel_id`, `channel_name`, `channel_url`, `description`, `subscriber_count`, `thumbnail_url`, `fetch_status`, `fetch_error`); the `channels` table created by conftest's `_setup_db`.
- Produces:
  - `upsert_channel(conn: sqlite3.Connection, meta: ChannelMetadata, source_url: Optional[str] = None) -> None` — inserts/updates by `channel_id`, commits.
  - `get_channel_by_source_url(conn: sqlite3.Connection, url: str) -> Optional[dict]` — row where `channel_url = url OR source_url = url`, else `None`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/webapp/test_db.py` (top-level import already imports channel funcs on line 15 — extend it to `from webapp.db import (... get_all_channels, get_channel, upsert_channel, get_channel_by_source_url)`; add `from crawler.models import ChannelMetadata`):

```python
class TestUpsertChannel:
    def test_inserts_new_channel(self, db_conn):
        meta = ChannelMetadata(
            channel_id="UCaaa111", channel_name="Chan A",
            channel_url="https://www.youtube.com/channel/UCaaa111",
            description="hello", subscriber_count=42,
            thumbnail_url="https://img/x.jpg",
        )
        upsert_channel(db_conn, meta, source_url="https://www.youtube.com/@chanA")
        row = get_channel(db_conn, "UCaaa111")
        assert row["channel_name"] == "Chan A"
        assert row["description"] == "hello"
        assert row["subscriber_count"] == 42

    def test_upsert_preserves_source_url_when_refetched_without_one(self, db_conn):
        meta = ChannelMetadata(
            channel_id="UCbbb222", channel_name="Chan B",
            channel_url="https://www.youtube.com/channel/UCbbb222",
        )
        upsert_channel(db_conn, meta, source_url="https://www.youtube.com/@chanB")
        # Re-upsert with no source_url must not wipe the stored one (COALESCE).
        upsert_channel(db_conn, meta, source_url=None)
        found = get_channel_by_source_url(db_conn, "https://www.youtube.com/@chanB")
        assert found is not None
        assert found["channel_id"] == "UCbbb222"


class TestGetChannelBySourceUrl:
    def test_matches_channel_url(self, db_conn):
        meta = ChannelMetadata(
            channel_id="UCccc333", channel_name="Chan C",
            channel_url="https://www.youtube.com/channel/UCccc333",
        )
        upsert_channel(db_conn, meta, source_url="https://www.youtube.com/@chanC")
        assert get_channel_by_source_url(
            db_conn, "https://www.youtube.com/channel/UCccc333"
        )["channel_id"] == "UCccc333"

    def test_returns_none_for_unknown(self, db_conn):
        assert get_channel_by_source_url(db_conn, "https://www.youtube.com/@nobody") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/webapp/test_db.py::TestUpsertChannel tests/webapp/test_db.py::TestGetChannelBySourceUrl -q`
Expected: FAIL — `ImportError: cannot import name 'upsert_channel'` (or `get_channel_by_source_url`).

- [ ] **Step 3: Implement the functions**

Append to `webapp/db/channels.py` (add `from crawler.models import ChannelMetadata` to the imports at the top):

```python
def upsert_channel(
    conn: sqlite3.Connection,
    meta: ChannelMetadata,
    source_url: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO channels
            (channel_id, channel_name, channel_url, description,
             subscriber_count, thumbnail_url, source_url, fetch_error, fetch_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(channel_id) DO UPDATE SET
            channel_name     = excluded.channel_name,
            channel_url      = excluded.channel_url,
            description      = excluded.description,
            subscriber_count = excluded.subscriber_count,
            thumbnail_url    = excluded.thumbnail_url,
            source_url       = COALESCE(excluded.source_url, channels.source_url),
            fetch_error      = excluded.fetch_error,
            fetch_status     = excluded.fetch_status
        """,
        (
            meta.channel_id, meta.channel_name, meta.channel_url,
            meta.description, meta.subscriber_count, meta.thumbnail_url,
            source_url, meta.fetch_error, meta.fetch_status,
        ),
    )
    conn.commit()


def get_channel_by_source_url(conn: sqlite3.Connection, url: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT channel_id, channel_name, channel_url, description, "
        "subscriber_count, thumbnail_url, source_url, fetch_error, fetch_status, "
        "date_added FROM channels WHERE channel_url = ? OR source_url = ?",
        (url, url),
    ).fetchone()
    return dict(row) if row else None
```

In `webapp/db/__init__.py`, extend the `from webapp.db.channels import (...)` block (currently `get_all_channels, get_channel`) to also import `upsert_channel, get_channel_by_source_url`, and add both names to the `__all__`/export list on the `# channels` line (`"get_all_channels", "get_channel", "upsert_channel", "get_channel_by_source_url"`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/webapp/test_db.py::TestUpsertChannel tests/webapp/test_db.py::TestGetChannelBySourceUrl -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add webapp/db/channels.py webapp/db/__init__.py tests/webapp/test_db.py
git commit -m "feat(webapp/db): add upsert_channel and get_channel_by_source_url"
```

---

### Task 2: Route — `GET /api/channel/status`

**Files:**
- Modify: `webapp/routes.py`
- Test: `tests/webapp/test_routes.py`

**Interfaces:**
- Consumes: `get_channel_by_source_url` (Task 1); `_YT_CHANNEL_RE` from `crawler.models`; `_CORS_HEADERS`, `g.db`.
- Produces: route `GET/OPTIONS /api/channel/status?url=…` returning JSON `{status: "exists", channel_name}` / `{status: "not_found"}` / `{status:"error", error}` (400).

- [ ] **Step 1: Write the failing tests**

Add to `tests/webapp/test_routes.py` (module already has `client` fixture; add `from crawler.models import ChannelMetadata, FetchStatus` and `import sqlite3` if not present — `sqlite3` is already imported per the shelf tests):

```python
class TestApiChannelStatus:
    def _insert_channel(self, client):
        conn = sqlite3.connect(client.application.config["DATABASE"])
        conn.execute(
            "INSERT INTO channels (channel_id, channel_name, channel_url, source_url, "
            "fetch_status) VALUES (?, ?, ?, ?, 'ok')",
            ("UCzzz999", "Tracked Chan",
             "https://www.youtube.com/channel/UCzzz999",
             "https://www.youtube.com/@tracked"),
        )
        conn.commit()
        conn.close()

    def test_not_found_for_untracked(self, client):
        resp = client.get("/api/channel/status?url=https://www.youtube.com/@nobody")
        assert resp.get_json()["status"] == "not_found"

    def test_exists_for_tracked(self, client):
        self._insert_channel(client)
        data = client.get(
            "/api/channel/status?url=https://www.youtube.com/@tracked"
        ).get_json()
        assert data["status"] == "exists"
        assert data["channel_name"] == "Tracked Chan"

    def test_non_channel_url_returns_400(self, client):
        resp = client.get("/api/channel/status?url=https://example.com/foo")
        assert resp.status_code == 400
        assert resp.get_json()["status"] == "error"

    def test_cors_header_present(self, client):
        resp = client.get("/api/channel/status?url=https://www.youtube.com/@nobody")
        assert "Access-Control-Allow-Origin" in resp.headers

    def test_options_preflight(self, client):
        resp = client.options("/api/channel/status")
        assert resp.status_code == 204
        assert "Access-Control-Allow-Origin" in resp.headers
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/webapp/test_routes.py::TestApiChannelStatus -q`
Expected: FAIL — 404 responses (route not registered).

- [ ] **Step 3: Implement the route**

In `webapp/routes.py`, extend the crawler import on line 7 to `from crawler.models import _YT_ID_RE, _YT_CHANNEL_RE, FetchStatus`. Add the route (place it next to `api_add`):

```python
@bp.route("/api/channel/status", methods=["GET", "OPTIONS"])
def api_channel_status():
    if request.method == "OPTIONS":
        return make_response("", 204, _CORS_HEADERS)

    url = (request.args.get("url") or "").strip()
    if not _YT_CHANNEL_RE.search(url):
        resp = jsonify({"status": "error", "error": "Not a YouTube channel URL"})
        resp.headers.update(_CORS_HEADERS)
        return resp, 400

    existing = _db.get_channel_by_source_url(g.db, url)
    if existing:
        resp = jsonify({"status": "exists", "channel_name": existing["channel_name"]})
    else:
        resp = jsonify({"status": "not_found"})
    resp.headers.update(_CORS_HEADERS)
    return resp
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/webapp/test_routes.py::TestApiChannelStatus -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add webapp/routes.py tests/webapp/test_routes.py
git commit -m "feat(webapp): add GET /api/channel/status pre-check route"
```

---

### Task 3: Route — `POST /api/channel/add`

**Files:**
- Modify: `webapp/routes.py`
- Test: `tests/webapp/test_routes.py`

**Interfaces:**
- Consumes: `get_channel_by_source_url`, `upsert_channel` (Task 1); `_YT_CHANNEL_RE`, `FetchStatus`; `fetch_channel_metadata` from `crawler.metadata_fetcher` (local import inside the route, mirroring `api_add`); `_CORS_HEADERS`, `g.db`.
- Produces: route `POST/OPTIONS /api/channel/add` with JSON body `{url}` returning `{status:"added"|"exists"|"error", channel_name?, error?}`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/webapp/test_routes.py`:

```python
class TestApiChannelAdd:
    def _fake_meta(self):
        return ChannelMetadata(
            channel_id="UCadd777", channel_name="Added Chan",
            channel_url="https://www.youtube.com/channel/UCadd777",
            description="desc", subscriber_count=5,
            thumbnail_url="https://img/y.jpg", fetch_status=FetchStatus.OK,
        )

    def test_adds_new_channel(self, client, monkeypatch):
        monkeypatch.setattr(
            "crawler.metadata_fetcher.fetch_channel_metadata",
            lambda url, delay=0: self._fake_meta(),
        )
        data = client.post(
            "/api/channel/add", json={"url": "https://www.youtube.com/@added"}
        ).get_json()
        assert data["status"] == "added"
        assert data["channel_name"] == "Added Chan"

    def test_second_add_reports_exists(self, client, monkeypatch):
        monkeypatch.setattr(
            "crawler.metadata_fetcher.fetch_channel_metadata",
            lambda url, delay=0: self._fake_meta(),
        )
        client.post("/api/channel/add", json={"url": "https://www.youtube.com/@added"})
        data = client.post(
            "/api/channel/add", json={"url": "https://www.youtube.com/@added"}
        ).get_json()
        assert data["status"] == "exists"

    def test_fetch_error_returns_error(self, client, monkeypatch):
        err = ChannelMetadata(
            channel_id="", channel_name="",
            channel_url="https://www.youtube.com/@broken",
            fetch_status=FetchStatus.PRIVATE, fetch_error="unavailable",
        )
        monkeypatch.setattr(
            "crawler.metadata_fetcher.fetch_channel_metadata",
            lambda url, delay=0: err,
        )
        data = client.post(
            "/api/channel/add", json={"url": "https://www.youtube.com/@broken"}
        ).get_json()
        assert data["status"] == "error"
        assert data["error"] == "unavailable"

    def test_non_channel_url_returns_400(self, client):
        resp = client.post("/api/channel/add", json={"url": "https://example.com/foo"})
        assert resp.status_code == 400

    def test_cors_header_present(self, client, monkeypatch):
        monkeypatch.setattr(
            "crawler.metadata_fetcher.fetch_channel_metadata",
            lambda url, delay=0: self._fake_meta(),
        )
        resp = client.post("/api/channel/add", json={"url": "https://www.youtube.com/@added"})
        assert "Access-Control-Allow-Origin" in resp.headers

    def test_options_preflight(self, client):
        resp = client.options("/api/channel/add")
        assert resp.status_code == 204
        assert "Access-Control-Allow-Origin" in resp.headers
```

Note: `FetchStatus.PRIVATE = 'private'` is defined in `crawler/models.py` (verified). Any non-OK value works for this test.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/webapp/test_routes.py::TestApiChannelAdd -q`
Expected: FAIL — 404 (route not registered).

- [ ] **Step 3: Implement the route**

In `webapp/routes.py`, add next to `api_channel_status`:

```python
@bp.route("/api/channel/add", methods=["POST", "OPTIONS"])
def api_channel_add():
    if request.method == "OPTIONS":
        return make_response("", 204, _CORS_HEADERS)

    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not _YT_CHANNEL_RE.search(url):
        resp = jsonify({"status": "error", "error": "Not a YouTube channel URL"})
        resp.headers.update(_CORS_HEADERS)
        return resp, 400

    existing = _db.get_channel_by_source_url(g.db, url)
    if existing:
        resp = jsonify({"status": "exists", "channel_name": existing["channel_name"]})
        resp.headers.update(_CORS_HEADERS)
        return resp

    from crawler.metadata_fetcher import fetch_channel_metadata
    meta = fetch_channel_metadata(url, delay=0)
    if meta.fetch_status != FetchStatus.OK:
        resp = jsonify({"status": "error", "error": meta.fetch_error or "fetch failed"})
        resp.headers.update(_CORS_HEADERS)
        return resp, 200

    _db.upsert_channel(g.db, meta, source_url=url)
    resp = jsonify({"status": "added", "channel_name": meta.channel_name})
    resp.headers.update(_CORS_HEADERS)
    return resp
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/webapp/test_routes.py::TestApiChannelAdd -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add webapp/routes.py tests/webapp/test_routes.py
git commit -m "feat(webapp): add POST /api/channel/add route"
```

---

### Task 4: Extension popup — channel detection, pre-check, and add

**Files:**
- Modify: `extension/popup/popup.js`
- Modify: `CHANGELOG.md`, `plan-webapp.md`, `TODO.md`

**Interfaces:**
- Consumes: `GET /api/channel/status` (Task 2), `POST /api/channel/add` (Task 3); existing helpers `esc`, `getOrCreateFolder`.
- Produces: user-facing channel-add behaviour. No automated tests (extension has none — manual verification only, consistent with the watch-later-on-add feature).

- [ ] **Step 1: Add the channel regex and URL normalizer**

At the top of `extension/popup/popup.js`, below `const YT_ID_RE = …`, add:

```javascript
const YT_CHANNEL_RE = /youtube\.com\/(channel\/UC[A-Za-z0-9_-]+|(?:c|user)\/[^/?#]+|@[^/?#]+)/;

function channelUrlFrom(match) {
  // match[1] is the canonical path segment (@handle, channel/UC…, c/name, user/name).
  return `https://www.youtube.com/${match[1]}`;
}
```

- [ ] **Step 2: Add `renderChannelState` and `doAddChannel`**

Add these functions to `extension/popup/popup.js` (near `renderState`/`doAdd`):

```javascript
async function doAddChannel(viewtubeUrl, channelUrl, tabTitle) {
  const root = document.getElementById('root');
  root.innerHTML = '<div class="status">Adding channel…</div>';
  const [bookmarkResult, vtResult] = await Promise.allSettled([
    getOrCreateFolder().then(id =>
      browser.bookmarks.create({ title: tabTitle, url: channelUrl, parentId: id })
    ),
    fetch(`${viewtubeUrl}/api/channel/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: channelUrl }),
    }).then(r => r.json()),
  ]);
  const bookmarkOk = bookmarkResult.status === 'fulfilled';
  const vtData = vtResult.status === 'fulfilled' ? vtResult.value : null;
  const viewtubeOk = vtData && ['added', 'exists'].includes(vtData.status);

  if (bookmarkOk && viewtubeOk) {
    root.innerHTML = `<div class="status success">&#10003; ${esc(vtData.channel_name || tabTitle)}</div>`;
    setTimeout(() => window.close(), 1500);
    return;
  }
  const lines = [];
  if (bookmarkOk) lines.push('&#10003; Bookmarked in Firefox');
  else lines.push(`&#10007; Bookmark failed: ${esc(bookmarkResult.reason?.message || 'unknown')}`);
  if (viewtubeOk) lines.push('&#10003; Added to ViewTube');
  else if (vtResult.status === 'rejected') lines.push('&#10007; ViewTube unreachable');
  else lines.push(`&#10007; ViewTube: ${esc(vtData?.error || 'unknown error')}`);
  const cls = (bookmarkOk || viewtubeOk) ? 'partial' : 'error';
  root.innerHTML = `<div class="status ${cls}">${lines.map(l => `<div>${l}</div>`).join('')}</div>`;
}

function renderChannelState(root, viewtubeUrl, channelUrl, tabTitle, data) {
  if (data.status === 'exists') {
    root.innerHTML = `<div class="status success">&#10003; Already tracked: ${esc(data.channel_name)}</div>`;
    return;
  }
  if (data.status === 'not_found') {
    root.innerHTML = `<button id="btn-add-channel" class="action-btn">Add channel to ViewTube</button>`;
    document.getElementById('btn-add-channel').addEventListener('click', () =>
      doAddChannel(viewtubeUrl, channelUrl, tabTitle)
    );
    return;
  }
  root.innerHTML = `<div class="status error">&#10007; ${esc(data.error || 'Unknown error')}</div>`;
}
```

- [ ] **Step 3: Branch `run()` on channel URLs**

Replace the not-a-video guard and status call in `run()`. The current block is:

```javascript
  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  if (!tab?.url || !YT_ID_RE.test(tab.url)) {
    root.innerHTML = '<div class="status error">Not a YouTube video.</div>';
    return;
  }

  const settings = await browser.storage.local.get(URL_KEY);
  const viewtubeUrl = settings[URL_KEY] || DEFAULT_URL;

  let data;
  try {
    data = await checkStatus(viewtubeUrl, tab.url);
  } catch {
    root.innerHTML = `<div class="status error">&#10007; ViewTube unreachable<br><small>Is it running at ${esc(viewtubeUrl)}?</small></div>`;
    return;
  }

  renderState(root, viewtubeUrl, tab.url, tab.title || '', data);
```

Replace it with:

```javascript
  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  const isVideo = tab?.url && YT_ID_RE.test(tab.url);
  const channelMatch = tab?.url ? tab.url.match(YT_CHANNEL_RE) : null;
  if (!isVideo && !channelMatch) {
    root.innerHTML = '<div class="status error">Not a YouTube video or channel.</div>';
    return;
  }

  const settings = await browser.storage.local.get(URL_KEY);
  const viewtubeUrl = settings[URL_KEY] || DEFAULT_URL;

  if (!isVideo && channelMatch) {
    const channelUrl = channelUrlFrom(channelMatch);
    let chData;
    try {
      const resp = await fetch(
        `${viewtubeUrl}/api/channel/status?url=${encodeURIComponent(channelUrl)}`
      );
      chData = await resp.json();
    } catch {
      root.innerHTML = `<div class="status error">&#10007; ViewTube unreachable<br><small>Is it running at ${esc(viewtubeUrl)}?</small></div>`;
      return;
    }
    renderChannelState(root, viewtubeUrl, channelUrl, tab.title || '', chData);
    return;
  }

  let data;
  try {
    data = await checkStatus(viewtubeUrl, tab.url);
  } catch {
    root.innerHTML = `<div class="status error">&#10007; ViewTube unreachable<br><small>Is it running at ${esc(viewtubeUrl)}?</small></div>`;
    return;
  }

  renderState(root, viewtubeUrl, tab.url, tab.title || '', data);
```

Note the fallback copy changes from "Not a YouTube video." to "Not a YouTube video or channel." — this retires the memory-noted always-reject behaviour on channel pages.

- [ ] **Step 4: Manual verification**

Load the extension in Firefox (`about:debugging` → temporary add-on) with the webapp running at `http://localhost:8080`, then confirm:
- On `https://www.youtube.com/@<somechannel>` the popup shows **Add channel to ViewTube**; clicking it shows `✓ <channel name>` and creates a Firefox bookmark in the ViewTube folder.
- Re-opening the popup on the same channel shows **✓ Already tracked: <name>**.
- Works on `/channel/UC…`, `/c/name`, and `/user/name` forms.
- A non-YouTube tab still shows **Not a YouTube video or channel.**
- A normal `/watch?v=…` video page still behaves exactly as before.

- [ ] **Step 5: Update docs**

- `CHANGELOG.md`: append a dated entry — channel bookmark action added to the extension (popup detects channel pages, pre-checks via `/api/channel/status`, adds via `/api/channel/add` + Firefox bookmark). Implication (pro): channels are now first-class from the browser; (con): status pre-check is URL-based, so `@handle` vs `/channel/UC…` may show "Add" for an already-tracked channel (resolved correctly on click via `channel_id`).
- `plan-webapp.md`: document the two new API routes and the popup's three-way branch (video / channel / neither), including the documented status-pre-check limitation.
- `TODO.md`: mark **Extension: "bookmark channel" action on youtube.com/c/\* and youtube.com/@\* pages** complete (strike through).

- [ ] **Step 6: Run the full test suite**

Run: `python -m pytest -q`
Expected: PASS (all tests, including Tasks 1–3).

- [ ] **Step 7: Commit**

```bash
git add extension/popup/popup.js CHANGELOG.md plan-webapp.md TODO.md
git commit -m "feat(extension): add bookmark-channel action on channel pages"
```

---

## Self-Review Notes

- **Spec coverage:** DB `upsert_channel` + `get_channel_by_source_url` (Task 1) ← Section 1; `/api/channel/status` (Task 2) and `/api/channel/add` (Task 3) ← Section 2; popup regex/normalizer/branch/render/add (Task 4) ← Section 3; documented status limitation ← Section 4 (CHANGELOG + plan-webapp in Task 4 Step 5). No hide/archive/watch-later for channels (YAGNI) — respected.
- **Type consistency:** `upsert_channel(conn, meta, source_url=None)` and `get_channel_by_source_url(conn, url)` used identically across Tasks 1–3; `channel_name` key returned by both routes matches what `renderChannelState`/`doAddChannel` read (`data.channel_name`); `channelUrlFrom(match)` returns the string passed to both `/api/channel/status` and `/api/channel/add`.
- **Verified against codebase:** `FetchStatus.PRIVATE` exists; `routes.py` uses the `from webapp import db as _db` alias and imports `jsonify`/`make_response`/`g`; `channels` table and conftest `db_conn`/`client` fixtures exist; `webapp/db/__init__.py` already re-exports channel functions.

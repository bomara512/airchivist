# Extension: Add to Watch Later on Video Add — Implementation Plan

> **Status: COMPLETED** — shipped; `alsoWatchLater` is live in `extension/popup/popup.js`. This plan is retained as an artifact of record.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the extension popup opens on a YouTube video not yet in ViewTube, show a prompt ("Add to ViewTube" button + "Also add to Watch Later" checkbox) instead of firing the add immediately; when submitted, optionally enqueue the video in Watch Later after the add completes.

**Architecture:** Two sequential changes, both in `extension/popup/popup.js`. First, extend `doAdd` to accept and honour an `alsoWatchLater` flag. Second, replace the auto-fire `doAdd()` call in `renderState`'s `not_found` branch with HTML that renders the button + checkbox and calls `doAdd` only on user click. The watch-later API call must be sequential (after add), because `/api/watch-later/add` 404s if the video is not yet in the DB.

**Tech Stack:** Vanilla JS browser extension (Firefox WebExtensions API); no build step, no test suite for extension JS (manual testing only).

---

## File Map

| File | Action |
|---|---|
| `extension/popup/popup.js` | Modify `doAdd` (lines 40–69) and `renderState` not_found branch (lines 114–117) |
| `CHANGELOG.md` | Append entry |
| `plan-webapp.md` | Update to reflect new popup behaviour |

---

### Task 1: Add `alsoWatchLater` parameter and sequential watch-later call to `doAdd`

**Files:**
- Modify: `extension/popup/popup.js:40–69`

- [x] **Step 1: Replace `doAdd` with the updated version**

Open `extension/popup/popup.js` and replace the entire `doAdd` function (lines 40–69) with:

```js
async function doAdd(viewtubeUrl, tabUrl, tabTitle, alsoWatchLater = false) {
  const root = document.getElementById('root');
  root.innerHTML = '<div class="status">Adding…</div>';
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
    if (watchLaterOk === true) lines.push('+ Added to Watch Later');
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

Key changes from the original:
- Signature gains `alsoWatchLater = false`
- After the parallel bookmark + ViewTube settlement, if `alsoWatchLater && viewtubeOk`, fires `POST /api/watch-later/add` sequentially
- 409 `already_in_queue` is treated as success (no spurious error)
- Watch-later result appended as secondary line on both success and partial/error paths
- Watch-later failure does **not** prevent the 1.5 s auto-close on the success path

- [x] **Step 2: Verify the file saved cleanly**

Open `extension/popup/popup.js` and confirm:
- `doAdd` signature is `async function doAdd(viewtubeUrl, tabUrl, tabTitle, alsoWatchLater = false)`
- The `watchLaterOk` block exists between the settled-result derivation and the success path
- No old version of `doAdd` remains

- [x] **Step 3: Commit Task 1**

```bash
git add extension/popup/popup.js
git commit -m "feat(extension): add alsoWatchLater param to doAdd with sequential watch-later call"
```

---

### Task 2: Replace auto-fire `doAdd` with prompt UI in `renderState` `not_found` branch

**Files:**
- Modify: `extension/popup/popup.js:114–117`

- [x] **Step 1: Replace the `not_found` branch**

In `renderState`, replace lines 114–117:

```js
  if (data.status === 'not_found') {
    doAdd(viewtubeUrl, tabUrl, tabTitle);
    return;
  }
```

with:

```js
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

Notes:
- Styles mirror the `exists` branch (`.action-btn` class, inline label styles)
- Checkbox defaults to unchecked — opt-in behaviour
- `doAdd` is called **only** on button click, not on popup open

- [x] **Step 2: Manually test the happy path (no watch later)**

1. Open Firefox and navigate to any YouTube video not in your ViewTube DB.
2. Click the extension icon.
3. Verify the popup shows "Add to ViewTube" button and unchecked checkbox.
4. Click "Add to ViewTube" without checking the box.
5. Verify the success message shows the video title with ✓ and no watch-later line.
6. Verify the popup auto-closes after ~1.5 s.

- [x] **Step 3: Manually test with watch later checked**

1. Navigate to a YouTube video not in ViewTube.
2. Click the extension icon.
3. Check "Also add to Watch Later".
4. Click "Add to ViewTube".
5. Verify success message shows title on line 1 and "+ Added to Watch Later" on line 2.
6. Verify the video appears in the ViewTube Watch Later queue (open the Watch Later page).

- [x] **Step 4: Manually test watch-later failure path**

1. Stop the ViewTube server (or block the `/api/watch-later/add` endpoint temporarily).
2. Navigate to a YouTube video not in ViewTube.
3. Check "Also add to Watch Later" and click "Add to ViewTube".
4. Verify success message shows title and "✗ Watch Later failed" — popup still auto-closes.

- [x] **Step 5: Verify `exists` state is unchanged**

1. Navigate to a YouTube video already in ViewTube.
2. Click the extension icon.
3. Confirm the popup still shows the title + "Archive" button + "Also remove browser bookmark" checkbox — no watch-later checkbox here.

- [x] **Step 6: Commit Task 2**

```bash
git add extension/popup/popup.js
git commit -m "feat(extension): show Add to ViewTube prompt with optional Watch Later checkbox"
```

---

### Task 3: Update CHANGELOG and plan

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `plan-webapp.md`

- [x] **Step 1: Append to CHANGELOG.md**

Add an entry under today's date (2026-07-02):

```
## 2026-07-02

### Extension: Add to Watch Later on video add

- Opening the popup on a YouTube video not yet in ViewTube now shows an "Add to ViewTube" button and an "Also add to Watch Later" checkbox, rather than firing the add immediately.
- If the checkbox is ticked, a sequential POST to `/api/watch-later/add` fires after the ViewTube add succeeds.
- **Trade-off:** The extra click is a minor friction increase for the common case (add without watch later), but avoids accidentally enqueuing videos and matches the opt-in pattern of "Also remove browser bookmark" on the Archive flow.
- `already_in_queue` (409) is treated as success so re-adding an already-queued video doesn't show an error.
```

- [x] **Step 2: Update plan-webapp.md**

Find the section describing the extension popup flow (the `not_found` → immediate add behaviour) and update it to describe the new prompt-first flow. Remove any description of the old auto-fire behaviour.

- [x] **Step 3: Commit Task 3**

```bash
git add CHANGELOG.md plan-webapp.md
git commit -m "docs: update changelog and plan for add-to-watch-later extension feature"
```

---

## Self-Review

**Spec coverage:**
- ✅ `not_found` branch shows prompt (Task 2, Step 1)
- ✅ Checkbox defaults unchecked (Task 2, Step 1)
- ✅ Watch later fires sequentially after add (Task 1, Step 1)
- ✅ 409 treated as success (Task 1, Step 1)
- ✅ Watch later failure shown as secondary line, does not block auto-close (Task 1, Step 1)
- ✅ `exists` state untouched (Task 2, Step 5 verifies)
- ✅ Partial/error path also shows watch later result (Task 1, Step 1)

**Placeholder scan:** No TBDs, no "similar to Task N" shortcuts, no vague steps.

**Type/name consistency:** `alsoWatchLater` used consistently in signature, flag variable, and success/error path checks. `watchLaterOk` initialised to `null` and only set to `true`/`false` — both falsy/truthy paths handled correctly.

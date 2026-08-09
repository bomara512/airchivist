# Extension: Watch Later Toggle at Any Time Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the extension popup add or remove a video from the Watch Later queue at any time the video is already in ViewTube — not just at the moment it's first added — via a checkbox that reflects current queue membership.

**Architecture:** Extension-only change to `extension/popup/popup.js`. No backend changes: `POST /api/watch-later/status`, `/add`, and `/remove` already exist, are CORS-compliant, and are tested. The popup's `exists`-state branch gains a disabled/unchecked checkbox that a follow-up status fetch enables and sets, and whose `change` event fires `/add` or `/remove` directly (no separate submit step).

**Tech Stack:** Vanilla-JS Firefox WebExtension popup (no build, no JS test suite — extension has none, consistent with the existing add-time watch-later feature).

## Global Constraints

- No backend changes — `webapp/routes.py` and `webapp/db.py` are untouched by this plan.
- Only the `exists` state in `renderState` changes. The `not_found` state's existing "Also add to Watch Later" checkbox, and the `hidden` state, are unchanged.
- Remove any debug logging before finishing.
- Append a `CHANGELOG.md` entry and update `plan-webapp.md` for the implementation change.
- No `python -m pytest` run is required (no Python files touched), but run it anyway at the end as a regression check since it's fast and the instructions require confirming tests pass before finishing.

---

### Task 1: Watch Later checkbox in the popup's `exists` state

**Files:**
- Modify: `extension/popup/popup.js:194-208` (the `data.status === 'exists'` branch of `renderState`)
- Modify: `CHANGELOG.md`, `plan-webapp.md`

**Interfaces:**
- Consumes: `POST /api/watch-later/status` → `{in_queue: bool}` (404/`{status:"error"}` if the video isn't in the DB — won't happen here since we're already in the `exists` branch); `POST /api/watch-later/add` → `{status: "added"|"already_in_queue"}`; `POST /api/watch-later/remove` → `{status: "removed"}` or 404 `{status:"error", error:"Not in queue"}`. All three take JSON body `{url}` and already set CORS headers. Existing helper `esc(str)` for title escaping (unused by this task directly, but already used by the surrounding branch).
- Produces: a new `initWatchLaterToggle(viewtubeUrl, tabUrl)` function, called from the `exists` branch after rendering. No other task depends on this — it's the only task in this plan.

- [ ] **Step 1: Add the checkbox markup to the `exists` branch**

In `extension/popup/popup.js`, the current `exists` branch reads:

```javascript
  if (data.status === 'exists') {
    root.innerHTML = `
      <div class="status success" style="margin-bottom:0.5rem">&#10003; ${esc(data.title)}</div>
      <button id="btn-hide" class="action-btn action-btn--danger">Archive</button>
      <label style="display:block;margin-top:0.4rem;font-size:0.8rem;cursor:pointer;color:#aaa">
        <input type="checkbox" id="chk-unbookmark" style="margin-right:0.3rem">
        Also remove browser bookmark
      </label>
    `;
    document.getElementById('btn-hide').addEventListener('click', () => {
      const alsoUnbookmark = document.getElementById('chk-unbookmark').checked;
      doHide(viewtubeUrl, tabUrl, alsoUnbookmark);
    });
    return;
  }
```

Replace it with:

```javascript
  if (data.status === 'exists') {
    root.innerHTML = `
      <div class="status success" style="margin-bottom:0.5rem">&#10003; ${esc(data.title)}</div>
      <button id="btn-hide" class="action-btn action-btn--danger">Archive</button>
      <label style="display:block;margin-top:0.4rem;font-size:0.8rem;cursor:pointer;color:#aaa">
        <input type="checkbox" id="chk-unbookmark" style="margin-right:0.3rem">
        Also remove browser bookmark
      </label>
      <label style="display:block;margin-top:0.4rem;font-size:0.8rem;cursor:pointer;color:#aaa">
        <input type="checkbox" id="chk-watch-later" disabled style="margin-right:0.3rem">
        Add to Watch Later
      </label>
      <div id="wl-error" class="status error" style="margin-top:0.3rem;display:none"></div>
    `;
    document.getElementById('btn-hide').addEventListener('click', () => {
      const alsoUnbookmark = document.getElementById('chk-unbookmark').checked;
      doHide(viewtubeUrl, tabUrl, alsoUnbookmark);
    });
    initWatchLaterToggle(viewtubeUrl, tabUrl);
    return;
  }
```

- [ ] **Step 2: Add `initWatchLaterToggle`**

Add this function above `renderState` in `extension/popup/popup.js` (same file, so it's in scope when `renderState` calls it):

```javascript
async function initWatchLaterToggle(viewtubeUrl, tabUrl) {
  const chk = document.getElementById('chk-watch-later');
  const errBox = document.getElementById('wl-error');

  let inQueue;
  try {
    const resp = await fetch(`${viewtubeUrl}/api/watch-later/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: tabUrl }),
    });
    const data = await resp.json();
    inQueue = !!data.in_queue;
  } catch {
    return; // Leave disabled — unknown state, nothing safe to toggle.
  }

  chk.checked = inQueue;
  chk.disabled = false;

  chk.addEventListener('change', async () => {
    const wantQueued = chk.checked;
    const prevChecked = !wantQueued;
    chk.disabled = true;
    errBox.style.display = 'none';

    const endpoint = wantQueued ? 'add' : 'remove';
    let ok;
    try {
      const resp = await fetch(`${viewtubeUrl}/api/watch-later/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: tabUrl }),
      });
      const data = await resp.json();
      ok = wantQueued
        ? ['added', 'already_in_queue'].includes(data.status)
        : data.status === 'removed';
    } catch {
      ok = false;
    }

    if (!ok) {
      chk.checked = prevChecked;
      errBox.textContent = '✗ Watch Later update failed';
      errBox.style.display = 'block';
    }
    chk.disabled = false;
  });
}
```

- [ ] **Step 3: Manual verification**

Load the extension in Firefox (`about:debugging` → temporary add-on) with the webapp running at `http://localhost:8080`. Using a video already added to ViewTube:

- Open the popup: the "Add to Watch Later" checkbox appears disabled/unchecked briefly, then becomes enabled with the correct checked state (compare against the `/watch-later` page).
- Check it: request fires, checkbox re-enables and stays checked; reopening the popup still shows it checked; the video now appears on `/watch-later`.
- Uncheck it: checkbox re-enables and stays unchecked; the video is removed from `/watch-later`.
- Stop the webapp server, open the popup on a video already in the library: the checkbox stays disabled (status fetch fails), and the popup doesn't otherwise error.
- With the server running again, toggle the checkbox, then immediately stop the server before the request would resolve is impractical to time manually — instead simulate failure by toggling twice quickly to confirm the checkbox disables during the in-flight request (can't be re-clicked) and re-enables after.
- Archive button and "Also remove browser bookmark" checkbox still work exactly as before, independent of the new checkbox.
- The `not_found`-state "Also add to Watch Later" checkbox (different code path, unchanged) still works when adding a brand-new video.

- [ ] **Step 4: Update docs**

- `CHANGELOG.md`: append a dated entry (today's date) — extension popup now lets you add/remove a video from Watch Later at any time via a checkbox in the "already added" state, not just when first adding it. Implication (pro): closes the gap where toggling watch-later required visiting the web UI; (con): the checkbox depends on a live status fetch on every popup open (small extra round trip vs. the add-time-only checkbox, which needed no such check).
- `plan-webapp.md`: in the `**Bookmarklet / quick-add**` paragraph (around the sentence describing the `not_found`-state watch-later checkbox), add a sentence describing the mirror-image `exists`-state behavior: the popup's `exists` state also renders a disabled "Add to Watch Later" checkbox that `initWatchLaterToggle` enables once `POST /api/watch-later/status` resolves (`in_queue` sets the initial checked state), and whose `change` event calls `/api/watch-later/add` or `/api/watch-later/remove` directly and reverts on failure (shown via an inline `#wl-error` line) — no separate "apply" step, unlike the add-time checkbox which is read at click time by `doAdd`.

- [ ] **Step 5: Run the test suite**

Run: `python -m pytest -q`
Expected: PASS (no Python files changed by this plan; this is a regression check).

- [ ] **Step 6: Commit**

```bash
git add extension/popup/popup.js CHANGELOG.md plan-webapp.md
git commit -m "feat(extension): toggle watch-later membership at any time from the popup"
```

---

## Self-Review Notes

- **Spec coverage:** Checkbox markup + disabled-until-loaded behavior ← spec's "New behaviour" and the loading-state clarifying answer (Step 1); `initWatchLaterToggle` status fetch + `change` handler with add/remove/error/revert semantics ← spec's "Changes" section including the edge-case table (race conditions on 409/404 are handled by the existing `ok` boolean logic — 409 `already_in_queue` counts as success on add, 404 on remove counts as failure and reverts) (Step 2); manual verification ← spec's "Testing" section, expanded to cover the specific edge cases in the spec's table (Step 3); doc bookkeeping ← CLAUDE.md's always-update-plans/changelog instructions (Step 4).
- **Type consistency:** `initWatchLaterToggle(viewtubeUrl, tabUrl)` signature matches its call site in Step 1; `chk-watch-later` / `wl-error` element IDs are consistent between the markup (Step 1) and the function that queries them (Step 2).
- **Verified against codebase:** `/api/watch-later/status` returns `{in_queue: bool}` per `webapp/routes.py:766-789`; `/add` returns `{status:"added"}` (200) or `{status:"already_in_queue"}` (409) per `routes.py:704-732`; `/remove` returns `{status:"removed"}` (200) or `{status:"error"}` (404) per `routes.py:735-763` — all confirmed against the current route implementations and their existing tests in `tests/webapp/test_routes.py`. The `exists` branch's current markup (lines 194-208) was read directly from the file before drafting the replacement.

# Extension: Watch Later Toggle at Any Time

**Date:** 2026-08-08
**Status:** Approved

## Summary

Currently the extension popup only offers "Also add to Watch Later" at the moment a video is first added to ViewTube ([[2026-07-02-extension-add-to-watch-later-design]]). There is no way to add or remove a video from the Watch Later queue afterward without visiting the web UI. This adds a checkbox to the popup's `exists` state (video already in ViewTube) that reflects and toggles current Watch Later membership.

## Scope

- **Only file changed:** `extension/popup/popup.js`.
- **No backend changes.** `/api/watch-later/add`, `/api/watch-later/remove`, and `/api/watch-later/status` already exist, are CORS-compliant, and are tested (`tests/webapp/test_routes.py`).
- **Only the `exists` state.** Archived (`hidden`) videos are out of scope — restore first, then toggle from the (now `exists`) popup. The `not_found` state's existing "Also add to Watch Later" checkbox is unchanged.

## Current behaviour

`renderState`'s `data.status === 'exists'` branch renders the video title, an "Archive" button, and an "Also remove browser bookmark" checkbox. No Watch Later affordance.

## New behaviour

```
✓ <video title>
[ Archive ]
☐ Also remove browser bookmark
☐ Add to Watch Later          (disabled until status loads)
```

The new checkbox starts disabled and unchecked. A `POST /api/watch-later/status` call resolves its real state (checked = in queue) and enables it. Toggling it fires `/api/watch-later/add` or `/api/watch-later/remove` immediately — no separate "apply" step, matching the checkbox's implicit semantics as a live reflection of queue membership rather than a pending form field.

## Changes

### `renderState` — `exists` branch

Add the checkbox markup (disabled, unchecked) alongside the existing Archive/unbookmark markup:

```js
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
    <div id="wl-error"></div>
  `;
  document.getElementById('btn-hide').addEventListener('click', () => {
    const alsoUnbookmark = document.getElementById('chk-unbookmark').checked;
    doHide(viewtubeUrl, tabUrl, alsoUnbookmark);
  });
  initWatchLaterToggle(viewtubeUrl, tabUrl);
  return;
}
```

### New `initWatchLaterToggle(viewtubeUrl, tabUrl)`

1. `fetch(POST /api/watch-later/status, { url: tabUrl })`.
   - On success: set `chk.checked = data.in_queue`, `chk.disabled = false`.
   - On failure/unreachable: leave disabled (nothing to toggle safely — we don't know true state).
2. Attach a `change` listener to the checkbox:
   - Disable the checkbox immediately (prevents double-fire while the request is in flight).
   - Read the new `checked` value; call `/api/watch-later/add` if `true`, `/api/watch-later/remove` if `false`.
   - On success (`added`/`already_in_queue` for add; `removed` for remove): re-enable, leave `checked` as the user set it, clear any prior error text.
   - On failure (network error, or unexpected status): revert `checked` to the pre-toggle value, re-enable, and set `#wl-error` to a short inline message (e.g. `✗ Watch Later update failed`), styled like the existing `.status.error` text but sized to fit inline under the checkbox (reuse `.status.error`'s color, no need for a new CSS class — inline style consistent with the other conditional lines in this file).

## Edge cases

| Scenario | Behaviour |
|---|---|
| Watch-later status check fails/unreachable | Checkbox stays disabled; no error shown (matches how other popup fetch failures already fail silently/early-return elsewhere, e.g. `run()`'s catch blocks) |
| Toggle to "add" when already `in_queue` server-side (race) | `/add` returns 409 `already_in_queue`; treated as success, same as the existing add-time flow |
| Toggle to "remove" when already removed server-side (race) | `/remove` returns 404 `Not in queue`; treated as failure — checkbox reverts to checked, error shown, since the popup's local state was stale |
| Rapid re-toggle while a request is in flight | Not possible — checkbox is disabled for the duration of each request |
| Archive clicked while Watch Later checkbox is mid-toggle | Independent controls; no interlock. Archiving does not remove the video from Watch Later server-side (existing behaviour, unchanged by this spec) |

## Testing

No JS test framework exists yet for the extension (`background.js`/`content.js`/`popup.js` are all currently untested — tracked as an open TODO item). This change will be verified manually: load the unpacked extension, open the popup on a video already in ViewTube, confirm the checkbox loads checked/unchecked correctly, toggle both directions, and confirm state persists correctly on the `/watch-later` page and on popup reopen.

# Extension: Add to Watch Later on Video Add

**Date:** 2026-07-02
**Status:** Approved

## Summary

When the extension popup is opened on a YouTube video not yet in ViewTube, the popup should show an "Add to ViewTube" button plus an optional "Also add to Watch Later" checkbox before firing the add action. This mirrors the existing "Also remove browser bookmark" checkbox pattern on the Archive flow.

## Scope

- **Only file changed:** `extension/popup/popup.js`
- **No backend changes.** `/api/watch-later/add` already exists and handles the requirement that the video must be in the DB first.
- **Strictly the add-new-video flow.** The `exists` state (already in ViewTube) is not changed.

## Current behaviour

When `checkStatus` returns `not_found`, `renderState` immediately calls `doAdd()` with no intermediate UI. The add fires automatically on popup open.

## New behaviour

`not_found` renders a prompt instead of firing immediately:

```
[ Add to ViewTube ]
☐ Also add to Watch Later
```

The user clicks "Add to ViewTube" to trigger the add. The checkbox state is read at click time and passed to `doAdd`.

## Changes

### `renderState` — `not_found` branch

Replace the immediate `doAdd()` call with HTML rendering and a click handler:

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

### `doAdd` — `alsoWatchLater` parameter

Signature changes to `doAdd(viewtubeUrl, tabUrl, tabTitle, alsoWatchLater = false)`.

After the existing parallel bookmark + ViewTube calls resolve, if ViewTube succeeded and `alsoWatchLater` is true, fire `/api/watch-later/add` sequentially (must happen after video is in DB).

#### Success path (bookmark + ViewTube both ok)

- Auto-close after 1.5s is unchanged.
- If watch later was requested and succeeded: show `+ Added to Watch Later` as a secondary line below the title.
- If watch later was requested and failed: show `✗ Watch Later failed` as a secondary line. Still auto-closes (watch later failure does not block success).

#### Partial/error path (bookmark or ViewTube failed)

- Existing behaviour unchanged.
- If watch later was requested, append a `✓ Added to Watch Later` or `✗ Watch Later failed` line to the existing error lines.

## Sequencing

Watch-later call is sequential (after add), not parallel, because `/api/watch-later/add` returns 404 if the video is not yet in the DB.

## Edge cases

| Scenario | Behaviour |
|---|---|
| Watch later requested, video already in queue (409) | Treated as success (`already_in_queue` → no error shown) |
| Watch later requested, network error | Shown as `✗ Watch Later failed`, popup still auto-closes |
| Watch later not requested | No change from current behaviour |

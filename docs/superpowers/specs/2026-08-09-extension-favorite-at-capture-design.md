# Extension: Mark Favorite at Capture Time

**Date:** 2026-08-09
**Status:** Approved

## Summary

When the extension popup is opened on a YouTube video not yet in ViewTube, add a second opt-in checkbox — "Also mark as favorite" — alongside the existing "Also add to Watch Later" checkbox ([[2026-07-02-extension-add-to-watch-later-design]]), so a standout video can be starred the moment it's captured rather than requiring a later trip to the web UI's ★ button.

## Scope

- **Backend:** one new route, `POST /api/favourite/add`. No new DB function — reuses `set_favourite(conn, video_id, value)` (`webapp/db/videos.py:66`), the same function the existing same-origin `/videos/<id>/favourite` toggle route already calls.
- **Extension:** `extension/popup/popup.js`, the `not_found` branch of `renderState` and `doAdd` only.
- **Not in scope:** toggling favorite status on a video already in ViewTube (the `exists` popup state is untouched) — deliberately deferred, matching the watch-later feature's own history of starting capture-time-only before later gaining an anytime toggle. If wanted later, it's a separate TODO/spec.

## Backend: `POST /api/favourite/add`

Mirrors `/api/watch-later/add` (`webapp/routes.py:704-732`) exactly in shape:

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

Differences from `/api/watch-later/add`: no 409 case. Watch-later is a queue with a uniqueness constraint (already-queued is a distinct, reportable state); `is_favourite` is a plain boolean column — setting it `True` when already `True` is a no-op success, not a conflict. Always `{"status": "added"}` on success.

## Extension: `popup.js`

### `not_found` branch of `renderState`

Add the second checkbox under the existing watch-later one:

```js
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

### `doAdd` — new `alsoFavorite` parameter

Signature becomes `doAdd(viewtubeUrl, tabUrl, tabTitle, alsoWatchLater = false, alsoFavorite = false)`.

After the existing parallel bookmark + ViewTube-add calls resolve and ViewTube succeeded, fire watch-later and favorite as a second parallel batch (both depend only on the video now existing in the DB, not on each other):

```js
async function postJson(url, body) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return resp.json();
}

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
```

(`null` means "not requested," distinct from `true`/`false`, exactly as the existing `watchLaterOk` variable already does — this just extends the same pattern to a second flag.)

#### Success path (bookmark + ViewTube both ok)

- Auto-close after 1.5s unchanged.
- Existing watch-later line unchanged.
- If favorite was requested and succeeded: show `★ Marked as favorite` as a secondary line.
- If favorite was requested and failed: show `✗ Favorite failed` as a secondary line. Still auto-closes (matches watch-later's non-blocking failure behavior).

#### Partial/error path (bookmark or ViewTube failed)

- Existing behavior unchanged.
- If favorite was requested, append a `✓ Marked as favorite` or `✗ Favorite failed` line to the existing error lines, same as watch-later's existing handling.

## Edge cases

| Scenario | Behaviour |
|---|---|
| Favorite requested, video already favorited (idempotent) | Always `{"status":"added"}` — no distinct "already" case needed, unlike watch-later |
| Favorite requested, network error | Shown as `✗ Favorite failed`, popup still auto-closes |
| Favorite requested, ViewTube add itself failed | Favorite call never fires (mirrors watch-later: `if (alsoWatchLater && viewtubeOk)` gating extends to `alsoFavorite && viewtubeOk`) |
| Favorite not requested | No change from current behavior |
| Both watch-later and favorite requested | Both fire in parallel; independent success/failure, independent report lines |

## Testing

- `tests/webapp/test_routes.py`: new `TestApiFavouriteAdd` class — happy path (video exists, becomes favorited), idempotent re-add, 404 for unknown video, 400 for non-YouTube URL, CORS header present, OPTIONS preflight. Mirrors the existing `TestApiWatchLaterAdd` structure.
- `popup.js`: manual verification only (no JS test framework, tracked separately in `TODO.md`) — open the popup on a new video, check both boxes, confirm both watch-later and favorite state on the web UI after add; verify unchecked boxes leave both features untouched; verify a stopped-server scenario still reports failures without crashing the popup.

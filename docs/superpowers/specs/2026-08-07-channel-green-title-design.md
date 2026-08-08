# Green Channel Title on Captured Channel Pages — Design

**Date:** 2026-08-07
**Status:** Approved
**Scope:** The browser extension's content script colors a YouTube channel page's header title **green** when that channel is already tracked in ViewTube — mirroring the existing captured-video green title. Out of scope: highlighting channel names anywhere other than the channel's own page (owner links under videos, search/home feeds), and any "hidden/archived" (red) state for channels.

---

## Summary

On a `/watch` page, `extension/content/content.js` already paints the current video's `<h1>` title green (`#388e3c`) when `/api/status` reports the video is tracked (`exists`), or red when `hidden`. This extends the same idea to channel pages: on `/@handle`, `/channel/UC…`, `/c/name`, or `/user/name`, color the channel-header title green when `/api/channel/status` reports the channel is tracked. The status endpoint (`GET /api/channel/status`) already exists and returns `{status: "exists", channel_name}` or `{status: "not_found"}`. Channels have no hidden state, so this is **green-only** — no red case.

---

## Section 1: Manifest

Broaden the content script's `matches` (currently only `https://www.youtube.com/watch*`) so the script is injected on channel pages too:

```json
"matches": [
  "https://www.youtube.com/watch*",
  "https://www.youtube.com/@*",
  "https://www.youtube.com/channel/*",
  "https://www.youtube.com/c/*",
  "https://www.youtube.com/user/*"
]
```

No new permissions are needed. YouTube is a SPA: once the script is live it re-runs on every `yt-navigate-finish` (already wired), so navigating between video and channel pages works; the broadened `matches` only ensures the script is injected when a channel page is loaded directly.

---

## Section 2: Background script

Add one message handler to `extension/background.js`, parallel to the existing `fetchStatus`:

```javascript
if (msg.action === 'fetchChannelStatus') {
  return getViewtubeUrl().then(vtUrl =>
    fetch(`${vtUrl}/api/channel/status?url=${encodeURIComponent(msg.url)}`)
      .then(r => r.json())
      .catch(() => ({ status: 'error' }))
  );
}
```

No backend changes — `GET /api/channel/status` already validates the URL against the channel regex and looks up by `channel_url`/`source_url`.

---

## Section 3: Content script (`content.js`)

- **Channel detection.** Add `YT_CHANNEL_RE` (the same pattern used by `popup.js`, kept in sync with `crawler/models.py`) and a `channelUrlFrom(match)` helper that rebuilds the canonical base URL (`https://www.youtube.com/@handle`, `/channel/UC…`, `/c/name`, `/user/name`), stripping sub-tab suffixes (`/videos`, `/featured`, …) and query strings so the URL sent to the backend is stable.

- **`checkCurrentChannel()`** mirrors `checkCurrentVideo()`:
  1. Clear any color previously applied to the channel title element (SPA navigation reuses the DOM).
  2. If the current URL isn't a channel URL, return.
  3. `waitFor` the channel-title element (see selector note below).
  4. Guard against SPA navigation racing: re-check that the URL still resolves to the same canonical channel URL before and after the await.
  5. Send `{action: 'fetchChannelStatus', url: <canonicalChannelUrl>}` to the background.
  6. If `data.status === 'exists'`, set the title element's `style.color = '#388e3c'`. Otherwise do nothing (no red case).

- **`run()` branching.** Currently `run()` returns immediately unless the URL has a video id. Change it to:
  1. If `extractId(location.href)` → existing video flow (`checkCurrentVideo()` + `watchRelated()`).
  2. Else if the URL matches `YT_CHANNEL_RE` → `checkCurrentChannel()`.
  3. Else nothing.

- **Channel title selector (the fragile part).** YouTube's channel-header title lives in the redesigned "page header." Use a short ordered list of fallback selectors targeting the header title element, e.g.:
  - `yt-page-header-renderer h1` / `.page-header-view-model-wiz__page-header-title`
  - `#channel-header #text` / `ytd-channel-name #text` (older layouts)

  A `_channelTitle()` helper returns the first match. This selector is version-dependent and is the single most likely thing to need adjustment after a live check — flagged for manual verification, not machine-verifiable here.

---

## Section 4: Decisions & known limitations

- **URL-based match, not `channel_id`.** `/api/channel/status` matches on stored `channel_url`/`source_url` string equality (same as the popup pre-check). A channel tracked under `/channel/UC…` but viewed via `/@handle` (or vice-versa) may show **no green** even though it is tracked. Worst case is a missing convenience signal — never a wrong action, never a false green.
- **Green-only.** Channels have no hidden/archived concept, so there is no red state (unlike the video title).
- **Channel page only.** Channel names shown elsewhere (owner link under a video, search/home feeds) are out of scope; no batch channel-status endpoint is introduced.
- **No automated extension tests.** The extension has no JS test suite; verification is manual/in-browser (consistent with the bookmark-channel and spinner features). The DOM selector especially must be confirmed on a live channel page.

---

## File Map

| File | Action |
|---|---|
| `extension/manifest.json` | Add channel URL patterns to the content script `matches` |
| `extension/background.js` | Add the `fetchChannelStatus` message handler |
| `extension/content/content.js` | Add `YT_CHANNEL_RE`, `channelUrlFrom`, `_channelTitle`, `checkCurrentChannel`; branch `run()` |
| `CHANGELOG.md` | Append entry |
| `plan-extension.md` | Document the channel green-title behaviour |
| `TODO.md` | Note the feature if a matching item exists (else no change) |

---

## Testing Strategy

- **No automated tests** (extension has none). `node --check extension/content/content.js` and `node --check extension/background.js` to confirm the files parse.
- **Manual (pending a human):** Load the extension in Firefox with the webapp running. On a channel page for a **tracked** channel, the header title turns green; on an **untracked** channel it stays default; navigating (SPA) from a video to a channel page and between channels updates correctly; a `/watch` video page still behaves exactly as before. Confirm/adjust the channel-title selector against the live DOM.

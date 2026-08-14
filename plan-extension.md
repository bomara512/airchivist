# ViewTube — Browser Extension Plan

## Goal

A Firefox extension that, with one toolbar button click on a YouTube video page:

1. Creates a Firefox bookmark for the current video (title + URL)
2. Posts the URL to ViewTube's `/api/add` endpoint

The extension replaces the need for both the manual Ctrl+D bookmark and the existing bookmarklet. It surfaces as a toolbar icon that is active only on YouTube video pages.

---

## Approach

**Toolbar button with auto-run popup.** Clicking the button opens a small popup that immediately initiates both saves (no second "Save" click). The popup shows status while the requests are in-flight, then a success or error message. It auto-closes on success.

### Why not intercept normal bookmarks?

`browser.bookmarks.onCreated` fires whenever any bookmark is created, including ones from Ctrl+D, the star button, and other extensions. Listening on this event would silently add every YouTube bookmark to ViewTube, which is likely desirable but also surprising. It could be added as an option later ("Also watch for bookmarks made with Ctrl+D") but should not be the default.

### Why not a notification instead of a popup?

Firefox notifications (`browser.notifications`) require the `notifications` permission and produce a system notification, which is heavier and harder to dismiss. A popup is lighter, stays on screen only while open, and can show incremental status without any extra OS chrome.

---

## File Structure

```
viewtube-extension/
├── manifest.json
├── background.js           # optional: bookmark-watcher feature (future)
├── popup/
│   ├── popup.html
│   ├── popup.js            # core logic: create bookmark + call api/add
│   └── popup.css
└── options/
    ├── options.html        # settings page: ViewTube URL, bookmark folder
    └── options.js
```

No build step. All plain JavaScript. The extension can be loaded via `about:debugging` → "Load Temporary Add-on" during development, and signed/packaged via `web-ext` for distribution.

---

## Manifest (V2)

Firefox supports both MV2 and MV3; MV2 is used here because Firefox's MV3 support is still catching up (no `declarativeNetRequest` equivalents for some APIs). This is a local-only extension so Chrome compatibility is not a goal.

```json
{
  "manifest_version": 2,
  "name": "ViewTube",
  "version": "1.0",
  "description": "Bookmark YouTube videos to Firefox and ViewTube in one click",
  "permissions": [
    "bookmarks",
    "activeTab",
    "storage"
  ],
  "browser_action": {
    "default_icon": {
      "48": "icons/icon-48.png"
    },
    "default_popup": "popup/popup.html",
    "default_title": "Save to ViewTube"
  },
  "options_ui": {
    "page": "options/options.html",
    "browser_style": true
  }
}
```

**Permissions rationale:**

| Permission | Why |
|---|---|
| `bookmarks` | Create Firefox bookmarks via `browser.bookmarks.create` |
| `activeTab` | Read the current tab's URL and title without a broad host permission |
| `storage` | Persist user settings (ViewTube URL, target bookmark folder) |

No `host_permissions` block is needed because `activeTab` grants temporary access to the current page URL, and the fetch to `localhost:8080` is a regular cross-origin request allowed by the CORS headers already on `/api/add`.

---

## Core Flow

```
User on youtube.com/watch?v=... → clicks toolbar button
  → popup opens
  → popup.js reads tab URL + title via browser.tabs.query
  → validate: is this a YouTube video URL? (check yt ID regex)
       if not: show "Not a YouTube video" and stop
  → read settings from browser.storage.local
       (viewtubeUrl, bookmarkFolderId)
  → in parallel:
       browser.bookmarks.create({ title, url, parentId })
       fetch(viewtubeUrl + '/api/add', { method: 'POST', body: {url} })
  → on both resolved:
       show "✓ Saved: <title>" for 1.5 s, then close popup
  → on any error:
       show error message, leave popup open so user can read it
```

Both saves run in parallel (`Promise.all`) so the popup is responsive even if one is slow. If ViewTube's `/api/add` returns `"status": "exists"`, that is treated as success (video was already saved; `record_visit` is called server-side to log the re-visit).

---

## Options Page

Two settings, persisted via `browser.storage.local`:

| Setting | Default | Notes |
|---|---|---|
| ViewTube URL | `http://localhost:8080` | Displayed as a text input; no trailing slash |
| Bookmark folder | "ViewTube" (auto-created) | Shown as a folder picker or text input; if blank, saves to Bookmarks Toolbar |

On first run (no `bookmarkFolderId` in storage), the extension creates a "ViewTube" folder in Other Bookmarks and saves its ID. Subsequent bookmarks go into that folder, keeping ViewTube saves distinct from regular browser bookmarks.

---

## YouTube Page Detection

The toolbar icon should only be fully active on YouTube video pages. Two options:

**Option A — Validate in popup.** Always show the popup; display an error if the URL is not a YouTube video. Simpler to implement but the icon looks the same on all pages.

**Option B — `content_scripts` + `pageAction`.** A content script detects YouTube video pages and shows/hides a `pageAction` button (shows only on matching pages). Cleaner UX but more complexity; `pageAction` is deprecated in MV3.

**Recommendation: Option A for Phase 1.** The icon is always visible, but the popup shows "Not a YouTube video" clearly. If the always-visible icon is annoying, add Option B in Phase 2.

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Not a YouTube video URL | Popup shows "Not a YouTube video" |
| ViewTube not running (fetch fails) | Popup shows "ViewTube unreachable — is it running at `<url>`?". Firefox bookmark is still created. |
| ViewTube returns `status: error` | Popup shows the error message from the response |
| Bookmark creation fails (duplicate?) | `browser.bookmarks.create` does not deduplicate; a second bookmark is created. This is Firefox's default behavior. |
| Settings not yet configured | Uses defaults (`localhost:8080`, auto-created folder) |

---

## Implementation Phases

### Phase 1 — Core (working extension) ✅ IMPLEMENTED (2026-05-29)

Files in `extension/`:
- `manifest.json` — MV2, permissions: `bookmarks`, `activeTab`, `storage`
- `icons/icon.svg` — red rounded square with white V stroke
- `popup/popup.html` — minimal shell, status div, loads popup.js
- `popup/popup.css` — dark theme matching ViewTube; `.success` (green), `.partial` (orange), `.error` (red)
- `popup/popup.js`:
  - `getOrCreateFolder()` — finds or creates "ViewTube" bookmark folder; caches ID in `browser.storage.local`; validates cached ID still exists on each open
  - `run()` — validates YouTube URL (`/(?:v=|youtu\.be\/)([A-Za-z0-9_-]{11})/`); loads folder + settings in parallel; runs `browser.bookmarks.create` and `fetch /api/add` in parallel via `Promise.allSettled`; shows per-action status on partial failure; auto-closes after 1.5 s on full success
  - ViewTube `status: "exists"` treated as success (visit is still recorded server-side)

### Phase 2 — Options

- `options/options.html` + `options.js`
  - ViewTube URL field
  - Bookmark folder picker (lists existing bookmark folders)
  - "Test connection" button that POSTs a dummy request and shows the response

### Phase 3 — In-page status indicators ✅ IMPLEMENTED (2026-06-11)

Content script (`extension/content/content.js`) injected on `youtube.com/watch*`:

**Current video badge** — after the video title (`#above-the-fold #title`), a colored pill shows:
- `✓ In ViewTube` (green) if the video is saved
- `⊘ Hidden in ViewTube` (red) if it's hidden
- Nothing if not found (no noise for unsaved videos)

**Related video badges** — for each `ytd-compact-video-renderer` in the side panel, a smaller version of the same badge is prepended into the `#meta` text area (below the video title in the card). A `MutationObserver` on `#secondary` catches cards loading after the initial page render.

**Navigation** — YouTube is a SPA; the script re-runs on every `yt-navigate-finish` event (YouTube's own navigation hook). Fallback `DOMContentLoaded` listener handles initial page load.

**Batch endpoint** — `POST /api/status/batch` (server-side) accepts `{"ids": [...]}` (max 50), returns `{"videoId": "exists"|"hidden"|"not_found"}` in a single SQL query. Used by the related-video scan.

**Manifest changes:**
- Version bumped to `1.1`
- Added `"http://localhost:*/*"` permission so the content script can fetch from the local ViewTube server
- Added `content_scripts` block

**Known limitation:** YouTube's DOM element names change occasionally; if selectors break after a YouTube update, `ytd-compact-video-renderer a#thumbnail` and `#above-the-fold #title` are the ones to re-check.

### Phase 3b — Channel page green title ✅ IMPLEMENTED (2026-08-07)

The content script now also injects on channel pages, not just `/watch*` — `content_scripts.matches` in `manifest.json` was broadened to `https://www.youtube.com/watch*`, `/@*`, `/channel/*`, `/c/*`, and `/user/*`.

**Current channel title** — on a channel page, the header title (`CHANNEL_TITLE_SELECTOR`, a comma-separated list of known YouTube channel-header selectors) is colored green (`TITLE_COLOR.exists`) if the channel is already tracked in ViewTube. Unlike video titles, there is no red/hidden case — channels have no "hidden" state, so the title is either green or left at its default color.

`content.js` gained `YT_CHANNEL_RE` (kept byte-identical to the copy in `popup.js`, itself synced to `crawler/models.py`'s `_YT_CHANNEL_RE`) and `channelUrlFrom()` to derive the canonical channel URL, plus `checkCurrentChannel()` which mirrors `checkCurrentVideo()`'s structure: it re-checks the URL after each `await` so a fast SPA navigation away from the channel (or to a different channel) can't leave a stale green title behind.

`run()` now branches on the URL: video-ID URLs still take the existing `checkCurrentVideo`/`watchRelated` path unchanged; otherwise, if the URL matches `YT_CHANNEL_RE`, `checkCurrentChannel()` runs instead. The existing `yt-navigate-finish`/`DOMContentLoaded` wiring re-triggers `run()` automatically, so it re-branches correctly when navigating between video and channel pages.

**New background action** — `fetchChannelStatus` (in `background.js`, sibling to `fetchStatus`/`fetchStatusBatch`) calls the existing `GET /api/channel/status?url=<canonicalChannelUrl>` and returns `{status: "exists", channel_name}` | `{status: "not_found"}` | `{status: "error"}`. No backend changes were needed.

**Known limitation:** `CHANNEL_TITLE_SELECTOR` is a best-effort list of selectors covering known YouTube channel-header DOM shapes as of this writing; like the video-title selectors above, it is DOM-version-dependent and is the first thing to check/extend if the green title stops appearing after a YouTube layout change. Also, since the status check is URL-based, a channel viewed via a URL form different from the one it was stored under will not light up (a missing signal, not a false positive).

### Phase 4 — Bookmark watcher (optional)

- `background.js` listens to `browser.bookmarks.onCreated`
- When a new bookmark's URL matches a YouTube video, post it to ViewTube automatically
- Guarded by a toggle in the options page (off by default to avoid surprises)

---

## Development Workflow

```bash
# Install web-ext (Mozilla's official tool)
npm install -g web-ext

# Run in Firefox with auto-reload
cd viewtube-extension
web-ext run --firefox=/Applications/Firefox.app/Contents/MacOS/firefox

# Build a signed .xpi for permanent installation
web-ext build
web-ext sign --api-key=... --api-secret=...   # requires AMO developer account
```

For local use without signing, Firefox Developer Edition or Nightly allow unsigned extensions via `about:config → xpinstall.signatures.required = false`.

---

## Open Questions

1. **Should the Firefox bookmark be created even when ViewTube fails?** Current plan: yes — the bookmark is the "ground truth" fallback. ViewTube is bonus metadata.
2. **Bookmark folder hierarchy**: Should saves go into a date-organized subfolder (e.g. `ViewTube/2026-05`)? Probably overkill; a flat "ViewTube" folder is fine at personal-library scale.
3. **What if the user is watching a YouTube short or channel page?** The URL regex will reject non-video URLs cleanly. Shorts URLs (`/shorts/<id>`) should probably be supported — the same regex can be extended.
4. **Icon design**: A simple red "V" or the YouTube play-button shape with a red accent would signal the extension's purpose clearly.

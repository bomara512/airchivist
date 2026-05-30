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

### Phase 1 — Core (working extension)

- `manifest.json`
- `popup/popup.html` + `popup.js` + `popup.css`
  - Reads tab URL/title
  - Validates YouTube video URL using the same regex pattern as the server (`/[?&]v=([A-Za-z0-9_-]{11})/` or `youtu.be/...`)
  - Creates Firefox bookmark (in a "ViewTube" auto-created folder)
  - POSTs to `/api/add`
  - Shows status

### Phase 2 — Options

- `options/options.html` + `options.js`
  - ViewTube URL field
  - Bookmark folder picker (lists existing bookmark folders)
  - "Test connection" button that POSTs a dummy request and shows the response

### Phase 3 — Active-page indicator (optional)

- Dim the toolbar icon on non-YouTube-video pages via a content script + `browser.browserAction.setIcon` / `setTitle`
- Or switch to `pageAction` (icon appears in the URL bar, only on YouTube video pages)

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
2. **Bookmark folder hierarchy**: Should saves go into a date-organised subfolder (e.g. `ViewTube/2026-05`)? Probably overkill; a flat "ViewTube" folder is fine at personal-library scale.
3. **What if the user is watching a YouTube short or channel page?** The URL regex will reject non-video URLs cleanly. Shorts URLs (`/shorts/<id>`) should probably be supported — the same regex can be extended.
4. **Icon design**: A simple red "V" or the YouTube play-button shape with a red accent would signal the extension's purpose clearly.

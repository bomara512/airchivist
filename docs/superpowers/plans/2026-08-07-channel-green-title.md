# Green Channel Title on Captured Channel Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On a YouTube channel page, color the channel-header title green when that channel is already tracked in ViewTube — mirroring the existing captured-video green title.

**Architecture:** Three coupled edits in the extension: (1) broaden the content script's manifest `matches` to channel URLs; (2) add a `fetchChannelStatus` message handler to `background.js` that calls the existing `GET /api/channel/status`; (3) add channel detection + `checkCurrentChannel()` to `content.js` and branch `run()`. Green-only (no red — channels have no hidden state). No backend changes. The extension has no JS test suite, so verification is `node --check` + manual browser testing.

**Tech Stack:** Vanilla-JS Firefox WebExtension (no build step); the ViewTube Flask backend is unchanged.

## Global Constraints

- Reuse the existing `TITLE_COLOR.exists` (`#388e3c`) constant — do not hard-code a new green.
- Keep `YT_CHANNEL_RE` byte-identical to the copy in `extension/popup/popup.js` (which is itself kept in sync with `crawler/models.py`); carry the same "keep in sync" comment.
- Green-only: apply color solely when `status === 'exists'`; never a red/hidden case for channels.
- Match the surrounding style of `content.js` (existing `waitFor`, `checkCurrentVideo`, SPA-navigation guards).
- No new manifest permissions; localhost fetch is already granted and the fetch happens in the background script.
- Remove any debug logging before finishing.
- Append a `CHANGELOG.md` entry and update `plan-extension.md`. Only touch `TODO.md` if a matching open item exists.

---

### Task 1: Green channel title (manifest + background + content script)

**Files:**
- Modify: `extension/manifest.json`
- Modify: `extension/background.js`
- Modify: `extension/content/content.js`
- Modify: `CHANGELOG.md`, `plan-extension.md`

**Interfaces:**
- Consumes: `GET /api/channel/status?url=<canonicalChannelUrl>` → `{status: "exists", channel_name}` | `{status: "not_found"}` | `{status: "error"}` (already implemented); the existing `waitFor`, `extractId`, `TITLE_COLOR` in `content.js`; `getViewtubeUrl` in `background.js`.
- Produces: user-facing behaviour only (no code interface consumed by later tasks).

- [ ] **Step 1: Broaden the content-script matches**

In `extension/manifest.json`, change the content script's `matches` array (currently only the watch pattern) to:

```json
      "matches": [
        "https://www.youtube.com/watch*",
        "https://www.youtube.com/@*",
        "https://www.youtube.com/channel/*",
        "https://www.youtube.com/c/*",
        "https://www.youtube.com/user/*"
      ],
```

Leave `"js": ["content/content.js"]` and `"run_at": "document_idle"` unchanged.

- [ ] **Step 2: Add the `fetchChannelStatus` background handler**

In `extension/background.js`, inside the `browser.runtime.onMessage.addListener((msg) => { ... })`, add a third branch after the `fetchStatusBatch` block (mirroring `fetchStatus`):

```javascript
  if (msg.action === 'fetchChannelStatus') {
    return getViewtubeUrl().then(vtUrl =>
      fetch(`${vtUrl}/api/channel/status?url=${encodeURIComponent(msg.url)}`)
        .then(r => r.json())
        .catch(() => ({ status: 'error' }))
    );
  }
```

- [ ] **Step 3: Add channel detection + title lookup to `content.js`**

At the top of `extension/content/content.js`, below the existing `const YT_ID_RE = ...` line, add (mirroring `popup.js`):

```javascript
// Channel-URL detection. Keep in sync with crawler/models.py _YT_CHANNEL_RE.
const YT_CHANNEL_RE = /youtube\.com\/(channel\/UC[A-Za-z0-9_-]+|(?:c|user)\/[^/?#]+|@[^/?#]+)/;

const CHANNEL_TITLE_SELECTOR =
  'yt-page-header-renderer h1, .page-header-view-model-wiz__page-header-title, ' +
  '#channel-header #text, ytd-channel-name #text';

function channelUrlFrom(match) {
  // match[1] is the canonical path segment (@handle, channel/UC…, c/name, user/name).
  return `https://www.youtube.com/${match[1]}`;
}

function _channelTitle() {
  return document.querySelector(CHANNEL_TITLE_SELECTOR);
}
```

Then add `checkCurrentChannel()` (place it near `checkCurrentVideo`, mirroring its structure and SPA-navigation guards):

```javascript
async function checkCurrentChannel() {
  const prev = _channelTitle();
  if (prev) prev.style.color = '';

  const m = YT_CHANNEL_RE.exec(location.href);
  if (!m) return;
  const channelUrl = channelUrlFrom(m);

  const titleEl = await waitFor(CHANNEL_TITLE_SELECTOR);
  if (!titleEl) return;
  // Bail if SPA navigation moved to a different channel while we waited.
  const m2 = YT_CHANNEL_RE.exec(location.href);
  if (!m2 || channelUrlFrom(m2) !== channelUrl) return;

  try {
    const data = await browser.runtime.sendMessage({
      action: 'fetchChannelStatus', url: channelUrl,
    });
    if (data.status !== 'exists') return;
    const el = _channelTitle();
    const m3 = YT_CHANNEL_RE.exec(location.href);
    if (el && m3 && channelUrlFrom(m3) === channelUrl) {
      el.style.color = TITLE_COLOR.exists;
    }
  } catch { /* ViewTube unreachable */ }
}
```

- [ ] **Step 4: Branch `run()`**

Replace the current `run()`:

```javascript
function run() {
  if (!extractId(location.href)) return;
  checkCurrentVideo();
  watchRelated();
}
```

with:

```javascript
function run() {
  if (extractId(location.href)) {
    checkCurrentVideo();
    watchRelated();
    return;
  }
  if (YT_CHANNEL_RE.test(location.href)) {
    checkCurrentChannel();
  }
}
```

The existing `yt-navigate-finish` / `DOMContentLoaded` wiring is unchanged, so SPA navigation between video and channel pages re-triggers `run()` automatically.

- [ ] **Step 5: Syntax-check both scripts**

Run:
```bash
node --check extension/content/content.js
node --check extension/background.js
```
Expected: both exit 0 with no output.

- [ ] **Step 6: Manual verification (pending a human — cannot be run headless)**

Load the extension in Firefox (`about:debugging` → temporary add-on) with the webapp running at `http://localhost:8080`, then confirm:
- On a channel page (`/@handle`) for a **tracked** channel, the header channel title renders green (`#388e3c`).
- On an **untracked** channel, the title keeps its default color.
- Navigating (SPA) from a `/watch` video to a channel page, and between two channel pages, updates the green correctly (no stale color carried over).
- A normal `/watch` video page still greens/reds the video title exactly as before.
- **Confirm/adjust `CHANNEL_TITLE_SELECTOR`** against the live channel-header DOM — this selector is the most likely thing to need tuning; if the title doesn't color, inspect the channel-name element and add/adjust a selector in the list.

Because the selector is DOM-version-dependent, an implementer/agent must NOT claim the visual checks passed — report them as PENDING a human.

- [ ] **Step 7: Update docs**

- `CHANGELOG.md`: append a dated (2026-08-07) entry — the content script now colors a channel page's header title green when the channel is tracked (via a new `fetchChannelStatus` → `/api/channel/status`), mirroring the captured-video title; green-only since channels have no hidden state; content-script `matches` broadened to channel URLs. Implication: at-a-glance "already tracked" signal without opening the popup. Trade-off: the status check is URL-based, so a channel viewed via a different URL form than it was stored under may not light up (a missing signal, never a false green); and the channel-title selector is DOM-version-dependent and may need maintenance.
- `plan-extension.md`: extend the content-script section (around the existing "injected on youtube.com/watch*" description) to document the channel green-title behaviour, the broadened matches, and the `fetchChannelStatus` action.
- `TODO.md`: only if a matching open item exists (there is no dedicated green-title item in the creator-pages list — if so, leave `TODO.md` unchanged).

- [ ] **Step 8: Commit**

```bash
git add extension/manifest.json extension/background.js extension/content/content.js CHANGELOG.md plan-extension.md
git commit -m "feat(extension): green channel title on captured channel pages"
```

---

## Self-Review Notes

- **Spec coverage:** manifest matches (Step 1) ← Section 1; `fetchChannelStatus` handler (Step 2) ← Section 2; `YT_CHANNEL_RE`/`channelUrlFrom`/`_channelTitle`/`checkCurrentChannel` + `run()` branch (Steps 3–4) ← Section 3; green-only, URL-match limitation, channel-page-only, no-tests (Section 4) all honored — green applied solely on `status === 'exists'`, reusing `TITLE_COLOR.exists`.
- **Type/name consistency:** `channelUrlFrom(match)` returns the string passed to `fetchChannelStatus`; the background handler reads `msg.url` and returns `{status}`; `checkCurrentChannel` reads `data.status`. `CHANNEL_TITLE_SELECTOR` is defined once and reused by `_channelTitle()`, `checkCurrentChannel`'s `waitFor`, and the initial clear. `YT_CHANNEL_RE` matches the `popup.js` copy verbatim.
- **Verified against codebase:** `waitFor(selector)` uses `querySelector`, which accepts a comma-separated selector list; `TITLE_COLOR.exists === '#388e3c'` already exists; `GET /api/channel/status` already validates + looks up by `channel_url`/`source_url`; `background.js` has `getViewtubeUrl()` and the `onMessage` listener with `fetchStatus`/`fetchStatusBatch` siblings; the existing `run()` is gated on `extractId`. The DOM title selector is the one item that cannot be verified without a live page — flagged in Step 6.

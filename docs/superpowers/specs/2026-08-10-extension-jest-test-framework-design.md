# Extension: Jest Test Framework + doAdd/initWatchLaterToggle Coverage

**Date:** 2026-08-10
**Status:** Approved

## Summary

The Firefox extension (`extension/`) has no automated tests — every feature added to `popup.js` (add-time watch-later checkbox, exists-state watch-later toggle, add-time favorite checkbox) has so far been verified by manual browser use or code-reading trace-throughs only, tracked as an open gap at `TODO.md:72`. This closes that gap: stand up Jest + jsdom, make `popup.js`'s functions importable without a bundler via a guarded `module.exports`, and write the first real test suite covering `doAdd` and `initWatchLaterToggle` — the two pieces of non-trivial async/checkbox logic shipped so far.

This also retroactively satisfies the manual-verification gap flagged by the favorite-at-capture feature's final review (`docs/superpowers/plans/2026-08-09-extension-favorite-at-capture.md`): automated assertions on `doAdd`'s actual behavior are stronger, more durable evidence than the one-off code-reading trace-through that shipped in that plan's Task 2.

## Scope

- **New root-level files:** `package.json` (devDependencies only — Jest, `jest-environment-jsdom`), `tests/extension/setup.js` (shared `browser` global stub), `tests/extension/popup.test.js`.
- **Modified:** `extension/popup/popup.js` — only the final ~5 lines (the `run().catch(...)` auto-invocation), wrapped in a guard that adds a `module.exports` branch. No other line of `popup.js` changes; no behavior change in the shipped extension.
- **Not in scope:** `background.js`, `content.js` (still untested — `TODO.md:72` gets updated to reflect `popup.js` is now covered, but the other two files stay open items); any bundler/build step; any `web-ext`/real-Firefox E2E automation (a possible future layer, not this pass); testing `doAddChannel`, `doHide`, `doRestore`, `doDelete`, `renderChannelState`, or `run()` itself (only `doAdd` and `initWatchLaterToggle` — the two functions with non-trivial async/checkbox logic — are covered in this pass).

## Making `popup.js` testable

`popup.js` is loaded today as a classic (non-module) script via `<script src="popup.js">` in `popup.html`, and its last lines unconditionally invoke `run()`:

```js
run().catch(err => {
  const root = document.getElementById('root');
  root.innerHTML = `<div class="status error">Error: ${esc(err.message)}</div>`;
});
```

Replace this with a guard keyed on whether CommonJS `module` exists — it does not exist in a browser `<script>` context, but does exist when Jest/Node `require()`s the file:

```js
if (typeof module === 'undefined') {
  run().catch(err => {
    const root = document.getElementById('root');
    root.innerHTML = `<div class="status error">Error: ${esc(err.message)}</div>`;
  });
} else {
  module.exports = {
    doAdd, doAddChannel, doHide, doRestore, doDelete,
    initWatchLaterToggle, renderState, renderChannelState,
    checkStatus, channelUrlFrom, esc, getOrCreateFolder, postJson,
  };
}
```

All function names in the export list already exist at top level in `popup.js` (function declarations are hoisted, so listing them at the bottom works regardless of declaration order). Exporting the full set (not just `doAdd`/`initWatchLaterToggle`) costs nothing and avoids a second edit to this guard when a future pass covers the other functions.

In the real browser: `<script src="popup.js">` runs as a classic script, `module` is `undefined`, so the `if` branch runs and `run()` fires exactly as it does today — zero behavior change.

Under Jest: `require('.../popup.js')` runs the file as CommonJS, `module` is defined, so `run()` is never auto-invoked, and the test file gets the exported functions to call directly with mocked `browser`/`fetch`.

## Test infrastructure

### `package.json` (new, repo root)

```json
{
  "name": "viewtube-extension-tests",
  "private": true,
  "scripts": {
    "test": "jest"
  },
  "devDependencies": {
    "jest": "^29.7.0",
    "jest-environment-jsdom": "^29.7.0"
  },
  "jest": {
    "testEnvironment": "jsdom",
    "testMatch": ["<rootDir>/tests/extension/**/*.test.js"]
  }
}
```

(Exact version pins resolved at implementation time to whatever `npm install jest jest-environment-jsdom` resolves as latest-stable; the `^29.7.0` above is illustrative, not a hard requirement.)

### `tests/extension/setup.js` (new)

A shared `browser` global stub, `require`d at the top of `popup.test.js` (not a Jest `setupFiles` global, since only one test file exists — keeping it an explicit import avoids hidden global magic while the suite is this small; revisit if a second test file needs the same stub):

```js
function makeBrowserStub() {
  return {
    bookmarks: {
      create: jest.fn().mockResolvedValue({ id: 'bm1' }),
      get: jest.fn().mockRejectedValue(new Error('not found')),
      remove: jest.fn().mockResolvedValue(undefined),
      search: jest.fn().mockResolvedValue([]),
    },
    storage: {
      local: {
        get: jest.fn().mockResolvedValue({}),
        set: jest.fn().mockResolvedValue(undefined),
      },
    },
    tabs: {
      query: jest.fn().mockResolvedValue([]),
    },
  };
}

module.exports = { makeBrowserStub };
```

`makeBrowserStub()` returns a fresh object per call so each test gets independent mock call histories — a shared singleton would leak `mock.calls` state across tests via `beforeEach` reset alone, which is more fragile than just constructing a new stub per test.

### `tests/extension/popup.test.js` (new)

Structure (illustrative — the plan will contain the literal, complete test bodies):

```js
const { makeBrowserStub } = require('./setup');

let popup;

beforeEach(() => {
  jest.resetModules();
  document.body.innerHTML = '<div id="root"></div>';
  global.browser = makeBrowserStub();
  global.fetch = jest.fn();
  global.window.close = jest.fn();
  popup = require('../../extension/popup/popup.js');
});

describe('doAdd', () => {
  // ...
});

describe('initWatchLaterToggle', () => {
  // ...
});
```

`jest.resetModules()` + re-`require`-ing `popup.js` inside `beforeEach` is necessary because `popup.js` is a classic script with top-level `const` declarations (`YT_ID_RE`, `DEFAULT_URL`, etc.) — re-requiring gives each test a clean module instance rather than a cached one, avoiding any possibility of state leaking between tests (there isn't mutable top-level state today, but this makes the suite robust against that changing later).

`jest.useFakeTimers()` is enabled per-test (not globally) wherever a test needs to assert on the `setTimeout(() => window.close(), 1500)` auto-close behavior, then `jest.advanceTimersByTime(1500)` and assert `window.close` was called — real timers otherwise for tests that don't care about the close behavior, to avoid unrelated test flakiness from forgetting to advance fake timers.

## Test cases

### `doAdd(viewtubeUrl, tabUrl, tabTitle, alsoWatchLater, alsoFavorite)`

All tests set up `global.fetch` to return per-URL responses (a small `fetch.mockImplementation(url => ...)` keyed on `url.includes('/api/add')` etc., since `doAdd` calls up to three different endpoints in one run).

1. **Neither checkbox checked, add succeeds** → `root.innerHTML` contains the title success line, no watch-later or favorite lines; `fetch` was never called for `/api/watch-later/add` or `/api/favourite/add`; `window.close` fires after 1.5s (fake timers).
2. **`alsoWatchLater=true` only, both calls succeed** → success line + `Added to Watch Later` line present; no favorite line; favorite endpoint never called.
3. **`alsoFavorite=true` only, both calls succeed** → success line + `Marked as favorite` line present; no watch-later line; watch-later endpoint never called.
4. **Both true, both succeed** → both follow-up lines present.
5. **Both true, watch-later fetch rejects (network error), favorite succeeds** → `Watch Later failed` line + `Marked as favorite` line both present (independent failure/success, not one blocking the other).
6. **Both true, favorite returns `{status:"error"}` (e.g. 404), watch-later succeeds** → `Favorite failed` line + `Added to Watch Later` line.
7. **ViewTube `/api/add` itself returns `{status:"error"}`** → neither follow-up endpoint is called at all (assert via `fetch.mock.calls`), regardless of the checkbox flags; partial/error rendering path is used.
8. **Bookmark creation rejects but ViewTube add succeeds, both checkboxes true** → partial-path rendering still includes both follow-up result lines (mirrors existing pre-favorite behavior for watch-later, extended to favorite).

### `initWatchLaterToggle(viewtubeUrl, tabUrl)`

Each test first renders the minimal required DOM fragment (`chk-watch-later` checkbox + `wl-error` div) into `#root`, since `initWatchLaterToggle` queries those IDs directly rather than receiving them as parameters — matching how it's actually invoked from `renderState`'s `exists` branch.

1. **Status fetch resolves `{in_queue: true}`** → checkbox ends up `checked = true`, `disabled = false`.
2. **Status fetch resolves `{in_queue: false}`** → `checked = false`, `disabled = false`.
3. **Status fetch rejects (network error)** → checkbox stays `disabled = true`; no `change` listener behavior is exercised (can't toggle a disabled checkbox in practice, but the test confirms no listener was even needed/attached in a way that would fire on a synthetic event — or simply confirms the disabled state and stops there).
4. **User checks the box (simulated `change` event with `checked = true`), `/add` resolves `{status:"added"}`** → stays checked, re-enabled, `#wl-error` hidden.
5. **User unchecks the box, `/remove` resolves `{status:"removed"}`** → stays unchecked, re-enabled, error hidden.
6. **Toggle-on request rejects (network error)** → checkbox reverts to unchecked, `#wl-error` shows text and is visible, re-enabled.
7. **Toggle-on, `/add` resolves `{status:"already_in_queue"}`** (409 case) → treated as success — stays checked, no error shown.
8. **Toggle-off, `/remove` resolves `{status:"error"}`** (404 "not in queue" case) → treated as failure — checkbox reverts to checked, error shown.

## Documentation

- `TODO.md:72` updated from `background.js`, `content.js`, and `popup.js` are currently untested`" to reflect that `popup.js` now has Jest coverage for `doAdd`/`initWatchLaterToggle`, while `background.js`/`content.js` (and the rest of `popup.js`) remain untested. Exact wording decided at implementation time; the item stays open (not struck through) since it's partial coverage, not the whole item.
- `CHANGELOG.md`: dated entry noting the new Jest suite, what it covers, and the trade-off that it's popup.js-only for now (no `background.js`/`content.js`/real-browser coverage yet).
- No `plan-webapp.md` change — that file documents the Flask webapp, not the extension test tooling; nothing about webapp behavior changes here.
- A brief root-level note on running tests: covered by `CHANGELOG.md`'s entry (`npm test`) — no separate `README.md` exists in this repo to extend, so no new doc file is created for this alone.

## Testing the tests

Since this task's entire purpose is testing infrastructure, "testing" here means: run `npm test` and confirm all new tests pass (RED before the `module.exports` guard exists — `require('.../popup.js')` returns `{}` or throws, so `popup.doAdd` is `undefined` and any test calling it fails; GREEN after the guard is added). Also run `python -m pytest -q` once at the end to confirm the new `package.json`/`tests/extension/` files don't interfere with pytest's collection (`testpaths = ["tests"]` in `pyproject.toml` only matches `test_*.py`/`*_test.py` by default, so `.test.js` files should be silently ignored — confirmed as an explicit check, not just assumed).

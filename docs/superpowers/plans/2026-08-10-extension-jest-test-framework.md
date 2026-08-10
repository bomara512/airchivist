# Extension: Jest Test Framework + doAdd/initWatchLaterToggle Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up Jest + jsdom as the extension's test framework, make `popup.js` importable/testable without a bundler, and write the first real test suite covering `doAdd` and `initWatchLaterToggle` — the two pieces of non-trivial async/checkbox logic shipped so far.

**Architecture:** A guarded `module.exports` at the bottom of `popup.js` (active only under Node/Jest, a no-op in the real browser where `<script src="popup.js">` loads it as a classic script). A root-level `package.json` with Jest as the sole devDependency, config inline in `package.json`'s `"jest"` field. Shared test helpers (`browser` global stub, a URL-routed `fetch` mock, a microtask-flushing helper) live in `tests/extension/setup.js`; all test cases live in `tests/extension/popup.test.js`.

**Tech Stack:** Jest 29 + `jest-environment-jsdom`, plain CommonJS (no TypeScript, no bundler, no Babel — `popup.js` is already valid CommonJS-compatible JS once the export guard is added).

## Global Constraints

- No build step, no bundler, no new runtime dependency for the extension itself — Jest and `jest-environment-jsdom` are devDependencies only.
- `popup.js`'s real-browser behavior must not change. The `module.exports` guard must be additive: `typeof module === 'undefined'` is true in every real browser context, so the existing `run().catch(...)` auto-invocation still fires unconditionally there.
- `node_modules/` must be gitignored before `npm install` is ever run in this repo (it isn't yet — check `.gitignore` first).
- `package-lock.json` IS committed (reproducible installs); `node_modules/` is NOT.
- Test file layout mirrors the existing Python convention (`tests/webapp/`, `tests/crawler/`) → `tests/extension/`.
- `python -m pytest -q` must still pass unmodified at the end — the new `package.json`/`tests/extension/*.js` files must not be collected by pytest (`pyproject.toml`'s `testpaths = ["tests"]` only matches `test_*.py`/`*_test.py` by default; verify this rather than assume it).
- Only `doAdd` and `initWatchLaterToggle` get test coverage in this pass. `background.js`, `content.js`, and the rest of `popup.js` (`doAddChannel`, `doHide`, `doRestore`, `doDelete`, `renderState`, `renderChannelState`, `run`) stay untested — do not add tests for them, and do not restructure them.
- Append a `CHANGELOG.md` entry. Update `TODO.md`'s JS-test-framework line to reflect partial (popup.js `doAdd`/`initWatchLaterToggle`) coverage — the item stays open (not struck through), since `background.js`/`content.js` and the rest of `popup.js` remain untested.
- Remove any debug logging (`console.log`, etc.) before finishing any task.

---

### Task 1: Test infrastructure — `package.json`, `tests/extension/setup.js`, and the `module.exports` guard

**Files:**
- Create: `package.json`
- Create: `tests/extension/setup.js`
- Create: `tests/extension/popup.test.js` (smoke test only — Tasks 2 and 3 append to this same file)
- Modify: `.gitignore`
- Modify: `extension/popup/popup.js` (only the final ~4 lines)

**Interfaces:**
- Consumes: nothing from earlier tasks (this is the first task).
- Produces: `tests/extension/setup.js` exports `{ makeBrowserStub, jsonResponse, mockFetchRouter, flushPromises }` — the exact shared helpers Tasks 2 and 3 both `require('./setup')` and use. `popup.js` exports `{ doAdd, doAddChannel, doHide, doRestore, doDelete, initWatchLaterToggle, renderState, renderChannelState, checkStatus, channelUrlFrom, esc, getOrCreateFolder, postJson }` under Node/Jest. `tests/extension/popup.test.js` establishes the shared `beforeEach` (resets modules, stubs `browser`/`fetch`/`window.close`, re-requires `popup.js` into a `popup` variable) that Tasks 2 and 3 rely on being present exactly as written here — they do not redefine it.

- [ ] **Step 1: Check `.gitignore` for `node_modules/`, add it if missing**

Run: `grep -n "node_modules" .gitignore`
If no match, add `node_modules/` to `.gitignore` (append to the existing file, same style as its other entries — no comment needed, matches e.g. `.venv/`).

- [ ] **Step 2: Write the failing smoke test**

Create `tests/extension/setup.js`:

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

function jsonResponse(body) {
  return Promise.resolve({ json: () => Promise.resolve(body) });
}

// routes: array of [urlSubstring, (url) => Promise] pairs, checked in order.
function mockFetchRouter(routes) {
  return jest.fn((url) => {
    for (const [substr, handler] of routes) {
      if (url.includes(substr)) return handler(url);
    }
    return Promise.reject(new Error(`Unmocked fetch: ${url}`));
  });
}

// Flushes pending microtasks (promise chains inside event listeners that
// the test can't otherwise `await`, since dispatchEvent() doesn't return
// the listener's promise).
function flushPromises() {
  return new Promise(resolve => setImmediate(resolve));
}

module.exports = { makeBrowserStub, jsonResponse, mockFetchRouter, flushPromises };
```

Create `tests/extension/popup.test.js`:

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

describe('module exports', () => {
  test('exports doAdd and initWatchLaterToggle as functions', () => {
    expect(typeof popup.doAdd).toBe('function');
    expect(typeof popup.initWatchLaterToggle).toBe('function');
  });
});
```

Create `package.json` at the repo root:

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

- [ ] **Step 2b: Install dependencies**

Run: `npm install`
This creates `node_modules/` (gitignored per Step 1) and `package-lock.json` (committed).

- [ ] **Step 3: Run the test to verify it fails**

Run: `npm test`
Expected: FAIL. `popup.js` has no `module.exports` yet, so `require('../../extension/popup/popup.js')` returns Node's default empty `{}` for a script with no exports — `popup.doAdd` is `undefined`, and `expect(typeof popup.doAdd).toBe('function')` fails (`Expected: "function", Received: "undefined"`).

- [ ] **Step 4: Add the `module.exports` guard to `popup.js`**

`extension/popup/popup.js` currently ends (last 4 lines) with:

```js
run().catch(err => {
  const root = document.getElementById('root');
  root.innerHTML = `<div class="status error">Error: ${esc(err.message)}</div>`;
});
```

Replace those exact final 4 lines with:

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

No other line of `popup.js` changes. In a real browser, `<script src="popup.js">` runs as a classic script — `typeof module` is `'undefined'` there, so `run()` still fires exactly as before.

- [ ] **Step 5: Run the test to verify it passes**

Run: `npm test`
Expected: PASS (1 test).

- [ ] **Step 6: Confirm pytest is unaffected**

Run: `python -m pytest -q`
Expected: PASS, same count as before this task (541) — confirms `package.json`/`tests/extension/*.js` aren't collected by pytest.

- [ ] **Step 7: Commit**

```bash
git add package.json package-lock.json .gitignore tests/extension/setup.js tests/extension/popup.test.js extension/popup/popup.js
git commit -m "test(extension): add Jest test infrastructure and make popup.js testable"
```

---

### Task 2: `doAdd` test suite

**Files:**
- Modify: `tests/extension/popup.test.js` (append a new `describe('doAdd', ...)` block — do not touch the `beforeEach` or the `module exports` block from Task 1)

**Interfaces:**
- Consumes: `popup.doAdd(viewtubeUrl, tabUrl, tabTitle, alsoWatchLater, alsoFavorite)` (exported by Task 1); `makeBrowserStub`, `jsonResponse`, `mockFetchRouter` from `tests/extension/setup.js` (Task 1); the shared `beforeEach` from Task 1 (runs before every test in this file, including these).
- Produces: nothing further tasks depend on — Task 3 is independent of this one (different function under test, same shared infra).

- [ ] **Step 1: Write the tests**

Add to `tests/extension/popup.test.js`, after the `module exports` describe block (add `mockFetchRouter, jsonResponse` to the existing `require('./setup')` destructure at the top of the file):

```js
const { makeBrowserStub, jsonResponse, mockFetchRouter } = require('./setup');
```

```js
describe('doAdd', () => {
  const viewtubeUrl = 'http://localhost:8080';
  const tabUrl = 'https://www.youtube.com/watch?v=abc123';
  const tabTitle = 'My Video';

  test('neither checkbox checked: shows title only, no follow-up calls, closes after 1.5s', async () => {
    jest.useFakeTimers();
    global.fetch = mockFetchRouter([
      ['/api/add', () => jsonResponse({ status: 'added', title: tabTitle })],
    ]);

    await popup.doAdd(viewtubeUrl, tabUrl, tabTitle, false, false);

    const text = document.getElementById('root').textContent;
    expect(text).toContain(tabTitle);
    expect(text).not.toContain('Watch Later');
    expect(text).not.toContain('favorite');
    expect(text).not.toContain('Favorite');
    expect(global.fetch.mock.calls.some(([url]) => url.includes('/api/watch-later/add'))).toBe(false);
    expect(global.fetch.mock.calls.some(([url]) => url.includes('/api/favourite/add'))).toBe(false);

    jest.advanceTimersByTime(1500);
    expect(window.close).toHaveBeenCalled();
    jest.useRealTimers();
  });

  test('watch-later only, both succeed: shows Added to Watch Later, no favorite line', async () => {
    global.fetch = mockFetchRouter([
      ['/api/add', () => jsonResponse({ status: 'added', title: tabTitle })],
      ['/api/watch-later/add', () => jsonResponse({ status: 'added' })],
    ]);

    await popup.doAdd(viewtubeUrl, tabUrl, tabTitle, true, false);

    const text = document.getElementById('root').textContent;
    expect(text).toContain('Added to Watch Later');
    expect(text).not.toContain('favorite');
    expect(text).not.toContain('Favorite');
    expect(global.fetch.mock.calls.some(([url]) => url.includes('/api/favourite/add'))).toBe(false);
  });

  test('favorite only, both succeed: shows Marked as favorite, no watch-later line', async () => {
    global.fetch = mockFetchRouter([
      ['/api/add', () => jsonResponse({ status: 'added', title: tabTitle })],
      ['/api/favourite/add', () => jsonResponse({ status: 'added' })],
    ]);

    await popup.doAdd(viewtubeUrl, tabUrl, tabTitle, false, true);

    const text = document.getElementById('root').textContent;
    expect(text).toContain('Marked as favorite');
    expect(text).not.toContain('Watch Later');
    expect(global.fetch.mock.calls.some(([url]) => url.includes('/api/watch-later/add'))).toBe(false);
  });

  test('both checked, both succeed: shows both follow-up lines', async () => {
    global.fetch = mockFetchRouter([
      ['/api/add', () => jsonResponse({ status: 'added', title: tabTitle })],
      ['/api/watch-later/add', () => jsonResponse({ status: 'added' })],
      ['/api/favourite/add', () => jsonResponse({ status: 'added' })],
    ]);

    await popup.doAdd(viewtubeUrl, tabUrl, tabTitle, true, true);

    const text = document.getElementById('root').textContent;
    expect(text).toContain('Added to Watch Later');
    expect(text).toContain('Marked as favorite');
  });

  test('both checked, watch-later network error, favorite succeeds: independent failure/success', async () => {
    global.fetch = mockFetchRouter([
      ['/api/add', () => jsonResponse({ status: 'added', title: tabTitle })],
      ['/api/watch-later/add', () => Promise.reject(new Error('network fail'))],
      ['/api/favourite/add', () => jsonResponse({ status: 'added' })],
    ]);

    await popup.doAdd(viewtubeUrl, tabUrl, tabTitle, true, true);

    const text = document.getElementById('root').textContent;
    expect(text).toContain('Watch Later failed');
    expect(text).toContain('Marked as favorite');
    expect(text).not.toContain('Added to Watch Later');
    expect(text).not.toContain('Favorite failed');
  });

  test('both checked, favorite returns error status, watch-later succeeds', async () => {
    global.fetch = mockFetchRouter([
      ['/api/add', () => jsonResponse({ status: 'added', title: tabTitle })],
      ['/api/watch-later/add', () => jsonResponse({ status: 'added' })],
      ['/api/favourite/add', () => jsonResponse({ status: 'error', error: 'Video not found' })],
    ]);

    await popup.doAdd(viewtubeUrl, tabUrl, tabTitle, true, true);

    const text = document.getElementById('root').textContent;
    expect(text).toContain('Added to Watch Later');
    expect(text).toContain('Favorite failed');
    expect(text).not.toContain('Marked as favorite');
  });

  test('ViewTube add itself fails: follow-up endpoints are never called', async () => {
    global.fetch = mockFetchRouter([
      ['/api/add', () => jsonResponse({ status: 'error', error: 'Not a YouTube video URL' })],
    ]);

    await popup.doAdd(viewtubeUrl, tabUrl, tabTitle, true, true);

    expect(global.fetch.mock.calls.some(([url]) => url.includes('/api/watch-later/add'))).toBe(false);
    expect(global.fetch.mock.calls.some(([url]) => url.includes('/api/favourite/add'))).toBe(false);
    const text = document.getElementById('root').textContent;
    expect(text).not.toContain('Added to Watch Later');
    expect(text).not.toContain('Marked as favorite');
  });

  test('bookmark creation fails but ViewTube succeeds: partial path still shows both follow-up lines', async () => {
    global.browser.bookmarks.create.mockImplementation((opts) => {
      if (opts.url) return Promise.reject(new Error('bookmark failed'));
      return Promise.resolve({ id: 'bm1' }); // folder creation still succeeds
    });
    global.fetch = mockFetchRouter([
      ['/api/add', () => jsonResponse({ status: 'added', title: tabTitle })],
      ['/api/watch-later/add', () => jsonResponse({ status: 'added' })],
      ['/api/favourite/add', () => jsonResponse({ status: 'added' })],
    ]);

    await popup.doAdd(viewtubeUrl, tabUrl, tabTitle, true, true);

    const text = document.getElementById('root').textContent;
    expect(text).toContain('Bookmark failed');
    expect(text).toContain('Added to ViewTube');
    expect(text).toContain('Added to Watch Later');
    expect(text).toContain('Marked as favorite');
  });
});
```

- [ ] **Step 2: Run the tests**

Run: `npm test`
Expected: PASS (8 new tests + the 1 smoke test from Task 1 = 9 total).

- [ ] **Step 3: Commit**

```bash
git add tests/extension/popup.test.js
git commit -m "test(extension): add doAdd test coverage"
```

---

### Task 3: `initWatchLaterToggle` test suite + doc updates + final verification

**Files:**
- Modify: `tests/extension/popup.test.js` (append a new `describe('initWatchLaterToggle', ...)` block)
- Modify: `TODO.md`, `CHANGELOG.md`

**Interfaces:**
- Consumes: `popup.initWatchLaterToggle(viewtubeUrl, tabUrl)` (exported by Task 1); `flushPromises` from `tests/extension/setup.js` (Task 1, not yet used by Task 2 — first use is here); the shared `beforeEach` from Task 1.
- Produces: final state of this plan — no later task depends on this one.

- [ ] **Step 1: Write the tests**

Add `flushPromises` to the existing `require('./setup')` destructure at the top of `tests/extension/popup.test.js`:

```js
const { makeBrowserStub, jsonResponse, mockFetchRouter, flushPromises } = require('./setup');
```

Add to `tests/extension/popup.test.js`, after the `doAdd` describe block:

```js
describe('initWatchLaterToggle', () => {
  const viewtubeUrl = 'http://localhost:8080';
  const tabUrl = 'https://www.youtube.com/watch?v=abc123';

  function renderCheckboxFixture() {
    document.getElementById('root').innerHTML = `
      <input type="checkbox" id="chk-watch-later" disabled>
      <div id="wl-error" style="display:none"></div>
    `;
  }

  test('status fetch resolves in_queue=true: checkbox becomes checked and enabled', async () => {
    renderCheckboxFixture();
    global.fetch = mockFetchRouter([
      ['/api/watch-later/status', () => jsonResponse({ in_queue: true })],
    ]);

    await popup.initWatchLaterToggle(viewtubeUrl, tabUrl);

    const chk = document.getElementById('chk-watch-later');
    expect(chk.checked).toBe(true);
    expect(chk.disabled).toBe(false);
  });

  test('status fetch resolves in_queue=false: checkbox becomes unchecked and enabled', async () => {
    renderCheckboxFixture();
    global.fetch = mockFetchRouter([
      ['/api/watch-later/status', () => jsonResponse({ in_queue: false })],
    ]);

    await popup.initWatchLaterToggle(viewtubeUrl, tabUrl);

    const chk = document.getElementById('chk-watch-later');
    expect(chk.checked).toBe(false);
    expect(chk.disabled).toBe(false);
  });

  test('status fetch rejects: checkbox stays disabled', async () => {
    renderCheckboxFixture();
    global.fetch = mockFetchRouter([
      ['/api/watch-later/status', () => Promise.reject(new Error('network fail'))],
    ]);

    await popup.initWatchLaterToggle(viewtubeUrl, tabUrl);

    const chk = document.getElementById('chk-watch-later');
    expect(chk.disabled).toBe(true);
  });

  test('toggle on, /add succeeds: stays checked, re-enabled, no error', async () => {
    renderCheckboxFixture();
    global.fetch = mockFetchRouter([
      ['/api/watch-later/status', () => jsonResponse({ in_queue: false })],
      ['/api/watch-later/add', () => jsonResponse({ status: 'added' })],
    ]);
    await popup.initWatchLaterToggle(viewtubeUrl, tabUrl);

    const chk = document.getElementById('chk-watch-later');
    const errBox = document.getElementById('wl-error');
    chk.checked = true;
    chk.dispatchEvent(new Event('change'));
    await flushPromises();

    expect(chk.checked).toBe(true);
    expect(chk.disabled).toBe(false);
    expect(errBox.style.display).toBe('none');
  });

  test('toggle off, /remove succeeds: stays unchecked, re-enabled, no error', async () => {
    renderCheckboxFixture();
    global.fetch = mockFetchRouter([
      ['/api/watch-later/status', () => jsonResponse({ in_queue: true })],
      ['/api/watch-later/remove', () => jsonResponse({ status: 'removed' })],
    ]);
    await popup.initWatchLaterToggle(viewtubeUrl, tabUrl);

    const chk = document.getElementById('chk-watch-later');
    const errBox = document.getElementById('wl-error');
    chk.checked = false;
    chk.dispatchEvent(new Event('change'));
    await flushPromises();

    expect(chk.checked).toBe(false);
    expect(chk.disabled).toBe(false);
    expect(errBox.style.display).toBe('none');
  });

  test('toggle on, /add network error: reverts to unchecked, shows error, re-enabled', async () => {
    renderCheckboxFixture();
    global.fetch = mockFetchRouter([
      ['/api/watch-later/status', () => jsonResponse({ in_queue: false })],
      ['/api/watch-later/add', () => Promise.reject(new Error('network fail'))],
    ]);
    await popup.initWatchLaterToggle(viewtubeUrl, tabUrl);

    const chk = document.getElementById('chk-watch-later');
    const errBox = document.getElementById('wl-error');
    chk.checked = true;
    chk.dispatchEvent(new Event('change'));
    await flushPromises();

    expect(chk.checked).toBe(false);
    expect(chk.disabled).toBe(false);
    expect(errBox.style.display).toBe('block');
    expect(errBox.textContent).toBe('✗ Watch Later update failed');
  });

  test('toggle on, /add returns already_in_queue: treated as success', async () => {
    renderCheckboxFixture();
    global.fetch = mockFetchRouter([
      ['/api/watch-later/status', () => jsonResponse({ in_queue: false })],
      ['/api/watch-later/add', () => jsonResponse({ status: 'already_in_queue' })],
    ]);
    await popup.initWatchLaterToggle(viewtubeUrl, tabUrl);

    const chk = document.getElementById('chk-watch-later');
    const errBox = document.getElementById('wl-error');
    chk.checked = true;
    chk.dispatchEvent(new Event('change'));
    await flushPromises();

    expect(chk.checked).toBe(true);
    expect(errBox.style.display).toBe('none');
  });

  test('toggle off, /remove returns error status: treated as failure, reverts to checked', async () => {
    renderCheckboxFixture();
    global.fetch = mockFetchRouter([
      ['/api/watch-later/status', () => jsonResponse({ in_queue: true })],
      ['/api/watch-later/remove', () => jsonResponse({ status: 'error', error: 'Not in queue' })],
    ]);
    await popup.initWatchLaterToggle(viewtubeUrl, tabUrl);

    const chk = document.getElementById('chk-watch-later');
    const errBox = document.getElementById('wl-error');
    chk.checked = false;
    chk.dispatchEvent(new Event('change'));
    await flushPromises();

    expect(chk.checked).toBe(true);
    expect(errBox.style.display).toBe('block');
  });
});
```

- [ ] **Step 2: Run the tests**

Run: `npm test`
Expected: PASS (8 new tests + 9 prior = 17 total).

- [ ] **Step 3: Update `TODO.md`**

`TODO.md`'s Tech Debt → Medium (next) section currently has:

```
- [ ] Add JS test framework (e.g. Jest) for the browser extension — `background.js`, `content.js`, and `popup.js` are currently untested
```

Change to:

```
- [ ] Add JS test framework (e.g. Jest) for the browser extension — `background.js` and `content.js` are still untested; `popup.js` now has Jest coverage for `doAdd`/`initWatchLaterToggle` only (`doAddChannel`, `doHide`, `doRestore`, `doDelete`, `renderState`, `renderChannelState`, `run` remain untested)
```

Keep the `[ ]` (still open) — this is partial coverage, not the full item.

- [ ] **Step 4: Update `CHANGELOG.md`**

Append a dated entry (today's date): Jest + jsdom test framework added for the extension (`npm test`), with the first suite covering `popup.js`'s `doAdd` and `initWatchLaterToggle` — the two functions with non-trivial async/checkbox logic. `popup.js` gained a guarded `module.exports` (no-op in the real browser) to make this possible without a bundler. Implication (pro): this closes a long-open gap and gives durable automated evidence for exactly the kind of async/checkbox logic that's been shipping in this extension lately, replacing one-off manual/code-reading verification; (con): `background.js`, `content.js`, and the rest of `popup.js` remain untested — this is a first slice, not full coverage.

- [ ] **Step 5: Final verification**

Run: `npm test` — expect all 17 tests passing.
Run: `python -m pytest -q` — expect 541 passing, unchanged, confirming the JS test infra doesn't interfere with the Python suite.

- [ ] **Step 6: Commit**

```bash
git add tests/extension/popup.test.js TODO.md CHANGELOG.md
git commit -m "test(extension): add initWatchLaterToggle coverage, update docs"
```

---

## Self-Review Notes

- **Spec coverage:** testability guard (Task 1 Step 4) ← spec's "Making popup.js testable" section, verbatim; package.json/jest config (Task 1) ← spec's "Test infrastructure" section; all 8 `doAdd` cases and all 8 `initWatchLaterToggle` cases ← spec's "Test cases" section, one-to-one (spec's case 3 for `initWatchLaterToggle`, "no listener behavior exercised," is implemented as simply asserting `disabled` stays `true` and stopping there, matching the spec's own hedge on that case); doc updates ← spec's "Documentation" section (TODO.md wording differs slightly from the spec's placeholder text since the spec explicitly deferred exact wording to implementation time — the wording above satisfies the spec's stated intent: item stays open, names what's covered vs. not); `python -m pytest -q` / pytest-non-interference check ← spec's "Testing the tests" section, done explicitly in both Task 1 (before any JS tests exist, to confirm baseline non-interference from `package.json` alone) and Task 3 (final check with everything in place).
- **Type consistency:** `mockFetchRouter(routes)` signature and `[urlSubstring, handlerFn]` pair shape used identically across every test in Tasks 2 and 3; `flushPromises()` takes no arguments and returns a `Promise` in both its Task 1 definition and its Task 3 usage; the shared `beforeEach` (Task 1) sets `global.browser`, `global.fetch`, `global.window.close`, and re-requires `popup` — every test in Tasks 2 and 3 relies on exactly those four things being freshly set per-test, and none of them redefine `beforeEach`.
- **Verified against codebase:** `doAdd`'s current signature (`viewtubeUrl, tabUrl, tabTitle, alsoWatchLater = false, alsoFavorite = false`), its exact success/failure line strings (`'Added to Watch Later'`, `'Watch Later failed'`, `'Marked as favorite'`, `'Favorite failed'`), and `initWatchLaterToggle`'s exact DOM element IDs (`chk-watch-later`, `wl-error`) and error text (`'✗ Watch Later update failed'`) were all read directly from the current `extension/popup/popup.js` (364 lines) before drafting this plan — not recalled from memory or the earlier spec draft. `TODO.md`'s current JS-test-framework line and `.gitignore`'s current contents (no `node_modules/` entry yet) were both confirmed by direct read. No `node_modules/` or `package.json` exists in the repo yet, confirmed by direct check, so Task 1's `npm install` step has a clean slate.

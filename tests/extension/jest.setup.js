// Shared test lifecycle for every extension suite.
//
// Fake timers and the setImmediate polyfill live here rather than in a single test
// file for the reason CLAUDE.md records: inline `jest.useFakeTimers()` /
// `useRealTimers()` pairs are skipped when an assertion between them throws,
// leaking real timers into every later test and producing a "Jest did not exit"
// warning. A shared afterEach always runs.

// jsdom does not define setImmediate, which some async helpers rely on.
if (typeof setImmediate === 'undefined') {
  global.setImmediate = (fn, ...args) => setTimeout(fn, 0, ...args);
}

beforeEach(() => {
  jest.useFakeTimers();
});

afterEach(() => {
  // Run pending timers BEFORE clearing them. content.js's `waitFor` disconnects its
  // MutationObserver from inside a setTimeout, so a test that starts an async
  // lookup and ends without awaiting it (any test that calls `run()` on a page with
  // no related-videos sidebar) leaves that observer connected to the shared
  // document. Clearing the timer first would strand it, and it would then fire into
  // a later test's DOM and drive the *previous* module instance — which is exactly
  // the cross-test leak that made watchRelated's tests pass alone and fail in suite.
  jest.runOnlyPendingTimers();
  jest.clearAllTimers();
  jest.useRealTimers();
});

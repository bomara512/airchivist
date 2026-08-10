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

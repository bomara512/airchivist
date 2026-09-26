const { jsonResponse } = require('./setup');

let background;

beforeEach(() => {
  jest.resetModules();
  global.browser = {
    storage: { local: { get: jest.fn().mockResolvedValue({}) } },
    runtime: { onMessage: { addListener: jest.fn() } },
  };
  global.fetch = jest.fn();
  background = require('../../extension/background.js');
});

describe('module exports', () => {
  test('exports handleMessage and getAirchivistUrl', () => {
    expect(typeof background.handleMessage).toBe('function');
    expect(typeof background.getAirchivistUrl).toBe('function');
  });

  test('does not register a runtime listener when required as a module', () => {
    // Under `require`, the side-effectful registration must not run — otherwise a
    // test file importing this leaves a listener on a shared stub.
    expect(global.browser.runtime.onMessage.addListener).not.toHaveBeenCalled();
  });
});

describe('getAirchivistUrl', () => {
  test('falls back to localhost:8080 when nothing is stored', async () => {
    expect(await background.getAirchivistUrl()).toBe('http://localhost:8080');
  });

  test('uses the stored URL when one is set', async () => {
    global.browser.storage.local.get.mockResolvedValue({
      airchivistUrl: 'http://example.test:9999',
    });
    expect(await background.getAirchivistUrl()).toBe('http://example.test:9999');
  });
});

describe('handleMessage', () => {
  const videoUrl = 'https://www.youtube.com/watch?v=abc123';

  test('unknown action returns undefined so other listeners can answer', () => {
    expect(background.handleMessage({ action: 'somethingElse' })).toBeUndefined();
  });

  describe('fetchStatus', () => {
    test('returns the parsed status body', async () => {
      global.fetch.mockReturnValue(jsonResponse({ status: 'exists', title: 'T' }));
      const data = await background.handleMessage({ action: 'fetchStatus', url: videoUrl });
      expect(data).toEqual({ status: 'exists', title: 'T' });
    });

    test('url-encodes the video URL into the query string', async () => {
      global.fetch.mockReturnValue(jsonResponse({ status: 'not_found' }));
      await background.handleMessage({ action: 'fetchStatus', url: videoUrl });
      expect(global.fetch).toHaveBeenCalledWith(
        `http://localhost:8080/api/status?url=${encodeURIComponent(videoUrl)}`
      );
    });

    test('an unreachable server resolves to status error, never rejects', async () => {
      global.fetch.mockRejectedValue(new Error('Failed to fetch'));
      await expect(
        background.handleMessage({ action: 'fetchStatus', url: videoUrl })
      ).resolves.toEqual({ status: 'error' });
    });
  });

  describe('fetchStatusBatch', () => {
    test('posts the ids as JSON and returns the map', async () => {
      global.fetch.mockReturnValue(jsonResponse({ aaaaaaaaaa1: 'exists' }));
      const data = await background.handleMessage({
        action: 'fetchStatusBatch',
        ids: ['aaaaaaaaaa1', 'bbbbbbbbbb2'],
      });
      expect(data).toEqual({ aaaaaaaaaa1: 'exists' });
      const [url, init] = global.fetch.mock.calls[0];
      expect(url).toBe('http://localhost:8080/api/status/batch');
      expect(init.method).toBe('POST');
      expect(JSON.parse(init.body)).toEqual({ ids: ['aaaaaaaaaa1', 'bbbbbbbbbb2'] });
    });

    test('an unreachable server resolves to an empty map', async () => {
      // Must be {} and not {status:'error'} — the content script indexes this by
      // video id, so any other shape would be read as a per-id lookup.
      global.fetch.mockRejectedValue(new Error('Failed to fetch'));
      await expect(
        background.handleMessage({ action: 'fetchStatusBatch', ids: ['x'] })
      ).resolves.toEqual({});
    });
  });

  describe('fetchChannelStatus', () => {
    test('returns the parsed channel body', async () => {
      global.fetch.mockReturnValue(jsonResponse({ status: 'exists' }));
      const data = await background.handleMessage({
        action: 'fetchChannelStatus',
        url: 'https://www.youtube.com/@someone',
      });
      expect(data).toEqual({ status: 'exists' });
    });

    test('an unreachable server resolves to status error', async () => {
      global.fetch.mockRejectedValue(new Error('Failed to fetch'));
      await expect(
        background.handleMessage({
          action: 'fetchChannelStatus',
          url: 'https://www.youtube.com/@someone',
        })
      ).resolves.toEqual({ status: 'error' });
    });
  });
});

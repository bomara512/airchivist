const { makeBrowserStub, jsonResponse, mockFetchRouter } = require('./setup');

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

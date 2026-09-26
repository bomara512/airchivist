const { makeBrowserStub, jsonResponse, mockFetchRouter, flushPromises } = require('./setup');

let popup;

// Fake timers live in tests/extension/jest.setup.js, shared by every suite.
beforeEach(() => {
  jest.resetModules();
  document.body.innerHTML = '<div id="root"></div>';
  global.browser = makeBrowserStub();
  global.fetch = jest.fn();
  global.window.close = jest.fn();
  popup = require('../../extension/popup/popup.js');
});

describe('module exports', () => {
  test('exports doAdd, initToggle, initWatchLaterToggle, and initFavoriteToggle as functions', () => {
    expect(typeof popup.doAdd).toBe('function');
    expect(typeof popup.initToggle).toBe('function');
    expect(typeof popup.initWatchLaterToggle).toBe('function');
    expect(typeof popup.initFavoriteToggle).toBe('function');
  });
});

describe('doAdd', () => {
  const airchivistUrl = 'http://localhost:8080';
  const tabUrl = 'https://www.youtube.com/watch?v=abc123';
  const tabTitle = 'My Video';

  test('neither checkbox checked: shows title only, no follow-up calls, closes after 1.5s', async () => {
    global.fetch = mockFetchRouter([
      ['/api/add', () => jsonResponse({ status: 'added', title: tabTitle })],
    ]);

    await popup.doAdd(airchivistUrl, tabUrl, tabTitle, false, false);

    const text = document.getElementById('root').textContent;
    expect(text).toContain(tabTitle);
    expect(text).not.toContain('Watch Later');
    expect(text).not.toContain('favorite');
    expect(text).not.toContain('Favorite');
    expect(global.fetch.mock.calls.some(([url]) => url.includes('/api/watch-later/add'))).toBe(false);
    expect(global.fetch.mock.calls.some(([url]) => url.includes('/api/favorite/add'))).toBe(false);

    jest.advanceTimersByTime(1500);
    expect(window.close).toHaveBeenCalled();
  });

  test('watch-later only, both succeed: shows Added to Watch Later, no favorite line', async () => {
    global.fetch = mockFetchRouter([
      ['/api/add', () => jsonResponse({ status: 'added', title: tabTitle })],
      ['/api/watch-later/add', () => jsonResponse({ status: 'added' })],
    ]);

    await popup.doAdd(airchivistUrl, tabUrl, tabTitle, true, false);

    const text = document.getElementById('root').textContent;
    expect(text).toContain('Added to Watch Later');
    expect(text).not.toContain('favorite');
    expect(text).not.toContain('Favorite');
    expect(global.fetch.mock.calls.some(([url]) => url.includes('/api/favorite/add'))).toBe(false);
  });

  test('favorite only, both succeed: shows Marked as favorite, no watch-later line', async () => {
    global.fetch = mockFetchRouter([
      ['/api/add', () => jsonResponse({ status: 'added', title: tabTitle })],
      ['/api/favorite/add', () => jsonResponse({ status: 'added' })],
    ]);

    await popup.doAdd(airchivistUrl, tabUrl, tabTitle, false, true);

    const text = document.getElementById('root').textContent;
    expect(text).toContain('Marked as favorite');
    expect(text).not.toContain('Watch Later');
    expect(global.fetch.mock.calls.some(([url]) => url.includes('/api/watch-later/add'))).toBe(false);
  });

  test('both checked, both succeed: shows both follow-up lines', async () => {
    global.fetch = mockFetchRouter([
      ['/api/add', () => jsonResponse({ status: 'added', title: tabTitle })],
      ['/api/watch-later/add', () => jsonResponse({ status: 'added' })],
      ['/api/favorite/add', () => jsonResponse({ status: 'added' })],
    ]);

    await popup.doAdd(airchivistUrl, tabUrl, tabTitle, true, true);

    const text = document.getElementById('root').textContent;
    expect(text).toContain('Added to Watch Later');
    expect(text).toContain('Marked as favorite');
  });

  test('both checked, watch-later network error, favorite succeeds: independent failure/success', async () => {
    global.fetch = mockFetchRouter([
      ['/api/add', () => jsonResponse({ status: 'added', title: tabTitle })],
      ['/api/watch-later/add', () => Promise.reject(new Error('network fail'))],
      ['/api/favorite/add', () => jsonResponse({ status: 'added' })],
    ]);

    await popup.doAdd(airchivistUrl, tabUrl, tabTitle, true, true);

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
      ['/api/favorite/add', () => jsonResponse({ status: 'error', error: 'Video not found' })],
    ]);

    await popup.doAdd(airchivistUrl, tabUrl, tabTitle, true, true);

    const text = document.getElementById('root').textContent;
    expect(text).toContain('Added to Watch Later');
    expect(text).toContain('Favorite failed');
    expect(text).not.toContain('Marked as favorite');
  });

  test('Airchivist add itself fails: follow-up endpoints are never called', async () => {
    global.fetch = mockFetchRouter([
      ['/api/add', () => jsonResponse({ status: 'error', error: 'Not a YouTube video URL' })],
    ]);

    await popup.doAdd(airchivistUrl, tabUrl, tabTitle, true, true);

    expect(global.fetch.mock.calls.some(([url]) => url.includes('/api/watch-later/add'))).toBe(false);
    expect(global.fetch.mock.calls.some(([url]) => url.includes('/api/favorite/add'))).toBe(false);
    const text = document.getElementById('root').textContent;
    expect(text).not.toContain('Added to Watch Later');
    expect(text).not.toContain('Marked as favorite');
  });

  test('bookmark creation fails but Airchivist succeeds: partial path still shows both follow-up lines', async () => {
    global.browser.bookmarks.create.mockImplementation((opts) => {
      if (opts.url) return Promise.reject(new Error('bookmark failed'));
      return Promise.resolve({ id: 'bm1' }); // folder creation still succeeds
    });
    global.fetch = mockFetchRouter([
      ['/api/add', () => jsonResponse({ status: 'added', title: tabTitle })],
      ['/api/watch-later/add', () => jsonResponse({ status: 'added' })],
      ['/api/favorite/add', () => jsonResponse({ status: 'added' })],
    ]);

    await popup.doAdd(airchivistUrl, tabUrl, tabTitle, true, true);

    const text = document.getElementById('root').textContent;
    expect(text).toContain('Bookmark failed');
    expect(text).toContain('Added to Airchivist');
    expect(text).toContain('Added to Watch Later');
    expect(text).toContain('Marked as favorite');
  });
});

describe('initWatchLaterToggle', () => {
  const airchivistUrl = 'http://localhost:8080';
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

    await popup.initWatchLaterToggle(airchivistUrl, tabUrl);

    const chk = document.getElementById('chk-watch-later');
    expect(chk.checked).toBe(true);
    expect(chk.disabled).toBe(false);
  });

  test('status fetch resolves in_queue=false: checkbox becomes unchecked and enabled', async () => {
    renderCheckboxFixture();
    global.fetch = mockFetchRouter([
      ['/api/watch-later/status', () => jsonResponse({ in_queue: false })],
    ]);

    await popup.initWatchLaterToggle(airchivistUrl, tabUrl);

    const chk = document.getElementById('chk-watch-later');
    expect(chk.checked).toBe(false);
    expect(chk.disabled).toBe(false);
  });

  test('status fetch rejects: checkbox stays disabled', async () => {
    renderCheckboxFixture();
    global.fetch = mockFetchRouter([
      ['/api/watch-later/status', () => Promise.reject(new Error('network fail'))],
    ]);

    await popup.initWatchLaterToggle(airchivistUrl, tabUrl);

    const chk = document.getElementById('chk-watch-later');
    expect(chk.disabled).toBe(true);
  });

  test('toggle on, /add succeeds: stays checked, re-enabled, no error', async () => {
    renderCheckboxFixture();
    global.fetch = mockFetchRouter([
      ['/api/watch-later/status', () => jsonResponse({ in_queue: false })],
      ['/api/watch-later/add', () => jsonResponse({ status: 'added' })],
    ]);
    await popup.initWatchLaterToggle(airchivistUrl, tabUrl);

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
    await popup.initWatchLaterToggle(airchivistUrl, tabUrl);

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
    await popup.initWatchLaterToggle(airchivistUrl, tabUrl);

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
    await popup.initWatchLaterToggle(airchivistUrl, tabUrl);

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
    await popup.initWatchLaterToggle(airchivistUrl, tabUrl);

    const chk = document.getElementById('chk-watch-later');
    const errBox = document.getElementById('wl-error');
    chk.checked = false;
    chk.dispatchEvent(new Event('change'));
    await flushPromises();

    expect(chk.checked).toBe(true);
    expect(errBox.style.display).toBe('block');
  });
});

describe('initFavoriteToggle', () => {
  const airchivistUrl = 'http://localhost:8080';
  const tabUrl = 'https://www.youtube.com/watch?v=abc123';

  function renderCheckboxFixture() {
    document.getElementById('root').innerHTML = `
      <input type="checkbox" id="chk-favorite" disabled>
      <div id="fav-error" style="display:none"></div>
    `;
  }

  test('status fetch resolves is_favorite=true: checkbox becomes checked and enabled', async () => {
    renderCheckboxFixture();
    global.fetch = mockFetchRouter([
      ['/api/favorite/status', () => jsonResponse({ is_favorite: true })],
    ]);

    await popup.initFavoriteToggle(airchivistUrl, tabUrl);

    const chk = document.getElementById('chk-favorite');
    expect(chk.checked).toBe(true);
    expect(chk.disabled).toBe(false);
  });

  test('status fetch resolves is_favorite=false: checkbox becomes unchecked and enabled', async () => {
    renderCheckboxFixture();
    global.fetch = mockFetchRouter([
      ['/api/favorite/status', () => jsonResponse({ is_favorite: false })],
    ]);

    await popup.initFavoriteToggle(airchivistUrl, tabUrl);

    const chk = document.getElementById('chk-favorite');
    expect(chk.checked).toBe(false);
    expect(chk.disabled).toBe(false);
  });

  test('status fetch rejects: checkbox stays disabled', async () => {
    renderCheckboxFixture();
    global.fetch = mockFetchRouter([
      ['/api/favorite/status', () => Promise.reject(new Error('network fail'))],
    ]);

    await popup.initFavoriteToggle(airchivistUrl, tabUrl);

    const chk = document.getElementById('chk-favorite');
    expect(chk.disabled).toBe(true);
  });

  test('toggle on, /add succeeds: stays checked, re-enabled, no error', async () => {
    renderCheckboxFixture();
    global.fetch = mockFetchRouter([
      ['/api/favorite/status', () => jsonResponse({ is_favorite: false })],
      ['/api/favorite/add', () => jsonResponse({ status: 'added' })],
    ]);
    await popup.initFavoriteToggle(airchivistUrl, tabUrl);

    const chk = document.getElementById('chk-favorite');
    const errBox = document.getElementById('fav-error');
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
      ['/api/favorite/status', () => jsonResponse({ is_favorite: true })],
      ['/api/favorite/remove', () => jsonResponse({ status: 'removed' })],
    ]);
    await popup.initFavoriteToggle(airchivistUrl, tabUrl);

    const chk = document.getElementById('chk-favorite');
    const errBox = document.getElementById('fav-error');
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
      ['/api/favorite/status', () => jsonResponse({ is_favorite: false })],
      ['/api/favorite/add', () => Promise.reject(new Error('network fail'))],
    ]);
    await popup.initFavoriteToggle(airchivistUrl, tabUrl);

    const chk = document.getElementById('chk-favorite');
    const errBox = document.getElementById('fav-error');
    chk.checked = true;
    chk.dispatchEvent(new Event('change'));
    await flushPromises();

    expect(chk.checked).toBe(false);
    expect(chk.disabled).toBe(false);
    expect(errBox.style.display).toBe('block');
    expect(errBox.textContent).toBe('✗ Favorite update failed');
  });

  test('toggle off, /remove returns error status: treated as failure, reverts to checked', async () => {
    renderCheckboxFixture();
    global.fetch = mockFetchRouter([
      ['/api/favorite/status', () => jsonResponse({ is_favorite: true })],
      ['/api/favorite/remove', () => jsonResponse({ status: 'error', error: 'Video not found' })],
    ]);
    await popup.initFavoriteToggle(airchivistUrl, tabUrl);

    const chk = document.getElementById('chk-favorite');
    const errBox = document.getElementById('fav-error');
    chk.checked = false;
    chk.dispatchEvent(new Event('change'));
    await flushPromises();

    expect(chk.checked).toBe(true);
    expect(errBox.style.display).toBe('block');
  });
});

describe('initToggle', () => {
  const airchivistUrl = 'http://localhost:8080';
  const tabUrl = 'https://www.youtube.com/watch?v=abc123';

  test('is exported and drives an arbitrary checkbox/endpoint pair', async () => {
    document.getElementById('root').innerHTML = `
      <input type="checkbox" id="chk-generic" disabled>
      <div id="generic-error" style="display:none"></div>
    `;
    global.fetch = mockFetchRouter([
      ['/api/thing/status', () => jsonResponse({ on: true })],
    ]);

    await popup.initToggle({
      checkboxId: 'chk-generic',
      errorBoxId: 'generic-error',
      statusPath: '/api/thing/status',
      statusKey: 'on',
      addPath: '/api/thing/add',
      removePath: '/api/thing/remove',
      addSuccessStatuses: ['added'],
      errorLabel: '✗ Thing update failed',
      airchivistUrl,
      tabUrl,
    });

    const chk = document.getElementById('chk-generic');
    expect(chk.checked).toBe(true);
    expect(chk.disabled).toBe(false);
  });

  test('a failed toggle reverts the checkbox and shows the configured label', async () => {
    document.getElementById('root').innerHTML = `
      <input type="checkbox" id="chk-generic" disabled>
      <div id="generic-error" style="display:none"></div>
    `;
    global.fetch = mockFetchRouter([
      ['/api/thing/status', () => jsonResponse({ on: false })],
      ['/api/thing/add', () => jsonResponse({ status: 'error' })],
    ]);

    await popup.initToggle({
      checkboxId: 'chk-generic',
      errorBoxId: 'generic-error',
      statusPath: '/api/thing/status',
      statusKey: 'on',
      addPath: '/api/thing/add',
      removePath: '/api/thing/remove',
      addSuccessStatuses: ['added'],
      errorLabel: '✗ Thing update failed',
      airchivistUrl,
      tabUrl,
    });

    const chk = document.getElementById('chk-generic');
    chk.checked = true;
    chk.dispatchEvent(new Event('change'));
    await flushPromises();

    expect(chk.checked).toBe(false);
    expect(chk.disabled).toBe(false);
    expect(document.getElementById('generic-error').textContent).toContain('Thing update failed');
  });
});


describe('doAddChannel', () => {
  const airchivistUrl = 'http://localhost:8080';
  const channelUrl = 'https://www.youtube.com/@someone';

  test('bookmarks and adds, reporting the channel name the server returned', async () => {
    global.fetch = mockFetchRouter([
      ['/api/channel/add', () => jsonResponse({ status: 'added', channel_name: 'Some Channel' })],
    ]);
    await popup.doAddChannel(airchivistUrl, channelUrl, 'Tab Title');
    const body = document.getElementById('root').innerHTML;
    expect(body).toContain('Some Channel');
    expect(global.browser.bookmarks.create).toHaveBeenCalledWith(
      expect.objectContaining({ url: channelUrl, title: 'Tab Title' })
    );
  });

  test('falls back to the tab title when the server sends no channel name', async () => {
    global.fetch = mockFetchRouter([
      ['/api/channel/add', () => jsonResponse({ status: 'added' })],
    ]);
    await popup.doAddChannel(airchivistUrl, channelUrl, 'Tab Title');
    expect(document.getElementById('root').innerHTML).toContain('Tab Title');
  });

  test('treats an already-tracked channel as success', async () => {
    global.fetch = mockFetchRouter([
      ['/api/channel/add', () => jsonResponse({ status: 'exists', channel_name: 'Some Channel' })],
    ]);
    await popup.doAddChannel(airchivistUrl, channelUrl, 'Tab Title');
    expect(document.getElementById('root').innerHTML).toContain('status success');
  });

  test('an unreachable server still leaves the browser bookmark created', async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error('Failed to fetch'));
    await popup.doAddChannel(airchivistUrl, channelUrl, 'Tab Title');
    expect(global.browser.bookmarks.create).toHaveBeenCalled();
    expect(document.getElementById('root').innerHTML).toContain('Airchivist');
  });

  test('escapes a channel name containing markup', async () => {
    global.fetch = mockFetchRouter([
      ['/api/channel/add', () => jsonResponse({ status: 'added', channel_name: '<img src=x>' })],
    ]);
    await popup.doAddChannel(airchivistUrl, channelUrl, 'Tab Title');
    const body = document.getElementById('root').innerHTML;
    expect(body).not.toContain('<img src=x>');
    expect(body).toContain('&lt;img');
  });
});

describe('doHide', () => {
  const airchivistUrl = 'http://localhost:8080';
  const tabUrl = 'https://www.youtube.com/watch?v=abc123';

  test('reports the archived title on success', async () => {
    global.fetch = mockFetchRouter([
      ['/api/hide', () => jsonResponse({ status: 'hidden', title: 'Some Video' })],
    ]);
    await popup.doHide(airchivistUrl, tabUrl, false);
    expect(document.getElementById('root').innerHTML).toContain('Some Video');
  });

  test('leaves browser bookmarks alone when the checkbox is unticked', async () => {
    global.fetch = mockFetchRouter([
      ['/api/hide', () => jsonResponse({ status: 'hidden', title: 'Some Video' })],
    ]);
    await popup.doHide(airchivistUrl, tabUrl, false);
    expect(global.browser.bookmarks.remove).not.toHaveBeenCalled();
  });

  test('removes every matching bookmark when the checkbox is ticked', async () => {
    global.browser.bookmarks.search.mockResolvedValue([{ id: 'b1' }, { id: 'b2' }]);
    global.fetch = mockFetchRouter([
      ['/api/hide', () => jsonResponse({ status: 'hidden', title: 'Some Video' })],
    ]);
    await popup.doHide(airchivistUrl, tabUrl, true);
    expect(global.browser.bookmarks.remove).toHaveBeenCalledTimes(2);
  });

  test('does not touch bookmarks when the archive itself failed', async () => {
    // Removing the bookmark for a video that is still in the library would lose
    // the only pointer the user has to it.
    global.browser.bookmarks.search.mockResolvedValue([{ id: 'b1' }]);
    global.fetch = mockFetchRouter([
      ['/api/hide', () => jsonResponse({ status: 'error', error: 'Video not found' })],
    ]);
    await popup.doHide(airchivistUrl, tabUrl, true);
    expect(global.browser.bookmarks.remove).not.toHaveBeenCalled();
    expect(document.getElementById('root').innerHTML).toContain('Video not found');
  });

  test('an unreachable server reports it and touches nothing', async () => {
    global.browser.bookmarks.search.mockResolvedValue([{ id: 'b1' }]);
    global.fetch = jest.fn().mockRejectedValue(new Error('Failed to fetch'));
    await popup.doHide(airchivistUrl, tabUrl, true);
    expect(global.browser.bookmarks.remove).not.toHaveBeenCalled();
    expect(document.getElementById('root').innerHTML).toContain('unreachable');
  });
});

describe('doRestore and doDelete', () => {
  const airchivistUrl = 'http://localhost:8080';

  test('restore posts to the unhide route and closes the popup', async () => {
    global.fetch = jest.fn().mockResolvedValue({ json: () => Promise.resolve({}) });
    await popup.doRestore(airchivistUrl, 'abc123');
    expect(global.fetch).toHaveBeenCalledWith(
      `${airchivistUrl}/videos/abc123/unhide`, { method: 'POST' }
    );
    expect(document.getElementById('root').innerHTML).toContain('Restored');
    jest.advanceTimersByTime(1500);
    expect(global.window.close).toHaveBeenCalled();
  });

  test('delete posts to the delete route and closes the popup', async () => {
    global.fetch = jest.fn().mockResolvedValue({ json: () => Promise.resolve({}) });
    await popup.doDelete(airchivistUrl, 'abc123');
    expect(global.fetch).toHaveBeenCalledWith(
      `${airchivistUrl}/videos/abc123/delete`, { method: 'POST' }
    );
    expect(document.getElementById('root').innerHTML).toContain('Deleted');
    jest.advanceTimersByTime(1500);
    expect(global.window.close).toHaveBeenCalled();
  });

  test('the popup does not close before the delay elapses', async () => {
    global.fetch = jest.fn().mockResolvedValue({ json: () => Promise.resolve({}) });
    await popup.doDelete(airchivistUrl, 'abc123');
    jest.advanceTimersByTime(1499);
    expect(global.window.close).not.toHaveBeenCalled();
  });
});

describe('renderState', () => {
  const airchivistUrl = 'http://localhost:8080';
  const tabUrl = 'https://www.youtube.com/watch?v=abc123';
  let root;

  beforeEach(() => {
    root = document.getElementById('root');
  });

  test('not_found offers an add button and two opt-in checkboxes', () => {
    popup.renderState(root, airchivistUrl, tabUrl, 'T', { status: 'not_found' });
    expect(document.getElementById('btn-add')).toBeTruthy();
    expect(document.getElementById('chk-watch-later').checked).toBe(false);
    expect(document.getElementById('chk-favorite').checked).toBe(false);
  });

  test('clicking add passes both checkbox states through', async () => {
    global.fetch = mockFetchRouter([
      ['/api/add', () => jsonResponse({ status: 'added', title: 'T' })],
      ['/api/watch-later/add', () => jsonResponse({ status: 'added' })],
      ['/api/favorite/add', () => jsonResponse({ status: 'added' })],
    ]);
    popup.renderState(root, airchivistUrl, tabUrl, 'T', { status: 'not_found' });
    document.getElementById('chk-watch-later').checked = true;
    document.getElementById('chk-favorite').checked = true;
    document.getElementById('btn-add').click();
    await flushPromises();
    const called = global.fetch.mock.calls.map(c => c[0]);
    expect(called.some(u => u.includes('/api/watch-later/add'))).toBe(true);
    expect(called.some(u => u.includes('/api/favorite/add'))).toBe(true);
  });

  test('exists shows the title, an Archive button, and three checkboxes', async () => {
    global.fetch = mockFetchRouter([
      ['/api/watch-later/status', () => jsonResponse({ in_queue: false })],
      ['/api/favorite/status', () => jsonResponse({ is_favorite: false })],
    ]);
    popup.renderState(root, airchivistUrl, tabUrl, 'T', { status: 'exists', title: 'Some Video' });
    await flushPromises();
    expect(root.innerHTML).toContain('Some Video');
    expect(document.getElementById('btn-hide')).toBeTruthy();
    expect(document.getElementById('chk-unbookmark')).toBeTruthy();
    // Both toggles resolved their status, so both are now interactive.
    expect(document.getElementById('chk-watch-later').disabled).toBe(false);
    expect(document.getElementById('chk-favorite').disabled).toBe(false);
  });

  test('exists reflects a video already queued and favorited', async () => {
    global.fetch = mockFetchRouter([
      ['/api/watch-later/status', () => jsonResponse({ in_queue: true })],
      ['/api/favorite/status', () => jsonResponse({ is_favorite: true })],
    ]);
    popup.renderState(root, airchivistUrl, tabUrl, 'T', { status: 'exists', title: 'V' });
    await flushPromises();
    expect(document.getElementById('chk-watch-later').checked).toBe(true);
    expect(document.getElementById('chk-favorite').checked).toBe(true);
  });

  test('clicking Archive passes the unbookmark checkbox through', async () => {
    global.fetch = mockFetchRouter([
      ['/api/watch-later/status', () => jsonResponse({ in_queue: false })],
      ['/api/favorite/status', () => jsonResponse({ is_favorite: false })],
      ['/api/hide', () => jsonResponse({ status: 'hidden', title: 'V' })],
    ]);
    global.browser.bookmarks.search.mockResolvedValue([{ id: 'b1' }]);
    popup.renderState(root, airchivistUrl, tabUrl, 'T', { status: 'exists', title: 'V' });
    await flushPromises();
    document.getElementById('chk-unbookmark').checked = true;
    document.getElementById('btn-hide').click();
    await flushPromises();
    expect(global.browser.bookmarks.remove).toHaveBeenCalledWith('b1');
  });

  test('hidden offers Restore and Delete wired to the video id', () => {
    popup.renderState(root, airchivistUrl, tabUrl, 'T', {
      status: 'hidden', title: 'V', video_id: 'abc123',
    });
    expect(root.innerHTML).toContain('Archived');
    expect(document.getElementById('btn-restore')).toBeTruthy();
    expect(document.getElementById('btn-delete')).toBeTruthy();
  });

  test('an unrecognized status shows the error the server sent', () => {
    popup.renderState(root, airchivistUrl, tabUrl, 'T', {
      status: 'error', error: 'Not a YouTube URL',
    });
    expect(root.innerHTML).toContain('Not a YouTube URL');
  });

  test('an unrecognized status with no error message still says something', () => {
    popup.renderState(root, airchivistUrl, tabUrl, 'T', { status: 'weird' });
    expect(root.innerHTML).toContain('Unknown error');
  });

  test('escapes a title containing markup', () => {
    popup.renderState(root, airchivistUrl, tabUrl, 'T', {
      status: 'hidden', title: '<script>x</script>', video_id: 'abc123',
    });
    expect(root.innerHTML).not.toContain('<script>');
  });
});

describe('renderChannelState', () => {
  const airchivistUrl = 'http://localhost:8080';
  const channelUrl = 'https://www.youtube.com/@someone';
  let root;

  beforeEach(() => {
    root = document.getElementById('root');
  });

  test('exists reports the tracked channel name', () => {
    popup.renderChannelState(root, airchivistUrl, channelUrl, 'T', {
      status: 'exists', channel_name: 'Some Channel',
    });
    expect(root.innerHTML).toContain('Some Channel');
    expect(document.getElementById('btn-add-channel')).toBeNull();
  });

  test('not_found offers an add button', () => {
    popup.renderChannelState(root, airchivistUrl, channelUrl, 'T', { status: 'not_found' });
    expect(document.getElementById('btn-add-channel')).toBeTruthy();
  });

  test('clicking add posts the channel URL', async () => {
    global.fetch = mockFetchRouter([
      ['/api/channel/add', () => jsonResponse({ status: 'added', channel_name: 'C' })],
    ]);
    popup.renderChannelState(root, airchivistUrl, channelUrl, 'T', { status: 'not_found' });
    document.getElementById('btn-add-channel').click();
    await flushPromises();
    expect(global.fetch.mock.calls[0][0]).toContain('/api/channel/add');
  });

  test('an error status shows the message', () => {
    popup.renderChannelState(root, airchivistUrl, channelUrl, 'T', {
      status: 'error', error: 'Not a channel URL',
    });
    expect(root.innerHTML).toContain('Not a channel URL');
  });

  test('escapes a channel name containing markup', () => {
    popup.renderChannelState(root, airchivistUrl, channelUrl, 'T', {
      status: 'exists', channel_name: '<img src=x>',
    });
    expect(root.innerHTML).not.toContain('<img src=x>');
  });
});

describe('run', () => {
  const airchivistUrl = 'http://localhost:8080';
  // A real 11-character id: run() is the only function that checks YT_ID_RE, so a
  // short placeholder here reads as "not a YouTube video" rather than exercising
  // the video path.

  function onTab(url, title = 'Tab Title') {
    global.browser.tabs.query.mockResolvedValue([{ url, title }]);
  }

  test('a video tab renders the video state', async () => {
    onTab('https://www.youtube.com/watch?v=aaaaaaaaaa1');
    global.fetch = mockFetchRouter([
      ['/api/status', () => jsonResponse({ status: 'not_found' })],
    ]);
    await popup.run();
    expect(document.getElementById('btn-add')).toBeTruthy();
  });

  test('a channel tab renders the channel state', async () => {
    onTab('https://www.youtube.com/@someone');
    global.fetch = mockFetchRouter([
      ['/api/channel/status', () => jsonResponse({ status: 'not_found' })],
    ]);
    await popup.run();
    expect(document.getElementById('btn-add-channel')).toBeTruthy();
  });

  test('a non-YouTube tab says so without calling the server', async () => {
    onTab('https://example.com/');
    global.fetch = jest.fn();
    await popup.run();
    expect(document.getElementById('root').innerHTML).toContain('Not a YouTube video or channel');
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test('a tab with no URL is treated as unsupported rather than crashing', async () => {
    global.browser.tabs.query.mockResolvedValue([{}]);
    global.fetch = jest.fn();
    await expect(popup.run()).resolves.toBeUndefined();
    expect(document.getElementById('root').innerHTML).toContain('Not a YouTube');
  });

  test('uses the configured Airchivist URL over the default', async () => {
    onTab('https://www.youtube.com/watch?v=aaaaaaaaaa1');
    global.browser.storage.local.get.mockResolvedValue({ airchivistUrl: 'http://host.test:9999' });
    global.fetch = mockFetchRouter([
      ['host.test:9999', () => jsonResponse({ status: 'not_found' })],
    ]);
    await popup.run();
    expect(global.fetch.mock.calls[0][0]).toContain('host.test:9999');
  });

  test('an unreachable server on a video tab names the URL it tried', async () => {
    onTab('https://www.youtube.com/watch?v=aaaaaaaaaa1');
    global.fetch = jest.fn().mockRejectedValue(new Error('Failed to fetch'));
    await popup.run();
    const body = document.getElementById('root').innerHTML;
    expect(body).toContain('unreachable');
    expect(body).toContain(airchivistUrl);
  });

  test('an unreachable server on a channel tab reports it too', async () => {
    onTab('https://www.youtube.com/@someone');
    global.fetch = jest.fn().mockRejectedValue(new Error('Failed to fetch'));
    await popup.run();
    expect(document.getElementById('root').innerHTML).toContain('unreachable');
  });
});

describe('doAddChannel partial failures', () => {
  const airchivistUrl = 'http://localhost:8080';
  const channelUrl = 'https://www.youtube.com/@someone';

  test('bookmark failed but Airchivist succeeded reads as partial', async () => {
    global.browser.bookmarks.create.mockRejectedValue(new Error('quota reached'));
    global.fetch = mockFetchRouter([
      ['/api/channel/add', () => jsonResponse({ status: 'added', channel_name: 'C' })],
    ]);
    await popup.doAddChannel(airchivistUrl, channelUrl, 'T');
    const body = document.getElementById('root').innerHTML;
    expect(body).toContain('status partial');
    expect(body).toContain('quota reached');
    expect(body).toContain('Added to Airchivist');
  });

  test('Airchivist returned an error, surfaced verbatim', async () => {
    global.fetch = mockFetchRouter([
      ['/api/channel/add', () => jsonResponse({ status: 'error', error: 'Not a channel URL' })],
    ]);
    await popup.doAddChannel(airchivistUrl, channelUrl, 'T');
    const body = document.getElementById('root').innerHTML;
    expect(body).toContain('Not a channel URL');
    expect(body).toContain('Bookmarked in Firefox');  // the bookmark still worked
  });

  test('both failed reads as error, not partial', async () => {
    global.browser.bookmarks.create.mockRejectedValue(new Error('quota reached'));
    global.fetch = jest.fn().mockRejectedValue(new Error('Failed to fetch'));
    await popup.doAddChannel(airchivistUrl, channelUrl, 'T');
    const body = document.getElementById('root').innerHTML;
    expect(body).toContain('status error');
    expect(body).not.toContain('status partial');
  });
});

describe('getOrCreateFolder', () => {
  test('reuses a cached folder id when it still exists', async () => {
    global.browser.storage.local.get.mockResolvedValue({ bookmarkFolderId: 'cached1' });
    global.browser.bookmarks.get.mockResolvedValue([{ id: 'cached1' }]);
    expect(await popup.getOrCreateFolder()).toBe('cached1');
    expect(global.browser.bookmarks.create).not.toHaveBeenCalled();
  });

  test('recreates the folder when the cached id was deleted', async () => {
    global.browser.storage.local.get.mockResolvedValue({ bookmarkFolderId: 'stale1' });
    global.browser.bookmarks.get.mockRejectedValue(new Error('not found'));
    global.browser.bookmarks.search.mockResolvedValue([]);
    global.browser.bookmarks.create.mockResolvedValue({ id: 'new1' });
    expect(await popup.getOrCreateFolder()).toBe('new1');
  });

  test('adopts an existing folder of the right name over creating a second', async () => {
    global.browser.storage.local.get.mockResolvedValue({});
    global.browser.bookmarks.search.mockResolvedValue([
      { id: 'bookmarkNotFolder', url: 'https://example.com' },  // has a url — not a folder
      { id: 'folder1' },
    ]);
    expect(await popup.getOrCreateFolder()).toBe('folder1');
    expect(global.browser.bookmarks.create).not.toHaveBeenCalled();
    expect(global.browser.storage.local.set).toHaveBeenCalledWith({ bookmarkFolderId: 'folder1' });
  });
});

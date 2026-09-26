const { flushPromises } = require('./setup');

let content;

// jsdom gives every test the same document; `location` is not writable, so each
// test declares the page it is on through this helper instead.
function setLocation(href) {
  delete global.window.location;
  global.window.location = new URL(href);
}

beforeEach(() => {
  jest.resetModules();
  document.body.innerHTML = '';
  setLocation('https://www.youtube.com/');
  global.browser = { runtime: { sendMessage: jest.fn().mockResolvedValue({}) } };
  content = require('../../extension/content/content.js');
});

describe('module exports', () => {
  test('exports the functions a test needs to drive', () => {
    for (const name of [
      'extractId', 'channelUrlFrom', 'waitFor',
      'checkCurrentVideo', 'checkCurrentChannel', 'scanRelated', 'run',
    ]) {
      expect(typeof content[name]).toBe('function');
    }
  });

  test('does not run or bind navigation handlers when required as a module', () => {
    // The script's bottom calls run() immediately when readyState isn't 'loading'.
    // Under require that must not happen, or importing the module would fire a
    // sendMessage before the test has set up the page.
    expect(global.browser.runtime.sendMessage).not.toHaveBeenCalled();
  });
});

describe('extractId', () => {
  test.each([
    ['https://www.youtube.com/watch?v=aaaaaaaaaa1', 'aaaaaaaaaa1'],
    ['https://www.youtube.com/watch?list=PL1&v=bbbbbbbbbb2', 'bbbbbbbbbb2'],
    ['https://www.youtube.com/watch?v=cccccccccc3&t=90s', 'cccccccccc3'],
  ])('%s → %s', (url, expected) => {
    expect(content.extractId(url)).toBe(expected);
  });

  test.each([
    ['https://www.youtube.com/'],
    ['https://www.youtube.com/@someone'],
    ['https://www.youtube.com/watch?v=tooshort'],
  ])('%s → null', (url) => {
    expect(content.extractId(url)).toBeNull();
  });

  test('takes the first 11 characters of an over-long v=, matching the backend', () => {
    // Not a rounding error in the test: none of the three ID regexes in this
    // project (here, popup.js, crawler/models.py YT_ID_RE) anchor the end of the
    // 11-character group, so all three read the first 11 characters of a 12-char
    // value. Verified against the backend's extract_video_id, which returns the
    // same prefix. YouTube never emits a v= of any other length, so this is
    // unreachable in practice — pinned here so a future "fix" to one regex has to
    // be a deliberate change to all three rather than a silent divergence.
    expect(content.extractId('https://www.youtube.com/watch?v=abcdefghijkl')).toBe('abcdefghijk');
  });
});

describe('channelUrlFrom', () => {
  test.each([
    ['https://www.youtube.com/@someone', 'https://www.youtube.com/@someone'],
    ['https://www.youtube.com/channel/UCabc123', 'https://www.youtube.com/channel/UCabc123'],
    ['https://www.youtube.com/c/SomeName', 'https://www.youtube.com/c/SomeName'],
    ['https://www.youtube.com/user/SomeName', 'https://www.youtube.com/user/SomeName'],
  ])('%s → canonical %s', (href, expected) => {
    const m = /youtube\.com\/(channel\/UC[A-Za-z0-9_-]+|(?:c|user)\/[^/?#]+|@[^/?#]+)/.exec(href);
    expect(content.channelUrlFrom(m)).toBe(expected);
  });

  test('strips a trailing path such as /videos', () => {
    const m = /youtube\.com\/(channel\/UC[A-Za-z0-9_-]+|(?:c|user)\/[^/?#]+|@[^/?#]+)/
      .exec('https://www.youtube.com/@someone/videos');
    expect(content.channelUrlFrom(m)).toBe('https://www.youtube.com/@someone');
  });
});

describe('waitFor', () => {
  test('resolves immediately when the element is already present', async () => {
    document.body.innerHTML = '<div id="target"></div>';
    await expect(content.waitFor('#target')).resolves.toBe(document.getElementById('target'));
  });

  test('resolves once the element is inserted later', async () => {
    const promise = content.waitFor('#late');
    document.body.innerHTML = '<div id="late"></div>';
    await expect(promise).resolves.toBeTruthy();
  });

  test('resolves to null on timeout rather than hanging', async () => {
    const promise = content.waitFor('#never', document, 5000);
    jest.advanceTimersByTime(5000);
    await expect(promise).resolves.toBeNull();
  });
});

describe('checkCurrentVideo', () => {
  const VIDEO_URL = 'https://www.youtube.com/watch?v=aaaaaaaaaa1';

  function withTitle(text = 'Some Video') {
    document.body.innerHTML = `
      <div id="above-the-fold"><div><h1>${text}</h1></div></div>
    `;
    return document.querySelector('#above-the-fold > div:nth-child(1) h1');
  }

  test('tints the title green when the video is in the library', async () => {
    setLocation(VIDEO_URL);
    const h1 = withTitle();
    global.browser.runtime.sendMessage.mockResolvedValue({ status: 'exists' });
    await content.checkCurrentVideo();
    expect(h1.style.color).toBe('rgb(56, 142, 60)');
  });

  test('tints the title red when the video is archived', async () => {
    setLocation(VIDEO_URL);
    const h1 = withTitle();
    global.browser.runtime.sendMessage.mockResolvedValue({ status: 'hidden' });
    await content.checkCurrentVideo();
    expect(h1.style.color).toBe('rgb(229, 57, 53)');
  });

  test('leaves the title alone for an unknown video', async () => {
    setLocation(VIDEO_URL);
    const h1 = withTitle();
    global.browser.runtime.sendMessage.mockResolvedValue({ status: 'not_found' });
    await content.checkCurrentVideo();
    expect(h1.style.color).toBe('');
  });

  test('clears a stale color from the previous video before checking', async () => {
    setLocation(VIDEO_URL);
    const h1 = withTitle();
    h1.style.color = 'rgb(56, 142, 60)';  // left over from the last video
    global.browser.runtime.sendMessage.mockResolvedValue({ status: 'not_found' });
    await content.checkCurrentVideo();
    expect(h1.style.color).toBe('');
  });

  test('does nothing when the page is not a watch page', async () => {
    setLocation('https://www.youtube.com/feed/subscriptions');
    withTitle();
    await content.checkCurrentVideo();
    expect(global.browser.runtime.sendMessage).not.toHaveBeenCalled();
  });

  test('does not tint if SPA navigation moved to another video mid-flight', async () => {
    setLocation(VIDEO_URL);
    const h1 = withTitle();
    global.browser.runtime.sendMessage.mockImplementation(() => {
      setLocation('https://www.youtube.com/watch?v=zzzzzzzzzz9');
      return Promise.resolve({ status: 'exists' });
    });
    await content.checkCurrentVideo();
    expect(h1.style.color).toBe('');
  });

  test('an unreachable Airchivist leaves the page untouched', async () => {
    setLocation(VIDEO_URL);
    const h1 = withTitle();
    global.browser.runtime.sendMessage.mockRejectedValue(new Error('no connection'));
    await expect(content.checkCurrentVideo()).resolves.toBeUndefined();
    expect(h1.style.color).toBe('');
  });
});

describe('checkCurrentChannel', () => {
  const CHANNEL_URL = 'https://www.youtube.com/@someone';

  function withChannelTitle(text = 'Some Channel') {
    document.body.innerHTML = `<yt-page-header-renderer><h1>${text}</h1></yt-page-header-renderer>`;
    return document.querySelector('yt-page-header-renderer h1');
  }

  test('tints the channel title green when the channel is bookmarked', async () => {
    setLocation(CHANNEL_URL);
    const h1 = withChannelTitle();
    global.browser.runtime.sendMessage.mockResolvedValue({ status: 'exists' });
    await content.checkCurrentChannel();
    expect(h1.style.color).toBe('rgb(56, 142, 60)');
  });

  test('sends the canonical channel URL, not the current page URL', async () => {
    setLocation(`${CHANNEL_URL}/videos?view=0`);
    withChannelTitle();
    global.browser.runtime.sendMessage.mockResolvedValue({ status: 'exists' });
    await content.checkCurrentChannel();
    expect(global.browser.runtime.sendMessage).toHaveBeenCalledWith({
      action: 'fetchChannelStatus',
      url: CHANNEL_URL,
    });
  });

  test('leaves the title alone when the channel is unknown', async () => {
    setLocation(CHANNEL_URL);
    const h1 = withChannelTitle();
    global.browser.runtime.sendMessage.mockResolvedValue({ status: 'not_found' });
    await content.checkCurrentChannel();
    expect(h1.style.color).toBe('');
  });

  test('does nothing on a non-channel page', async () => {
    setLocation('https://www.youtube.com/watch?v=aaaaaaaaaa1');
    withChannelTitle();
    await content.checkCurrentChannel();
    expect(global.browser.runtime.sendMessage).not.toHaveBeenCalled();
  });

  test('does not tint if navigation moved to a different channel mid-flight', async () => {
    setLocation(CHANNEL_URL);
    const h1 = withChannelTitle();
    global.browser.runtime.sendMessage.mockImplementation(() => {
      setLocation('https://www.youtube.com/@someoneelse');
      return Promise.resolve({ status: 'exists' });
    });
    await content.checkCurrentChannel();
    expect(h1.style.color).toBe('');
  });

  test('gives up quietly when no title element ever appears', async () => {
    setLocation(CHANNEL_URL);
    document.body.innerHTML = '';
    const promise = content.checkCurrentChannel();
    jest.advanceTimersByTime(5000);
    await expect(promise).resolves.toBeUndefined();
    expect(global.browser.runtime.sendMessage).not.toHaveBeenCalled();
  });
});

describe('scanRelated', () => {
  function withCards(...ids) {
    document.body.innerHTML = ids.map(id => `
      <yt-lockup-view-model>
        <a href="https://www.youtube.com/watch?v=${id}"></a>
        <yt-lockup-metadata-view-model><h3><a>Title ${id}</a></h3></yt-lockup-metadata-view-model>
      </yt-lockup-view-model>
    `).join('');
    return [...document.querySelectorAll('yt-lockup-view-model')];
  }

  test('tints each card according to its own status', async () => {
    const [a, b] = withCards('aaaaaaaaaa1', 'bbbbbbbbbb2');
    global.browser.runtime.sendMessage.mockResolvedValue({
      aaaaaaaaaa1: 'exists',
      bbbbbbbbbb2: 'hidden',
    });
    await content.scanRelated();
    expect(a.querySelector('h3 a').style.color).toBe('rgb(56, 142, 60)');
    expect(b.querySelector('h3 a').style.color).toBe('rgb(229, 57, 53)');
  });

  test('batches every unchecked id into one message', async () => {
    withCards('aaaaaaaaaa1', 'bbbbbbbbbb2', 'cccccccccc3');
    await content.scanRelated();
    expect(global.browser.runtime.sendMessage).toHaveBeenCalledTimes(1);
    expect(global.browser.runtime.sendMessage.mock.calls[0][0].ids).toEqual([
      'aaaaaaaaaa1', 'bbbbbbbbbb2', 'cccccccccc3',
    ]);
  });

  test('marks cards checked so a second scan does not re-query them', async () => {
    withCards('aaaaaaaaaa1');
    await content.scanRelated();
    await content.scanRelated();
    expect(global.browser.runtime.sendMessage).toHaveBeenCalledTimes(1);
  });

  test('sends nothing when there are no cards', async () => {
    await content.scanRelated();
    expect(global.browser.runtime.sendMessage).not.toHaveBeenCalled();
  });

  test('ignores a card with no watch link', async () => {
    document.body.innerHTML = '<yt-lockup-view-model><h3>No link</h3></yt-lockup-view-model>';
    await content.scanRelated();
    expect(global.browser.runtime.sendMessage).not.toHaveBeenCalled();
  });

  test('leaves a card untinted when its id is absent from the response', async () => {
    const [a] = withCards('aaaaaaaaaa1');
    global.browser.runtime.sendMessage.mockResolvedValue({});
    await content.scanRelated();
    expect(a.querySelector('h3 a').style.color).toBe('');
  });

  test('an unreachable Airchivist leaves every card untouched and unmarked', async () => {
    const [a] = withCards('aaaaaaaaaa1');
    global.browser.runtime.sendMessage.mockRejectedValue(new Error('no connection'));
    await content.scanRelated();
    expect(a.querySelector('h3 a').style.color).toBe('');
    // Not marked checked, so a later scan retries once the server is back.
    expect(a.dataset.vtChecked).toBeUndefined();
  });

  test('also handles the older ytd-compact-video-renderer card markup', async () => {
    document.body.innerHTML = `
      <ytd-compact-video-renderer>
        <a href="https://www.youtube.com/watch?v=aaaaaaaaaa1"></a>
        <div id="meta"><h3><a>Old markup</a></h3></div>
      </ytd-compact-video-renderer>
    `;
    global.browser.runtime.sendMessage.mockResolvedValue({ aaaaaaaaaa1: 'exists' });
    await content.scanRelated();
    expect(document.querySelector('#meta h3 a').style.color).toBe('rgb(56, 142, 60)');
  });
});

describe('run', () => {
  test('on a watch page, checks the current video', async () => {
    setLocation('https://www.youtube.com/watch?v=aaaaaaaaaa1');
    document.body.innerHTML = '<div id="above-the-fold"><div><h1>T</h1></div></div>';
    content.run();
    await flushPromises();
    expect(global.browser.runtime.sendMessage).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'fetchStatus' })
    );
  });

  test('on a channel page, checks the channel and not the video', async () => {
    setLocation('https://www.youtube.com/@someone');
    document.body.innerHTML = '<yt-page-header-renderer><h1>C</h1></yt-page-header-renderer>';
    content.run();
    await flushPromises();
    const actions = global.browser.runtime.sendMessage.mock.calls.map(c => c[0].action);
    expect(actions).toContain('fetchChannelStatus');
    expect(actions).not.toContain('fetchStatus');
  });

  test('on an unrelated page, sends nothing', async () => {
    setLocation('https://www.youtube.com/feed/subscriptions');
    content.run();
    await flushPromises();
    expect(global.browser.runtime.sendMessage).not.toHaveBeenCalled();
  });
});

describe('watchRelated', () => {
  function withContainerAndCard(id = 'aaaaaaaaaa1') {
    document.body.innerHTML = `
      <div id="secondary">
        <yt-lockup-view-model>
          <a href="https://www.youtube.com/watch?v=${id}"></a>
          <yt-lockup-metadata-view-model><h3><a>Title</a></h3></yt-lockup-metadata-view-model>
        </yt-lockup-view-model>
      </div>
    `;
  }

  test('scans once as soon as the sidebar is present', async () => {
    withContainerAndCard();
    content.watchRelated();
    await flushPromises();
    expect(global.browser.runtime.sendMessage).toHaveBeenCalledTimes(1);
  });

  test('a later mutation triggers a rescan after the debounce elapses', async () => {
    withContainerAndCard();
    content.watchRelated();
    await flushPromises();
    global.browser.runtime.sendMessage.mockClear();

    // A new card arrives, as it does when YouTube lazy-loads more related videos.
    document.getElementById('secondary').insertAdjacentHTML('beforeend', `
      <yt-lockup-view-model>
        <a href="https://www.youtube.com/watch?v=bbbbbbbbbb2"></a>
        <yt-lockup-metadata-view-model><h3><a>Two</a></h3></yt-lockup-metadata-view-model>
      </yt-lockup-view-model>
    `);
    await flushPromises();
    expect(global.browser.runtime.sendMessage).not.toHaveBeenCalled();  // still debouncing
    jest.advanceTimersByTime(400);
    await flushPromises();
    expect(global.browser.runtime.sendMessage).toHaveBeenCalledTimes(1);
  });

  test('a burst of mutations coalesces into a single rescan', async () => {
    withContainerAndCard();
    content.watchRelated();
    await flushPromises();
    global.browser.runtime.sendMessage.mockClear();

    const secondary = document.getElementById('secondary');
    for (let i = 0; i < 5; i++) {
      secondary.insertAdjacentHTML('beforeend', `
        <yt-lockup-view-model>
          <a href="https://www.youtube.com/watch?v=cccccccccc${i}"></a>
          <yt-lockup-metadata-view-model><h3><a>C${i}</a></h3></yt-lockup-metadata-view-model>
        </yt-lockup-view-model>
      `);
      await flushPromises();
      jest.advanceTimersByTime(100);  // each well inside the 400ms window
    }
    jest.advanceTimersByTime(400);
    await flushPromises();
    // One request for the whole burst, not five — the point of the debounce.
    expect(global.browser.runtime.sendMessage).toHaveBeenCalledTimes(1);
  });

  test('gives up quietly when no sidebar ever appears', async () => {
    document.body.innerHTML = '';
    content.watchRelated();
    jest.advanceTimersByTime(5000);
    await flushPromises();
    expect(global.browser.runtime.sendMessage).not.toHaveBeenCalled();
  });
});

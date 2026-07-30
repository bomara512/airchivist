const YT_ID_RE = /(?:v=|youtu\.be\/)([A-Za-z0-9_-]{11})/;
// Channel-URL detection. Keep in sync with crawler/models.py _YT_CHANNEL_RE.
const YT_CHANNEL_RE = /youtube\.com\/(channel\/UC[A-Za-z0-9_-]+|(?:c|user)\/[^/?#]+|@[^/?#]+)/;

function channelUrlFrom(match) {
  // match[1] is the canonical path segment (@handle, channel/UC…, c/name, user/name).
  return `https://www.youtube.com/${match[1]}`;
}
const DEFAULT_URL = 'http://localhost:8080';
const URL_KEY = 'viewtubeUrl';
const FOLDER_KEY = 'bookmarkFolderId';
const FOLDER_NAME = 'ViewTube';

function esc(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

async function getOrCreateFolder() {
  const stored = await browser.storage.local.get(FOLDER_KEY);
  if (stored[FOLDER_KEY]) {
    try {
      await browser.bookmarks.get(stored[FOLDER_KEY]);
      return stored[FOLDER_KEY];
    } catch {
      // Folder was deleted; fall through to create
    }
  }
  const results = await browser.bookmarks.search({ title: FOLDER_NAME });
  const existing = results.find(r => !r.url);
  if (existing) {
    await browser.storage.local.set({ [FOLDER_KEY]: existing.id });
    return existing.id;
  }
  const folder = await browser.bookmarks.create({ title: FOLDER_NAME });
  await browser.storage.local.set({ [FOLDER_KEY]: folder.id });
  return folder.id;
}

async function checkStatus(viewtubeUrl, tabUrl) {
  const resp = await fetch(`${viewtubeUrl}/api/status?url=${encodeURIComponent(tabUrl)}`);
  return resp.json();
}

async function doAdd(viewtubeUrl, tabUrl, tabTitle, alsoWatchLater = false) {
  const root = document.getElementById('root');
  root.innerHTML = '<div class="status">Adding…</div>';
  const [bookmarkResult, vtResult] = await Promise.allSettled([
    getOrCreateFolder().then(id =>
      browser.bookmarks.create({ title: tabTitle, url: tabUrl, parentId: id })
    ),
    fetch(`${viewtubeUrl}/api/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: tabUrl }),
    }).then(r => r.json()),
  ]);
  const bookmarkOk = bookmarkResult.status === 'fulfilled';
  const vtData = vtResult.status === 'fulfilled' ? vtResult.value : null;
  const viewtubeOk = vtData && ['added', 'exists'].includes(vtData.status);

  let watchLaterOk = null;
  if (alsoWatchLater && viewtubeOk) {
    try {
      const wlResp = await fetch(`${viewtubeUrl}/api/watch-later/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: tabUrl }),
      });
      const wlData = await wlResp.json();
      watchLaterOk = ['added', 'already_in_queue'].includes(wlData.status);
    } catch {
      watchLaterOk = false;
    }
  }

  if (bookmarkOk && viewtubeOk) {
    const lines = [`&#10003; ${esc(vtData.title || tabTitle)}`];
    if (watchLaterOk === true) lines.push('&#10003; Added to Watch Later');
    if (watchLaterOk === false) lines.push('&#10007; Watch Later failed');
    root.innerHTML = `<div class="status success">${lines.map(l => `<div>${l}</div>`).join('')}</div>`;
    setTimeout(() => window.close(), 1500);
    return;
  }
  const lines = [];
  if (bookmarkOk) lines.push('&#10003; Bookmarked in Firefox');
  else lines.push(`&#10007; Bookmark failed: ${esc(bookmarkResult.reason?.message || 'unknown')}`);
  if (viewtubeOk) lines.push('&#10003; Added to ViewTube');
  else if (vtResult.status === 'rejected') lines.push(`&#10007; ViewTube unreachable`);
  else lines.push(`&#10007; ViewTube: ${esc(vtData?.error || 'unknown error')}`);
  if (alsoWatchLater && watchLaterOk === true) lines.push('&#10003; Added to Watch Later');
  if (alsoWatchLater && watchLaterOk === false) lines.push('&#10007; Watch Later failed');
  const cls = (bookmarkOk || viewtubeOk) ? 'partial' : 'error';
  root.innerHTML = `<div class="status ${cls}">${lines.map(l => `<div>${l}</div>`).join('')}</div>`;
}

async function doAddChannel(viewtubeUrl, channelUrl, tabTitle) {
  const root = document.getElementById('root');
  root.innerHTML = '<div class="status">Adding channel…</div>';
  const [bookmarkResult, vtResult] = await Promise.allSettled([
    getOrCreateFolder().then(id =>
      browser.bookmarks.create({ title: tabTitle, url: channelUrl, parentId: id })
    ),
    fetch(`${viewtubeUrl}/api/channel/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: channelUrl }),
    }).then(r => r.json()),
  ]);
  const bookmarkOk = bookmarkResult.status === 'fulfilled';
  const vtData = vtResult.status === 'fulfilled' ? vtResult.value : null;
  const viewtubeOk = vtData && ['added', 'exists'].includes(vtData.status);

  if (bookmarkOk && viewtubeOk) {
    root.innerHTML = `<div class="status success">&#10003; ${esc(vtData.channel_name || tabTitle)}</div>`;
    setTimeout(() => window.close(), 1500);
    return;
  }
  const lines = [];
  if (bookmarkOk) lines.push('&#10003; Bookmarked in Firefox');
  else lines.push(`&#10007; Bookmark failed: ${esc(bookmarkResult.reason?.message || 'unknown')}`);
  if (viewtubeOk) lines.push('&#10003; Added to ViewTube');
  else if (vtResult.status === 'rejected') lines.push('&#10007; ViewTube unreachable');
  else lines.push(`&#10007; ViewTube: ${esc(vtData?.error || 'unknown error')}`);
  const cls = (bookmarkOk || viewtubeOk) ? 'partial' : 'error';
  root.innerHTML = `<div class="status ${cls}">${lines.map(l => `<div>${l}</div>`).join('')}</div>`;
}

async function doHide(viewtubeUrl, tabUrl, alsoUnbookmark) {
  const root = document.getElementById('root');
  root.innerHTML = '<div class="status">Hiding…</div>';
  let data;
  try {
    const resp = await fetch(`${viewtubeUrl}/api/hide`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: tabUrl }),
    });
    data = await resp.json();
  } catch {
    root.innerHTML = '<div class="status error">&#10007; ViewTube unreachable</div>';
    return;
  }
  if (data.status !== 'hidden') {
    root.innerHTML = `<div class="status error">&#10007; ${esc(data.error || 'Archive failed')}</div>`;
    return;
  }
  if (alsoUnbookmark) {
    const matches = await browser.bookmarks.search({ url: tabUrl });
    await Promise.all(matches.map(b => browser.bookmarks.remove(b.id)));
  }
  root.innerHTML = `<div class="status success">Archived: ${esc(data.title)}</div>`;
}

async function doRestore(viewtubeUrl, videoId) {
  const root = document.getElementById('root');
  root.innerHTML = '<div class="status">Restoring…</div>';
  await fetch(`${viewtubeUrl}/videos/${videoId}/unhide`, { method: 'POST' });
  root.innerHTML = '<div class="status success">&#10003; Restored</div>';
  setTimeout(() => window.close(), 1500);
}

async function doDelete(viewtubeUrl, videoId) {
  const root = document.getElementById('root');
  root.innerHTML = '<div class="status">Deleting…</div>';
  await fetch(`${viewtubeUrl}/videos/${videoId}/delete`, { method: 'POST' });
  root.innerHTML = '<div class="status success">&#10003; Deleted</div>';
  setTimeout(() => window.close(), 1500);
}

function renderState(root, viewtubeUrl, tabUrl, tabTitle, data) {
  if (data.status === 'not_found') {
    root.innerHTML = `
      <button id="btn-add" class="action-btn">Add to ViewTube</button>
      <label style="display:block;margin-top:0.4rem;font-size:0.8rem;cursor:pointer;color:#aaa">
        <input type="checkbox" id="chk-watch-later" style="margin-right:0.3rem">
        Also add to Watch Later
      </label>
    `;
    document.getElementById('btn-add').addEventListener('click', () => {
      const alsoWatchLater = document.getElementById('chk-watch-later').checked;
      doAdd(viewtubeUrl, tabUrl, tabTitle, alsoWatchLater);
    });
    return;
  }

  if (data.status === 'exists') {
    root.innerHTML = `
      <div class="status success" style="margin-bottom:0.5rem">&#10003; ${esc(data.title)}</div>
      <button id="btn-hide" class="action-btn action-btn--danger">Archive</button>
      <label style="display:block;margin-top:0.4rem;font-size:0.8rem;cursor:pointer;color:#aaa">
        <input type="checkbox" id="chk-unbookmark" style="margin-right:0.3rem">
        Also remove browser bookmark
      </label>
    `;
    document.getElementById('btn-hide').addEventListener('click', () => {
      const alsoUnbookmark = document.getElementById('chk-unbookmark').checked;
      doHide(viewtubeUrl, tabUrl, alsoUnbookmark);
    });
    return;
  }

  if (data.status === 'hidden') {
    root.innerHTML = `
      <div class="status error" style="margin-bottom:0.5rem">&#8856; Archived: ${esc(data.title)}</div>
      <button id="btn-restore" class="action-btn">Restore to ViewTube</button>
      <button id="btn-delete" class="action-btn action-btn--danger" style="margin-top:0.25rem">Delete permanently</button>
    `;
    document.getElementById('btn-restore').addEventListener('click', () => doRestore(viewtubeUrl, data.video_id));
    document.getElementById('btn-delete').addEventListener('click', () => doDelete(viewtubeUrl, data.video_id));
    return;
  }

  root.innerHTML = `<div class="status error">&#10007; ${esc(data.error || 'Unknown error')}</div>`;
}

function renderChannelState(root, viewtubeUrl, channelUrl, tabTitle, data) {
  if (data.status === 'exists') {
    root.innerHTML = `<div class="status success">&#10003; Already tracked: ${esc(data.channel_name)}</div>`;
    return;
  }
  if (data.status === 'not_found') {
    root.innerHTML = `<button id="btn-add-channel" class="action-btn">Add channel to ViewTube</button>`;
    document.getElementById('btn-add-channel').addEventListener('click', () =>
      doAddChannel(viewtubeUrl, channelUrl, tabTitle)
    );
    return;
  }
  root.innerHTML = `<div class="status error">&#10007; ${esc(data.error || 'Unknown error')}</div>`;
}

async function run() {
  const root = document.getElementById('root');
  root.innerHTML = '<div class="status">Checking…</div>';

  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  const isVideo = tab?.url && YT_ID_RE.test(tab.url);
  const channelMatch = tab?.url ? tab.url.match(YT_CHANNEL_RE) : null;
  if (!isVideo && !channelMatch) {
    root.innerHTML = '<div class="status error">Not a YouTube video or channel.</div>';
    return;
  }

  const settings = await browser.storage.local.get(URL_KEY);
  const viewtubeUrl = settings[URL_KEY] || DEFAULT_URL;

  if (!isVideo && channelMatch) {
    const channelUrl = channelUrlFrom(channelMatch);
    let chData;
    try {
      const resp = await fetch(
        `${viewtubeUrl}/api/channel/status?url=${encodeURIComponent(channelUrl)}`
      );
      chData = await resp.json();
    } catch {
      root.innerHTML = `<div class="status error">&#10007; ViewTube unreachable<br><small>Is it running at ${esc(viewtubeUrl)}?</small></div>`;
      return;
    }
    renderChannelState(root, viewtubeUrl, channelUrl, tab.title || '', chData);
    return;
  }

  let data;
  try {
    data = await checkStatus(viewtubeUrl, tab.url);
  } catch {
    root.innerHTML = `<div class="status error">&#10007; ViewTube unreachable<br><small>Is it running at ${esc(viewtubeUrl)}?</small></div>`;
    return;
  }

  renderState(root, viewtubeUrl, tab.url, tab.title || '', data);
}

run().catch(err => {
  const root = document.getElementById('root');
  root.innerHTML = `<div class="status error">Error: ${esc(err.message)}</div>`;
});

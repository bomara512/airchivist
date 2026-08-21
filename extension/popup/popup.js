const YT_ID_RE = /(?:v=|youtu\.be\/)([A-Za-z0-9_-]{11})/;
// Channel-URL detection. Keep in sync with crawler/models.py _YT_CHANNEL_RE.
const YT_CHANNEL_RE = /youtube\.com\/(channel\/UC[A-Za-z0-9_-]+|(?:c|user)\/[^/?#]+|@[^/?#]+)/;

function channelUrlFrom(match) {
  // match[1] is the canonical path segment (@handle, channel/UC…, c/name, user/name).
  return `https://www.youtube.com/${match[1]}`;
}
const DEFAULT_URL = 'http://localhost:8080';
const URL_KEY = 'airchivistUrl';
const FOLDER_KEY = 'bookmarkFolderId';
const FOLDER_NAME = 'Airchivist';

function esc(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// Animated in-progress state shown while a request is outstanding.
function working(label) {
  return `<div class="status status--working"><span class="spinner"></span>${esc(label)}</div>`;
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

async function checkStatus(airchivistUrl, tabUrl) {
  const resp = await fetch(`${airchivistUrl}/api/status?url=${encodeURIComponent(tabUrl)}`);
  return resp.json();
}

async function postJson(url, body) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return resp.json();
}

async function doAdd(airchivistUrl, tabUrl, tabTitle, alsoWatchLater = false, alsoFavorite = false) {
  const root = document.getElementById('root');
  root.innerHTML = working('Adding…');
  const [bookmarkResult, vtResult] = await Promise.allSettled([
    getOrCreateFolder().then(id =>
      browser.bookmarks.create({ title: tabTitle, url: tabUrl, parentId: id })
    ),
    fetch(`${airchivistUrl}/api/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: tabUrl }),
    }).then(r => r.json()),
  ]);
  const bookmarkOk = bookmarkResult.status === 'fulfilled';
  const vtData = vtResult.status === 'fulfilled' ? vtResult.value : null;
  const airchivistOk = vtData && ['added', 'exists'].includes(vtData.status);

  let watchLaterOk = null;
  let favoriteOk = null;
  if (airchivistOk) {
    const [wlResult, favResult] = await Promise.allSettled([
      alsoWatchLater
        ? postJson(`${airchivistUrl}/api/watch-later/add`, { url: tabUrl })
        : Promise.resolve(null),
      alsoFavorite
        ? postJson(`${airchivistUrl}/api/favorite/add`, { url: tabUrl })
        : Promise.resolve(null),
    ]);
    if (alsoWatchLater) {
      watchLaterOk = wlResult.status === 'fulfilled'
        && ['added', 'already_in_queue'].includes(wlResult.value?.status);
    }
    if (alsoFavorite) {
      favoriteOk = favResult.status === 'fulfilled' && favResult.value?.status === 'added';
    }
  }

  if (bookmarkOk && airchivistOk) {
    const lines = [`&#10003; ${esc(vtData.title || tabTitle)}`];
    if (watchLaterOk === true) lines.push('&#10003; Added to Watch Later');
    if (watchLaterOk === false) lines.push('&#10007; Watch Later failed');
    if (favoriteOk === true) lines.push('&#9733; Marked as favorite');
    if (favoriteOk === false) lines.push('&#10007; Favorite failed');
    root.innerHTML = `<div class="status success">${lines.map(l => `<div>${l}</div>`).join('')}</div>`;
    setTimeout(() => window.close(), 1500);
    return;
  }
  const lines = [];
  if (bookmarkOk) lines.push('&#10003; Bookmarked in Firefox');
  else lines.push(`&#10007; Bookmark failed: ${esc(bookmarkResult.reason?.message || 'unknown')}`);
  if (airchivistOk) lines.push('&#10003; Added to Airchivist');
  else if (vtResult.status === 'rejected') lines.push(`&#10007; Airchivist unreachable`);
  else lines.push(`&#10007; Airchivist: ${esc(vtData?.error || 'unknown error')}`);
  if (alsoWatchLater && watchLaterOk === true) lines.push('&#10003; Added to Watch Later');
  if (alsoWatchLater && watchLaterOk === false) lines.push('&#10007; Watch Later failed');
  if (alsoFavorite && favoriteOk === true) lines.push('&#9733; Marked as favorite');
  if (alsoFavorite && favoriteOk === false) lines.push('&#10007; Favorite failed');
  const cls = (bookmarkOk || airchivistOk) ? 'partial' : 'error';
  root.innerHTML = `<div class="status ${cls}">${lines.map(l => `<div>${l}</div>`).join('')}</div>`;
}

async function doAddChannel(airchivistUrl, channelUrl, tabTitle) {
  const root = document.getElementById('root');
  root.innerHTML = working('Adding channel…');
  const [bookmarkResult, vtResult] = await Promise.allSettled([
    getOrCreateFolder().then(id =>
      browser.bookmarks.create({ title: tabTitle, url: channelUrl, parentId: id })
    ),
    fetch(`${airchivistUrl}/api/channel/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: channelUrl }),
    }).then(r => r.json()),
  ]);
  const bookmarkOk = bookmarkResult.status === 'fulfilled';
  const vtData = vtResult.status === 'fulfilled' ? vtResult.value : null;
  const airchivistOk = vtData && ['added', 'exists'].includes(vtData.status);

  if (bookmarkOk && airchivistOk) {
    root.innerHTML = `<div class="status success">&#10003; ${esc(vtData.channel_name || tabTitle)}</div>`;
    setTimeout(() => window.close(), 1500);
    return;
  }
  const lines = [];
  if (bookmarkOk) lines.push('&#10003; Bookmarked in Firefox');
  else lines.push(`&#10007; Bookmark failed: ${esc(bookmarkResult.reason?.message || 'unknown')}`);
  if (airchivistOk) lines.push('&#10003; Added to Airchivist');
  else if (vtResult.status === 'rejected') lines.push('&#10007; Airchivist unreachable');
  else lines.push(`&#10007; Airchivist: ${esc(vtData?.error || 'unknown error')}`);
  const cls = (bookmarkOk || airchivistOk) ? 'partial' : 'error';
  root.innerHTML = `<div class="status ${cls}">${lines.map(l => `<div>${l}</div>`).join('')}</div>`;
}

async function doHide(airchivistUrl, tabUrl, alsoUnbookmark) {
  const root = document.getElementById('root');
  root.innerHTML = working('Hiding…');
  let data;
  try {
    const resp = await fetch(`${airchivistUrl}/api/hide`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: tabUrl }),
    });
    data = await resp.json();
  } catch {
    root.innerHTML = '<div class="status error">&#10007; Airchivist unreachable</div>';
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

async function doRestore(airchivistUrl, videoId) {
  const root = document.getElementById('root');
  root.innerHTML = working('Restoring…');
  await fetch(`${airchivistUrl}/videos/${videoId}/unhide`, { method: 'POST' });
  root.innerHTML = '<div class="status success">&#10003; Restored</div>';
  setTimeout(() => window.close(), 1500);
}

async function doDelete(airchivistUrl, videoId) {
  const root = document.getElementById('root');
  root.innerHTML = working('Deleting…');
  await fetch(`${airchivistUrl}/videos/${videoId}/delete`, { method: 'POST' });
  root.innerHTML = '<div class="status success">&#10003; Deleted</div>';
  setTimeout(() => window.close(), 1500);
}

async function initWatchLaterToggle(airchivistUrl, tabUrl) {
  const chk = document.getElementById('chk-watch-later');
  const errBox = document.getElementById('wl-error');

  let inQueue;
  try {
    const resp = await fetch(`${airchivistUrl}/api/watch-later/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: tabUrl }),
    });
    const data = await resp.json();
    inQueue = !!data.in_queue;
  } catch {
    return; // Leave disabled — unknown state, nothing safe to toggle.
  }

  chk.checked = inQueue;
  chk.disabled = false;

  chk.addEventListener('change', async () => {
    const wantQueued = chk.checked;
    const prevChecked = !wantQueued;
    chk.disabled = true;
    errBox.style.display = 'none';

    const endpoint = wantQueued ? 'add' : 'remove';
    let ok;
    try {
      const resp = await fetch(`${airchivistUrl}/api/watch-later/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: tabUrl }),
      });
      const data = await resp.json();
      ok = wantQueued
        ? ['added', 'already_in_queue'].includes(data.status)
        : data.status === 'removed';
    } catch {
      ok = false;
    }

    if (!ok) {
      chk.checked = prevChecked;
      errBox.textContent = '✗ Watch Later update failed';
      errBox.style.display = 'block';
    }
    chk.disabled = false;
  });
}

function renderState(root, airchivistUrl, tabUrl, tabTitle, data) {
  if (data.status === 'not_found') {
    root.innerHTML = `
      <button id="btn-add" class="action-btn">Add to Airchivist</button>
      <label style="display:block;margin-top:0.4rem;font-size:0.8rem;cursor:pointer;color:#aaa">
        <input type="checkbox" id="chk-watch-later" style="margin-right:0.3rem">
        Also add to Watch Later
      </label>
      <label style="display:block;margin-top:0.4rem;font-size:0.8rem;cursor:pointer;color:#aaa">
        <input type="checkbox" id="chk-favorite" style="margin-right:0.3rem">
        Also mark as favorite (&#9733;)
      </label>
    `;
    document.getElementById('btn-add').addEventListener('click', () => {
      const alsoWatchLater = document.getElementById('chk-watch-later').checked;
      const alsoFavorite = document.getElementById('chk-favorite').checked;
      doAdd(airchivistUrl, tabUrl, tabTitle, alsoWatchLater, alsoFavorite);
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
      <label style="display:block;margin-top:0.4rem;font-size:0.8rem;cursor:pointer;color:#aaa">
        <input type="checkbox" id="chk-watch-later" disabled style="margin-right:0.3rem">
        Add to Watch Later
      </label>
      <div id="wl-error" class="status error" style="margin-top:0.3rem;display:none"></div>
    `;
    document.getElementById('btn-hide').addEventListener('click', () => {
      const alsoUnbookmark = document.getElementById('chk-unbookmark').checked;
      doHide(airchivistUrl, tabUrl, alsoUnbookmark);
    });
    initWatchLaterToggle(airchivistUrl, tabUrl);
    return;
  }

  if (data.status === 'hidden') {
    root.innerHTML = `
      <div class="status error" style="margin-bottom:0.5rem">&#8856; Archived: ${esc(data.title)}</div>
      <button id="btn-restore" class="action-btn">Restore to Airchivist</button>
      <button id="btn-delete" class="action-btn action-btn--danger" style="margin-top:0.25rem">Delete permanently</button>
    `;
    document.getElementById('btn-restore').addEventListener('click', () => doRestore(airchivistUrl, data.video_id));
    document.getElementById('btn-delete').addEventListener('click', () => doDelete(airchivistUrl, data.video_id));
    return;
  }

  root.innerHTML = `<div class="status error">&#10007; ${esc(data.error || 'Unknown error')}</div>`;
}

function renderChannelState(root, airchivistUrl, channelUrl, tabTitle, data) {
  if (data.status === 'exists') {
    root.innerHTML = `<div class="status success">&#10003; Already tracked: ${esc(data.channel_name)}</div>`;
    return;
  }
  if (data.status === 'not_found') {
    root.innerHTML = `<button id="btn-add-channel" class="action-btn">Add channel to Airchivist</button>`;
    document.getElementById('btn-add-channel').addEventListener('click', () =>
      doAddChannel(airchivistUrl, channelUrl, tabTitle)
    );
    return;
  }
  root.innerHTML = `<div class="status error">&#10007; ${esc(data.error || 'Unknown error')}</div>`;
}

async function run() {
  const root = document.getElementById('root');
  root.innerHTML = working('Checking…');

  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  const isVideo = tab?.url && YT_ID_RE.test(tab.url);
  const channelMatch = tab?.url ? tab.url.match(YT_CHANNEL_RE) : null;
  if (!isVideo && !channelMatch) {
    root.innerHTML = '<div class="status error">Not a YouTube video or channel.</div>';
    return;
  }

  const settings = await browser.storage.local.get(URL_KEY);
  const airchivistUrl = settings[URL_KEY] || DEFAULT_URL;

  if (!isVideo && channelMatch) {
    const channelUrl = channelUrlFrom(channelMatch);
    let chData;
    try {
      const resp = await fetch(
        `${airchivistUrl}/api/channel/status?url=${encodeURIComponent(channelUrl)}`
      );
      chData = await resp.json();
    } catch {
      root.innerHTML = `<div class="status error">&#10007; Airchivist unreachable<br><small>Is it running at ${esc(airchivistUrl)}?</small></div>`;
      return;
    }
    renderChannelState(root, airchivistUrl, channelUrl, tab.title || '', chData);
    return;
  }

  let data;
  try {
    data = await checkStatus(airchivistUrl, tab.url);
  } catch {
    root.innerHTML = `<div class="status error">&#10007; Airchivist unreachable<br><small>Is it running at ${esc(airchivistUrl)}?</small></div>`;
    return;
  }

  renderState(root, airchivistUrl, tab.url, tab.title || '', data);
}

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

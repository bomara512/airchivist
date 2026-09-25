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
  // Not postJson: /api/status is a GET with the url in the query string.
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
    postJson(`${airchivistUrl}/api/add`, { url: tabUrl }),
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
    postJson(`${airchivistUrl}/api/channel/add`, { url: channelUrl }),
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
    data = await postJson(`${airchivistUrl}/api/hide`, { url: tabUrl });
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
  // Not postJson: these two routes take no body and answer with a redirect, not JSON.
  await fetch(`${airchivistUrl}/videos/${videoId}/unhide`, { method: 'POST' });
  root.innerHTML = '<div class="status success">&#10003; Restored</div>';
  setTimeout(() => window.close(), 1500);
}

async function doDelete(airchivistUrl, videoId) {
  const root = document.getElementById('root');
  root.innerHTML = working('Deleting…');
  // Not postJson: see doRestore.
  await fetch(`${airchivistUrl}/videos/${videoId}/delete`, { method: 'POST' });
  root.innerHTML = '<div class="status success">&#10003; Deleted</div>';
  setTimeout(() => window.close(), 1500);
}

/**
 * Drive one checkbox that mirrors a server-side boolean.
 *
 * The Watch Later and Favorite toggles were ~90% identical line for line; the
 * only real differences are the endpoint paths, the key the status response uses,
 * and which `status` values count as a successful add (watch-later has two,
 * because re-adding a queued video answers `already_in_queue`).
 *
 * The checkbox starts disabled in the markup and is only enabled once the status
 * fetch resolves: a status we could not read is left disabled, because there is
 * nothing safe to toggle from an unknown state.
 */
async function initToggle({
  checkboxId, errorBoxId, statusPath, statusKey,
  addPath, removePath, addSuccessStatuses, removeSuccessStatus = 'removed',
  errorLabel, airchivistUrl, tabUrl,
}) {
  const chk = document.getElementById(checkboxId);
  const errBox = document.getElementById(errorBoxId);

  let initial;
  try {
    const data = await postJson(`${airchivistUrl}${statusPath}`, { url: tabUrl });
    initial = !!data[statusKey];
  } catch {
    return; // Leave disabled — unknown state, nothing safe to toggle.
  }

  chk.checked = initial;
  chk.disabled = false;

  chk.addEventListener('change', async () => {
    const wantOn = chk.checked;
    chk.disabled = true;
    errBox.style.display = 'none';

    let ok;
    try {
      const data = await postJson(`${airchivistUrl}${wantOn ? addPath : removePath}`, { url: tabUrl });
      ok = wantOn
        ? addSuccessStatuses.includes(data.status)
        : data.status === removeSuccessStatus;
    } catch {
      ok = false;
    }

    if (!ok) {
      chk.checked = !wantOn;
      errBox.textContent = errorLabel;
      errBox.style.display = 'block';
    }
    chk.disabled = false;
  });
}

async function initWatchLaterToggle(airchivistUrl, tabUrl) {
  return initToggle({
    checkboxId: 'chk-watch-later', errorBoxId: 'wl-error',
    statusPath: '/api/watch-later/status', statusKey: 'in_queue',
    addPath: '/api/watch-later/add', removePath: '/api/watch-later/remove',
    addSuccessStatuses: ['added', 'already_in_queue'],
    errorLabel: '✗ Watch Later update failed',
    airchivistUrl, tabUrl,
  });
}

async function initFavoriteToggle(airchivistUrl, tabUrl) {
  return initToggle({
    checkboxId: 'chk-favorite', errorBoxId: 'fav-error',
    statusPath: '/api/favorite/status', statusKey: 'is_favorite',
    addPath: '/api/favorite/add', removePath: '/api/favorite/remove',
    addSuccessStatuses: ['added'],
    errorLabel: '✗ Favorite update failed',
    airchivistUrl, tabUrl,
  });
}


function renderState(root, airchivistUrl, tabUrl, tabTitle, data) {
  if (data.status === 'not_found') {
    root.innerHTML = `
      <button id="btn-add" class="action-btn">Add to Airchivist</button>
      <label class="popup-check-label">
        <input type="checkbox" id="chk-watch-later" style="margin-right:0.3rem">
        Also add to Watch Later
      </label>
      <label class="popup-check-label">
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
      <label class="popup-check-label">
        <input type="checkbox" id="chk-unbookmark" style="margin-right:0.3rem">
        Also remove browser bookmark
      </label>
      <label class="popup-check-label">
        <input type="checkbox" id="chk-watch-later" disabled style="margin-right:0.3rem">
        Add to Watch Later
      </label>
      <div id="wl-error" class="status error" style="margin-top:0.3rem;display:none"></div>
      <label class="popup-check-label">
        <input type="checkbox" id="chk-favorite" disabled style="margin-right:0.3rem">
        Mark as favorite (&#9733;)
      </label>
      <div id="fav-error" class="status error" style="margin-top:0.3rem;display:none"></div>
    `;
    document.getElementById('btn-hide').addEventListener('click', () => {
      const alsoUnbookmark = document.getElementById('chk-unbookmark').checked;
      doHide(airchivistUrl, tabUrl, alsoUnbookmark);
    });
    initWatchLaterToggle(airchivistUrl, tabUrl);
    initFavoriteToggle(airchivistUrl, tabUrl);
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
    initToggle, initWatchLaterToggle, initFavoriteToggle, renderState, renderChannelState,
    checkStatus, channelUrlFrom, esc, getOrCreateFolder, postJson,
  };
}

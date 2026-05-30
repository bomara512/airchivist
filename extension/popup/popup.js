// Matches standard watch URLs and youtu.be short links
const YT_ID_RE = /(?:v=|youtu\.be\/)([A-Za-z0-9_-]{11})/;
const DEFAULT_URL = 'http://localhost:8080';
const URL_KEY = 'viewtubeUrl';
const FOLDER_KEY = 'bookmarkFolderId';
const FOLDER_NAME = 'ViewTube';

function setStatus(el, html, cls) {
  el.innerHTML = html;
  el.className = `status ${cls}`;
}

// Returns the ID of the "ViewTube" bookmark folder, creating it if needed.
// Caches the ID in storage so subsequent opens are instant.
async function getOrCreateFolder() {
  const stored = await browser.storage.local.get(FOLDER_KEY);
  if (stored[FOLDER_KEY]) {
    try {
      await browser.bookmarks.get(stored[FOLDER_KEY]);
      return stored[FOLDER_KEY];
    } catch {
      // Folder was deleted; fall through to create a new one
    }
  }

  const results = await browser.bookmarks.search({ title: FOLDER_NAME });
  const existing = results.find(r => !r.url); // folders have no url
  if (existing) {
    await browser.storage.local.set({ [FOLDER_KEY]: existing.id });
    return existing.id;
  }

  const folder = await browser.bookmarks.create({ title: FOLDER_NAME });
  await browser.storage.local.set({ [FOLDER_KEY]: folder.id });
  return folder.id;
}

async function run() {
  const statusEl = document.getElementById('status');

  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });

  if (!tab?.url || !YT_ID_RE.test(tab.url)) {
    setStatus(statusEl, 'Not a YouTube video.', 'error');
    return;
  }

  // Load folder and settings in parallel
  const [folderId, settings] = await Promise.all([
    getOrCreateFolder(),
    browser.storage.local.get(URL_KEY),
  ]);
  const viewtubeUrl = settings[URL_KEY] || DEFAULT_URL;

  // Create bookmark and add to ViewTube in parallel
  const [bookmarkResult, viewtubeResult] = await Promise.allSettled([
    browser.bookmarks.create({
      title: tab.title,
      url: tab.url,
      parentId: folderId,
    }),
    fetch(`${viewtubeUrl}/api/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: tab.url }),
    }).then(r => r.json()),
  ]);

  const bookmarkOk = bookmarkResult.status === 'fulfilled';
  const vtData = viewtubeResult.status === 'fulfilled' ? viewtubeResult.value : null;
  const viewtubeOk = vtData && ['added', 'exists'].includes(vtData.status);

  if (bookmarkOk && viewtubeOk) {
    setStatus(statusEl, `&#10003; ${vtData.title || tab.title}`, 'success');
    setTimeout(() => window.close(), 1500);
    return;
  }

  // Partial or full failure — show per-action status
  const lines = [];

  if (bookmarkOk) {
    lines.push('&#10003; Bookmarked in Firefox');
  } else {
    const msg = bookmarkResult.reason?.message || 'unknown error';
    lines.push(`&#10007; Bookmark failed: ${msg}`);
  }

  if (viewtubeOk) {
    lines.push('&#10003; Added to ViewTube');
  } else if (viewtubeResult.status === 'rejected') {
    lines.push(`&#10007; ViewTube unreachable<br><small>Is it running at ${viewtubeUrl}?</small>`);
  } else {
    const msg = vtData?.error || 'unknown error';
    lines.push(`&#10007; ViewTube: ${msg}`);
  }

  const cls = (bookmarkOk || viewtubeOk) ? 'partial' : 'error';
  setStatus(statusEl, lines.map(l => `<div>${l}</div>`).join(''), cls);
}

run().catch(err => {
  const statusEl = document.getElementById('status');
  setStatus(statusEl, `Error: ${err.message}`, 'error');
});

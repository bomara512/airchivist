const YT_ID_RE = /[?&]v=([A-Za-z0-9_-]{11})/;

// Channel-URL detection. Keep in sync with crawler/models.py _YT_CHANNEL_RE.
const YT_CHANNEL_RE = /youtube\.com\/(channel\/UC[A-Za-z0-9_-]+|(?:c|user)\/[^/?#]+|@[^/?#]+)/;

const CHANNEL_TITLE_SELECTOR =
  'yt-page-header-renderer h1, .page-header-view-model-wiz__page-header-title, ' +
  '#channel-header #text, ytd-channel-name #text';

function channelUrlFrom(match) {
  // match[1] is the canonical path segment (@handle, channel/UC…, c/name, user/name).
  return `https://www.youtube.com/${match[1]}`;
}

function _channelTitle() {
  return document.querySelector(CHANNEL_TITLE_SELECTOR);
}

const TITLE_COLOR = { exists: '#388e3c', hidden: '#e53935' };

// ── Helpers ───────────────────────────────────────────────────────────────

function extractId(url) {
  const m = YT_ID_RE.exec(url);
  return m ? m[1] : null;
}

// Resolves when selector matches something in root, or null on timeout.
function waitFor(selector, root = document, timeout = 5000) {
  return new Promise(resolve => {
    const el = root.querySelector(selector);
    if (el) { resolve(el); return; }
    const obs = new MutationObserver(() => {
      const el = root.querySelector(selector);
      if (el) { obs.disconnect(); resolve(el); }
    });
    obs.observe(root, { childList: true, subtree: true });
    setTimeout(() => { obs.disconnect(); resolve(null); }, timeout);
  });
}

// ── Current video title ───────────────────────────────────────────────────

function _titleH1() {
  return document.querySelector('#above-the-fold > div:nth-child(1) h1');
}

async function checkCurrentVideo() {
  const prevH1 = _titleH1();
  if (prevH1) prevH1.style.color = '';

  const id = extractId(location.href);
  if (!id) return;

  await waitFor('#above-the-fold > div:nth-child(1) h1');
  if (extractId(location.href) !== id) return;

  try {
    const data = await browser.runtime.sendMessage({ action: 'fetchStatus', url: location.href });
    const color = TITLE_COLOR[data.status];
    if (!color) return;
    const h1 = _titleH1();
    if (h1 && extractId(location.href) === id) h1.style.color = color;
  } catch { /* Airchivist unreachable */ }
}

// ── Current channel title ─────────────────────────────────────────────────

async function checkCurrentChannel() {
  const prev = _channelTitle();
  if (prev) prev.style.color = '';

  const m = YT_CHANNEL_RE.exec(location.href);
  if (!m) return;
  const channelUrl = channelUrlFrom(m);

  const titleEl = await waitFor(CHANNEL_TITLE_SELECTOR);
  if (!titleEl) return;
  // Bail if SPA navigation moved to a different channel while we waited.
  const m2 = YT_CHANNEL_RE.exec(location.href);
  if (!m2 || channelUrlFrom(m2) !== channelUrl) return;

  try {
    const data = await browser.runtime.sendMessage({
      action: 'fetchChannelStatus', url: channelUrl,
    });
    if (data.status !== 'exists') return;
    const el = _channelTitle();
    const m3 = YT_CHANNEL_RE.exec(location.href);
    if (el && m3 && channelUrlFrom(m3) === channelUrl) {
      el.style.color = TITLE_COLOR.exists;
    }
  } catch { /* Airchivist unreachable */ }
}

// ── Related video titles ──────────────────────────────────────────────────

let _relObserver = null;

async function scanRelated() {
  const cards = document.querySelectorAll(
    'yt-lockup-view-model, ytd-compact-video-renderer'
  );
  const toCheck = new Map(); // videoId → card element

  for (const card of cards) {
    if (card.dataset.vtChecked) continue;
    const link = card.querySelector('a[href*="watch?v="]');
    if (!link) continue;
    const id = extractId(link.href);
    if (!id) continue;
    toCheck.set(id, card);
  }
  if (toCheck.size === 0) return;

  try {
    const data = await browser.runtime.sendMessage({
      action: 'fetchStatusBatch',
      ids: [...toCheck.keys()],
    });
    for (const [id, card] of toCheck) {
      card.dataset.vtChecked = '1';
      const color = TITLE_COLOR[data[id]];
      if (!color) continue;
      const h3 = card.querySelector('yt-lockup-metadata-view-model h3, #meta h3');
      if (!h3) continue;
      (h3.querySelector('a') || h3).style.color = color;
    }
  } catch { /* Airchivist unreachable */ }
}

function watchRelated() {
  _relObserver?.disconnect();
  let debounce;
  waitFor('#secondary, #related').then(container => {
    if (!container) return;
    _relObserver = new MutationObserver(() => {
      clearTimeout(debounce);
      debounce = setTimeout(() => scanRelated(), 400);
    });
    _relObserver.observe(container, { childList: true, subtree: true });
    scanRelated();
  });
}

// ── Navigation & init ─────────────────────────────────────────────────────

function run() {
  if (extractId(location.href)) {
    checkCurrentVideo();
    watchRelated();
    return;
  }
  if (YT_CHANNEL_RE.test(location.href)) {
    checkCurrentChannel();
  }
}

document.addEventListener('yt-navigate-finish', run);

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', run);
} else {
  run();
}

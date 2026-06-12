const YT_ID_RE = /[?&]v=([A-Za-z0-9_-]{11})/;
const URL_KEY = 'viewtubeUrl';
const DEFAULT_URL = 'http://localhost:8080';

// ── Styles ────────────────────────────────────────────────────────────────

function ensureStyles() {
  if (document.getElementById('vt-styles')) return;
  const s = document.createElement('style');
  s.id = 'vt-styles';
  s.textContent = `
    .vt-badge {
      display: inline-block;
      font-size: 11px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 3px;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      line-height: 1.6;
    }
    .vt-badge--exists { background: #1a3a1a; color: #5cb85c; border: 1px solid #2d5a2d; }
    .vt-badge--hidden { background: #2a1a1a; color: #e74c3c; border: 1px solid #5a2a2a; }
    #vt-current-badge  { display: block; margin: 6px 0 2px; }
    .vt-rel-badge      { display: block; margin: 2px 0 0; font-size: 10px; padding: 1px 6px; }
  `;
  document.head.appendChild(s);
}

// ── Helpers ───────────────────────────────────────────────────────────────

function extractId(url) {
  const m = YT_ID_RE.exec(url);
  return m ? m[1] : null;
}

async function getViewtubeUrl() {
  const s = await browser.storage.local.get(URL_KEY);
  return s[URL_KEY] || DEFAULT_URL;
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

const BADGE_CFG = {
  exists: { text: '✓ In ViewTube', cls: 'vt-badge--exists' },
  hidden: { text: '⊘ Hidden in ViewTube', cls: 'vt-badge--hidden' },
};

function makeBadge(status, extraClass = '') {
  const cfg = BADGE_CFG[status];
  if (!cfg) return null;
  const el = document.createElement('span');
  el.className = `vt-badge ${cfg.cls}${extraClass ? ' ' + extraClass : ''}`;
  el.textContent = cfg.text;
  return el;
}

// ── Current video badge ───────────────────────────────────────────────────

async function checkCurrentVideo(vtUrl) {
  document.getElementById('vt-current-badge')?.remove();
  const id = extractId(location.href);
  if (!id) return;

  // Wait for the title element to exist before fetching.
  await waitFor('#above-the-fold #title, ytd-watch-metadata #title');
  if (extractId(location.href) !== id) return;

  try {
    const resp = await fetch(
      `${vtUrl}/api/status?url=${encodeURIComponent(location.href)}`
    );
    const data = await resp.json();
    const cfg = BADGE_CFG[data.status];
    if (!cfg) return;

    function inject() {
      // Re-query after the async fetch — the original reference may be
      // orphaned if YouTube's reactive renderer replaced the node.
      const titleEl = document.querySelector(
        '#above-the-fold #title, ytd-watch-metadata #title'
      );
      if (!titleEl || extractId(location.href) !== id) return;
      document.getElementById('vt-current-badge')?.remove();
      const badge = document.createElement('span');
      badge.id = 'vt-current-badge';
      badge.className = `vt-badge ${cfg.cls}`;
      badge.textContent = cfg.text;
      titleEl.after(badge);
    }

    inject();

    // If YouTube's renderer wipes our badge immediately, inject once more.
    const guard = new MutationObserver(() => {
      if (!document.getElementById('vt-current-badge')) {
        guard.disconnect();
        inject();
      }
    });
    guard.observe(document.body, { childList: true, subtree: true });
    setTimeout(() => guard.disconnect(), 3000);
  } catch { /* ViewTube unreachable */ }
}

// ── Related video badges ──────────────────────────────────────────────────

let _relObserver = null;

async function scanRelated(vtUrl) {
  const cards = document.querySelectorAll('ytd-compact-video-renderer');
  const toCheck = new Map(); // videoId → card element

  for (const card of cards) {
    if (card.querySelector('.vt-rel-badge')) continue; // already labelled
    const link = card.querySelector('a#thumbnail[href]');
    if (!link) continue;
    const id = extractId(link.href);
    if (!id) continue;
    toCheck.set(id, card);
  }
  if (toCheck.size === 0) return;

  try {
    const resp = await fetch(`${vtUrl}/api/status/batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids: [...toCheck.keys()] }),
    });
    const data = await resp.json();
    for (const [id, card] of toCheck) {
      const badge = makeBadge(data[id], 'vt-rel-badge');
      if (!badge) continue;
      // Prepend into the text metadata area below the video title.
      const meta = card.querySelector('#meta, #metadata');
      if (meta) meta.prepend(badge);
    }
  } catch { /* ViewTube unreachable */ }
}

function watchRelated(vtUrl) {
  _relObserver?.disconnect();
  let debounce;
  waitFor('#secondary, #related').then(container => {
    if (!container) return;
    _relObserver = new MutationObserver(() => {
      clearTimeout(debounce);
      debounce = setTimeout(() => scanRelated(vtUrl), 400);
    });
    _relObserver.observe(container, { childList: true, subtree: true });
    scanRelated(vtUrl);
  });
}

// ── Navigation & init ─────────────────────────────────────────────────────

async function run() {
  ensureStyles();
  if (!extractId(location.href)) return;
  const vtUrl = await getViewtubeUrl();
  checkCurrentVideo(vtUrl);
  watchRelated(vtUrl);
}

// YouTube fires this on every SPA navigation (including initial load finish).
document.addEventListener('yt-navigate-finish', run);

// Fallback for when the content script loads after yt-navigate-finish already fired.
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', run);
} else {
  run();
}

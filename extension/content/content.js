const YT_ID_RE = /[?&]v=([A-Za-z0-9_-]{11})/;

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

// ── Current video badge ───────────────────────────────────────────────────

async function checkCurrentVideo() {
  document.getElementById('vt-current-badge')?.remove();
  const id = extractId(location.href);
  if (!id) return;

  // Wait for the title element to exist before fetching.
  await waitFor('#above-the-fold #title, ytd-watch-metadata #title');
  if (extractId(location.href) !== id) return;

  try {
    // Route through background script to avoid mixed-content blocking
    // (content scripts on https://youtube.com can't fetch http://localhost).
    const data = await browser.runtime.sendMessage({
      action: 'fetchStatus',
      url: location.href,
    });
    const cfg = BADGE_CFG[data.status];
    if (!cfg) return;

    function inject() {
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
  } catch(e) { console.log('[VT] checkCurrentVideo error:', e); }
}

// ── Related video badges ──────────────────────────────────────────────────

let _relObserver = null;

async function scanRelated() {
  // YouTube's current layout uses yt-lockup-view-model; older layouts used
  // ytd-compact-video-renderer. Query both so either layout works.
  const cards = document.querySelectorAll(
    'yt-lockup-view-model, ytd-compact-video-renderer'
  );
  const toCheck = new Map(); // videoId → card element

  for (const card of cards) {
    if (card.querySelector('.vt-rel-badge')) continue; // already labelled
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
      const cfg = BADGE_CFG[data[id]];
      if (!cfg) continue;
      const badge = document.createElement('span');
      badge.className = `vt-rel-badge vt-badge ${cfg.cls}`;
      badge.textContent = cfg.text;
      const meta = card.querySelector(
        'yt-lockup-metadata-view-model, #meta, #metadata, h3'
      );
      if (meta) meta.prepend(badge);
    }
  } catch(e) { console.log('[VT] scanRelated error:', e); }
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
  ensureStyles();
  if (!extractId(location.href)) return;
  checkCurrentVideo();
  watchRelated();
}

// YouTube fires this on every SPA navigation (including initial load finish).
document.addEventListener('yt-navigate-finish', run);

// Fallback for when the content script loads after yt-navigate-finish already fired.
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', run);
} else {
  run();
}

const YT_ID_RE = /[?&]v=([A-Za-z0-9_-]{11})/;

// ── Styles ────────────────────────────────────────────────────────────────

function ensureStyles() {
  if (document.getElementById('vt-styles')) return;
  const s = document.createElement('style');
  s.id = 'vt-styles';
  s.textContent = `
    .vt-dot {
      display: inline-block;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      text-align: center;
      line-height: 18px;
      font-size: 12px;
      font-weight: 700;
      color: #fff;
      vertical-align: middle;
      margin-right: 7px;
      flex-shrink: 0;
    }
    .vt-dot--exists { background: #4caf50; }
    .vt-dot--hidden { background: #e53935; }
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
  exists: { symbol: '✓', cls: 'vt-dot--exists' },
  hidden: { symbol: '⊘', cls: 'vt-dot--hidden' },
};

// ── Current video badge ───────────────────────────────────────────────────

async function checkCurrentVideo() {
  document.getElementById('vt-current-badge')?.remove();
  const id = extractId(location.href);
  if (!id) return;

  // Wait for the title area to exist before fetching.
  await waitFor('#above-the-fold > div:nth-child(1) h1');
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
      const h1 = document.querySelector('#above-the-fold > div:nth-child(1) h1');
      if (!h1 || extractId(location.href) !== id) return;
      document.getElementById('vt-current-badge')?.remove();
      const dot = document.createElement('span');
      dot.id = 'vt-current-badge';
      dot.className = `vt-dot ${cfg.cls}`;
      dot.textContent = cfg.symbol;
      h1.prepend(dot);
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
    if (card.querySelector('.vt-rel-dot')) continue; // already labelled
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
      const h3 = card.querySelector('yt-lockup-metadata-view-model h3, #meta h3');
      if (!h3) continue;
      const dot = document.createElement('span');
      dot.className = `vt-dot vt-rel-dot ${cfg.cls}`;
      dot.textContent = cfg.symbol;
      h3.prepend(dot);
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

const YT_ID_RE = /[?&]v=([A-Za-z0-9_-]{11})/;

// ── Styles ────────────────────────────────────────────────────────────────

function ensureStyles() {
  if (document.getElementById('vt-styles')) return;
  const s = document.createElement('style');
  s.id = 'vt-styles';
  s.textContent = `
    .vt-dot {
      display: inline-block;
      vertical-align: text-top;
      margin-right: 5px;
      line-height: 0;
    }
    .vt-dot--exists { color: #4caf50; }
    .vt-dot--hidden { color: #e53935; }
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
  exists: { cls: 'vt-dot--exists' },
  hidden: { cls: 'vt-dot--hidden' },
};

const _CHECK_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="17" height="17" aria-hidden="true"><path d="M5.341,12.247a1,1,0,0,0,1.317,1.505l4-3.5a1,1,0,0,0,.028-1.48l-9-8.5A1,1,0,0,0,.313,1.727l8.2,7.745Z" transform="translate(19 6.5) rotate(90)" fill="currentColor"/></svg>';

function makeDot(cfg, id) {
  const span = document.createElement('span');
  span.className = `vt-dot ${cfg.cls}`;
  if (id) span.id = id;
  span.innerHTML = _CHECK_SVG;
  return span;
}

// ── Current video badge ───────────────────────────────────────────────────

const TITLE_COLOR = { exists: '#4caf50', hidden: '#e53935' };

function _titleH1() {
  return document.querySelector('#above-the-fold > div:nth-child(1) h1');
}

async function checkCurrentVideo() {
  // Reset any coloring left from a previous video.
  const prevH1 = _titleH1();
  if (prevH1) prevH1.style.color = '';

  const id = extractId(location.href);
  if (!id) return;

  await waitFor('#above-the-fold > div:nth-child(1) h1');
  if (extractId(location.href) !== id) return;

  try {
    const data = await browser.runtime.sendMessage({
      action: 'fetchStatus',
      url: location.href,
    });
    const color = TITLE_COLOR[data.status];
    if (!color) return;
    const h1 = _titleH1();
    if (h1 && extractId(location.href) === id) h1.style.color = color;
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
      const dot = makeDot(cfg);
      dot.classList.add('vt-rel-dot');
      (h3.querySelector('a') || h3).prepend(dot);
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

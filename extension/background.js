const URL_KEY = 'viewtubeUrl';
const DEFAULT_URL = 'http://localhost:8080';

async function getViewtubeUrl() {
  const s = await browser.storage.local.get(URL_KEY);
  return s[URL_KEY] || DEFAULT_URL;
}

browser.runtime.onMessage.addListener((msg) => {
  if (msg.action === 'fetchStatus') {
    return getViewtubeUrl().then(vtUrl =>
      fetch(`${vtUrl}/api/status?url=${encodeURIComponent(msg.url)}`)
        .then(r => r.json())
        .catch(() => ({ status: 'error' }))
    );
  }
  if (msg.action === 'fetchStatusBatch') {
    return getViewtubeUrl().then(vtUrl =>
      fetch(`${vtUrl}/api/status/batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: msg.ids }),
      })
        .then(r => r.json())
        .catch(() => ({}))
    );
  }
  if (msg.action === 'fetchChannelStatus') {
    return getViewtubeUrl().then(vtUrl =>
      fetch(`${vtUrl}/api/channel/status?url=${encodeURIComponent(msg.url)}`)
        .then(r => r.json())
        .catch(() => ({ status: 'error' }))
    );
  }
});

const URL_KEY = 'airchivistUrl';
const DEFAULT_URL = 'http://localhost:8080';

async function getAirchivistUrl() {
  const s = await browser.storage.local.get(URL_KEY);
  return s[URL_KEY] || DEFAULT_URL;
}

/**
 * Answer one message from the content script.
 *
 * Returns a Promise for a recognized action and `undefined` for anything else —
 * returning undefined is what tells the browser this listener isn't handling the
 * message, so another listener still could.
 *
 * Every branch swallows fetch failures into a benign shape rather than rejecting:
 * the content script's job is to tint a title, and an unreachable Airchivist should
 * leave the page alone, not surface an error on YouTube. Note the batch case falls
 * back to `{}` rather than `{status: 'error'}` — its result is indexed by video id.
 */
function handleMessage(msg) {
  if (msg.action === 'fetchStatus') {
    return getAirchivistUrl().then(vtUrl =>
      fetch(`${vtUrl}/api/status?url=${encodeURIComponent(msg.url)}`)
        .then(r => r.json())
        .catch(() => ({ status: 'error' }))
    );
  }
  if (msg.action === 'fetchStatusBatch') {
    return getAirchivistUrl().then(vtUrl =>
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
    return getAirchivistUrl().then(vtUrl =>
      fetch(`${vtUrl}/api/channel/status?url=${encodeURIComponent(msg.url)}`)
        .then(r => r.json())
        .catch(() => ({ status: 'error' }))
    );
  }
}

// Same guard as popup.js: register the listener when loaded as an extension
// script, export the pieces when required by a test.
if (typeof module === 'undefined') {
  browser.runtime.onMessage.addListener(handleMessage);
} else {
  module.exports = { handleMessage, getAirchivistUrl, URL_KEY, DEFAULT_URL };
}

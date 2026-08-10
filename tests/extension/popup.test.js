const { makeBrowserStub } = require('./setup');

let popup;

beforeEach(() => {
  jest.resetModules();
  document.body.innerHTML = '<div id="root"></div>';
  global.browser = makeBrowserStub();
  global.fetch = jest.fn();
  global.window.close = jest.fn();
  popup = require('../../extension/popup/popup.js');
});

describe('module exports', () => {
  test('exports doAdd and initWatchLaterToggle as functions', () => {
    expect(typeof popup.doAdd).toBe('function');
    expect(typeof popup.initWatchLaterToggle).toBe('function');
  });
});

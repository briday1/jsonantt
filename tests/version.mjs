import assert from 'node:assert/strict';
import {wirePublishedVersion} from '../jsonantt/web/version.mjs';

const key = 'jsonantt.pypi-version.v1';
const storage = new Map();
globalThis.localStorage = {
  getItem: key => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, value),
};
const tick = () => new Promise(resolve => setImmediate(resolve));
const setup = () => {
  const menu = new EventTarget(), label = {};
  menu.open = false;
  wirePublishedVersion(menu, label);
  const open = () => { menu.open = true; menu.dispatchEvent(new Event('toggle')); };
  return {menu, label, open};
};
let requests = 0;
let finish;
globalThis.fetch = (url, options) => {
  requests++;
  assert.equal(url, 'https://pypi.org/pypi/jsonantt/json');
  assert.equal(options.credentials, 'omit');
  assert.equal(options.referrerPolicy, 'no-referrer');
  return new Promise(resolve => { finish = resolve; });
};
const first = setup();
assert.equal(requests, 0, 'Startup must not request PyPI');
first.open();
assert.equal(first.label.textContent, 'Checking…');
first.open();
assert.equal(requests, 1, 'Concurrent toggles share one request');
finish(new Response(JSON.stringify({info: {version: '2026.34'}})));
await tick();
assert.equal(first.label.textContent, '2026.34');
assert.equal(JSON.parse(storage.get(key)).version, '2026.34');
const fresh = setup();
assert.equal(fresh.label.textContent, '2026.34');
fresh.open();
assert.equal(requests, 1, 'Fresh cached results avoid a request');

globalThis.fetch = async () => { throw new Error('offline'); };
storage.set(key, JSON.stringify({version: '2026.33', checkedAt: 0}));
const offline = setup();
offline.open();
await tick();
assert.equal(offline.label.textContent, '2026.33');
assert.match(offline.label.title, /Cached/);
storage.clear();
const missing = setup();
missing.open();
await tick();
assert.equal(missing.label.textContent, 'Unavailable');

for (const body of [{}, {info: {version: '<script>'}}, {info: {version: 123}}]) {
  globalThis.fetch = async () => new Response(JSON.stringify(body));
  const invalid = setup(); invalid.open(); await tick();
  assert.equal(invalid.label.textContent, 'Unavailable');
  assert.equal(storage.size, 0);
}
globalThis.fetch = async () => new Response('unavailable', {status: 503});
const httpError = setup(); httpError.open(); await tick();
assert.equal(httpError.label.textContent, 'Unavailable');

// Storage denial must not prevent a successful lookup.
globalThis.localStorage = {getItem() {throw new Error('denied');}, setItem() {throw new Error('denied');}};
globalThis.fetch = async () => new Response(JSON.stringify({info: {version: '2026.35'}}));
const denied = setup(); denied.open(); await tick();
assert.equal(denied.label.textContent, '2026.35');
console.log('Passed lazy PyPI lookup, request deduplication, cache, offline, invalid responses and storage denial.');

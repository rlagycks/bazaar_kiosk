/* 6A: the attempt id must be available on every screen that can order.
 *
 * `crypto.randomUUID` only exists in a secure context. This kiosk may be served
 * over plain HTTP on the venue's LAN until TLS lands (12A1), and there the
 * helper has to keep working -- an exception here would mean no orders at all.
 */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const nodeCrypto = require('node:crypto');

const HELPER = path.join(__dirname, '..', 'orders', 'static', 'orders', 'ui', 'request_id.js');
const SOURCE = fs.readFileSync(HELPER, 'utf8');
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function load(crypto) {
  const context = {window: {crypto: crypto}, Uint8Array, Object, Date, Math, String};
  vm.createContext(context);
  vm.runInContext(SOURCE, context);
  return context.window.BazaarRequestId;
}

const secure = {
  randomUUID: () => nodeCrypto.randomUUID(),
  getRandomValues: (a) => nodeCrypto.webcrypto.getRandomValues(a),
};
const insecure = {getRandomValues: (a) => nodeCrypto.webcrypto.getRandomValues(a)};
const throwing = {
  randomUUID: () => { throw new Error('not a secure context'); },
  getRandomValues: (a) => nodeCrypto.webcrypto.getRandomValues(a),
};

test('a secure context uses the native UUID', () => {
  assert.match(load(secure).create(), UUID);
});

test('without randomUUID it still produces a v4 UUID', () => {
  assert.match(load(insecure).create(), UUID);
});

test('a randomUUID that throws falls back instead of failing the order', () => {
  assert.match(load(throwing).create(), UUID);
});

test('with no crypto at all it still returns a usable id', () => {
  const id = load(undefined).create();
  // The server's shape rule: 8-64 chars, alphanumeric start, limited symbols.
  assert.ok(id.length >= 8 && id.length <= 64, id);
  assert.match(id, /^[A-Za-z0-9][A-Za-z0-9._:-]*$/);
});

test('ids do not repeat', () => {
  const helper = load(insecure);
  const seen = new Set();
  for (let i = 0; i < 500; i += 1) seen.add(helper.create());
  assert.strictEqual(seen.size, 500);
});

test('every generated id satisfies the server pattern', () => {
  const pattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{7,63}$/;
  [secure, insecure, throwing, undefined].forEach((crypto) => {
    assert.match(load(crypto).create(), pattern);
  });
});

test('the helper is frozen so a page cannot swap the generator', () => {
  const helper = load(secure);
  const original = helper.create;
  // Non-strict assignment to a frozen object fails silently rather than
  // throwing, so the check is that nothing changed.
  helper.create = () => 'fixed-id';
  assert.strictEqual(helper.create, original);
  assert.ok(Object.isFrozen(helper));
});

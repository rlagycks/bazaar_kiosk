/* Run with: node --test scripts/test_auth_client.cjs (no dependencies). */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {runInNewContext} = require('node:vm');
const source = readFileSync(new URL('../orders/static/orders/ui/auth.js', `file://${__filename}`), 'utf8');
const tokenResponse = (token = 'access-1', account = 'account-1', session = 'session-1') => new Response(JSON.stringify({access_token: token, account_id: account, account_name: 'tester', permissions: ['SERVING'], session_id: session, expires_in: 900}));

function client(handler, locks) {
  const calls = [];
  const redirects = [];
  const document = {cookie: 'csrftoken=csrf-one', currentScript: {dataset: {authAccount: 'account-1', authSession: 'session-1'}}};
  const window = {
    location: {href: 'https://kiosk.test/orders/order/', origin: 'https://kiosk.test', assign: path => redirects.push(path)},
    navigator: locks ? {locks} : {},
    setTimeout: callback => setTimeout(callback, 0),
    fetch: async (input, options) => {
      const request = input instanceof Request ? input : new Request(new URL(input, window.location.href), options);
      calls.push(request);
      return handler(request, calls);
    }
  };
  Object.defineProperties(window, {
    localStorage: {get() {throw new Error('No localStorage');}},
    sessionStorage: {get() {throw new Error('No sessionStorage');}}
  });
  runInNewContext(source, {window, document, URL, Request, Headers, Promise, Error, TypeError, Object});
  return {fetch: window.BazaarAuth.fetch, calls, redirects, document, window};
}
const isRefresh = request => request.url.endsWith('/orders/auth/refresh/');

test('access stays private; parallel cold requests refresh once and get current CSRF', async () => {
  const app = client(async request => {
    if (isRefresh(request)) {await new Promise(resolve => setTimeout(resolve, 5)); return tokenResponse();}
    return new Response('{}');
  });
  await Promise.all([app.fetch('/orders/menus/'), app.fetch('/orders/tables/')]);
  assert.equal(app.calls.filter(isRefresh).length, 1);
  assert.equal(app.calls[0].headers.get('X-CSRFToken'), 'csrf-one');
  app.document.cookie = 'csrftoken=csrf-two';
  await app.fetch('/orders/api/orders/', {method: 'POST', body: '{}'});
  const write = app.calls.at(-1);
  assert.equal(write.headers.get('Authorization'), 'Bearer access-1');
  assert.equal(write.headers.get('X-CSRFToken'), 'csrf-two');
  assert.equal(write.credentials, 'same-origin');
  assert.equal(write.redirect, 'error');
  assert.equal(write.cache, 'no-store');
  assert.deepEqual(Object.keys(app.window.BazaarAuth), ['fetch']);
});

test('cross-origin URL or Request is rejected before any credentials are sent', async () => {
  const app = client(() => tokenResponse());
  await assert.rejects(app.fetch('https://other.test/orders/'), /출처/);
  await assert.rejects(app.fetch(new Request('https://other.test/orders/')), /출처/);
  assert.equal(app.calls.length, 0);
});

test('explicit 401 rotates once and replays the same POST body once', async () => {
  let refreshes = 0;
  let writes = 0;
  const bodies = [];
  const app = client(async request => {
    if (isRefresh(request)) return tokenResponse(`access-${++refreshes}`);
    bodies.push(await request.text());
    writes += 1;
    return new Response('{}', {status: writes === 1 ? 401 : 200});
  });
  const response = await app.fetch(new Request('https://kiosk.test/orders/api/orders/', {method: 'POST', body: '{"qty":2}'}));
  assert.equal(response.status, 200);
  assert.equal(refreshes, 2);
  assert.deepEqual(bodies, ['{"qty":2}', '{"qty":2}']);
  assert.equal(app.calls.at(-1).headers.get('Authorization'), 'Bearer access-2');
});

test('403 is returned without a second refresh or API replay', async () => {
  const app = client(request => isRefresh(request) ? tokenResponse() : new Response('{}', {status: 403}));
  assert.equal((await app.fetch('/orders/menus/')).status, 403);
  assert.equal(app.calls.length, 2);
  assert.deepEqual(app.redirects, []);
});

test('a network failure never replays a possibly accepted mutation', async () => {
  const app = client(request => {
    if (isRefresh(request)) return tokenResponse();
    throw new Error('connection lost after write');
  });
  await assert.rejects(app.fetch('/orders/api/orders/', {method: 'POST', body: '{}'}), /connection lost/);
  assert.equal(app.calls.length, 2);
});

test('409 retries refresh with fresh cookie CSRF and optional cross-tab lock', async () => {
  let refreshes = 0;
  const locks = [];
  const app = client(request => {
    if (!isRefresh(request)) return new Response('{}');
    refreshes += 1;
    if (refreshes === 1) {
      app.document.cookie = 'csrftoken=csrf-rotated';
      return new Response('{}', {status: 409});
    }
    assert.equal(request.headers.get('X-CSRFToken'), 'csrf-rotated');
    return tokenResponse();
  }, {request: async (name, run) => {locks.push(name); return run();}});
  await app.fetch('/orders/menus/');
  assert.equal(refreshes, 2);
  assert.deepEqual(locks, ['bazaar-refresh']);
});

test('persistent 409 stops after five attempts without sending the API request', async () => {
  const app = client(() => new Response('{}', {status: 409}));
  await assert.rejects(app.fetch('/orders/menus/'), /409/);
  assert.equal(app.calls.length, 5);
  assert.ok(app.calls.every(isRefresh));
});

test('refresh 401 redirects once; repeated API 401 cannot loop', async () => {
  const unauthenticated = client(() => new Response('{}', {status: 401}));
  await assert.rejects(unauthenticated.fetch('/orders/menus/'), /로그인/);
  assert.deepEqual(unauthenticated.redirects, ['/orders/login/']);
  assert.equal(unauthenticated.calls.length, 1);
  const revoked = client(request => isRefresh(request) ? tokenResponse() : new Response('{}', {status: 401}));
  await assert.rejects(revoked.fetch('/orders/menus/'), /로그인/);
  assert.equal(revoked.calls.length, 4);
  assert.deepEqual(revoked.redirects, ['/orders/login/']);
});

test('concurrent expired-token responses share one refresh even when one arrives late', async () => {
  let refreshes = 0;
  let expiredResponses = 0;
  const app = client(async request => {
    if (isRefresh(request)) {
      refreshes += 1;
      return tokenResponse(`access-${refreshes}`);
    }
    if (request.url.endsWith('/warmup')) return new Response('{}');
    if (request.headers.get('Authorization') === 'Bearer access-1') {
      expiredResponses += 1;
      if (expiredResponses === 2) await new Promise(resolve => setTimeout(resolve, 10));
      return new Response('{}', {status: 401});
    }
    return new Response('{}');
  });
  await app.fetch('/warmup');
  const responses = await Promise.all([app.fetch('/orders/menus/'), app.fetch('/orders/tables/')]);
  assert.ok(responses.every(response => response.status === 200));
  assert.equal(refreshes, 2);
});

test('bootstrap after account switch cannot send the old page action', async () => {
  const app = client(() => tokenResponse('counter-access', 'account-2', 'session-2'));
  await assert.rejects(app.fetch('/orders/api/orders/', {method: 'POST', body: '{"qty":2}'}), /로그인/);
  assert.equal(app.calls.length, 1);
  assert.ok(app.calls.every(isRefresh));
  assert.deepEqual(app.redirects, ['/orders/login/']);
  // A timer or second click before navigation completes must stay blocked.
  await assert.rejects(app.fetch('/orders/api/orders/', {method: 'POST', body: '{}'}), /로그인/);
  assert.equal(app.calls.length, 1);
});

test('outstanding POST 401 after an account switch never replays under new identity', async () => {
  let refreshes = 0;
  const app = client(request => {
    if (isRefresh(request)) {
      refreshes += 1;
      return refreshes === 1 ? tokenResponse() : tokenResponse('counter-access', 'account-2', 'session-2');
    }
    return new Response('{}', {status: 401});
  });
  await assert.rejects(app.fetch('/orders/api/orders/', {method: 'POST', body: '{"qty":2}'}), /로그인/);
  const writes = app.calls.filter(request => !isRefresh(request));
  assert.equal(refreshes, 2);
  assert.equal(writes.length, 1);
  assert.equal(writes[0].headers.get('Authorization'), 'Bearer access-1');
  assert.deepEqual(app.redirects, ['/orders/login/']);
});

test('same-account fresh login in another tab is also a different session', async () => {
  const app = client(() => tokenResponse('fresh-access', 'account-1', 'session-2'));
  await assert.rejects(app.fetch('/orders/api/orders/', {method: 'POST', body: '{}'}), /로그인/);
  assert.equal(app.calls.length, 1);
  assert.ok(app.calls.every(isRefresh));
});

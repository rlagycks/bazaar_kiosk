/* 10D2: the kitchen board's one scheduler (BK-R020, BK-R033).
 *
 * Run with: node --test scripts/test_kitchen_live.cjs (no dependencies).
 *
 * The module is loaded into a fake window with a manual clock, a recording
 * fetch and a scripted EventSource, so every path the card names can be
 * driven deterministically: CONNECTING and CLOSED, a hidden tab, a network
 * cut, a failed HTTP read, a late response, revocation mid-stream, and a
 * hub that is beating but not working. A real browser remains the
 * acceptance evidence; this pins the properties in CI.
 */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {runInNewContext} = require('node:vm');

const source = readFileSync(new URL('../orders/static/orders/ui/kitchen_live.js', `file://${__filename}`), 'utf8');

const STREAM = '/orders/api/stream/kitchen';
const SNAPSHOT = '/orders/api/snapshot/waiting';
const POLL_MS = 5000;

function snapshot(version, orders, extra) {
  return Object.assign({
    version, unchanged: false, cursor: 'absent', orders, count: orders.length,
    total: orders.length, has_more: false, complete: true,
  }, extra || {});
}

function harness(options) {
  const settings = options || {};
  let now = 0;
  let nextId = 1;
  let timers = [];
  const window = {
    location: {href: 'http://kiosk.test/orders/kitchen/', origin: 'http://kiosk.test'},
    setTimeout(fn, ms) {
      const id = nextId++;
      // The module arms every timer with a named function, so a test can say
      // which one it is looking at without the module exposing its internals.
      const kind = String(fn.name || '').replace(/Due$/, '') || 'anonymous';
      timers.push({id, fn, at: now + ms, ms, kind});
      return id;
    },
    clearTimeout(id) { timers = timers.filter(t => t.id !== id); },
  };
  const listeners = {};
  const document = {
    hidden: settings.hidden === true,
    addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
    dispatch(type, event) { (listeners[type] || []).forEach(fn => fn(event || {})); },
  };
  window.document = document;
  window.addEventListener = document.addEventListener;

  const sources = [];
  class EventSource {
    constructor(url) {
      this.url = url;
      this.readyState = EventSource.CONNECTING;
      this.handlers = {};
      this.closed = false;
      sources.push(this);
    }
    addEventListener(type, fn) { (this.handlers[type] = this.handlers[type] || []).push(fn); }
    close() { this.closed = true; this.readyState = EventSource.CLOSED; }
    frame(name, payload) {
      if (this.closed) throw new Error('frame on a closed source');
      this.readyState = EventSource.OPEN;
      (this.handlers[name] || []).forEach(fn => fn({data: JSON.stringify(payload)}));
    }
    error(readyState) {
      this.readyState = readyState;
      (this.handlers.error || []).forEach(fn => fn({}));
    }
  }
  EventSource.CONNECTING = 0;
  EventSource.OPEN = 1;
  EventSource.CLOSED = 2;

  const pending = [];
  const fetchCalls = [];
  const fetch = (url, opts) => new Promise((resolve, reject) => {
    fetchCalls.push({url, opts});
    pending.push({url, resolve, reject});
  });

  const applied = [];
  const statuses = [];
  let authLost = 0;
  runInNewContext(source, {window, document, URL, Object, Error, Promise, Math, JSON, Number, String, Date});
  const live = window.BazaarLive.create({
    streamUrl: STREAM,
    snapshotUrl: SNAPSHOT,
    fetch,
    EventSource,
    document,
    window,
    pollMs: POLL_MS,
    // Deterministic by default: no jitter, so the backoff tests can name the
    // exact delays. The jitter test passes its own `random`.
    random: settings.random || (() => 0),
    onApply: data => {
      applied.push(data);
      if (typeof settings.onApply === 'function') settings.onApply(data);
    },
    onStatus: state => statuses.push(state),
    onAuthLost: () => { authLost += 1; },
  });

  const flush = () => new Promise(resolve => setImmediate(resolve));
  async function respond(body, init) {
    const call = pending.shift();
    if (!call) throw new Error('no fetch in flight');
    const status = (init && init.status) || 200;
    call.resolve({ok: status >= 200 && status < 300, status, json: async () => body});
    await flush();
    await flush();
  }
  async function fail(error) {
    const call = pending.shift();
    if (!call) throw new Error('no fetch in flight');
    call.reject(error || new TypeError('Failed to fetch'));
    await flush();
    await flush();
  }
  async function advance(ms) {
    const until = now + ms;
    for (;;) {
      const due = timers.filter(t => t.at <= until).sort((a, b) => a.at - b.at)[0];
      if (!due) break;
      now = due.at;
      timers = timers.filter(t => t.id !== due.id);
      due.fn();
      await flush();
    }
    now = until;
    await flush();
  }
  return {
    live, sources, fetchCalls, pending, applied, statuses, document, window,
    respond, fail, advance, flush,
    get source() { return sources[sources.length - 1]; },
    get timers() { return timers.slice(); },
    get authLost() { return authLost; },
    state: () => live.state(),
  };
}

async function opened(h) {
  h.live.start();
  await h.flush();
  return h.source;
}

test('starting opens one same-origin stream and reads the snapshot once', async () => {
  const h = harness();
  const source = await opened(h);
  assert.equal(h.sources.length, 1);
  assert.equal(source.url, STREAM);
  assert.equal(h.fetchCalls.length, 1);
  assert.equal(h.fetchCalls[0].url, SNAPSHOT);
  assert.equal(h.fetchCalls[0].opts.credentials, 'same-origin');
  await h.respond(snapshot('g:1:s', [{id: 1}]));
  assert.equal(h.applied.length, 1);
  assert.equal(h.state().applied.version, 'g:1:s');
});

test('a cross-origin stream URL is refused before anything is opened', () => {
  const h = harness();
  assert.throws(() => h.window.BazaarLive.create({
    streamUrl: 'http://other.test/orders/api/stream/kitchen', snapshotUrl: SNAPSHOT,
    fetch: h.window.fetch, EventSource: function () {}, document: h.document, window: h.window,
    onApply() {}, onStatus() {}, onAuthLost() {},
  }), /출처/);
});

test('polling runs until the stream is ready, the hub is healthy and a complete snapshot is applied -- then stops', async () => {
  const h = harness();
  const source = await opened(h);
  await h.respond(snapshot('g:1:s', []));
  // No `ready` yet: the stream is still connecting, so the board polls.
  assert.equal(h.state().polling, true);
  assert.equal(h.timers.length, 1);
  await h.advance(POLL_MS);
  assert.equal(h.fetchCalls.length, 2, 'the poll timer read the snapshot');
  assert.ok(h.fetchCalls[1].url.includes('since=g%3A1%3As'), 'a poll sends the version it holds');
  await h.respond(snapshot('g:1:s', [], {unchanged: true, cursor: 'accepted'}));
  assert.equal(h.applied.length, 1, 'an unchanged answer redraws nothing');

  source.frame('ready', {version: 'g:1:s', heartbeat_ms: 15000, hub_ok: true, stale_ms: 0, failures: 0});
  await h.flush();
  assert.equal(h.fetchCalls.length, 3, '`ready` reads once: something may have changed while connecting');
  await h.respond(snapshot('g:2:s', [{id: 2}]));
  assert.equal(h.state().stream, 'open');
  assert.equal(h.state().polling, false, 'D-019: hub ok + complete snapshot ends polling');
  assert.deepEqual(h.timers.filter(t => t.kind === 'poll'), [], 'no poll timer is armed while live');
});

test('a heartbeat alone never stops polling: hub_ok false keeps it, hub_ok true with a complete snapshot ends it', async () => {
  const h = harness();
  const source = await opened(h);
  await h.respond(snapshot('g:1:s', []));
  source.frame('ready', {version: 'g:1:s', heartbeat_ms: 15000, hub_ok: false, stale_ms: 4000, failures: 3});
  await h.flush();
  await h.respond(snapshot('g:1:s', [], {unchanged: true, cursor: 'accepted'}));
  assert.equal(h.state().polling, true, 'the stream is open but the hub cannot see changes');
  source.frame('heartbeat', {hub_ok: false, stale_ms: 9000, failures: 4});
  await h.flush();
  assert.equal(h.state().polling, true);
  await h.advance(POLL_MS);
  assert.equal(h.fetchCalls.length, 3, 'the poll went on during a beating but broken hub');
  await h.respond(snapshot('g:1:s', [], {unchanged: true, cursor: 'accepted'}));
  source.frame('heartbeat', {hub_ok: true, stale_ms: 10, failures: 0});
  await h.flush();
  assert.equal(h.state().polling, false);
});

test('an incomplete snapshot keeps polling even on a healthy stream', async () => {
  const h = harness();
  const source = await opened(h);
  await h.respond(snapshot('g:1:s', [{id: 1}], {complete: false, has_more: true, total: 501}));
  source.frame('ready', {version: 'g:1:s', heartbeat_ms: 15000, hub_ok: true, stale_ms: 0, failures: 0});
  await h.flush();
  await h.respond(snapshot('g:1:s', [], {unchanged: true, cursor: 'accepted'}));
  assert.equal(h.state().polling, true, 'a version on a cut list is not a claim of holding everything');
});

test('a change frame refetches with the held version; bursts collapse into one extra read', async () => {
  const h = harness();
  const source = await opened(h);
  await h.respond(snapshot('g:1:s', []));
  source.frame('ready', {version: 'g:1:s', heartbeat_ms: 15000, hub_ok: true, stale_ms: 0, failures: 0});
  await h.flush();
  await h.respond(snapshot('g:1:s', [], {unchanged: true, cursor: 'accepted'}));
  assert.equal(h.fetchCalls.length, 2);

  source.frame('change', {});
  await h.flush();
  assert.equal(h.fetchCalls.length, 3);
  // Three more while that read is in flight: one follow-up, not three.
  source.frame('change', {});
  source.frame('change', {reset: true});
  source.frame('change', {});
  await h.flush();
  assert.equal(h.fetchCalls.length, 3);
  await h.respond(snapshot('g:2:s', [{id: 2}]));
  assert.equal(h.fetchCalls.length, 4, 'exactly one follow-up read for the burst');
  assert.ok(h.fetchCalls[3].url.includes('since=g%3A2%3As'));
  await h.respond(snapshot('g:2:s', [], {unchanged: true, cursor: 'accepted'}));
  assert.equal(h.applied.length, 2);
});

test('a write asks for one immediate read through the same scheduler', async () => {
  const h = harness();
  const source = await opened(h);
  await h.respond(snapshot('g:1:s', []));
  source.frame('ready', {version: 'g:1:s', heartbeat_ms: 15000, hub_ok: true, stale_ms: 0, failures: 0});
  await h.flush();
  await h.respond(snapshot('g:1:s', [], {unchanged: true, cursor: 'accepted'}));
  h.live.refetch('write');
  await h.flush();
  assert.equal(h.fetchCalls.length, 3);
  assert.equal(h.pending.length, 1);
});

test('a response from before the tab was hidden is late and is not applied over the newer one', async () => {
  const h = harness();
  const source = await opened(h);
  await h.respond(snapshot('g:1:s', [{id: 1}]));
  source.frame('ready', {version: 'g:1:s', heartbeat_ms: 15000, hub_ok: true, stale_ms: 0, failures: 0});
  await h.flush();
  const late = h.pending.shift();          // the `ready` read, held back

  h.document.hidden = true;
  h.document.dispatch('visibilitychange');
  await h.flush();
  assert.equal(source.closed, true, 'a hidden tab holds no stream');
  assert.equal(h.timers.length, 0, 'and arms no timer');

  h.document.hidden = false;
  h.document.dispatch('visibilitychange');
  await h.flush();
  assert.equal(h.sources.length, 2, 'coming back opens a fresh stream');
  await h.respond(snapshot('g:3:s', [{id: 3}]));
  assert.equal(h.state().applied.version, 'g:3:s');

  late.resolve({ok: true, status: 200, json: async () => snapshot('g:2:s', [{id: 2}])});
  await h.flush();
  await h.flush();
  assert.equal(h.state().applied.version, 'g:3:s', 'the late 2 did not overwrite the applied 3');
  assert.equal(h.applied.length, 2);
});

test('a read that resolves while the tab is still hidden is dropped, not applied', async () => {
  // The half of the late-response property that the request counter cannot
  // cover: no newer read has been issued yet, so only the pause epoch says
  // this answer is stale (10D2 code review).
  const h = harness();
  const source = await opened(h);
  await h.respond(snapshot('g:1:s', [{id: 1}]));
  source.frame('ready', {version: 'g:1:s', heartbeat_ms: 15000, hub_ok: true, stale_ms: 0, failures: 0});
  await h.flush();
  const late = h.pending.shift();          // the `ready` read, still in flight
  h.document.hidden = true;
  h.document.dispatch('visibilitychange');
  await h.flush();
  late.resolve({ok: true, status: 200, json: async () => snapshot('g:2:s', [{id: 2}])});
  await h.flush();
  await h.flush();
  assert.equal(h.applied.length, 1, 'nothing was drawn while hidden');
  assert.equal(h.state().applied.version, 'g:1:s', 'the paused board still holds what it showed');
  assert.equal(h.state().inFlight, false);
});

test('coming back to the tab starts the reconnect backoff over', async () => {
  const h = harness();
  const source = await opened(h);
  await h.respond(snapshot('g:1:s', []));
  source.error(2);
  await h.flush();
  await h.advance(2000);
  while (h.pending.length) await h.respond(snapshot('g:1:s', [], {unchanged: true, cursor: 'accepted'}));
  h.source.error(2);
  await h.flush();
  assert.equal(h.timers.find(t => t.kind === 'reconnect').ms, 4000);
  h.document.hidden = true;
  h.document.dispatch('visibilitychange');
  h.document.hidden = false;
  h.document.dispatch('visibilitychange');
  await h.flush();
  while (h.pending.length) await h.respond(snapshot('g:1:s', [], {unchanged: true, cursor: 'accepted'}));
  h.source.error(2);
  await h.flush();
  assert.equal(h.timers.find(t => t.kind === 'reconnect').ms, 2000, 'a fresh tab is not punished for the old stream');
});

test('an EventSource in CONNECTING is left to its native retry, with polling meanwhile', async () => {
  const h = harness();
  const source = await opened(h);
  await h.respond(snapshot('g:1:s', []));
  source.frame('ready', {version: 'g:1:s', heartbeat_ms: 15000, hub_ok: true, stale_ms: 0, failures: 0});
  await h.flush();
  await h.respond(snapshot('g:1:s', [], {unchanged: true, cursor: 'accepted'}));
  assert.equal(h.state().polling, false);

  source.error(0 /* CONNECTING */);
  await h.flush();
  assert.equal(h.state().stream, 'connecting');
  assert.equal(h.state().polling, true);
  assert.equal(h.sources.length, 1, 'the browser reconnects this one; we do not open another');
  await h.advance(POLL_MS);
  assert.equal(h.fetchCalls.length, 3);
  await h.respond(snapshot('g:1:s', [], {unchanged: true, cursor: 'accepted'}));

  source.frame('ready', {version: 'g:1:s', heartbeat_ms: 15000, hub_ok: true, stale_ms: 0, failures: 0});
  await h.flush();
  await h.respond(snapshot('g:1:s', [], {unchanged: true, cursor: 'accepted'}));
  assert.equal(h.state().polling, false);
});

test('an EventSource that CLOSED is reopened by us with a bounded backoff, polling meanwhile', async () => {
  const h = harness();
  const source = await opened(h);
  await h.respond(snapshot('g:1:s', []));
  source.error(2 /* CLOSED: a 503 or a refusal the browser will not retry */);
  await h.flush();
  assert.equal(h.state().stream, 'closed');
  assert.equal(h.state().polling, true);
  const delays = [];
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const reconnect = h.timers.find(t => t.kind === 'reconnect');
    assert.ok(reconnect, `attempt ${attempt} armed a reconnect`);
    delays.push(reconnect.ms);
    await h.advance(reconnect.ms);
    while (h.pending.length) await h.respond(snapshot('g:1:s', [], {unchanged: true, cursor: 'accepted'}));
    h.source.error(2);
    await h.flush();
  }
  assert.deepEqual(delays, [2000, 4000, 8000, 16000, 30000, 30000], 'doubling, capped');
  assert.equal(h.sources.length, 7);
});

test('closed: unverified reconnects with backoff; a successful ready resets it', async () => {
  const h = harness();
  const source = await opened(h);
  await h.respond(snapshot('g:1:s', []));
  source.frame('closed', {reason: 'unverified'});
  await h.flush();
  assert.equal(source.closed, true);
  assert.equal(h.state().polling, true);
  let reconnect = h.timers.find(t => t.kind === 'reconnect');
  assert.equal(reconnect.ms, 2000);
  await h.advance(2000);
  while (h.pending.length) await h.respond(snapshot('g:1:s', [], {unchanged: true, cursor: 'accepted'}));
  h.source.frame('closed', {reason: 'unverified'});
  await h.flush();
  reconnect = h.timers.find(t => t.kind === 'reconnect');
  assert.equal(reconnect.ms, 4000);
  await h.advance(4000);
  while (h.pending.length) await h.respond(snapshot('g:1:s', [], {unchanged: true, cursor: 'accepted'}));
  h.source.frame('ready', {version: 'g:1:s', heartbeat_ms: 15000, hub_ok: true, stale_ms: 0, failures: 0});
  await h.flush();
  await h.respond(snapshot('g:1:s', [], {unchanged: true, cursor: 'accepted'}));
  h.source.frame('closed', {reason: 'unverified'});
  await h.flush();
  reconnect = h.timers.find(t => t.kind === 'reconnect');
  assert.equal(reconnect.ms, 2000, 'a ready in between started the backoff over');
  assert.equal(h.authLost, 0);
});

test('closed: revoked or reauthenticate ends everything and hands off to login', async () => {
  for (const reason of ['revoked', 'reauthenticate']) {
    const h = harness();
    const source = await opened(h);
    await h.respond(snapshot('g:1:s', [{id: 1}]));
    source.frame('ready', {version: 'g:1:s', heartbeat_ms: 15000, hub_ok: true, stale_ms: 0, failures: 0});
    await h.flush();
    await h.respond(snapshot('g:1:s', [], {unchanged: true, cursor: 'accepted'}));
    source.frame('closed', {reason});
    await h.flush();
    assert.equal(h.authLost, 1, reason);
    assert.equal(source.closed, true);
    assert.equal(h.timers.length, 0, `${reason}: no timer survives`);
    assert.equal(h.pending.length, 0, `${reason}: no read is issued`);
    assert.equal(h.state().ended, true);
    h.live.refetch('write');
    await h.flush();
    assert.equal(h.pending.length, 0, `${reason}: a later refetch is ignored`);
    h.live.start();
    await h.flush();
    assert.equal(h.sources.length, 1, `${reason}: a later start is ignored`);
  }
});

test('losing authentication during a read ends everything too', async () => {
  const h = harness();
  const source = await opened(h);
  const lost = new Error('로그인이 필요합니다.');
  lost.name = 'AuthenticationLost';
  await h.fail(lost);
  assert.equal(h.state().ended, true);
  assert.equal(source.closed, true);
  assert.equal(h.timers.length, 0);
  assert.equal(h.authLost, 1);
});

test('a failed read keeps what is applied, reports it, and keeps polling', async () => {
  const h = harness();
  const source = await opened(h);
  await h.respond(snapshot('g:1:s', [{id: 1}]));
  source.frame('ready', {version: 'g:1:s', heartbeat_ms: 15000, hub_ok: true, stale_ms: 0, failures: 0});
  await h.flush();
  await h.fail(new TypeError('Failed to fetch'));
  assert.equal(h.state().applied.version, 'g:1:s', 'nothing was thrown away');
  assert.equal(h.applied.length, 1);
  assert.ok(h.state().lastError, 'the failure is reported rather than swallowed');
  assert.equal(h.state().polling, true, 'a healthy stream is not evidence the last read is current');
  await h.advance(POLL_MS);
  await h.respond(snapshot('g:1:s', [], {status: 500}), {status: 500});
  assert.ok(h.state().lastError);
  await h.advance(POLL_MS);
  await h.respond(snapshot('g:1:s', [], {unchanged: true, cursor: 'accepted'}));
  assert.equal(h.state().lastError, null);
  assert.equal(h.state().polling, false);
});

test('silence longer than two heartbeats is a dead connection: reopen and poll', async () => {
  const h = harness();
  const source = await opened(h);
  await h.respond(snapshot('g:1:s', []));
  source.frame('ready', {version: 'g:1:s', heartbeat_ms: 15000, hub_ok: true, stale_ms: 0, failures: 0});
  await h.flush();
  await h.respond(snapshot('g:1:s', [], {unchanged: true, cursor: 'accepted'}));
  assert.equal(h.state().polling, false);
  await h.advance(15000);
  source.frame('heartbeat', {hub_ok: true, stale_ms: 5, failures: 0});
  await h.flush();
  assert.equal(h.state().polling, false, 'a beat on time keeps it live');
  await h.advance(30000 + 1);
  assert.equal(source.closed, true, 'a cable pulled without a FIN looks like silence');
  assert.equal(h.state().stream, 'closed');
  assert.equal(h.state().polling, true);
  assert.ok(h.timers.find(t => t.kind === 'reconnect'));
});

test('a page loaded hidden waits; pagehide closes, pageshow reopens', async () => {
  const h = harness({hidden: true});
  h.live.start();
  await h.flush();
  assert.equal(h.sources.length, 0);
  assert.equal(h.fetchCalls.length, 0);
  h.document.hidden = false;
  h.document.dispatch('visibilitychange');
  await h.flush();
  assert.equal(h.sources.length, 1);
  assert.equal(h.fetchCalls.length, 1);
  await h.respond(snapshot('g:1:s', []));

  h.document.dispatch('pagehide', {persisted: true});
  await h.flush();
  assert.equal(h.source.closed, true, 'BFCache gets a page holding no connection');
  assert.equal(h.timers.length, 0);
  h.document.dispatch('pageshow', {persisted: true});
  await h.flush();
  assert.equal(h.sources.length, 2);
  assert.equal(h.fetchCalls.length, 2, 'restored from BFCache: read once, the world moved on');
});

test('a manual refetch is reported as in flight and then not', async () => {
  const h = harness();
  await opened(h);
  assert.equal(h.state().inFlight, true);
  await h.respond(snapshot('g:1:s', []));
  assert.equal(h.state().inFlight, false);
  const before = h.statuses.length;
  h.live.refetch('manual');
  await h.flush();
  assert.equal(h.state().inFlight, true);
  assert.ok(h.statuses.length > before, 'status listeners hear the change');
});

test('a browser without EventSource polls and never pretends to be live', async () => {
  const h = harness();
  const live = h.window.BazaarLive.create({
    streamUrl: STREAM, snapshotUrl: SNAPSHOT, fetch: (url, opts) => h.window.fetch(url, opts),
    EventSource: undefined, document: h.document, window: h.window, pollMs: POLL_MS,
    onApply() {}, onStatus() {}, onAuthLost() {},
  });
  live.start();
  await h.flush();
  assert.equal(h.sources.length, 0);
  assert.equal(live.state().stream, 'closed');
  assert.equal(live.state().polling, true);
  assert.ok(h.timers.find(t => t.kind === 'poll') || h.pending.length === 1);
  assert.equal(h.timers.filter(t => t.kind === 'reconnect').length, 0, 'nothing to reconnect');
});

// ---- PR #80 review ----

test('a snapshot the board could not draw is not recorded as applied: the next read asks again', async () => {
  // The other order -- record, then draw -- commits a version whose data
  // never reached the screen. The following `since=` read comes back
  // `unchanged`, `lastError` clears, polling stops, and the kitchen looks at
  // a stale board under a status line that says live (PR #80 architecture
  // review).
  let broken = true;
  const h = harness({onApply: () => { if (broken) throw new Error('render failed'); }});
  const source = await opened(h);
  await h.respond(snapshot('g:1:s', [{id: 1}]));
  assert.equal(h.state().lastError, 'render failed');
  assert.equal(h.state().applied.version, null, 'what was not drawn is not held');
  source.frame('ready', {version: 'g:1:s', heartbeat_ms: 15000, hub_ok: true, stale_ms: 0, failures: 0});
  await h.flush();
  assert.equal(h.fetchCalls[h.fetchCalls.length - 1].url, SNAPSHOT, 'no cursor: the whole list again');
  broken = false;
  await h.respond(snapshot('g:1:s', [{id: 1}]));
  assert.equal(h.state().lastError, null);
  assert.equal(h.state().applied.version, 'g:1:s');
  assert.equal(h.state().polling, false, 'live only once something was actually drawn');
});

test('a ready without heartbeat_ms still arms silence detection, from the fallback interval', async () => {
  const h = harness();
  const source = await opened(h);
  await h.respond(snapshot('g:1:s', []));
  source.frame('ready', {version: 'g:1:s', hub_ok: true, stale_ms: 0, failures: 0});
  await h.flush();
  const silence = h.timers.find(t => t.kind === 'silence');
  assert.ok(silence, 'a stream that never says its interval is not exempt from being dead');
  assert.equal(silence.ms, 15000 * 2 + 1);
  assert.equal(h.state().heartbeatMs, 15000);
});

test('reconnect delays are jittered downwards only: never past the cap, never zero', async () => {
  const h = harness({random: () => 1});
  const source = await opened(h);
  await h.respond(snapshot('g:1:s', []));
  source.error(2);
  await h.flush();
  const delays = [];
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const reconnect = h.timers.find(t => t.kind === 'reconnect');
    delays.push(reconnect.ms);
    await h.advance(reconnect.ms);
    while (h.pending.length) await h.respond(snapshot('g:1:s', [], {unchanged: true, cursor: 'accepted'}));
    h.source.error(2);
    await h.flush();
  }
  assert.deepEqual(delays, [1600, 3200, 6400, 12800, 24000, 24000], 'each 20% short of its base, still doubling');
  assert.ok(delays.every(ms => ms > 0 && ms <= 30000));
});

test('a change frame is evidence the hub read the database: it clears hub_ok:false from ready', async () => {
  // `change` carries no `hub_ok`, and a heartbeat only comes after a full
  // idle interval. A board whose `ready` caught the hub before its first
  // read would otherwise poll for as long as the kitchen stays busy (PR #80
  // architecture review).
  const h = harness();
  const source = await opened(h);
  await h.respond(snapshot('g:1:s', []));
  source.frame('ready', {version: 'g:1:s', heartbeat_ms: 15000, hub_ok: false, stale_ms: null, failures: 0});
  await h.flush();
  await h.respond(snapshot('g:1:s', [], {unchanged: true, cursor: 'accepted'}));
  assert.equal(h.state().polling, true);
  source.frame('change', {});
  await h.flush();
  await h.respond(snapshot('g:2:s', [{id: 1}]));
  assert.equal(h.state().hubOk, true);
  assert.equal(h.state().polling, false, 'the change proved the hub is reading');
});

test('a list read before a cancel and answered after it is applied, then corrected by the read the write asked for', async () => {
  // BK-R033's scenario, with one path: the write draws nothing itself, so
  // the late list can only put back what the board was already showing, and
  // the read queued behind it removes the card. The board converges; it does
  // not reject the late list (KITCHEN_CLIENT.md, "쓰기 응답은 그리지 않는다").
  const h = harness();
  const source = await opened(h);
  await h.respond(snapshot('g:1:s', [{id: 1}]));
  source.frame('ready', {version: 'g:1:s', heartbeat_ms: 15000, hub_ok: true, stale_ms: 0, failures: 0});
  await h.flush();
  const before = h.pending.shift();        // the `ready` read: issued before the cancel, still in flight
  h.live.refetch('write');                  // the cancel's PATCH finished; the board asks for a read
  await h.flush();
  assert.equal(h.pending.length, 0, 'one read at a time: the write waits behind the one in flight');
  before.resolve({ok: true, status: 200, json: async () => snapshot('g:1:s', [{id: 1}], {unchanged: true, cursor: 'accepted'})});
  await h.flush();
  await h.flush();
  assert.equal(h.state().applied.version, 'g:1:s', 'the pre-cancel answer was applied: it changed nothing');
  assert.equal(h.pending.length, 1, 'and the read the write asked for went out');
  assert.ok(h.fetchCalls[h.fetchCalls.length - 1].url.includes('since=g%3A1%3As'));
  await h.respond(snapshot('g:2:s', []));
  assert.equal(h.state().applied.version, 'g:2:s');
  assert.deepEqual(h.applied[h.applied.length - 1].orders, [], 'the card is gone once the post-write read lands');
});

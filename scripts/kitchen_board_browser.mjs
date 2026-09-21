// V-BROWSER for 10D2: the kitchen board in a real browser (BK-R020, BK-R033).
//
// Drives a headless Chrome over its own DevTools protocol against a running
// dev server, so the acceptance evidence in docs/modernization/KITCHEN_CLIENT.md
// can be produced again. No dependencies beyond Node 24 (WebSocket, fetch) and
// a local Chrome. Like scripts/stream_smoke.py it does not start the stack:
//
//   # an isolated PostgreSQL (see POSTGRES_TESTING.md), a database on it with
//   # the migrations applied, an account "kitchen" holding both monitor
//   # permissions, a table 1 and a menu item, and the dev server:
//   PYTHONPATH=. uvicorn bazaar_kiosk.asgi:application --port 8010   # plus static files
//   BK_BROWSER_BASE=http://localhost:8010 BK_BROWSER_ENV=/path/to/env.sh \
//     node scripts/kitchen_board_browser.mjs
//
// BK_BROWSER_ENV is sourced before every server-side action (it carries
// DATABASE_URL and the other settings the dev server was started with), and
// BK_BROWSER_SERVER is the command that restarts that server (and
// BK_BROWSER_SERVER_PATTERN what `pkill -f` stops, default "uvicorn") for the
// "HTTP failure, then reconnect" step; without it that step is skipped.
// Everything here writes only to that throwaway database.
import {spawn, spawnSync, execSync} from 'node:child_process';
import {mkdtempSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';

const CHROME = process.env.BK_BROWSER_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const BASE = process.env.BK_BROWSER_BASE || 'http://localhost:8010';
const PORT = Number(process.env.BK_BROWSER_CDP_PORT || 9223);
const ROOT = new URL('..', import.meta.url).pathname;
const ENV_FILE = process.env.BK_BROWSER_ENV || '';
const SERVER_COMMAND = process.env.BK_BROWSER_SERVER || '';
const SERVER_PATTERN = process.env.BK_BROWSER_SERVER_PATTERN || 'uvicorn';
const ACCOUNT = process.env.BK_BROWSER_ACCOUNT || 'kitchen';
const PASSWORD = process.env.BK_BROWSER_PASSWORD || 'test-event-password';
const ACTIONS = `
from django.db import connection, transaction
# Every action below writes. Refuse anything that is not obviously a
# throwaway database, whatever BK_BROWSER_ENV happened to point at.
_name = connection.settings_dict["NAME"]
if not _name.startswith(("bk_dev", "bk_test")):
    raise SystemExit("refusing to write to database %r: not a bk_dev*/bk_test* name" % _name)
from orders.models import Account, MenuItem, Order, OrderItem, OrderStatus, OrderType, Table
from orders.services import revisions
if ACTION == "order":
    with transaction.atomic():
        order = Order.objects.create(table=Table.objects.order_by("number").first(), floor="B1",
            order_type="DINE_IN", status=OrderStatus.PREPARING, total_price=6000,
            payment_method="CASH", received_cash_amount=6000)
        OrderItem.objects.create(order=order, menu_item=MenuItem.objects.order_by("id").first(),
            qty=2, unit_price=3000, service_mode=OrderType.DINE_IN)
        revisions.mark()
    print(order.id)
elif ACTION == "deactivate":
    print(Account.objects.filter(name=NAME).update(is_active=False))
elif ACTION == "reactivate":
    print(Account.objects.filter(name=NAME).update(is_active=True))
elif ACTION == "clear":
    # Orders are never deleted (events reference them); an empty board is
    # every waiting order cancelled.
    with transaction.atomic():
        n = Order.objects.filter(status=OrderStatus.PREPARING).update(status=OrderStatus.CANCELLED)
        revisions.mark()
    print(n)
`;
const findings = [];
const note = (label, ok, detail) => { findings.push({label, ok, detail, skipped: false}); console.log((ok ? 'PASS ' : 'FAIL ') + label + (detail ? ' -- ' + detail : '')); };
// A step that could not run is neither a pass nor a failure, and the summary
// says so separately: a run with the server command unset must not read as
// the same evidence as one that restarted the server (PR #80 review).
const skip = (label, why) => { findings.push({label, ok: true, detail: why, skipped: true}); console.log('SKIP ' + label + ' -- ' + why); };

function shell(command) {
  // Single-quoted for the outer shell so that `$BK_ACTION_CODE` is expanded
  // by bash inside double quotes and reaches Django intact, quotes and all.
  const prelude = ENV_FILE ? `source "${ENV_FILE}" && ` : '';
  return `bash -c '${prelude}${command}'`;
}

function serverAction(action) {
  const code = `ACTION=${JSON.stringify(action)}; NAME=${JSON.stringify(ACCOUNT)}\n` + ACTIONS;
  let out;
  try {
    out = execSync(shell(`${ROOT}.venv/bin/python ${ROOT}manage.py shell -c "$BK_ACTION_CODE"`),
      {cwd: ROOT, encoding: 'utf8', env: {...process.env, BK_ACTION_CODE: code}, stdio: ['ignore', 'pipe', 'pipe']});
  } catch (error) {
    throw new Error(`server action ${action} failed: ${String(error.stderr || error.message).trim().split('\n').slice(-3).join(' | ')}`);
  }
  return out.trim().split('\n').pop();
}

function stopServer() {
  // No shell: a `sh -c "pkill -f <pattern>"` would carry the pattern in its
  // own command line and pkill would take the shell down with the server.
  // SIGKILL, not SIGTERM: on SIGTERM uvicorn drains and, without
  // --timeout-graceful-shutdown (compose.prod.yaml sets it), waits on the
  // open stream forever -- the stream stays up while every new request
  // fails, which the board handles (read failed, so it polls) but which is
  // not the "cable pulled" case this step is for.
  spawnSync('pkill', ['-9', '-f', SERVER_PATTERN], {stdio: 'ignore'});
}

function restartServer() {
  execSync(shell(SERVER_COMMAND), {cwd: ROOT, stdio: 'ignore'});
}

const profile = mkdtempSync(join(tmpdir(), 'bk-chrome-'));
const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check', 'about:blank'], {stdio: 'ignore'});
const sleep = ms => new Promise(r => setTimeout(r, ms));

let version;
for (let i = 0; i < 50 && !version; i++) {
  try { version = await (await fetch(`http://127.0.0.1:${PORT}/json/version`)).json(); } catch { await sleep(200); }
}
if (!version) { chrome.kill(); throw new Error('chrome did not start'); }

const ws = new WebSocket(version.webSocketDebuggerUrl);
await new Promise(r => ws.onopen = r);
let id = 0;
const waiting = new Map();
const events = [];
ws.onmessage = ({data}) => {
  const msg = JSON.parse(data);
  if (msg.id && waiting.has(msg.id)) { waiting.get(msg.id)(msg); waiting.delete(msg.id); }
  else if (msg.method) events.push(msg);
};
function send(method, params, sessionId) {
  const msgId = ++id;
  ws.send(JSON.stringify({id: msgId, method, params: params || {}, sessionId}));
  return new Promise((resolve, reject) => waiting.set(msgId, m => m.error ? reject(new Error(method + ': ' + JSON.stringify(m.error))) : resolve(m.result)));
}
const {targetId} = await send('Target.createTarget', {url: 'about:blank'});
const {sessionId} = await send('Target.attachToTarget', {targetId, flatten: true});
const page = (method, params) => send(method, params, sessionId);
await page('Page.enable');
await page('Runtime.enable');
await page('Network.enable');
const requests = () => events.filter(e => e.method === 'Network.requestWillBeSent' && e.sessionId === sessionId).map(e => e.params.request.url);
const consoleErrors = () => events.filter(e => e.method === 'Runtime.exceptionThrown' && e.sessionId === sessionId).map(e => e.params.exceptionDetails.text + ' ' + (e.params.exceptionDetails.exception?.description || ''));

async function evaluate(expression) {
  const r = await page('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
  if (r.exceptionDetails) throw new Error('evaluate: ' + JSON.stringify(r.exceptionDetails.exception?.description || r.exceptionDetails.text));
  return r.result.value;
}
async function navigate(url) {
  events.length = 0;   // requests are counted per page load
  await page('Page.navigate', {url});
  await sleep(600);
}
async function until(expression, timeoutMs, label) {
  const started = Date.now();
  for (;;) {
    let value;
    try { value = await evaluate(expression); } catch { value = undefined; }
    if (value) return {value, ms: Date.now() - started};
    if (Date.now() - started > timeoutMs) {
      let state = '';
      try { state = await evaluate('JSON.stringify(LIVE.state())'); } catch {}
      throw new Error('timeout: ' + label + ' (last=' + JSON.stringify(value) + ', state=' + state + ')');
    }
    await sleep(150);
  }
}

try {
  serverAction('reactivate');
  serverAction('clear');

  // 1. Login as the kitchen account through the real form.
  await navigate(`${BASE}/orders/login/`);
  await evaluate(`document.querySelector('#accountName').value=${JSON.stringify(ACCOUNT)}; document.querySelector('#accountPassword').value=${JSON.stringify(PASSWORD)}; document.querySelector('form.account-panel').submit(); true`);
  await sleep(1200);
  note('login lands on a page other than login', !(await evaluate('location.pathname')).includes('/login/'), await evaluate('location.pathname'));

  // 2. The board: goes live without anyone pressing anything.
  await navigate(`${BASE}/orders/kitchen/`);
  const live = await until(`document.getElementById('status').textContent.includes('실시간 연결') ? document.getElementById('status').textContent : ''`, 8000, 'board live');
  note('board reaches 실시간 연결 by itself', true, `${live.ms}ms: "${live.value}"`);
  const state0 = await evaluate('JSON.stringify(LIVE.state())');
  note('scheduler state: stream open, hub ok, not polling', /"stream":"open"/.test(state0) && /"hubOk":true/.test(state0) && /"polling":false/.test(state0), state0);
  const streams = requests().filter(u => u.includes('/api/stream/kitchen')).length;
  const snapshots0 = requests().filter(u => u.includes('/api/snapshot/waiting')).length;
  note('exactly one stream opened', streams === 1, `streams=${streams}, snapshot reads so far=${snapshots0}`);
  note('the board reads no list or single-order endpoint', !requests().some(u => /\/api\/orders\//.test(u)), requests().filter(u => u.includes('/api/')).join(', '));

  // 3. A change committed elsewhere reaches the board without a reload.
  const t0 = Date.now();
  serverAction('order');
  const shown = await until(`document.querySelectorAll('.order-card').length === 1 ? 1 : 0`, 8000, 'order appears');
  note('an order committed on another connection appears', true, `${Date.now() - t0}ms after commit`);
  note('status still says live after the change', (await evaluate(`document.getElementById('status').textContent`)).includes('실시간 연결'), await evaluate(`document.getElementById('status').textContent`));

  // 4. A write from this board: the response is not drawn, the refetch is.
  await evaluate(`window.confirm = () => true; true`);
  await evaluate(`document.querySelector('.todo-btn:not(.minus)').click(); true`);
  const done = await until(`document.querySelector('.status-pill')?.textContent === '완료 1 / 2' ? 1 : 0`, 8000, 'progress drawn');
  note('+1 shows 완료 1 / 2 through the snapshot', true, `${done.ms}ms`);
  const patchThenSnapshot = requests().slice(-3).map(u => u.replace(BASE, ''));
  note('the write was followed by a snapshot read', patchThenSnapshot.some(u => u.includes('/api/snapshot/waiting')), patchThenSnapshot.join(' -> '));

  // 5. Hidden tab: no stream. Visible again: a fresh one and one read.
  const before = requests().filter(u => u.includes('/api/stream/kitchen')).length;
  await page('Emulation.setFocusEmulationEnabled', {enabled: false}).catch(() => {});
  await evaluate(`Object.defineProperty(document, 'hidden', {configurable: true, get: () => true}); document.dispatchEvent(new Event('visibilitychange')); true`);
  await sleep(300);
  const hidden = await evaluate('JSON.stringify(LIVE.state())');
  note('hidden tab: scheduler not running, stream closed', /"running":false/.test(hidden) && /"stream":"closed"/.test(hidden), hidden);
  await evaluate(`Object.defineProperty(document, 'hidden', {configurable: true, get: () => false}); document.dispatchEvent(new Event('visibilitychange')); true`);
  const back = await until(`LIVE.state().stream === 'open' && !LIVE.state().polling ? 1 : 0`, 8000, 'live again');
  const after = requests().filter(u => u.includes('/api/stream/kitchen')).length;
  note('visible again: a fresh stream and live again', after === before + 1, `streams ${before} -> ${after}, ${back.ms}ms`);

  // 6. Cancel: the card leaves through the snapshot.
  await evaluate(`document.querySelector('.order-cancel').click(); true`);
  await until(`document.querySelectorAll('.order-card').length === 0 ? 1 : 0`, 8000, 'card gone');
  note('cancel removes the card via the snapshot', true, await evaluate(`document.getElementById('status').textContent`));

  // 7. The server goes away and comes back: the stream closes, the board
  // says so and polls, and once the server is back it is live again without
  // a reload (BK-R020: HTTP failure, then reconnect).
  if (SERVER_COMMAND) {
    stopServer();
    const down = await until(`LIVE.state().stream !== 'open' && LIVE.state().polling ? document.getElementById('status').textContent : ''`, 40000, 'server gone noticed');
    note('server gone: stream not open, board polling and says so', /다시 읽음/.test(down.value), `${down.ms}ms: "${down.value}"`);
    const t2 = Date.now();
    restartServer();
    const up = await until(`LIVE.state().stream === 'open' && !LIVE.state().polling ? document.getElementById('status').textContent : ''`, 60000, 'live again after restart');
    note('server back: live again without a reload', /실시간 연결/.test(up.value), `${Date.now() - t2}ms after restart: "${up.value}"`);
    const t3 = Date.now();
    serverAction('order');
    await until(`document.querySelectorAll('.order-card').length === 1 ? 1 : 0`, 8000, 'order appears after restart');
    note('a change after the restart still arrives', true, `${Date.now() - t3}ms`);
    await evaluate(`document.querySelector('.order-cancel').click(); true`);
    await until(`document.querySelectorAll('.order-card').length === 0 ? 1 : 0`, 8000, 'card gone again');
  } else {
    skip('server restart step', 'BK_BROWSER_SERVER not set');
  }

  // 8. Revocation mid-stream: the account is deactivated elsewhere; the page
  // must leave for login on its own (the hub re-checks every event and at
  // its own revalidation period, 15s by default).
  serverAction('deactivate');
  const t1 = Date.now();
  serverAction('order');   // an event: the hub re-authorizes before sending it
  const gone = await until(`location.pathname.includes('/login/') ? 1 : 0`, 30000, 'sent to login');
  note('a deactivated account is sent to login by the stream', true, `${Date.now() - t1}ms after deactivation`);

  note('no uncaught page errors', consoleErrors().length === 0, consoleErrors().join(' | '));
} catch (error) {
  note('run completed', false, String(error.stack || error));
} finally {
  serverAction('reactivate');
  try { await send('Target.closeTarget', {targetId}); } catch {}
  ws.close();
  chrome.kill();
  const ran = findings.filter(f => !f.skipped);
  const skipped = findings.length - ran.length;
  console.log('\nSUMMARY ' + ran.filter(f => f.ok).length + '/' + ran.length + ' passed'
    + (skipped ? ', ' + skipped + ' skipped' : ''));
  process.exit(findings.every(f => f.ok) ? 0 : 1);
}

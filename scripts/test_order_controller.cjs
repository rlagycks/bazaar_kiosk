/* Run: node --test scripts/test_order_controller.cjs (no dependencies).
 * Exercises the real controller and state through events. This small DOM models
 * controls, radio groups, bubbling and focus; layout/native-dialog QA is separate.
 */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {createContext, runInContext} = require('node:vm');
const sources = ['order_state.js', 'order.js'].map(name => ({
  name, source: readFileSync(join(__dirname, '../orders/static/orders/ui', name), 'utf8'),
}));

const {fakeDocument} = require('./fake_document.cjs');

async function app(respond) {
  const document = fakeDocument();
  const add = (parent, tag, id, attrs = {}) => parent.append(document.create(tag, {...attrs, ...(id ? {id} : {})}));
  const page = add(document, 'main', 'order-page', {class: 'serving-page', 'data-menu-url': '/orders/menus/', 'data-order-url': '/orders/'});
  const tabs = add(page, 'nav', 'menu-tabs');
  for (const mode of ['DINE_IN', 'TAKEOUT']) add(tabs, 'button', '', {class: 'menu-tab', 'data-mode': mode});
  for (const id of ['mode-hint', 'order-notice', 'menu-grid']) add(page, 'div', id);
  add(document, 'p', 'order-summary'); add(document, 'button', 'btn-checkout');
  const checkout = add(document, 'dialog', 'checkout', {class: 'checkout'});
  for (const id of ['btn-back', 'btn-submit', 'btn-reset']) add(checkout, 'button', id);
  add(checkout, 'input', 'table-number');
  for (const id of ['cart-title', 'cart-items', 'table-help', 'total-amount', 'change-amount', 'payment-error', 'save-error']) add(checkout, 'div', id);
  for (const value of ['CASH', 'TICKET', 'CASH_TICKET']) {
    const radio = add(checkout, 'input', '', {name: 'pay', value, type: 'radio'});
    radio.value = value; radio.checked = value === 'CASH';
  }
  const single = add(checkout, 'label', 'single-amount-row');
  add(single, 'span', 'single-amount-label'); add(single, 'input', 'cash-in');
  const mixed = add(checkout, 'div', 'mixed-amount-row');
  add(mixed, 'input', 'cash-mixed'); add(mixed, 'input', 'ticket-mixed');
  const posts = [];
  let nextId = 0;
  const window = {
    addEventListener() {}, confirm: () => false,
    BazaarRequestId: {create: () => `synthetic-attempt-${++nextId}`},
    BazaarAuth: {fetch: async (url, options = {}) => {
      if (options.method !== 'POST') {
        assert.equal(url, '/orders/menus/?scope=KITCHEN');
        return new Response(JSON.stringify({items: [{id: 7, name: '떡볶이', price: 4000}]}));
      }
      assert.equal(url, '/orders/');
      posts.push({payload: JSON.parse(options.body), options});
      return respond(posts.length);
    }},
    BazaarDom: {
      el(tag, options = {}, children = []) {
        const node = document.create(tag, {class: options.class || '', ...options.attrs});
        Object.entries(options.data || {}).forEach(([key, value]) => node.setAttribute('data-' + key, value));
        if (options.text !== undefined) node.textContent = options.text;
        (Array.isArray(children) ? children : [children]).forEach(child => node.append(child));
        return node;
      },
      render(node, children) { node.replaceChildren(...(Array.isArray(children) ? children : [children])); },
      delegate(node, type, selector, handler) {
        node.addEventListener(type, event => {
          const target = event.target.closest(selector);
          if (target) return handler(event, target);
        });
      },
    },
  };
  const context = createContext({window, document, TypeError});
  for (const {name, source} of sources) runInContext(source, context, {filename: name});
  // Drain the initial async menu read without wall-clock sleeps.
  await new Promise(resolve => setImmediate(resolve));
  const get = id => document.getElementById(id);
  const click = node => {
    assert.ok(node, 'control exists'); assert.equal(node.disabled, false, 'control is enabled');
    return node.dispatch('click');
  };
  async function input(id, value) {
    const node = get(id); node.value = value; await node.dispatch('input');
  }
  async function draft() {
    await click(get('menu-grid').querySelector('[data-action="add"]'));
    await click(get('btn-checkout'));
    await input('table-number', '12'); await input('cash-in', '5000');
  }
  return {document, posts, get, click, input, draft, submit: () => click(get('btn-submit'))};
}

function assertDraft(ui) {
  assert.equal(ui.get('checkout').open, true);
  assert.equal(ui.get('table-number').value, '12');
  assert.equal(ui.get('cash-in').value, '5000');
  assert.match(ui.get('cart-items').textContent, /떡볶이/);
  assert.equal(ui.get('total-amount').textContent, '4,000원');
  assert.equal(ui.get('btn-submit').disabled, false);
}
const saved = () => new Response(JSON.stringify({id: 42}), {status: 201});

for (const [name, response, expected] of [
  ['Django text/html 400 containing plain text', () => new Response('유효한 테이블 번호가 아닙니다.', {status: 400, headers: {'Content-Type': 'text/html; charset=utf-8'}}), '유효한 테이블 번호가 아닙니다.'],
  ['JSON refusal detail', () => new Response(JSON.stringify({detail: '이미 사용 중인 포장 번호입니다.'}), {status: 409, headers: {'Content-Type': 'application/json'}}), '이미 사용 중인 포장 번호입니다.'],
]) {
  test(`${name}: displays actionable refusal and retains draft`, async () => {
    const ui = await app(response); await ui.draft(); await ui.submit();
    assert.equal(ui.get('save-error').textContent, expected);
    assert.equal(ui.document.activeElement, ui.get('save-error'));
    assertDraft(ui); assert.equal(ui.posts.length, 1);
  });
}

for (const [name, failure, error] of [
  ['network failure', () => { throw new TypeError('connection lost'); }, /연결이 끊겼습니다/],
  ['malformed 200 body', () => new Response('{truncated', {status: 200}), /저장 결과를 확인하지 못했습니다/],
  ['200 JSON without order identity', () => new Response('{}'), /저장 결과를 확인하지 못했습니다/],
]) {
  test(`${name}: retains draft and reuses identical payload/request_id on explicit retry`, async () => {
    const ui = await app(count => count === 1 ? failure() : saved());
    await ui.draft(); await ui.submit();
    assertDraft(ui); assert.match(ui.get('save-error').textContent, error);
    assert.equal(ui.posts.length, 1, 'no automatic write replay');
    await ui.submit();
    assert.equal(ui.posts.length, 2);
    assert.ok(ui.posts[0].payload.request_id);
    assert.deepEqual(ui.posts[1].payload, ui.posts[0].payload);
    assert.equal(ui.get('checkout').open, false);
  });
}

test('successful order identity clears draft and the next order receives a fresh key', async () => {
  const ui = await app(saved); await ui.draft(); await ui.submit();
  assert.deepEqual(ui.posts[0].payload, {
    floor: 'B1', order_type: 'DINE_IN', is_takeout: false, payment_method: 'CASH',
    received_amount: 5000, received_cash_amount: 5000, received_ticket_amount: 0,
    table_number: '12', note: '', items: [{menu_item_id: 7, qty: 1, mode: 'DINE_IN'}],
    request_id: 'synthetic-attempt-1',
  });
  assert.equal(ui.posts[0].options.credentials, 'same-origin');
  assert.equal(ui.posts[0].options.headers['X-CSRFToken'], 'synthetic-csrf');
  assert.equal(ui.get('checkout').open, false);
  for (const id of ['table-number', 'cash-in', 'cash-mixed', 'ticket-mixed']) assert.equal(ui.get(id).value, '');
  assert.equal(ui.get('btn-checkout').disabled, true);
  assert.equal(ui.get('total-amount').textContent, '0원');
  assert.equal(ui.get('cart-items').querySelector('button'), null);
  assert.match(ui.get('order-notice').textContent, /주문이 접수되었습니다/);
  assert.equal(ui.document.activeElement, ui.document.querySelector('.menu-tab[aria-pressed="true"]'));
  await ui.draft(); await ui.submit();
  assert.notEqual(ui.posts[0].payload.request_id, ui.posts[1].payload.request_id);
});

test('two rapid submit events send one POST while the first response is pending', async () => {
  let resolve;
  const pending = new Promise(done => { resolve = done; });
  const ui = await app(() => pending); await ui.draft();
  const first = ui.submit();
  assert.equal(ui.posts.length, 1); assert.equal(ui.get('btn-submit').disabled, true);
  // Explicit event dispatch bypasses the native disabled-button suppression and
  // proves the controller guard also protects against a second invocation.
  await ui.get('btn-submit').dispatch('click');
  assert.equal(ui.posts.length, 1);
  resolve(saved()); await first;
  assert.equal(ui.posts.length, 1); assert.equal(ui.get('checkout').open, false);
});

test('shorthand transfers focus at first ticket digit and remaining typing enters tickets', async () => {
  const ui = await app(saved); await ui.draft();
  await ui.input('cash-in', ''); ui.get('cash-in').focus();
  for (const digit of '10000+5') {
    const active = ui.document.activeElement;
    await ui.input(active.attrs.id, active.value + digit);
  }
  assert.equal(ui.document.querySelector('input[name="pay"]:checked').value, 'CASH_TICKET');
  assert.equal(ui.get('single-amount-row').hidden, true);
  assert.equal(ui.get('mixed-amount-row').hidden, false);
  assert.equal(ui.get('cash-mixed').value, '10000');
  assert.equal(ui.get('ticket-mixed').value, '5');
  assert.equal(ui.document.activeElement, ui.get('ticket-mixed'));
  assert.equal(ui.get('ticket-mixed').selectionStart, 1);
  assert.equal(ui.get('ticket-mixed').selectionEnd, 1);
  for (const digit of '000') {
    const active = ui.document.activeElement;
    await ui.input(active.attrs.id, active.value + digit);
  }
  await ui.submit();
  assert.equal(ui.posts[0].payload.received_cash_amount, 10000);
  assert.equal(ui.posts[0].payload.received_ticket_amount, 5000);
  assert.equal(ui.posts[0].payload.payment_method, 'CASH_TICKET');
});

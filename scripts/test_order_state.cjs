const {test} = require('node:test');
const assert = require('node:assert/strict');
const {createOrder, payment, amount} = require('../orders/static/orders/ui/order_state.js');

test('selecting a quantity does not add it; hall and takeout remain separate', () => {
  const order = createOrder();
  const menu = {id: 1, name: '떡볶이', price: 4000};
  order.select('DINE_IN', 1, 2);
  assert.equal(order.total(), 0);
  order.add('DINE_IN', menu);
  order.add('TAKEOUT', menu);
  assert.deepEqual(order.counts(), {DINE_IN: 2, TAKEOUT: 1});
  assert.equal(order.total(), 12000);
  assert.equal(order.selection('DINE_IN', 1), 1);
  order.change('TAKEOUT', 1, -1);
  assert.equal(order.total(), 8000);
  assert.equal(order.items().length, 1);
});

test('quantity limits reject overflow without changing the basket', () => {
  const order = createOrder();
  const menu = {id: 1, name: 'A&W <cola>', price: 2000};
  order.select('DINE_IN', 1, 99);
  order.add('DINE_IN', menu);
  assert.throws(() => order.add('DINE_IN', menu), /99/);
  assert.equal(order.items()[0].qty, 99);
  assert.equal(order.items()[0].name, menu.name);
});

test('a failed save retry keeps its key despite quantity selection; payload edits replace it', () => {
  let n = 0;
  const order = createOrder(() => `request-${++n}`);
  const original = {items: [{menu_item_id: 1, qty: 2}], table_number: '12'};
  assert.equal(order.attempt(original), 'request-1');
  order.select('TAKEOUT', 2, 3);
  assert.equal(order.attempt(original), 'request-1');
  assert.equal(order.attempt({...original, table_number: '13'}), 'request-2');
  order.reset();
  assert.equal(order.attempt(original), 'request-3');
});

test('cash, ticket surplus, mixed payment, shortage and invalid input follow settlement rules', () => {
  assert.equal(payment('CASH', '15,000', '', '', 11000).change, 4000);
  assert.equal(payment('TICKET', '15000', '', '', 11000).change, 0);
  assert.equal(payment('CASH_TICKET', '', '10000', '5000', 11000).change, 4000);
  assert.match(payment('CASH', '10000', '', '', 11000).error, /1,000/);
  assert.match(payment('CASH_TICKET', '', '15000', '', 11000).error, /모두/);
  for (const value of ['-1', '1.5', '1e3', '10000001', 'NaN']) {
    assert.ok(Number.isNaN(amount(value)), value);
  }
});

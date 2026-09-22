const {test} = require('node:test');
const assert = require('node:assert/strict');
const state = require('../orders/static/orders/ui/monitor_state.js');
const order = () => ({id: 1, status: 'PREPARING', monitor_version: 'v1', departed_at: null,
  items: [{id: 7, qty: 3, prepared_qty: 1, service_mode: 'TAKEOUT'}, {id: 8, qty: 2, prepared_qty: 2, service_mode: 'DINE_IN'}]});
test('prepared is distinct from departure and unknown historical completion', () => {
  const row = order(); assert.equal(state.label(row), '준비 중'); row.items[0].prepared_qty = 3;
  assert.equal(state.label(row), '준비 완료 · 출발 대기'); row.status = 'READY';
  assert.equal(state.label(row), '기존 완료 · 출발 미확인'); row.departed_at = '2026-09-22T12:00:00+09:00';
  assert.equal(state.label(row), '서빙 출발'); row.status = 'CANCELLED'; assert.equal(state.label(row), '취소');
});
test('mixed orders are hall, all-takeout orders are takeout', () => {
  const row = order(); assert.equal(state.kind(row), '식당'); row.items.pop(); assert.equal(state.kind(row), '포장');
});
test('draft preserves original version and every line without mutating server snapshot', () => {
  const row = order(), draft = state.editor(row); draft.set(7, '3');
  assert.equal(row.items[0].prepared_qty, 1); assert.equal(draft.dirty(), true);
  assert.deepEqual(draft.payload('progress'), {action: 'progress', expected_version: 'v1', items: [{id:7, prepared_qty:3}, {id:8, prepared_qty:2}]});
  assert.deepEqual(draft.payload('depart'), {action:'depart', expected_version:'v1'});
  assert.equal(draft.conflicts({...row, monitor_version:'v2'}), true);
  assert.equal(draft.conflicts(undefined), true); assert.equal(draft.conflicts(row), false);
});
test('invalid quantities, unknown lines and cancelled drafts are rejected', () => {
  const draft = state.editor(order());
  for (const raw of ['', ' ', '-1', '1.5', '1e1', '４', 4, true, null]) assert.throws(() => draft.set(7, raw));
  assert.throws(() => draft.set(999, 0));
  assert.throws(() => state.editor({...order(), status:'CANCELLED'}).set(7, 0));
  draft.set(7, '0'); assert.equal(draft.items()[0].prepared_qty, 0);
});

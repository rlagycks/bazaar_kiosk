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
  const row = order(); row.items[0].service_mode = 'DINE_IN';
  const draft = state.editor(row); draft.set(7, '3');
  assert.equal(row.items[0].prepared_qty, 1); assert.equal(draft.dirty(), true);
  assert.deepEqual(draft.payload('progress'), {action: 'progress', expected_version: 'v1', items: [{id:7, prepared_qty:3}, {id:8, prepared_qty:2}]});
  assert.deepEqual(draft.payload('depart'), {action:'depart', expected_version:'v1'});
  assert.equal(draft.conflicts({...row, monitor_version:'v2'}), true);
  assert.equal(draft.conflicts(undefined), true); assert.equal(draft.conflicts(row), false);
});
test('invalid quantities, unknown lines and cancelled drafts are rejected', () => {
  const row = order(); row.items[0].service_mode = 'DINE_IN';
  const draft = state.editor(row);
  for (const raw of ['', ' ', '-1', '1.5', '1e1', '４', 4, true, null]) assert.throws(() => draft.set(7, raw));
  assert.throws(() => draft.set(999, 0));
  assert.throws(() => state.editor({...order(), status:'CANCELLED'}).set(7, 0));
  draft.set(7, '0'); assert.equal(draft.items()[0].prepared_qty, 0);
});
test('mixed ALL progress includes only hall IDs and takeout quantities cannot be edited', () => {
  const draft = state.editor(order());
  assert.throws(() => draft.set(7, 0)); draft.set(8, 1);
  assert.deepEqual(draft.payload('progress'), {action:'progress',expected_version:'v1',items:[{id:8,prepared_qty:1}]});
  assert.equal(draft.items()[0].prepared_qty,1);assert.equal(draft.editable(7),false);assert.equal(draft.editable(8),true);
});
test('HALL filtered snapshot retains full source token and its hall completion is independent of global status', () => {
  const row = {...order(), items:[order().items[1]], departed_at:'2026-10-03T01:00:00Z', hall_completed:true, takeout_pending_qty:2};
  assert.equal(state.label(row),'식당 서빙 출발 · 포장 대기');
  assert.equal(state.hallCompleted(row),true);
  assert.deepEqual(state.editor(row).payload('progress'), {action:'progress',expected_version:'v1',items:[{id:8,prepared_qty:2}]});
  assert.equal(state.label({...row,takeout_pending_qty:0,status:'READY'}),'서빙 출발');
});
test('pure takeout completion is not labelled as serving departure; mixed PREPARING departure remains visible', () => {
  assert.equal(state.label({...order(),status:'READY',items:[order().items[0]]}),'포장 완료');
  assert.equal(state.label({...order(),departed_at:'2026-10-03T01:00:00Z'}),'식당 서빙 출발 · 포장 대기');
  assert.equal(state.label({...order(),status:'CANCELLED',departed_at:'2026-10-03T01:00:00Z'}),'취소');
});

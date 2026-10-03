const {test} = require('node:test');
const assert = require('node:assert/strict');
const {create} = require('../orders/static/orders/ui/takeout_state.js');
const snapshot = (extra = {}) => ({version:'read-1', complete:true, completion_version:'completion-1',
  menus:[{key:'menu:7',name:'국수',remaining_qty:4,is_custom:false},
    {key:'custom:'+'a'.repeat(64),name:'특별 메뉴',remaining_qty:2,is_custom:true}],
  remaining_total:6, history:{orders:[],total:0,page:1,pages:1}, ...extra});

test('catalog keys, quantities and equality token produce only the exact completion fields', () => {
  const model=create(), data=snapshot();model.apply(data);model.set('menu:7',2);
  model.set(data.menus[1].key,1);
  assert.deepEqual(model.payload(),{expected_version:'completion-1',items:[{key:'menu:7',quantity:2},{key:data.menus[1].key,quantity:1}]});
  assert.equal(data.menus[0].remaining_qty,4);assert.equal(model.total(),3);
});
test('unchanged response retains catalog, history, token and selected quantities', () => {
  const model=create();model.apply(snapshot());model.set('menu:7',2);
  model.apply({unchanged:true,menus:[],history:{orders:[]}});
  assert.equal(model.rows().length,2);assert.equal(model.total(),2);assert.equal(model.stale(),false);
  assert.equal(model.payload().expected_version,'completion-1');
});
test('SSE change retains excessive quantities and requires acknowledgement before any edit or write', () => {
  const model=create();model.apply(snapshot());model.set('menu:7',4);
  model.apply(snapshot({completion_version:'completion-2',menus:[{key:'menu:7',name:'국수',remaining_qty:1}]}));
  assert.equal(model.total(),4);assert.equal(model.stale(),true);assert.throws(()=>model.payload());
  assert.throws(()=>model.set('menu:7',3));model.review();
  assert.throws(()=>model.payload());model.set('menu:7',3);model.set('menu:7',1);
  assert.deepEqual(model.payload(),{expected_version:'completion-2',items:[{key:'menu:7',quantity:1}]});
});
test('a disappeared selected menu remains visible and can only be reduced after review', () => {
  const model=create();model.apply(snapshot());model.set('menu:7',2);
  model.apply(snapshot({completion_version:'completion-2',menus:[],remaining_total:0}));
  assert.deepEqual(model.rows().map(row=>[row.key,row.quantity,row.missing]),[['menu:7',2,true]]);
  model.review();assert.throws(()=>model.payload());assert.throws(()=>model.set('menu:7',3));
  model.set('menu:7',1);model.set('menu:7',0);assert.equal(model.rows().length,0);
});
test('history-only update preserves selection without a false completion conflict; tokens are never ordered', () => {
  const model=create();model.apply(snapshot());model.set('menu:7',1);
  model.apply(snapshot({version:'read-2'}));assert.equal(model.stale(),false);
  model.apply(snapshot({completion_version:'aaa'}));assert.equal(model.stale(),true);
  model.review();assert.equal(model.payload().expected_version,'aaa');
});
test('failed writes retain selections until review; only confirmed success clears them', () => {
  const model=create();model.apply(snapshot());model.set('menu:7',2);model.invalidate();
  model.apply(snapshot());assert.equal(model.stale(),true);assert.equal(model.total(),2);
  model.review();assert.equal(model.total(),2);model.succeeded();assert.equal(model.total(),0);
});
test('invalid quantities, unknown menus, empty selections and incomplete snapshots fail closed', () => {
  const model=create();assert.throws(()=>model.payload());model.apply(snapshot());
  for(const quantity of [-1,1.5,NaN,Infinity,'1',true,null,5]) assert.throws(()=>model.set('menu:7',quantity));
  assert.throws(()=>model.set('menu:999',1));assert.throws(()=>model.payload());
  model.set('menu:7',1);
  assert.throws(()=>model.apply(snapshot({complete:false})));
  assert.throws(()=>model.apply(snapshot({completion_version:''})));
  assert.throws(()=>model.apply(snapshot({menus:[{key:'menu:7',remaining_qty:-1}]})));
});

/* Real monitor controller + state, event-driven DOM; scheduler has its own suite.
 * The shared fake normalizes HTML attribute case, preventing camelCase data-key regressions.
 */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {createContext, runInContext} = require('node:vm');
const {fakeDocument} = require('./fake_document.cjs');
const flush = () => new Promise(resolve => setImmediate(resolve));
const baseOrder = () => ({id:1, order_no:1, created_at:'2026-09-22T01:00:00Z', status:'PREPARING', monitor_version:'v1', table:{number:12},
  items:[{id:7,menu_item_name:'<img src=x onerror=alert(1)>',qty:3,prepared_qty:0,service_mode:'DINE_IN'}]});
function app(respond = async () => new Response(JSON.stringify({id:1}))) {
  const document = fakeDocument();
  const add = (parent, tag, id, attrs={}) => parent.append(document.create(tag, {id,...attrs}));
  const page = add(document, 'main', 'monitor-page', {'data-action-url':'/orders/api/orders/0/monitoring','data-login-url':'/orders/login/'});
  for (const id of ['waiting-orders','waiting-title','queue-warning','history-title','history-pagination','live-status','monitor-notice']) add(page,'div',id);
  add(page,'tbody','history-orders'); add(page,'button','reload-orders');
  const detail = add(document,'dialog','order-detail'), confirm = add(document,'dialog','confirm-action');
  for (const id of ['detail-title','detail-meta','detail-status','detail-note','detail-items','detail-error','detail-conflict']) add(detail,'div',id);
  for (const id of ['detail-close','save-progress','cancel-order','depart-order','reopen-order','detail-reload']) add(detail,'button',id);
  for (const id of ['confirm-title','confirm-description','confirm-error']) add(confirm,'div',id);
  for (const id of ['confirm-back','confirm-submit']) add(confirm,'button',id);
  const posts=[],refetches=[]; let callbacks;
  const window = {addEventListener(){}, confirm:()=>false,
    BazaarAuth:{fetch:async (url, options)=>{posts.push({url,...options,body:JSON.parse(options.body)});return respond();}},
    BazaarLive:{create:opts=>{callbacks=opts;return {start(){},refetch:reason=>refetches.push(reason)};}},
    BazaarDom:{
      el(tag, opts={}, children=[]) {
        const node=document.create(tag,{class:opts.class||'',...opts.attrs});
        Object.entries(opts.data||{}).forEach(([key,value])=>node.setAttribute('data-'+key,value));
        if(opts.text!==undefined) node.textContent=opts.text;
        (Array.isArray(children)?children:[children]).forEach(child=>node.append(child));return node;
      },
      render(node,children){node.replaceChildren(...(Array.isArray(children)?children:[children]));},
      delegate(node,type,selector,handler){node.addEventListener(type,event=>{const target=event.target.closest(selector);if(target)return handler(event,target);});}
    }};
  const context=createContext({window,document,TypeError});
  for (const name of ['monitor_state.js','monitor.js']) runInContext(readFileSync(join(__dirname,'../orders/static/orders/ui',name),'utf8'),context,{filename:name});
  const get=id=>document.getElementById(id);
  const click=async node=>{assert.ok(node); assert.equal(node.disabled,false,'button enabled');await node.dispatch('click');await flush();};
  const input=async value=>{get('prepared-7').value=value;await get('prepared-7').dispatch('input');};
  function snapshot(row=baseOrder(), extra={}) {
    callbacks.onApply({orders:row.status==='PREPARING'?[row]:[],total:row.status==='PREPARING'?1:0,count:1,has_more:false,
      history:{orders:[row],total:1,page:1,pages:1,has_previous:false,has_next:false,...extra}});
  }
  const open=()=>click(get('waiting-orders').querySelector('[data-action="detail"]') || get('history-orders').querySelector('[data-action="detail"]'));
  return {get,click,input,snapshot,open,posts,refetches,callbacks,document};
}
test('real data keys open details; inputs and +/- controls submit atomic versioned progress',async()=>{
  const ui=app();ui.snapshot();await ui.open();assert.equal(ui.get('order-detail').open,true);
  assert.match(ui.get('detail-items').textContent,/<img src=x/);
  await ui.input('1');await ui.click(ui.get('detail-items').querySelector('[data-step="1"]'));
  assert.equal(ui.get('prepared-7').value,'2');await ui.click(ui.get('save-progress'));
  assert.equal(ui.posts.length,1);assert.equal(ui.posts[0].url,'/orders/api/orders/1/monitoring');
  assert.equal(ui.posts[0].headers['X-CSRFToken'],'synthetic-csrf');
  assert.deepEqual(JSON.parse(JSON.stringify(ui.posts[0].body)),{action:'progress',expected_version:'v1',items:[{id:7,prepared_qty:2}]});
  assert.equal(ui.get('order-detail').open,false);assert.deepEqual(ui.refetches,['write']);
  assert.match(ui.get('waiting-orders').textContent,/준비 0 \/ 3/,'write response is not rendered');
});
test('invalid blank draft survives incoming snapshot and blocks stale save',async()=>{
  const ui=app();ui.snapshot();await ui.open();await ui.input('');
  ui.snapshot({...baseOrder(),monitor_version:'v2'});
  assert.equal(ui.get('prepared-7').value,'');assert.equal(ui.get('save-progress').disabled,true);
  assert.equal(ui.get('detail-reload').hidden,false);assert.equal(ui.posts.length,0);
});
test('departure needs confirmation and changing order invalidates open confirmation',async()=>{
  const ui=app();ui.snapshot();await ui.click(ui.get('waiting-orders').querySelector('[data-action="depart"]'));
  assert.equal(ui.get('confirm-action').open,true);assert.equal(ui.posts.length,0);
  assert.match(ui.get('confirm-description').textContent,/모든 품목/);
  ui.snapshot({...baseOrder(),monitor_version:'v2'});assert.equal(ui.get('confirm-submit').disabled,true);
  await ui.click(ui.get('confirm-back'));assert.equal(ui.posts.length,0);
});
test('confirmed departure submits once while response is pending',async()=>{
  let resolve;const ui=app(()=>new Promise(r=>{resolve=r;}));ui.snapshot();
  await ui.click(ui.get('waiting-orders').querySelector('[data-action="depart"]'));
  await ui.click(ui.get('confirm-submit'));assert.equal(ui.get('confirm-submit').disabled,true);
  await ui.get('confirm-submit').dispatch('click');assert.equal(ui.posts.length,1);
  resolve(new Response(JSON.stringify({id:1})));await flush();
  assert.equal(ui.posts[0].body.action,'depart');assert.equal(ui.get('confirm-action').open,false);
});
for (const [name,response] of [
  ['JSON conflict',()=>new Response(JSON.stringify({detail:'다른 직원이 수정했습니다'}),{status:409})],
  ['plain validation',()=>new Response('준비 수량 범위를 확인하세요',{status:400})],
  ['network failure',()=>Promise.reject(new TypeError('offline'))],
  ['uncertain success',()=>new Response('{}')],
]) test(name+' retains draft and requires latest snapshot, without automatic retry',async()=>{
  const ui=app(response);ui.snapshot();await ui.open();await ui.input('2');await ui.click(ui.get('save-progress'));
  assert.equal(ui.get('order-detail').open,true);assert.equal(ui.get('prepared-7').value,'2');
  assert.ok(ui.get('detail-error').textContent);assert.equal(ui.get('save-progress').disabled,true);
  assert.equal(ui.posts.length,1);assert.deepEqual(ui.refetches,['write']);
});
test('cancelled history is read-only, legacy READY has no claimed departure',async()=>{
  const ui=app();ui.snapshot({...baseOrder(),status:'CANCELLED'});await ui.open();
  assert.equal(ui.get('save-progress').hidden,true);assert.equal(ui.get('prepared-7').disabled,true);
  await ui.click(ui.get('detail-close'));ui.snapshot({...baseOrder(),status:'READY'});await ui.open();
  assert.match(ui.get('detail-status').textContent,/출발 미확인/);assert.equal(ui.get('reopen-order').hidden,false);
});
test('failed read disables mutation and out-of-range page can return directly',()=>{
  const ui=app();ui.snapshot(baseOrder(),{page:1000,pages:2,has_previous:true});
  assert.equal(ui.get('history-pagination').querySelector('a').attrs.href,'?page=2#history');
  ui.callbacks.onStatus({lastError:'offline',running:true,applied:{at:Date.now()}});
  assert.equal(ui.get('waiting-orders').querySelector('[data-action="depart"]').disabled,true);
});
test('status reports preserve card nodes, draft focus and last applied time',async()=>{
  const ui=app();ui.snapshot();await ui.open();await ui.input('1');ui.get('prepared-7').focus();
  const card=ui.get('waiting-orders').children[0], field=ui.get('prepared-7');
  const status={running:true,applied:{at:Date.parse('2026-09-22T01:02:00Z')},inFlight:true,polling:false,stream:'open',hubOk:true};
  ui.callbacks.onStatus(status);
  assert.equal(ui.get('waiting-orders').children[0],card);assert.equal(ui.document.activeElement,field);
  assert.equal(field.value,'1');assert.equal(ui.get('reload-orders').disabled,true);
  assert.match(ui.get('live-status').textContent,/실시간 연결/);assert.match(ui.get('live-status').textContent,/10:02/);
  ui.callbacks.onStatus({...status,lastError:'offline',inFlight:false,polling:true});
  assert.equal(ui.get('waiting-orders').children[0],card);assert.equal(field.value,'1');
  assert.match(ui.get('live-status').textContent,/읽기 실패/);assert.equal(ui.get('save-progress').disabled,true);
});
test('resuming must confirm a fresh read, not merely reuse the pre-hide timestamp',()=>{
  const ui=app();ui.snapshot();const at=new Date('2026-09-22T01:00:00Z');
  const state={running:true,applied:{at},inFlight:false,polling:false,stream:'open',hubOk:true};
  ui.callbacks.onStatus(state);ui.callbacks.onStatus({...state,running:false});
  ui.callbacks.onStatus({...state,inFlight:true});
  assert.equal(ui.get('waiting-orders').querySelector('[data-action="depart"]').disabled,true);
  // An unchanged response confirms freshness too; no onApply callback required.
  ui.callbacks.onStatus({...state,applied:{at:new Date('2026-09-22T01:01:00Z')}});
  assert.equal(ui.get('waiting-orders').querySelector('[data-action="depart"]').disabled,false);
});
test('reopening cannot silently discard an edited preparation quantity',async()=>{
  const ui=app();ui.snapshot({...baseOrder(),status:'READY'});await ui.open();await ui.input('1');
  await ui.click(ui.get('reopen-order'));assert.equal(ui.get('confirm-action').open,false);
  assert.match(ui.get('detail-error').textContent,/먼저 저장/);assert.equal(ui.get('prepared-7').value,'1');assert.equal(ui.posts.length,0);
});
test('missing latest order still requires dirty-input discard confirmation',async()=>{
  const ui=app();ui.snapshot();await ui.open();await ui.input('1');
  ui.callbacks.onApply({orders:[],total:0,history:{orders:[],total:0,page:1,pages:0}});
  await ui.click(ui.get('detail-reload'));
  assert.equal(ui.get('order-detail').open,true);assert.equal(ui.get('prepared-7').value,'1');assert.equal(ui.posts.length,0);
});

test('mixed detail names prepared quantity buttons by service mode', async () => {
  const ui = app();
  const row = baseOrder();
  row.items[0].menu_item_name = '김밥';
  row.items.push({...row.items[0], id:8, service_mode:'TAKEOUT'});
  ui.snapshot(row); await ui.open();
  for (const mode of ['홀', '포장']) {
    for (const suffix of ['준비 수량 줄이기', '준비 수량 늘리기']) {
      assert.equal(ui.get('detail-items').querySelectorAll('button').filter(node => node.attrs['aria-label'] === `${mode} 김밥 ${suffix}`).length,1);
    }
  }
  await ui.click(ui.get('detail-items').querySelectorAll('button').find(node => node.attrs['aria-label'] === '포장 김밥 준비 수량 늘리기'));
  assert.equal(ui.get('prepared-7').value,'0');
  assert.equal(ui.get('prepared-8').value,'1');
});

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
  const posts=[],refetches=[],timers=new Map(),windowListeners=new Map(); let callbacks, timerId=0, now=0;
  const setTimeout=(callback,delay)=>{const id=++timerId;timers.set(id,{callback,at:now+delay});return id;};
  const clearTimeout=id=>timers.delete(id);
  const advance=async ms=>{now+=ms;for(const [id,timer] of [...timers])if(timer.at<=now){timers.delete(id);timer.callback();}await flush();};
  const fire=async (target,type,fields={})=>{assert.ok(target,'event target exists');const event={type,target,button:0,isPrimary:true,pointerId:1,clientX:0,clientY:0,preventDefault(){},...fields};for(let node=target;node;node=node.parent)for(const handler of node.listeners.get(type)||[])await handler(event);await flush();};
  const windowEvent=async type=>{for(const handler of windowListeners.get(type)||[])handler({});await flush();};
  const window = {addEventListener(type,fn){if(!windowListeners.has(type))windowListeners.set(type,[]);windowListeners.get(type).push(fn);}, setTimeout, clearTimeout, confirm:()=>false,
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
  function snapshot(row=baseOrder(), extra={}, settled=true) {
    callbacks.onApply({orders:row.status==='PREPARING'?[row]:[],total:row.status==='PREPARING'?1:0,count:1,has_more:false,
      history:{orders:[row],total:1,page:1,pages:1,has_previous:false,has_next:false,...extra}});
    if(settled)callbacks.onStatus({running:true,applied:{at:new Date()},inFlight:false,polling:false,stream:'open',hubOk:true});
  }
  const open=()=>click(get('waiting-orders').querySelector('[data-action="detail"]') || get('history-orders').querySelector('[data-action="detail"]'));
  return {get,click,input,snapshot,open,posts,refetches,callbacks,document,fire,advance,windowEvent};
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
const mixedOrder = () => ({...baseOrder(),items:[...baseOrder().items,
  {id:8,menu_item_name:'포장 메뉴',qty:2,prepared_qty:1,service_mode:'TAKEOUT'}]});
test('ALL mixed detail shows takeout read-only and submits only hall quantities',async()=>{
  const ui=app();ui.snapshot(mixedOrder());await ui.open();
  assert.equal(ui.get('prepared-8'),null);assert.match(ui.get('detail-items').textContent,/포장 수량은 포장 모니터링에서 처리합니다/);
  await ui.input('2');await ui.click(ui.get('save-progress'));
  assert.deepEqual(JSON.parse(JSON.stringify(ui.posts[0].body.items)),[{id:7,prepared_qty:2}]);
});
test('hall-departed mixed order pending takeout has no second departure action and permits hall reopen',async()=>{
  const ui=app();ui.snapshot({...mixedOrder(),departed_at:'2026-10-03T01:00:00Z',hall_completed:true,takeout_pending_qty:1});
  assert.equal(ui.get('waiting-orders').querySelector('[data-action="depart"]'),null);
  assert.match(ui.get('waiting-orders').textContent,/식당 서빙 출발 · 포장 대기/);
  await ui.open();assert.equal(ui.get('depart-order').hidden,true);assert.equal(ui.get('reopen-order').hidden,false);
});
test('mixed departure confirmation explicitly completes hall quantities only',async()=>{
  const ui=app();ui.snapshot(mixedOrder());await ui.click(ui.get('waiting-orders').querySelector('[data-action="depart"]'));
  assert.match(ui.get('confirm-description').textContent,/식당 품목/);
  assert.match(ui.get('confirm-description').textContent,/포장 수량은 포장 모니터링에서 처리합니다/);
});

const prepare = ui => ui.get('waiting-orders').querySelector('[data-action="prepare"]');
test('hall rows expose every menu with custom and service labels; takeout retains its card',()=>{
  const ui=app();const order=baseOrder();order.items=Array.from({length:7},(_,i)=>({...order.items[0],id:i+1,menu_item_name:'메뉴'+i,is_custom:i===6,service_mode:i===6?'TAKEOUT':'DINE_IN'}));ui.snapshot(order);
  // D-075: the mixed order's takeout line is shown but held only by the takeout monitor.
  assert.equal(ui.get('waiting-orders').querySelectorAll('[data-action="prepare"]').length,6);
  assert.equal(ui.get('waiting-orders').querySelectorAll('.is-takeout').length,1);
  assert.match(ui.get('waiting-orders').textContent,/기타 · 메뉴6/);assert.match(ui.get('waiting-orders').textContent,/포장/);
  assert.equal(ui.get('waiting-orders').querySelectorAll('img').length,0);
  order.items.forEach(item=>item.service_mode='TAKEOUT');ui.snapshot(order);assert.equal(prepare(ui),null);
});
test('short tap does not mutate; one full second increments one line with full versioned payload',async()=>{
  const ui=app();const order=baseOrder();order.items.push({...order.items[0],id:8,prepared_qty:1});ui.snapshot(order);
  await ui.fire(prepare(ui),'pointerdown');await ui.advance(999);assert.equal(ui.posts.length,0);
  await ui.fire(prepare(ui),'pointerup');await ui.click(prepare(ui));await ui.advance(1);assert.equal(ui.posts.length,0);
  await ui.fire(prepare(ui),'pointerdown');await ui.advance(1000);assert.equal(ui.posts.length,1);
  assert.deepEqual(ui.posts[0].body,{action:'progress',expected_version:'v1',items:[{id:7,prepared_qty:1},{id:8,prepared_qty:1}]});
  await ui.advance(3000);assert.equal(ui.posts.length,1);assert.equal(prepare(ui).disabled,true);
  await ui.fire(prepare(ui),'pointerdown');await ui.advance(1000);assert.equal(ui.posts.length,1);
  ui.snapshot({...order,monitor_version:'v2',items:order.items.map(item=>({...item,prepared_qty:1}))});assert.equal(prepare(ui).disabled,false);
});
for(const cancel of ['pointercancel','pointerleave','lostpointercapture','movement','scroll','blur','hidden','snapshot','secondary','read failure','detail opened'])test('hold cancelled on '+cancel,async()=>{
  const ui=app();ui.snapshot();await ui.fire(prepare(ui),'pointerdown');await ui.advance(600);
  if(cancel==='movement')await ui.fire(prepare(ui),'pointermove',{clientX:20});
  else if(cancel==='blur')await ui.windowEvent('blur');
  else if(cancel==='hidden'){ui.document.hidden=true;await ui.fire(ui.document,'visibilitychange');}
  else if(cancel==='snapshot')ui.snapshot({...baseOrder(),monitor_version:'v2'});
  else if(cancel==='secondary')await ui.fire(prepare(ui),'pointerdown',{pointerId:2,isPrimary:false});
  else if(cancel==='detail opened')await ui.open();
  else if(cancel==='read failure')ui.callbacks.onStatus({lastError:'offline',running:true,applied:{at:1}});
  else await ui.fire(prepare(ui),cancel);
  await ui.advance(1000);assert.equal(ui.posts.length,0);
  assert.notEqual(prepare(ui).attrs['data-holding'],'true');
});
test('completed rows cannot overcount and keyboard routes to unchanged details',async()=>{
  const ui=app();ui.snapshot({...baseOrder(),items:[{...baseOrder().items[0],prepared_qty:3}]});assert.equal(prepare(ui).disabled,true);
  await ui.fire(prepare(ui),'pointerdown');await ui.advance(1000);assert.equal(ui.posts.length,0);
  ui.snapshot();await ui.fire(prepare(ui),'keydown',{key:'Enter'});assert.equal(ui.get('order-detail').open,true);assert.equal(ui.posts.length,0);
});
test('inline write failure is visible outside details, waits for snapshot, and never retries',async()=>{
  const ui=app(()=>new Response(JSON.stringify({detail:'다른 직원이 수정했습니다'}),{status:409}));ui.snapshot();
  await ui.fire(prepare(ui),'pointerdown');await ui.advance(1000);
  assert.match(ui.get('monitor-notice').textContent,/다른 직원/);assert.equal(ui.get('order-detail').open,false);assert.equal(prepare(ui).disabled,true);
  await ui.advance(5000);assert.equal(ui.posts.length,1);ui.snapshot({...baseOrder(),monitor_version:'v2'});assert.equal(prepare(ui).disabled,false);
});

test('secondary buttons never start progress, context menu does not interrupt touch hold',async()=>{
  const ui=app();ui.snapshot();await ui.fire(prepare(ui),'pointerdown',{button:2});await ui.advance(1000);assert.equal(ui.posts.length,0);
  await ui.fire(prepare(ui),'pointerdown');await ui.advance(500);await ui.fire(prepare(ui),'contextmenu');await ui.advance(500);assert.equal(ui.posts.length,1);
});
test('pending write remains single and heartbeat cannot unlock the old snapshot after success',async()=>{
  let resolve;const ui=app(()=>new Promise(r=>{resolve=r;}));ui.snapshot();
  const state={running:true,applied:{at:new Date()},inFlight:false,polling:false,stream:'open',hubOk:true};ui.callbacks.onStatus(state);
  await ui.fire(prepare(ui),'pointerdown');await ui.advance(1000);assert.equal(ui.posts.length,1);
  await ui.fire(prepare(ui),'pointerdown');await ui.advance(1000);assert.equal(ui.posts.length,1);
  resolve(new Response(JSON.stringify({id:1})));await flush();ui.callbacks.onStatus(state);assert.equal(prepare(ui).disabled,true);
  ui.callbacks.onStatus({...state,applied:{at:new Date()}});assert.equal(prepare(ui).disabled,false);
});
test('a snapshot during pending write cannot let another increment through',async()=>{
  let resolve;const ui=app(()=>new Promise(r=>{resolve=r;}));ui.snapshot();
  await ui.fire(prepare(ui),'pointerdown');await ui.advance(1000);
  ui.snapshot({...baseOrder(),monitor_version:'v2',items:[{...baseOrder().items[0],prepared_qty:1}]});assert.equal(prepare(ui).disabled,true);
  resolve(new Response(JSON.stringify({id:1})));await flush();assert.equal(prepare(ui).disabled,true);
  ui.snapshot({...baseOrder(),monitor_version:'v2',items:[{...baseOrder().items[0],prepared_qty:1}]});assert.equal(prepare(ui).disabled,false);
});

for(const unchanged of [false,true])test('pre-write read '+(unchanged?'unchanged':'snapshot')+' cannot unlock while post-write read is queued',async()=>{
  const ui=app();ui.snapshot();
  const initial={running:true,applied:{at:new Date()},inFlight:true,polling:false,stream:'open',hubOk:true};ui.callbacks.onStatus(initial);
  await ui.fire(prepare(ui),'pointerdown');await ui.advance(1000);assert.equal(ui.posts.length,1);assert.equal(prepare(ui).disabled,true);
  // Scheduler draws a pre-write response, then immediately starts the queued
  // post-write read. There is no idle status between these two reads.
  if(!unchanged)ui.snapshot(baseOrder(),{},false);
  assert.equal(prepare(ui).disabled,true,'drawing the old response must retain the write barrier');
  ui.callbacks.onStatus({...initial,applied:{at:new Date()}});
  assert.equal(prepare(ui).disabled,true,'queued read status must retain the write barrier');
  await ui.fire(prepare(ui),'pointerdown');await ui.advance(1000);assert.equal(ui.posts.length,1);
  ui.snapshot({...baseOrder(),monitor_version:'v2',items:[{...baseOrder().items[0],prepared_qty:1}]},{},false);
  assert.equal(prepare(ui).disabled,true,'only the scheduler idle status releases the barrier');
  ui.callbacks.onStatus({...initial,inFlight:false,applied:{at:new Date()}});assert.equal(prepare(ui).disabled,false);
  await ui.fire(prepare(ui),'pointerdown');await ui.advance(1000);assert.equal(ui.posts.length,2);assert.equal(ui.posts[1].body.expected_version,'v2');assert.equal(ui.posts[1].body.items[0].prepared_qty,2);
});
test('failed queued post-write read stays locked until a later successful unchanged read',async()=>{
  const ui=app();ui.snapshot();const oldTime=new Date();
  const state={running:true,applied:{at:oldTime},inFlight:true,polling:false,stream:'open',hubOk:true};ui.callbacks.onStatus(state);
  await ui.fire(prepare(ui),'pointerdown');await ui.advance(1000);
  const preWriteTime=new Date();ui.callbacks.onStatus({...state,applied:{at:preWriteTime}});
  ui.callbacks.onStatus({...state,applied:{at:preWriteTime},inFlight:false,lastError:'offline'});assert.equal(prepare(ui).disabled,true);
  ui.callbacks.onStatus({...state,applied:{at:preWriteTime},lastError:'offline'});assert.equal(prepare(ui).disabled,true);
  // An unchanged success has no drawSnapshot callback; only its new read time.
  ui.callbacks.onStatus({...state,inFlight:false,applied:{at:new Date()}});assert.equal(prepare(ui).disabled,false);
  assert.equal(ui.posts.length,1);
});

test('a successful hold returns focus to its row once the next read unlocks it, not to reload',async()=>{
  const ui=app();ui.snapshot();
  const state={running:true,applied:{at:new Date()},inFlight:false,polling:false,stream:'open',hubOk:true};ui.callbacks.onStatus(state);
  prepare(ui).focus();await ui.fire(prepare(ui),'pointerdown');await ui.advance(1000);assert.equal(ui.posts.length,1);
  assert.notEqual(ui.document.activeElement,ui.get('reload-orders'));
  ui.snapshot({...baseOrder(),monitor_version:'v2',items:[{...baseOrder().items[0],prepared_qty:1}]},{},false);
  ui.callbacks.onStatus({...state,applied:{at:new Date(Date.now()+1)}});
  assert.equal(prepare(ui).disabled,false);assert.equal(ui.document.activeElement,prepare(ui));
});

test('mixed takeout row never starts a hold write',async()=>{
  const ui=app();ui.snapshot(mixedOrder());
  const row=ui.get('waiting-orders').querySelector('.is-takeout');
  assert.equal(row.dataset.action,undefined);
  await ui.fire(row,'pointerdown');await ui.advance(1000);assert.equal(ui.posts.length,0);
});

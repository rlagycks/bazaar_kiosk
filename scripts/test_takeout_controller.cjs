/* Real controller/state with the shared event DOM. The race tests also run the
 * actual BazaarLive scheduler, holding HTTP responses across write boundaries. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {createContext,runInContext} = require('node:vm');
const {fakeDocument} = require('./fake_document.cjs');
const flush = () => new Promise(resolve=>setImmediate(resolve));
const customKey = 'custom:'+'a'.repeat(64);
const base = (extra={}) => ({version:'snapshot-1',unchanged:false,complete:true,cursor:null,orders:[],count:0,total:1,has_more:false,
  completion_version:'completion-1',remaining_total:5,
  menus:[{key:'menu:7',name:'국수',remaining_qty:3,is_custom:false},
    {key:customKey,name:'<img src=x onerror=alert(1)>',remaining_qty:2,is_custom:true}],
  history:{orders:[{id:1,order_no:27,created_at:'2026-10-02T15:30:00Z',order_date:'2026-10-03',is_practice:true,
    table:{number:101},items:[{id:7,menu_item_name:'국수',qty:3,is_custom:false}],total_qty:3}],
    total:1,page:1,pages:1,has_previous:false,has_next:false},...extra});
const response = body => new Response(JSON.stringify(body));
function app(settings={}) {
  const document=fakeDocument();document.hidden=false;
  const add=(parent,tag,id,attrs={})=>parent.append(document.create(tag,{id,...attrs}));
  const page=add(document,'main','takeout-page',{'data-snapshot-url':'/orders/api/snapshot/takeout?page=1',
    'data-stream-url':'/orders/api/stream/kitchen','data-complete-url':'/orders/api/takeout/complete','data-login-url':'/orders/login/'});
  for(const id of ['takeout-menus','takeout-live','takeout-notice','takeout-remaining-total','takeout-menu-count',
    'takeout-completion','takeout-selection-title','takeout-selected-total','takeout-selection-summary',
    'takeout-review-panel','takeout-review-message','takeout-error','takeout-history-title','takeout-pagination']) add(page,'div',id);
  add(page,'tbody','takeout-history');
  for(const id of ['takeout-reload','takeout-submit','takeout-review','takeout-retry']) add(page,'button',id);
  const posts=[],reads=[],refetches=[],redirects=[],listeners=new Map();let callbacks,live,timer=0,nextId=0;
  const window={navigator:{onLine:true},location:{origin:'https://kiosk.test',href:'https://kiosk.test/orders/kitchen/takeout/',assign:url=>redirects.push(url)},
    crypto:{randomUUID:()=>`00000000-0000-4000-8000-${String(++nextId).padStart(12,'0')}`},
    setTimeout:()=>++timer,clearTimeout(){},addEventListener(type,fn){if(!listeners.has(type))listeners.set(type,[]);listeners.get(type).push(fn);},
    BazaarAuth:{fetch:async(url,options={})=>{
      if(options.method==='POST') {
        posts.push({url,...options,rawBody:options.body,body:JSON.parse(options.body)});
        return settings.write ? settings.write(posts.at(-1),posts.length) : response({completed_qty:1,completed_orders:[]});
      }
      reads.push({url,options});return settings.read ? settings.read(reads.length,url) : response(base());
    }},
    BazaarDom:{el(tag,opts={},children=[]) {
      const node=document.create(tag,{class:opts.class||'',...opts.attrs});
      Object.entries(opts.data||{}).forEach(([key,value])=>node.setAttribute('data-'+key,value));
      if(opts.text!==undefined)node.textContent=opts.text;
      (Array.isArray(children)?children:[children]).forEach(child=>node.append(child));return node;
    },render(node,children){node.replaceChildren(...(Array.isArray(children)?children:[children]));},
    delegate(node,type,selector,handler){node.addEventListener(type,event=>{const target=event.target.closest(selector);if(target)return handler(event,target);});}}};
  const context=createContext({window,document,URL,TypeError});
  const load=name=>runInContext(readFileSync(join(__dirname,'../orders/static/orders/ui',name),'utf8'),context,{filename:name});
  if(settings.realLive)load('kitchen_live.js');
  const scheduler=window.BazaarLive;
  window.BazaarLive={create:options=>{
    callbacks=options;
    const actual=settings.realLive?scheduler.create(options):{start(){},refetch(){}};
    live={...actual,refetch:reason=>{refetches.push(reason);actual.refetch(reason);}};return live;
  }};
  load('request_id.js');load('takeout_state.js');load('takeout.js');
  const get=id=>document.getElementById(id);
  let current={running:true,ended:false,lastError:null,inFlight:false,polling:false,stream:'open',hubOk:true,applied:{at:null}};
  const status=extra=>{current={...current,...extra};callbacks.onStatus(current);};
  const snapshot=(data=base())=>{callbacks.onApply(data);status({lastError:null,inFlight:false,applied:{at:new Date(),complete:true,version:data.version}});};
  const click=async node=>{assert.ok(node,'control exists');assert.equal(node.disabled,false,'control enabled');node.focus();void node.dispatch('click');await flush();};
  const step=(key='menu:7',amount=1)=>[...get('takeout-menus').querySelectorAll('[data-step]')]
    .find(node=>node.dataset.menuKey===key&&node.dataset.step===String(amount));
  const quantity=(key='menu:7')=>get('takeout-menus').querySelectorAll('output').find(node=>node.dataset.menuKey===key)?.textContent;
  return {get,click,step,quantity,snapshot,status,callbacks,posts,reads,refetches,redirects,window,document,
    refetch:reason=>live.refetch(reason),event:type=>{
      const event={defaultPrevented:false,preventDefault(){this.defaultPrevented=true;}};
      (listeners.get(type)||[]).forEach(fn=>fn(event));return event;
    }};
}

test('dynamic catalog, zero quantities, safe names, voucher history and Seoul date include no history actions',()=>{
  const ui=app();ui.snapshot(base({menus:[...base().menus,{key:'menu:88',name:'추가 메뉴',remaining_qty:0,is_custom:false}]}));
  assert.match(ui.get('takeout-menus').textContent,/<img src=x/);assert.equal(ui.get('takeout-menus').querySelector('img'),null);
  assert.equal(ui.step('menu:88').disabled,true);assert.match(ui.get('takeout-menu-count').textContent,/3종/);
  assert.match(ui.get('takeout-history').textContent,/#027/);assert.match(ui.get('takeout-history').textContent,/2026\. 10\. 03/);
  assert.match(ui.get('takeout-history').textContent,/00:30/);assert.match(ui.get('takeout-history').textContent,/연습/);
  assert.doesNotMatch(ui.get('takeout-history').textContent,/101|상태|상세|수정|서빙 출발/);
  assert.equal(ui.get('takeout-history').querySelectorAll('button,a,input').length,0);
  assert.match(ui.step().attrs['aria-label'],/국수 이번 완료 수량 늘리기/);
});
test('selection posts exact contract with CSRF once and clears only a confirmed successful quantity',async()=>{
  let resolve;const ui=app({write:()=>new Promise(r=>{resolve=r;})});ui.snapshot();
  await ui.click(ui.step());await ui.click(ui.get('takeout-submit'));
  assert.equal(ui.get('takeout-submit').disabled,true);assert.equal(ui.step().disabled,true);
  void ui.get('takeout-submit').dispatch('click');assert.equal(ui.posts.length,1);assert.equal(ui.quantity(),'1');
  assert.equal(ui.posts[0].url,'/orders/api/takeout/complete');assert.equal(ui.posts[0].headers['X-CSRFToken'],'synthetic-csrf');
  assert.deepEqual(JSON.parse(JSON.stringify(ui.posts[0].body)),{expected_version:'completion-1',items:[{key:'menu:7',quantity:1}],request_id:'00000000-0000-4000-8000-000000000001'});
  resolve(response({completed_qty:1,completed_orders:[]}));await flush();
  assert.equal(ui.quantity(),'0');assert.equal(ui.get('takeout-submit').disabled,true);
  assert.equal(ui.step().disabled,true,'waits for read after write');assert.deepEqual(ui.refetches,['write']);
  assert.match(ui.get('takeout-remaining-total').textContent,/5개/,'write response is not a new snapshot');
  ui.snapshot(base({completion_version:'completion-2'}));assert.equal(ui.step().disabled,false);
});
test('custom key is submitted as supplied and not reconstructed from menu name',async()=>{
  const ui=app();ui.snapshot();await ui.click(ui.step(customKey));await ui.click(ui.get('takeout-submit'));
  assert.equal(ui.posts[0].body.items[0].key,customKey);
});
test('SSE preserves excessive selection, requires review, and only decrement becomes usable until corrected',async()=>{
  const ui=app();ui.snapshot();await ui.click(ui.step());await ui.click(ui.step());
  ui.snapshot(base({completion_version:'completion-2',menus:[{...base().menus[0],remaining_qty:1}]}));
  assert.equal(ui.quantity(),'2');assert.equal(ui.get('takeout-submit').disabled,true);assert.equal(ui.step('menu:7',-1).disabled,true);
  await ui.click(ui.get('takeout-review'));assert.equal(ui.quantity(),'2');assert.equal(ui.get('takeout-submit').disabled,true);
  assert.equal(ui.step().disabled,true);assert.equal(ui.document.activeElement,ui.step('menu:7',-1));
  await ui.click(ui.step('menu:7',-1));await ui.click(ui.get('takeout-submit'));
  assert.equal(ui.posts[0].body.expected_version,'completion-2');assert.equal(ui.posts[0].body.items[0].quantity,1);
});
test('removed selected menu stays visible through review until user reduces it to zero',async()=>{
  const ui=app();ui.snapshot();await ui.click(ui.step());ui.snapshot(base({menus:[],completion_version:'removed',remaining_total:0}));
  assert.equal(ui.quantity(),'1');assert.match(ui.get('takeout-menus').textContent,/대기 목록에 없는 메뉴/);
  await ui.click(ui.get('takeout-review'));await ui.click(ui.step('menu:7',-1));assert.equal(ui.quantity(),undefined);
  assert.equal(ui.document.activeElement,ui.get('takeout-selection-title'));
});
for(const [name,write,unknown] of [
  ['409 conflict',()=>new Response(JSON.stringify({detail:'다른 직원이 완료했습니다'}),{status:409}),false],
  ['400 plain validation',()=>new Response('완료 수량을 확인하세요',{status:400}),false],
  ['lost write response',()=>Promise.reject(new TypeError('offline')),true],
  ['503 unknown result',()=>new Response('unavailable',{status:503}),true],
  ['200 invalid JSON',()=>new Response('OK'),true],
  ['200 wrong quantity',()=>response({completed_qty:2,completed_orders:[]}),true],
  ['200 missing order list',()=>response({completed_qty:1}),true],
]) test(name+' retains quantity and uses only the recovery allowed by its result',async()=>{
  const ui=app({write});ui.snapshot();await ui.click(ui.step());await ui.click(ui.get('takeout-submit'));
  assert.equal(ui.quantity(),'1');assert.equal(ui.posts.length,1);assert.deepEqual(ui.refetches,['write']);
  assert.equal(ui.get('takeout-review').disabled,true);assert.equal(ui.get('takeout-submit').disabled,true);
  void ui.get('takeout-review').dispatch('click');void ui.get('takeout-submit').dispatch('click');assert.equal(ui.posts.length,1);
  ui.snapshot(base({completion_version:'completion-2'}));assert.equal(ui.get('takeout-submit').disabled,true);
  if(unknown) {
    assert.equal(ui.get('takeout-review').disabled,true,'fresh snapshot cannot release an uncertain attempt');
    assert.equal(ui.get('takeout-retry').hidden,false);assert.equal(ui.step().disabled,true);
    void ui.get('takeout-review').dispatch('click');void ui.step().dispatch('click');void ui.get('takeout-submit').dispatch('click');
    assert.equal(ui.quantity(),'1');assert.equal(ui.posts.length,1);
    await ui.click(ui.get('takeout-retry'));
    assert.equal(ui.posts.length,2);assert.equal(ui.posts[1].rawBody,ui.posts[0].rawBody);
    assert.equal(ui.posts[1].body.expected_version,'completion-1');
    assert.equal(ui.get('takeout-submit').disabled,true);assert.equal(ui.quantity(),'1');
  } else {
    assert.equal(ui.get('takeout-retry').hidden,true);
    await ui.click(ui.get('takeout-review'));assert.equal(ui.quantity(),'1');assert.equal(ui.posts.length,1);
    assert.equal(ui.get('takeout-submit').disabled,false,'definitive refusal permits a reviewed new intent');
  }
});
test('unchanged response and heartbeats retain cards, selections and stepper focus',async()=>{
  const ui=app();ui.snapshot();await ui.click(ui.step());const focused=ui.document.activeElement,card=ui.get('takeout-menus').children[0];
  assert.equal(focused,ui.step());ui.status({inFlight:true});ui.status({inFlight:false});
  assert.equal(ui.document.activeElement,focused);assert.equal(ui.get('takeout-menus').children[0],card);
  ui.snapshot({unchanged:true,version:'snapshot-1'});assert.equal(ui.get('takeout-menus').children[0],card);assert.equal(ui.quantity(),'1');
  ui.snapshot(base({version:'history-only'}));assert.equal(ui.document.activeElement,ui.step());
});
test('read failure, tab resume and offline reconnect cannot unlock edits on an old timestamp',async()=>{
  const ui=app();ui.snapshot();await ui.click(ui.step());ui.status({lastError:'offline'});
  assert.equal(ui.step().disabled,true);ui.status({lastError:null});assert.equal(ui.get('takeout-review').disabled,true);
  ui.snapshot();await ui.click(ui.get('takeout-review'));ui.status({running:false});ui.status({running:true,inFlight:true});
  assert.equal(ui.get('takeout-review').disabled,true);ui.snapshot();await ui.click(ui.get('takeout-review'));
  ui.window.navigator.onLine=false;ui.event('offline');assert.equal(ui.get('takeout-submit').disabled,true);
  ui.window.navigator.onLine=true;ui.event('online');assert.equal(ui.get('takeout-review').disabled,true);
  assert.equal(ui.refetches.at(-1),'online');ui.snapshot();assert.equal(ui.get('takeout-submit').disabled,true);
  await ui.click(ui.get('takeout-review'));assert.equal(ui.get('takeout-submit').disabled,false);
});
for(const code of [401,403])test('HTTP '+code+' blocks further reads and writes while preserving selections',async()=>{
  const ui=app({write:()=>new Response('',{status:code})});ui.snapshot();await ui.click(ui.step());await ui.click(ui.get('takeout-submit'));
  ui.snapshot();assert.equal(ui.quantity(),'1');assert.equal(ui.get('takeout-review').disabled,true);
  assert.equal(ui.get('takeout-submit').disabled,true);assert.equal(ui.get('takeout-retry').disabled,true);assert.equal(ui.refetches.length,0);
});
test('AuthenticationLost cannot be recovered by a later snapshot or automatic write retry',async()=>{
  const ui=app({write:()=>{const error=new Error('login');error.name='AuthenticationLost';throw error;}});
  ui.snapshot();await ui.click(ui.step());await ui.click(ui.get('takeout-submit'));ui.snapshot();
  assert.equal(ui.get('takeout-review').disabled,true);assert.equal(ui.quantity(),'1');assert.equal(ui.posts.length,1);
  ui.callbacks.onAuthLost();assert.deepEqual(ui.redirects,['/orders/login/']);
});
test('history pagination uses same scheduler and keeps selection; out-of-range page returns to last page',async()=>{
  const ui=app();ui.snapshot(base({history:{...base().history,page:1000,pages:2,has_previous:true}}));await ui.click(ui.step());
  await ui.click(ui.get('takeout-pagination').querySelector('button'));assert.deepEqual(ui.refetches,['history']);
  const result=await ui.callbacks.fetch('/orders/api/snapshot/takeout?page=1&since=old',{});await result.json();
  const url=new URL(ui.reads[0].url);assert.equal(url.searchParams.get('page'),'2');assert.equal(url.searchParams.has('since'),false);
  ui.snapshot(base({history:{...base().history,page:2,pages:2,has_previous:true}}));
  assert.equal(ui.quantity(),'1');assert.equal(ui.get('takeout-submit').disabled,false);
});
test('actual scheduler rejects pre-write read after ambiguous result; fresh read cannot release the original attempt',async()=>{
  let releaseOld,releaseFresh;
  const ui=app({realLive:true,write:()=>Promise.reject(new TypeError('lost response')),
    read:n=>n===1?response(base()):new Promise(resolve=>{if(n===2)releaseOld=resolve;else releaseFresh=resolve;})});
  await flush();await ui.click(ui.step());ui.refetch('change');await flush();
  await ui.click(ui.get('takeout-submit'));assert.equal(ui.reads.length,2);
  releaseOld(response(base()));await flush();assert.equal(ui.reads.length,3);
  assert.equal(ui.get('takeout-review').disabled,true,'old read cannot prove post-write state');
  releaseFresh(response({unchanged:true,version:'snapshot-1'}));await flush();
  assert.equal(ui.get('takeout-review').disabled,true);assert.equal(ui.get('takeout-submit').disabled,true);
  assert.equal(ui.get('takeout-retry').disabled,false);
  assert.equal(ui.quantity(),'1');assert.equal(ui.posts.length,1);
  void ui.get('takeout-review').dispatch('click');assert.equal(ui.posts.length,1);
});
test('actual scheduler cannot let a read started during a successful write unlock stale remaining counts',async()=>{
  let releaseWrite,releaseDuring,releaseAfter;
  const ui=app({realLive:true,write:()=>new Promise(resolve=>{releaseWrite=resolve;}),
    read:n=>n===1?response(base()):new Promise(resolve=>{if(n===2)releaseDuring=resolve;else releaseAfter=resolve;})});
  await flush();await ui.click(ui.step());await ui.click(ui.get('takeout-submit'));
  ui.refetch('change');await flush();releaseWrite(response({completed_qty:1,completed_orders:[]}));await flush();
  releaseDuring(response(base()));await flush();assert.equal(ui.step().disabled,true);
  releaseAfter(response(base({version:'snapshot-2',completion_version:'completion-2',remaining_total:4})));await flush();
  assert.equal(ui.step().disabled,false);assert.equal(ui.quantity(),'0');assert.equal(ui.posts.length,1);
});
test('lost 200 is recovered with identical request ID and payload after snapshot changed, without a second decrement',async()=>{
  let remaining=3,decrements=0;
  const receipts=new Map();
  const ui=app({write:post=>{
    const payload=post.body, receipt=receipts.get(payload.request_id);
    if(receipt) {
      assert.equal(post.rawBody,receipt.rawBody);
      return response(receipt.result);
    }
    remaining-=payload.items[0].quantity;decrements++;
    const result={completed_qty:payload.items[0].quantity,completed_orders:[]};
    receipts.set(payload.request_id,{rawBody:post.rawBody,result});
    if(decrements===1)throw new TypeError('200 response lost after commit');
    return response(result);
  }});
  ui.snapshot();await ui.click(ui.step());await ui.click(ui.get('takeout-submit'));
  const id=ui.posts[0].body.request_id;
  assert.ok(id);assert.equal(remaining,2);assert.equal(decrements,1);assert.equal(ui.quantity(),'1');
  ui.snapshot(base({completion_version:'completion-after-commit',menus:[{...base().menus[0],remaining_qty:remaining}]}));
  assert.equal(ui.get('takeout-review').disabled,true);assert.equal(ui.get('takeout-submit').disabled,true);
  assert.equal(ui.step('menu:7',-1).disabled,true);assert.equal(ui.posts.length,1);
  await ui.click(ui.get('takeout-retry'));
  assert.equal(ui.posts[1].body.request_id,id);assert.equal(ui.posts[1].rawBody,ui.posts[0].rawBody);
  assert.equal(remaining,2);assert.equal(decrements,1);assert.equal(ui.quantity(),'0');
  assert.equal(ui.get('takeout-retry').hidden,true);assert.equal(ui.document.activeElement,ui.get('takeout-selection-title'));
  ui.snapshot(base({completion_version:'completion-after-commit',menus:[{...base().menus[0],remaining_qty:remaining}]}));
  await ui.click(ui.step());await ui.click(ui.get('takeout-submit'));
  assert.notEqual(ui.posts[2].body.request_id,id);assert.equal(ui.posts[2].body.expected_version,'completion-after-commit');
  assert.equal(remaining,1);assert.equal(decrements,2,'only deliberate new completion changes inventory again');
});
for(const code of [400,409])test('uncertain attempt receiving definitive '+code+' releases only after fresh review and correction',async()=>{
  const ui=app({write:(post,n)=>{
    if(n===1)throw new TypeError('lost');
    if(n===2)return new Response('거절',{status:code});
    return response({completed_qty:1,completed_orders:[]});
  }});
  ui.snapshot();await ui.click(ui.step());await ui.click(ui.step());await ui.click(ui.get('takeout-submit'));
  const changed=base({completion_version:'completion-2',menus:[{...base().menus[0],remaining_qty:1}]});
  ui.snapshot(changed);assert.equal(ui.quantity(),'2');assert.equal(ui.get('takeout-review').disabled,true);
  await ui.click(ui.get('takeout-retry'));
  assert.equal(ui.posts[1].rawBody,ui.posts[0].rawBody,'even excessive old quantity is retried as the same attempt');
  assert.equal(ui.get('takeout-retry').hidden,true);assert.equal(ui.get('takeout-review').disabled,true);
  assert.equal(ui.get('takeout-submit').disabled,true);assert.equal(ui.quantity(),'2');
  ui.snapshot(changed);await ui.click(ui.get('takeout-review'));assert.equal(ui.get('takeout-submit').disabled,true);
  await ui.click(ui.step('menu:7',-1));await ui.click(ui.get('takeout-submit'));
  assert.notEqual(ui.posts[2].body.request_id,ui.posts[0].body.request_id);
  assert.equal(ui.posts[2].body.expected_version,'completion-2');assert.equal(ui.posts[2].body.items[0].quantity,1);
});
test('uncertain retry is manual, single-flight, blocked offline or hidden, and keeps the page departure guard',async()=>{
  let release;
  const ui=app({write:(post,n)=>{if(n===1)throw new TypeError('lost');return new Promise(resolve=>{release=resolve;});}});
  ui.snapshot();await ui.click(ui.step());await ui.click(ui.get('takeout-submit'));
  assert.equal(ui.event('beforeunload').defaultPrevented,true);
  ui.window.navigator.onLine=false;ui.event('offline');assert.equal(ui.get('takeout-retry').disabled,true);
  void ui.get('takeout-retry').dispatch('click');assert.equal(ui.posts.length,1);
  ui.window.navigator.onLine=true;ui.event('online');assert.equal(ui.posts.length,1,'reconnect never replays automatically');
  ui.status({running:false});assert.equal(ui.get('takeout-retry').disabled,true);
  ui.status({running:true,lastError:'snapshot unavailable'});assert.equal(ui.get('takeout-retry').disabled,false,'receipt can recover even when snapshot read fails');
  await ui.click(ui.get('takeout-retry'));assert.equal(ui.get('takeout-retry').disabled,true);
  void ui.get('takeout-retry').dispatch('click');void ui.get('takeout-submit').dispatch('click');assert.equal(ui.posts.length,2);
  assert.equal(ui.posts[1].rawBody,ui.posts[0].rawBody);
  release(response({completed_qty:1,completed_orders:[]}));await flush();assert.equal(ui.quantity(),'0');
  assert.equal(ui.event('beforeunload').defaultPrevented,false);
});
for(const code of [401,403])test('uncertain receipt retry receiving '+code+' remains auth-blocked after fresh snapshots',async()=>{
  const ui=app({write:(post,n)=>{if(n===1)throw new TypeError('lost');return new Response('',{status:code});}});
  ui.snapshot();await ui.click(ui.step());await ui.click(ui.get('takeout-submit'));await ui.click(ui.get('takeout-retry'));
  ui.snapshot(base({completion_version:'different'}));
  assert.equal(ui.quantity(),'1');assert.equal(ui.get('takeout-retry').disabled,true);
  assert.equal(ui.get('takeout-review').disabled,true);assert.equal(ui.get('takeout-submit').disabled,true);
  void ui.get('takeout-retry').dispatch('click');assert.equal(ui.posts.length,2);
});

/* Exercise the actual dashboard controller: report integrity, dates and response ordering. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {createContext,runInContext} = require('node:vm');
const {fakeDocument} = require('./fake_document.cjs');
const state = require('../orders/static/orders/ui/stats_state.js');
const flush = ()=>new Promise(resolve=>setImmediate(resolve));
const fixture = (start='2026-09-20',end=start) => ({
  period:{start_date:start,end_date:end,basis:'explicit',label:''},
  summary:{orders:2,items:3,revenue:12000,cancelled_orders:1,legacy_unsplit_orders:1,unattributed_orders:1,unattributed_amount:5000},
  payment:{cash:10000,ticket:2000,change:5000,net_cash:5000},
  menu:[{menu_item_id:1,name:'<img src=x onerror=alert(1)>',qty:3,amount:12000}],
  menu_by_mode:{DINE_IN:[{menu_item_id:1,name:'<img src=x onerror=alert(1)>',qty:3,amount:12000}],TAKEOUT:[]},
  hourly:[{date:start,hour:'12:00',orders:2,revenue:12000}],
});
const json=data=>new Response(JSON.stringify(data));
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}
function app(respond) {
  const document=fakeDocument(),create=document.create;
  document.create=(tag,attrs)=>{const node=create(tag,attrs);node.style={};return node;};
  const add=(parent,tag,id,attrs={})=>parent.append(document.create(tag,{id,...attrs}));
  const page=add(document,'main','stats-page',{'data-dashboard-url':'/orders/api/stats/dashboard'});
  const form=add(page,'form','periodForm');add(form,'input','periodStart');add(form,'input','periodEnd');add(form,'button','periodReset');
  for(const id of ['stats-error-panel','stats-error','stats-status','stats-results','periodLabel','summaryOrders','summaryItems','summaryRevenue','summaryNetCash','summaryExcluded','paymentCash','paymentChange','paymentNetCash','paymentTicket','paymentRatio','legacyNotice','unattributedPanel','unattributedAmount','stats-empty','hourlyChart','menuDineInTotal','menuTakeoutTotal']) add(page,'div',id);
  for(const id of ['menuDineInBody','menuTakeoutBody','hourlyTableBody'])add(page,'tbody',id);
  add(page,'button','stats-retry');
  const calls=[];
  const window={location:{href:'http://localhost/orders/b1-counter/'},BazaarAuth:{fetch:async (url,options)=>{calls.push({url,options});return respond(calls.length,url);}},
    BazaarDom:{
      el(tag,opts={},children=[]){const node=document.create(tag,{class:opts.class||'',...opts.attrs});if(opts.text!==undefined)node.textContent=opts.text;(Array.isArray(children)?children:[children]).forEach(child=>node.append(child));return node;},
      render(node,children){node.replaceChildren(...(Array.isArray(children)?children:[children]));}
    }};
  const ctx=createContext({document,window,TypeError,URL});
  for(const name of ['stats_state.js','stats.js'])runInContext(readFileSync(join(__dirname,'../orders/static/orders/ui',name),'utf8'),ctx,{filename:name});
  const get=id=>document.getElementById(id);
  const input=async(id,value)=>{get(id).value=value;await get(id).dispatch('input');};
  const submit=async(start,end)=>{await input('periodStart',start);await input('periodEnd',end);await get('periodForm').dispatch('submit');await flush();};
  return {get,calls,input,submit,click:async id=>{await get(id).dispatch('click');await flush();}};
}
test('zero receipts mean both ratios zero, while net cash can be negative',()=>{
  assert.deepEqual(state.ratio({cash:0,ticket:0}),{cash:0,ticket:0});
  const data=fixture();data.payment.net_cash=-100;assert.equal(state.validate(data),data);
});
test('malformed reports cannot become zero sales or ambiguous multiday bars',()=>{
  for(const change of [d=>delete d.summary.revenue,d=>d.payment.cash='100',d=>d.menu=null,d=>delete d.hourly[0].date,d=>d.period.start_date='2026-02-30',
    d=>delete d.menu_by_mode,d=>d.menu_by_mode.TAKEOUT=null,d=>delete d.menu_by_mode.DINE_IN,d=>d.menu_by_mode.DINE_IN[0].qty=-1]){
    const data=fixture();change(data);assert.throws(()=>state.validate(data));
  }
});
test('renders server money, excluded and unclassified records; menu names remain text',async()=>{
  const ui=app(()=>json(fixture()));await flush();
  assert.equal(ui.get('summaryRevenue').textContent,'12,000원');assert.equal(ui.get('summaryNetCash').textContent,'5,000원');
  assert.equal(ui.get('paymentCash').textContent,'10,000원');assert.equal(ui.get('paymentChange').textContent,'5,000원');
  assert.match(ui.get('summaryExcluded').textContent,/취소 1건/);assert.equal(ui.get('unattributedPanel').hidden,false);
  assert.match(ui.get('unattributedAmount').textContent,/5,000원/);assert.match(ui.get('menuDineInBody').textContent,/<img src=x/);
  assert.equal(ui.get('menuDineInBody').querySelector('img'),null);assert.equal(ui.get('stats-results').attrs['aria-busy'],'false');
});
test('fresh zero report is empty, not an error; no phantom 100% ticket',async()=>{
  const data=fixture();for(const key of Object.keys(data.summary))data.summary[key]=0;
  for(const key of Object.keys(data.payment))data.payment[key]=0;data.menu=[];data.menu_by_mode={DINE_IN:[],TAKEOUT:[]};data.hourly=[];
  const ui=app(()=>json(data));await flush();assert.equal(ui.get('summaryRevenue').textContent,'0원');
  assert.equal(ui.get('stats-empty').hidden,false);assert.equal(ui.get('stats-error-panel').hidden,true);
  assert.equal(ui.get('unattributedPanel').hidden,true);assert.match(ui.get('paymentRatio').textContent,/현금 0% · 티켓 0%/);
});
test('initial failure never renders a false zero and retry uses same default query',async()=>{
  const ui=app(n=>n===1?Promise.reject(new TypeError('offline')):json(fixture()));await flush();
  assert.equal(ui.get('stats-error-panel').hidden,false);assert.equal(ui.get('summaryRevenue').textContent,'');
  assert.match(ui.get('stats-error').textContent,/매출 0원을 의미하지/);await ui.click('stats-retry');
  assert.equal(ui.calls[0].url,ui.calls[1].url);assert.equal(ui.get('summaryRevenue').textContent,'12,000원');
});
for(const [name,response] of [['plain 400',()=>new Response('시작일이 종료일보다 늦습니다',{status:400})],['JSON 403',()=>new Response(JSON.stringify({detail:'권한이 없습니다.'}),{status:403})],['bad success',()=>json({})]])
 test(name+' keeps successful figures tied to their original period',async()=>{
  const ui=app(n=>n===1?json(fixture()):response());await flush();await ui.submit('2026-09-22','2026-09-21');
  assert.match(ui.get('periodLabel').textContent,/2026-09-20/);assert.equal(ui.get('summaryRevenue').textContent,'12,000원');
  assert.equal(ui.get('periodStart').value,'2026-09-22');assert.match(ui.get('stats-status').textContent,/조회 실패/);
 });
test('latest response wins even when older response arrives after a newer result',async()=>{
  const old=deferred(),next=deferred();const ui=app(n=>n===1?old.promise:next.promise);
  await ui.submit('2026-09-21','2026-09-21');next.resolve(json(fixture('2026-09-21')));await flush();
  old.resolve(json(fixture('2026-09-20')));await flush();
  assert.match(ui.get('periodLabel').textContent,/2026-09-21/);assert.equal(ui.get('periodStart').value,'2026-09-21');
});
test('late failure cannot overwrite a newer successful query',async()=>{
  const old=deferred();const ui=app(n=>n===1?old.promise:json(fixture('2026-09-21')));
  await ui.submit('2026-09-21','2026-09-21');old.reject(new TypeError('offline'));await flush();
  assert.equal(ui.get('stats-error-panel').hidden,true);assert.match(ui.get('stats-status').textContent,/조회 완료/);
});
test('changing date input while a read is pending preserves unsent dates',async()=>{
  const pending=deferred(),ui=app(()=>pending.promise);
  await ui.input('periodStart','2026-09-25');pending.resolve(json(fixture()));await flush();
  assert.equal(ui.get('periodStart').value,'2026-09-25');assert.match(ui.get('periodLabel').textContent,/2026-09-20/);
});
test('default reset drops explicit parameters; retry keeps the failed parameters',async()=>{
  const ui=app(n=>n===2?new Response('invalid',{status:400}):json(fixture()));await flush();
  await ui.submit('2026-09-21','2026-09-22');await ui.click('stats-retry');assert.equal(ui.calls[1].url,ui.calls[2].url);
  await ui.click('periodReset');assert.equal(new URL(ui.calls[3].url).search,'');
});
test('multiple dates with the same hour stay distinct in chart and accessible table',async()=>{
  const data=fixture('2026-09-20','2026-09-21');data.hourly.push({date:'2026-09-21',hour:'12:00',orders:1,revenue:0});
  const ui=app(()=>json(data));await flush();
  for(const id of ['hourlyChart','hourlyTableBody']){
    assert.match(ui.get(id).textContent,/2026-09-20 · 12:00/);assert.match(ui.get(id).textContent,/2026-09-21 · 12:00/);
  }
  assert.equal(ui.get('hourlyChart').children[1].querySelector('div').style.height,'0px');
});

test('D-073: a menu sold partly as custom lines shows its total and both parts; unmatched names are 기타 rows',async()=>{
  const data=fixture();
  data.menu_by_mode.DINE_IN=[{menu_item_id:1,name:'삼계탕',qty:33,amount:320000,custom_qty:3,custom_amount:20000},
    {menu_item_id:null,name:'떡꼬치',qty:2,amount:5000,custom_qty:2,custom_amount:5000},
    {menu_item_id:2,name:'Meal',qty:1,amount:5000,custom_qty:0,custom_amount:0}];
  const ui=app(()=>json(data));await flush();
  const rows=ui.get('menuDineInBody').children.map(row=>row.children.slice(0,3).map(cell=>cell.textContent));
  assert.deepEqual(rows,[
    ['삼계탕','33개','320,000원'],['└ 정가','30개','300,000원'],['└ 기타','3개','20,000원'],
    ['기타 · 떡꼬치','2개','5,000원'],['Meal','1개','5,000원']]);
});
test('D-073: a malformed custom part is refused like any other figure',()=>{
  const data=fixture();data.menu[0].custom_qty='3';
  assert.throws(()=>state.validate(data));
  const split=fixture();split.menu_by_mode.DINE_IN[0].custom_amount=-1;
  assert.throws(()=>state.validate(split));
});
test('D-079: hall and takeout menu sales are separate tables, each with its own totals',async()=>{
  const data=fixture();
  data.menu_by_mode={DINE_IN:[{menu_item_id:1,name:'떡볶이',qty:8,amount:32000},{menu_item_id:2,name:'어묵',qty:4,amount:16000}],
    TAKEOUT:[{menu_item_id:1,name:'떡볶이',qty:5,amount:20000}]};
  const ui=app(()=>json(data));await flush();
  const cells=id=>ui.get(id).children.map(row=>row.children.slice(0,3).map(cell=>cell.textContent));
  assert.deepEqual(cells('menuDineInBody'),[['떡볶이','8개','32,000원'],['어묵','4개','16,000원']]);
  assert.deepEqual(cells('menuTakeoutBody'),[['떡볶이','5개','20,000원']]);
  assert.equal(ui.get('menuDineInTotal').textContent,'12개 · 48,000원');
  assert.equal(ui.get('menuTakeoutTotal').textContent,'5개 · 20,000원');
});
test('D-079: a side with no sales says so instead of borrowing the other side',async()=>{
  const ui=app(()=>json(fixture()));await flush();
  assert.equal(ui.get('menuTakeoutBody').textContent,'집계할 주문이 없습니다');
  assert.equal(ui.get('menuTakeoutTotal').textContent,'0개 · 0원');
  assert.match(ui.get('menuDineInBody').textContent,/3개/);
});

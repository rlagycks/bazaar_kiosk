(function () {
  'use strict';
  const page = document.getElementById('stats-page');
  if (!page) return;
  const DOM = window.BazaarDom, state = window.BazaarStatsState;
  const get = id => document.getElementById(id), el = DOM.el, money = state.money;
  let issued = 0, draftRevision = 0, lastParams = {}, applied = null;
  const dates = period => period.start_date === period.end_date ? period.start_date : period.start_date + ' ~ ' + period.end_date;
  const emptyRow = columns => el('tr', {}, [el('td', {text:'집계할 주문이 없습니다',attrs:{colspan:columns}})]);
  function draw(data) {
    const {summary:s, payment:p, period} = data;
    get('periodLabel').textContent = state.periodText(period);
    get('summaryOrders').textContent = s.orders.toLocaleString('ko-KR') + '건';
    get('summaryItems').textContent = s.items.toLocaleString('ko-KR') + '개';
    get('summaryRevenue').textContent = money(s.revenue);
    get('summaryNetCash').textContent = money(p.net_cash);
    get('summaryExcluded').textContent = `취소 ${s.cancelled_orders}건 · 연습 주문 제외`;
    for (const [id,key] of [['paymentCash','cash'],['paymentChange','change'],['paymentNetCash','net_cash'],['paymentTicket','ticket']]) get(id).textContent = money(p[key]);
    const percentages = state.ratio(p);
    get('paymentRatio').textContent = `받은 현금·식권 합계 기준: 현금 ${percentages.cash}% · 식권 ${percentages.ticket}%`;
    get('legacyNotice').textContent = s.legacy_unsplit_orders ? `구형 수납 기록 ${s.legacy_unsplit_orders}건은 기존 결제 방식으로 해석했습니다.` : '';
    get('unattributedPanel').hidden = s.unattributed_orders === 0;
    get('unattributedAmount').textContent = `과거 혼합 결제 ${s.unattributed_orders}건 · ${money(s.unattributed_amount)}은 현금·식권 내역에 포함되지 않습니다.`;
    get('stats-empty').hidden = s.orders !== 0;
    DOM.render(get('menuTableBody'), data.menu.length ? data.menu.map(row => el('tr',{},[
      el('td',{text:row.name}),el('td',{class:'numeric',text:row.qty.toLocaleString('ko-KR')+'개'}),
      el('td',{class:'numeric',text:money(row.amount)}),el('td',{text:dates(period)})])) : emptyRow(4));
    const max = data.hourly.reduce((value,row)=>Math.max(value,row.revenue),0);
    const hourLabel = row => (period.start_date !== period.end_date ? row.date + ' · ' : '') + row.hour;
    DOM.render(get('hourlyChart'), data.hourly.length ? data.hourly.map(row => {
      const bar = el('div',{class:'hourly-fill'+(max > 0 && row.revenue === max ? ' hourly-peak' : ''),attrs:{'aria-hidden':'true'}});
      bar.style.height = (max ? row.revenue / max * 180 : 0) + 'px';
      return el('li',{class:'hourly-bar'},[el('p',{class:'hourly-value',text:money(row.revenue)}),bar,el('p',{class:'hourly-label',text:hourLabel(row)+' · '+row.orders+'건'})]);
    }) : el('li',{class:'ui-muted',text:'집계할 주문이 없습니다'}));
    DOM.render(get('hourlyTableBody'), data.hourly.length ? data.hourly.map(row => el('tr',{},[
      el('td',{text:row.date+' · '+row.hour}),el('td',{class:'numeric',text:row.orders+'건'}),el('td',{class:'numeric',text:money(row.revenue)})])) : emptyRow(3));
  }
  async function load(params = {}) {
    const request = ++issued, revision = draftRevision;
    lastParams = {...params};
    get('stats-error-panel').hidden = true; get('stats-error').textContent = '';
    get('stats-results').setAttribute('aria-busy','true');
    get('stats-status').textContent = applied ? '조회 중… 아래에는 이전 조회 결과를 유지합니다.' : '통계를 불러오는 중…';
    const url = new URL(page.dataset.dashboardUrl, window.location.href);
    Object.entries(params).forEach(([key,value])=>{if(value)url.searchParams.set(key,value);});
    try {
      const response = await window.BazaarAuth.fetch(url.toString(),{credentials:'same-origin'});
      if (request !== issued) return;
      if (!response.ok) {
        const text = await response.text(); let detail;
        try { detail = JSON.parse(text).detail; } catch (_) { /* Validation can be plain text. */ }
        throw new Error(typeof detail === 'string' ? detail : response.status === 400 ? text.slice(0,300) : '연결 상태와 조회 권한을 확인한 뒤 다시 시도해 주세요.');
      }
      const data = state.validate(await response.json());
      if (request !== issued) return;
      draw(data); applied = data;
      // An in-flight response must not erase a newer, not-yet-submitted date edit.
      if (revision === draftRevision) {
        get('periodStart').value = data.period.start_date;
        get('periodEnd').value = data.period.end_date;
      }
      get('stats-status').textContent = '조회 완료 · '+new Date().toLocaleTimeString('ko-KR',{timeZone:'Asia/Seoul',hour12:false})+' 확인 · 자동 갱신 없음';
    } catch (error) {
      if (request !== issued || error.name === 'AuthenticationLost') return;
      get('stats-error-panel').hidden = false;
      get('stats-error').textContent = '통계를 불러오지 못했어요. '+(error instanceof TypeError ? '연결 상태를 확인한 뒤 다시 시도해 주세요.' : error.message)+' 조회 실패는 매출 0원을 의미하지 않습니다.';
      get('stats-status').textContent = applied ? '조회 실패 · 아래에는 '+state.periodText(applied.period)+' 결과를 유지합니다.' : '조회 실패 · 아직 확인된 통계가 없습니다.';
    } finally {
      if (request === issued) get('stats-results').setAttribute('aria-busy','false');
    }
  }
  get('periodForm').addEventListener('submit',event=>{
    event.preventDefault();
    load({start_date:get('periodStart').value,end_date:get('periodEnd').value});
  });
  for (const id of ['periodStart','periodEnd']) get(id).addEventListener('input',()=>{draftRevision++;});
  get('periodReset').addEventListener('click',()=>{draftRevision++;load();});
  get('stats-retry').addEventListener('click',()=>load(lastParams));
  load();
})();

(function () {
  'use strict';
  const page = document.getElementById('monitor-page');
  if (!page) return;
  const DOM = window.BazaarDom, model = window.BazaarMonitorState;
  const el = DOM.el, byId = id => document.getElementById(id);
  const detail = byId('order-detail'), confirmation = byId('confirm-action');
  const orders = new Map();
  let draft = null, pending = null, busy = false, conflict = false, fresh = false;
  let opener = null, latestState = null, inputDirty = false, blockedRead = null;
  const hasEdits = () => inputDirty || Boolean(draft?.dirty());
  const modeName = item => item.service_mode === 'TAKEOUT' ? '포장' : '홀';
  const number = order => '#' + String(order.order_no ?? order.id).padStart(3, '0');
  const tableName = order => (model.kind(order) === '포장' ? '포장 ' : '테이블 ') + (order.table?.number ?? '미지정');
  const clock = value => value ? new Date(value).toLocaleString('ko-KR', {timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false}) : '—';
  const menuSummary = order => order.items.map(item => `${modeName(item)} ${item.menu_item_name} ${item.qty}`).join(' · ');
  const notice = text => { byId('monitor-notice').textContent = text; };
  function button(text, action, id, primary = false) {
    return el('button', {text, class: 'ui-button' + (primary ? ' ui-button-primary' : ''),
      attrs: {type: 'button', 'aria-label': `${number(orders.get(id))} ${text}`}, data: {action, 'order-id': id}});
  }
  function badge(order) {
    return el('span', {class: 'status-label' + (order.status === 'CANCELLED' ? ' status-cancelled' : order.status === 'READY' && !order.departed_at ? ' status-legacy' : ''), text: model.label(order)});
  }
  function reference(order) {
    const parts = [el('span', {text: number(order) + ' · ' + clock(order.created_at)})];
    if (order.is_practice) parts.unshift(el('span', {class: 'practice-tag', text: '연습'}));
    return el('div', {}, parts);
  }
  function card(order) {
    const sum = model.totals(order);
    return el('article', {class: 'monitor-card'}, [
      el('p', {class: 'status-label', text: model.kind(order) + ' · ' + model.label(order)}),
      el('h3', {text: tableName(order)}), reference(order),
      el('p', {class: 'menu-summary', text: menuSummary(order)}),
      el('p', {class: 'ui-muted', text: `준비 ${sum.prepared} / ${sum.qty}개`}),
      el('div', {class: 'card-actions'}, [button('상세 · 부분 체크', 'detail', order.id), button('완료 · 서빙 출발', 'depart', order.id, true)]),
    ]);
  }
  function row(order) {
    const sum = model.totals(order);
    return el('tr', {}, [el('td', {}, [reference(order)]), el('td', {text: tableName(order)}),
      el('td', {text: menuSummary(order)}), el('td', {text: `${sum.prepared} / ${sum.qty}`}),
      el('td', {}, [badge(order)]), el('td', {}, [button(order.status === 'CANCELLED' ? '취소 내역' : '상세 · 수정', 'detail', order.id)])]);
  }
  function drawSnapshot(data) {
    if (!Array.isArray(data.orders) || !Array.isArray(data.history?.orders)) throw new Error('모니터링 응답을 확인할 수 없습니다.');
    const active = document.activeElement;
    const restore = active?.dataset?.orderId ? {id: active.dataset.orderId, action: active.dataset.action, region: active.closest('tbody') ? 'history-orders' : 'waiting-orders'} : null;
    orders.clear();
    [...data.history.orders, ...data.orders].forEach(order => orders.set(order.id, order));
    DOM.render(byId('waiting-orders'), data.orders.length ? data.orders.map(card) : el('p', {class: 'monitor-empty', text: '미완료 주문이 없습니다.'}));
    byId('waiting-orders').setAttribute('aria-busy', 'false');
    byId('waiting-title').textContent = `미완료 주문 ${data.total}건`;
    byId('queue-warning').textContent = data.has_more ? `대기 ${data.total}건 중 오래된 ${data.count}건을 표시합니다. 나머지 주문은 앞 주문을 처리하면 나타납니다.` : '';
    byId('history-title').textContent = `전체 주문 내역 ${data.history.total}건`;
    DOM.render(byId('history-orders'), data.history.orders.length ? data.history.orders.map(row) : el('tr', {}, [el('td', {attrs: {colspan: '6'}, text: '이 페이지에 주문이 없습니다.'})]));
    const history = data.history, links = [];
    if (history.has_previous) links.push(el('a', {class: 'ui-button', text: '이전', attrs: {href: `?page=${Math.min(history.page - 1, history.pages)}#history`}}));
    links.push(el('span', {class: 'ui-muted', text: `${history.page} / ${Math.max(1, history.pages)} 페이지 · 페이지당 50건`}));
    if (history.has_next) links.push(el('a', {class: 'ui-button', text: '다음', attrs: {href: `?page=${history.page + 1}#history`}}));
    DOM.render(byId('history-pagination'), links);
    fresh = true;
    if (detail.open && draft) {
      const latest = orders.get(draft.original.id);
      if (draft.conflicts(latest)) {
        if (hasEdits() || busy || confirmation.open || !latest) conflict = true;
        else { draft = model.editor(latest); conflict = false; renderDetail(); }
      }
    }
    if (confirmation.open && pending && pending.editor.conflicts(orders.get(pending.editor.original.id))) {
      pending.stale = true;
      byId('confirm-error').textContent = '주문이 변경되었습니다. 돌아간 뒤 최신 내용을 확인해 주세요.';
    }
    updateControls();
    if (restore) {
      const container = byId(restore.region);
      (container.querySelector(`[data-order-id="${restore.id}"][data-action="${restore.action}"]`) || byId('reload-orders')).focus({preventScroll: true});
    }
  }
  function onLiveStatus(state) {
    latestState = state;
    if (state.lastError || !state.running) {
      fresh = false;
      blockedRead = state.applied.at;
    } else if (state.applied.at && state.applied.at !== blockedRead) {
      // The scheduler keeps the same Date object through heartbeats/resume;
      // only a successful read (including unchanged) supplies a new one.
      fresh = true;
    }
    const last = clock(state.applied.at);
    let text = !state.running ? '탭이 보이지 않아 갱신을 멈췄습니다' : state.lastError ? `읽기 실패 · ${last} 목록 유지 · 5초마다 다시 읽음` : !state.polling ? '실시간 연결' : state.stream !== 'open' ? '연결 중 · 5초마다 다시 읽음' : !state.hubOk ? '서버 감지 지연 · 5초마다 다시 읽음' : '5초마다 다시 읽음';
    if (state.ended) text = '로그인 화면으로 이동합니다';
    byId('live-status').textContent = text + ' · 목록 읽은 시각 ' + last;
    byId('reload-orders').disabled = state.inFlight || busy;
    byId('reload-orders').textContent = state.inFlight ? '읽는 중…' : '새로고침';
    updateControls();
  }
  const live = window.BazaarLive.create({window, document, EventSource: window.EventSource,
    fetch: window.BazaarAuth.fetch, streamUrl: page.dataset.streamUrl, snapshotUrl: page.dataset.snapshotUrl,
    onApply: drawSnapshot, onStatus: onLiveStatus, onAuthLost: () => window.location.assign(page.dataset.loginUrl)});

  function renderDetail() {
    const order = draft.original;
    byId('detail-title').textContent = tableName(order);
    byId('detail-meta').textContent = `${order.is_practice ? '연습 · ' : ''}${number(order)} · ${model.kind(order)} · ${clock(order.created_at)} 접수`;
    byId('detail-status').textContent = model.label(order) + (order.departed_at ? ` · 출발 기록 ${clock(order.departed_at)}` : '');
    byId('detail-note').textContent = order.note || '';
    DOM.render(byId('detail-items'), draft.items().map(item => {
      const id = 'prepared-' + item.id;
      return el('section', {class: 'detail-item'}, [
        el('h3', {text: `${modeName(item)} · ${item.menu_item_name} · 주문 ${item.qty}개`}),
        el('div', {class: 'prepared-control'}, [el('label', {text: '준비 수량', attrs: {for: id}}),
          el('button', {class: 'ui-button', text: '−', attrs: {type: 'button', 'aria-label': item.menu_item_name + ' 준비 수량 줄이기'}, data: {step: '-1', 'item-id': item.id}}),
          el('input', {attrs: {id, type: 'text', inputmode: 'numeric', maxlength: '2', value: String(item.prepared_qty), 'aria-label': `${modeName(item)} ${item.menu_item_name} 준비 수량`, 'aria-describedby': 'remaining-' + item.id}, data: {'item-id': item.id}}),
          el('span', {text: '/ ' + item.qty}),
          el('button', {class: 'ui-button', text: '+', attrs: {type: 'button', 'aria-label': item.menu_item_name + ' 준비 수량 늘리기'}, data: {step: '1', 'item-id': item.id}})]),
        el('p', {class: 'ui-muted', text: `남은 ${item.qty - item.prepared_qty}개`, attrs: {id: 'remaining-' + item.id}}),
      ]);
    }));
    byId('detail-error').textContent = '';
    updateControls();
  }
  function updateControls() {
    page.querySelectorAll('[data-action]').forEach(control => { control.disabled = busy || !fresh; });
    if (draft) {
      const cancelled = draft.original.status === 'CANCELLED', ready = draft.original.status === 'READY';
      const disabled = busy || conflict || !fresh || cancelled;
      byId('detail-items').querySelectorAll('input,button').forEach(control => { control.disabled = disabled; });
      byId('save-progress').hidden = cancelled;
      byId('save-progress').disabled = disabled;
      byId('cancel-order').hidden = cancelled;
      byId('cancel-order').disabled = disabled;
      byId('depart-order').hidden = cancelled || ready;
      byId('depart-order').disabled = disabled;
      byId('reopen-order').hidden = cancelled || !ready;
      byId('reopen-order').disabled = disabled;
      byId('detail-reload').hidden = !conflict;
      byId('detail-reload').disabled = busy || !fresh || Boolean(latestState?.inFlight);
      byId('detail-conflict').textContent = conflict ? '주문이 변경되었습니다. 입력은 유지했습니다. 최신 내용을 다시 확인해 주세요.' : !fresh ? '최신 주문을 확인하는 동안 수정할 수 없습니다.' : '';
    }
    byId('detail-close').disabled = busy;
    byId('confirm-back').disabled = busy;
    byId('confirm-submit').disabled = busy || !fresh || Boolean(pending?.stale);
    confirmation.setAttribute('aria-busy', String(busy));
    detail.setAttribute('aria-busy', String(busy));
  }
  function openDetail(order, source) {
    draft = model.editor(order); conflict = false; inputDirty = false; opener = source;
    renderDetail(); detail.showModal(); byId('detail-close').focus();
  }
  function closeDetail(saved = false) {
    if (busy || (!saved && hasEdits() && !window.confirm('저장하지 않은 준비 수량이 있습니다. 닫을까요?'))) return;
    detail.close(); draft = null; conflict = false; inputDirty = false;
    (opener?.isConnected ? opener : byId('reload-orders')).focus({preventScroll: true});
  }
  function ask(action, editor, source) {
    if (busy || !fresh) return;
    if (action === 'reopen' && hasEdits()) {
      byId('detail-error').textContent = '수정 중인 준비 수량을 먼저 저장하거나, 닫고 다시 열어 주세요.';
      byId('detail-error').focus();
      return;
    }
    pending = {action, editor, source, stale: false};
    const order = editor.original;
    const words = {depart: ['완료 · 서빙 출발', '모든 음식이 준비되어 서빙을 출발하나요? 확인하면 모든 품목의 준비 수량을 주문 수량으로 맞추고 출발을 기록합니다.'],
      cancel: ['주문 전체 취소', '이 주문 전체를 취소하나요? 취소 후 되돌릴 수 없으며 매출 집계에서 제외됩니다.'],
      reopen: ['준비 중으로 되돌리기', '완료 상태를 준비 중으로 되돌리나요? 저장된 준비 수량은 유지되며 미완료 목록에 다시 표시됩니다.']};
    byId('confirm-title').textContent = words[action][0];
    byId('confirm-description').textContent = `${number(order)} · ${tableName(order)}\n${words[action][1]}`;
    byId('confirm-error').textContent = '';
    byId('confirm-submit').textContent = words[action][0];
    confirmation.showModal(); byId('confirm-back').focus(); updateControls();
  }
  function closeConfirm() {
    if (busy) return;
    const source = pending?.source; confirmation.close(); pending = null;
    (source?.isConnected ? source : detail.open ? byId('detail-close') : byId('reload-orders')).focus({preventScroll: true});
  }
  async function write(action, editor) {
    if (busy || !fresh || editor.conflicts(orders.get(editor.original.id))) return;
    const errorRegion = confirmation.open ? byId('confirm-error') : byId('detail-error');
    errorRegion.textContent = ''; busy = true; updateControls();
    let succeeded = false;
    try {
      const csrf = document.cookie.split('; ').find(part => part.startsWith('csrftoken='))?.split('=')[1] || '';
      const response = await window.BazaarAuth.fetch(page.dataset.actionUrl.replace('/0/', `/${editor.original.id}/`), {
        method: 'PATCH', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf}, body: JSON.stringify(editor.payload(action))});
      const text = await response.text(); let body = null;
      try { body = JSON.parse(text); } catch (_) { /* Error bodies can be plain text. */ }
      if (!response.ok) throw new Error(body?.detail || (response.status === 400 ? text.slice(0, 500) : '변경하지 못했습니다. 최신 주문을 확인해 주세요.'));
      if (body?.id !== editor.original.id) throw new Error('저장 결과를 확인하지 못했습니다. 최신 주문을 확인해 주세요.');
      succeeded = true;
      notice(`${number(editor.original)} ${action === 'progress' ? '준비 수량을 저장했습니다.' : action === 'depart' ? '서빙 출발을 기록했습니다.' : action === 'reopen' ? '준비 중으로 되돌렸습니다.' : '주문 전체를 취소했습니다.'}`);
    } catch (error) {
      errorRegion.textContent = error instanceof TypeError ? '연결이 끊겼습니다. 자동으로 다시 저장하지 않습니다. 최신 내용 확인 후 다시 시도해 주세요.' : error.message;
      errorRegion.focus();
      if (draft) conflict = true;
      if (pending) pending.stale = true;
    } finally {
      busy = false;
      if (succeeded) { closeConfirm(); if (detail.open) closeDetail(true); }
      updateControls();
      // All rendered order data, including after a refusal, comes from this scheduler.
      live.refetch('write');
    }
  }
  function captureInputs() {
    const inputs = [...byId('detail-items').querySelectorAll('input')];
    for (const input of inputs) draft.set(Number(input.dataset.itemId), input.value);
  }
  DOM.delegate(page, 'click', '[data-action]', (event, control) => {
    if (busy || !fresh) return;
    const order = orders.get(Number(control.dataset.orderId)); if (!order) return;
    if (control.dataset.action === 'detail') openDetail(order, control);
    else ask('depart', model.editor(order), control);
  });
  DOM.delegate(byId('detail-items'), 'input', 'input', (event, input) => {
    if (busy || conflict || !draft) return;
    inputDirty = true;
    try {
      const id = Number(input.dataset.itemId);
      draft.set(id, input.value);
      const item = draft.items().find(row => row.id === id);
      byId('remaining-' + id).textContent = `남은 ${item.qty - item.prepared_qty}개`;
      byId('detail-error').textContent = '';
    }
    catch (error) { byId('detail-error').textContent = error.message; }
  });
  DOM.delegate(byId('detail-items'), 'click', '[data-step]', (event, control) => {
    if (busy || conflict || !draft) return;
    const id = Number(control.dataset.itemId), input = byId('prepared-' + id);
    try {
      captureInputs(); draft.set(id, Number(input.value) + Number(control.dataset.step));
      renderDetail(); byId('detail-items').querySelector(`[data-item-id="${id}"][data-step="${control.dataset.step}"]`).focus();
    } catch (error) { byId('detail-error').textContent = error.message; }
  });
  byId('save-progress').addEventListener('click', () => {
    try { captureInputs(); write('progress', draft); }
    catch (error) { byId('detail-error').textContent = error.message; byId('detail-error').focus(); }
  });
  for (const [id, action] of [['depart-order', 'depart'], ['cancel-order', 'cancel'], ['reopen-order', 'reopen']]) {
    byId(id).addEventListener('click', event => { if (draft && !conflict) ask(action, draft, event.currentTarget); });
  }
  byId('detail-reload').addEventListener('click', () => {
    const latest = orders.get(draft?.original.id);
    if (hasEdits() && !window.confirm('입력 중인 수량을 버리고 최신 내용을 불러올까요?')) return;
    if (!latest) { closeDetail(true); notice('이 주문은 현재 목록에 없습니다. 전체 내역에서 다시 확인해 주세요.'); return; }
    draft = model.editor(latest); conflict = false; inputDirty = false; renderDetail(); byId('detail-close').focus();
  });
  byId('detail-close').addEventListener('click', () => closeDetail());
  detail.addEventListener('cancel', event => { event.preventDefault(); closeDetail(); });
  byId('confirm-back').addEventListener('click', closeConfirm);
  confirmation.addEventListener('cancel', event => { event.preventDefault(); closeConfirm(); });
  byId('confirm-submit').addEventListener('click', () => { if (pending && !pending.stale) write(pending.action, pending.editor); });
  byId('reload-orders').addEventListener('click', () => live.refetch('manual'));
  window.addEventListener('beforeunload', event => { if (busy || hasEdits()) { event.preventDefault(); event.returnValue = ''; } });
  live.start();
})();

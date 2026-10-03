(function () {
  'use strict';
  const page = document.getElementById('takeout-page');
  if (!page) return;
  const DOM = window.BazaarDom, el = DOM.el, model = window.BazaarTakeoutState.create();
  const byId = id => document.getElementById(id);
  let busy = false, fresh = false, authBlocked = false, uncertain = false;
  // Keep the original intent until its receipt is confirmed or definitively
  // refused. Incoming snapshots must never give an uncertain write a new key.
  let pendingPayload = null;
  let latestStatus = null, blockedAt = null, readBarrier = 0;
  let historyPage = Number(new URL(page.dataset.snapshotUrl, window.location.href).searchParams.get('page')) || 1;
  const offline = () => window.navigator?.onLine === false;
  const editable = () => fresh && !busy && !authBlocked && !offline() && !model.stale() && !pendingPayload;
  const retryable = () => Boolean(pendingPayload && uncertain && !busy && !authBlocked && !offline() && latestStatus?.running);
  const notice = text => { byId('takeout-notice').textContent = text; };
  const dateTime = value => {
    const date = new Date(value);
    return value && !Number.isNaN(date.getTime()) ? date.toLocaleString('ko-KR', {
      timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hour12: false,
    }) : '접수 일시 미확인';
  };
  function blockOldReads() {
    // A response begun before this boundary cannot unlock recovery, even if
    // it arrives after a write. The shared scheduler queues the next read.
    readBarrier += 1;
    fresh = false;
    blockedAt = latestStatus?.applied.at || null;
  }
  async function snapshotFetch(url, options) {
    const barrier = readBarrier, target = new URL(url, window.location.href);
    target.searchParams.set('page', String(historyPage));
    if (model.snapshot()?.history.page !== historyPage) target.searchParams.delete('since');
    const response = await window.BazaarAuth.fetch(target.href, options);
    return {ok: response.ok, status: response.status, json: async () => {
      const data = await response.json();
      if (barrier !== readBarrier) throw new Error('완료 요청 이후의 최신 내역을 다시 확인합니다.');
      return data;
    }};
  }
  function renderMenus() {
    const active = document.activeElement;
    const restore = active?.dataset?.menuKey ? {key: active.dataset.menuKey, step: active.dataset.step} : null;
    const rows = model.rows();
    DOM.render(byId('takeout-menus'), rows.length ? rows.map((menu, index) => {
      const nameId = 'takeout-menu-name-' + index, quantityId = 'takeout-menu-selected-' + index;
      const step = (amount, text) => el('button', {class: 'ui-button', text,
        attrs: {type: 'button', 'aria-label': `${menu.name} 이번 완료 수량 ${amount < 0 ? '줄이기' : '늘리기'}`, 'aria-controls': quantityId},
        data: {'menu-key': menu.key, step: amount}});
      const nameParts = [el('span', {text: menu.name})];
      if (menu.is_custom) nameParts.push(el('span', {class: 'takeout-custom', text: '기타 메뉴'}));
      const name = el('h3', {attrs: {id: nameId}}, nameParts);
      const children = [
        el('div', {class: 'takeout-tile' + (menu.quantity ? ' is-selected' : '') + (menu.quantity > menu.remaining_qty ? ' is-invalid' : '')}, [
          name, el('p', {class: 'takeout-quantity' + (menu.remaining_qty ? '' : ' is-zero'), text: menu.remaining_qty}),
          el('p', {class: 'takeout-caption', text: menu.missing ? '현재 대기 목록에 없는 메뉴' : menu.remaining_qty ? '남은 수량' : '대기 없음'}),
        ]),
        el('div', {class: 'takeout-stepper', attrs: {role: 'group', 'aria-labelledby': nameId}}, [
          el('span', {class: 'takeout-step-label', text: '이번 완료'}), step(-1, '−'),
          el('output', {class: 'takeout-selected', text: menu.quantity,
            attrs: {id: quantityId, tabindex: '-1', 'aria-label': `${menu.name} 이번 완료 수량`}, data: {'menu-key': menu.key}}),
          step(1, '+'),
        ]),
      ];
      if (menu.quantity > menu.remaining_qty) children.push(el('p', {class: 'takeout-menu-error',
        text: `선택 ${menu.quantity}개 · 남은 ${menu.remaining_qty}개. ` + (uncertain ? '먼저 완료 요청의 결과를 확인해 주세요.' : '확인 후 수량을 줄여 주세요.')}));
      return el('article', {class: 'takeout-menu', attrs: {'aria-labelledby': nameId}}, children);
    }) : el('p', {class: 'takeout-empty', text: '남은 포장 메뉴가 없습니다. 새 주문이 들어오면 여기에 표시됩니다.'}));
    byId('takeout-menus').setAttribute('aria-busy', 'false');
    renderSelection();
    if (restore) {
      const controls = [...byId('takeout-menus').querySelectorAll('[data-menu-key]')];
      const same = controls.find(node => node.dataset.menuKey === restore.key && node.dataset.step === restore.step);
      const output = controls.find(node => node.dataset.menuKey === restore.key && node.dataset.step === undefined);
      (same && !same.disabled ? same : output || byId('takeout-selection-title')).focus({preventScroll: true});
    }
  }
  function renderSelection() {
    byId('takeout-selected-total').textContent = `${model.total()}개`;
    byId('takeout-selection-summary').textContent = model.rows().filter(row => row.quantity)
      .map(row => `${row.name} ${row.quantity}개`).join(' · ') || '완료할 수량을 선택해 주세요.';
    updateControls();
  }
  function renderHistory(history) {
    const focusDirection = document.activeElement?.dataset?.historyDirection;
    byId('takeout-history-title').textContent = `전체 주문 내역 ${history.total}건`;
    DOM.render(byId('takeout-history'), history.orders.length ? history.orders.map(order => {
      const reference = [el('strong', {text: '#' + String(order.order_no ?? order.id).padStart(3, '0')}),
        el('time', {class: 'takeout-history-time', text: dateTime(order.created_at), attrs: {datetime: order.created_at}})];
      if (order.is_practice) reference.unshift(el('span', {class: 'takeout-practice', text: '연습'}));
      return el('tr', {}, [el('td', {}, reference),
        el('td', {}, [el('ul', {class: 'takeout-history-items'}, order.items.map(item => el('li', {
          text: `${item.is_custom ? '기타 · ' : ''}${item.menu_item_name} ${item.qty}개`,
        })))]), el('td', {text: `${order.total_qty}개`})]);
    }) : el('tr', {}, [el('td', {attrs: {colspan: '3'}, text: '이 페이지에 주문 내역이 없습니다.'})]));
    const links = [];
    const link = (text, number, direction) => el('button', {class: 'ui-button', text,
      attrs: {type: 'button'}, data: {'history-page': number, 'history-direction': direction}});
    if (history.has_previous) links.push(link('이전', Math.max(1, Math.min(history.page - 1, history.pages)), 'previous'));
    links.push(el('span', {text: `${history.page} / ${Math.max(1, history.pages)} 페이지`, attrs: {id: 'takeout-page-number', tabindex: '-1'}}));
    if (history.has_next) links.push(link('다음', history.page + 1, 'next'));
    DOM.render(byId('takeout-pagination'), links);
    updateControls();
    if (focusDirection) {
      const next = [...byId('takeout-pagination').querySelectorAll('[data-history-direction]')]
        .find(node => node.dataset.historyDirection === focusDirection);
      (next && !next.disabled ? next : byId('takeout-page-number')).focus({preventScroll: true});
    }
  }
  function drawSnapshot(data) {
    if (data.unchanged) return;
    model.apply(data);
    byId('takeout-remaining-total').textContent = `총 ${data.remaining_total}개`;
    byId('takeout-menu-count').textContent = `메뉴 ${data.menus.length}종`;
    renderMenus(); renderHistory(data.history);
  }
  function updateControls() {
    const rows = new Map(model.rows().map(row => [row.key, row]));
    byId('takeout-menus').querySelectorAll('[data-step]').forEach(button => {
      const row = rows.get(button.dataset.menuKey), step = Number(button.dataset.step);
      button.disabled = !editable() || (step < 0 ? !row.quantity : row.quantity >= row.remaining_qty);
    });
    byId('takeout-submit').disabled = !editable() || !model.total() || model.invalid();
    byId('takeout-submit').textContent = busy ? '완료 처리 중…' : model.total() ? `선택한 ${model.total()}개 완료` : '선택한 수량 완료';
    byId('takeout-completion').setAttribute('aria-busy', String(busy));
    byId('takeout-review-panel').hidden = !model.stale() && !uncertain;
    byId('takeout-review').hidden = uncertain;
    byId('takeout-review').disabled = Boolean(pendingPayload) || !fresh || busy || offline() || authBlocked || Boolean(latestStatus?.inFlight);
    byId('takeout-retry').hidden = !uncertain;
    byId('takeout-retry').disabled = !retryable();
    byId('takeout-retry').textContent = busy ? '완료 결과 확인 중…' : '완료 결과 다시 확인';
    byId('takeout-review-message').textContent = uncertain
      ? '완료 요청의 결과를 확인하지 못했습니다. 아래 버튼으로 같은 요청의 결과를 다시 확인해 주세요. 이미 처리되었다면 수량을 다시 차감하지 않습니다. 결과를 확인할 때까지 수량 변경과 새 완료 요청은 잠깐 멈춥니다.'
      : '남은 수량 또는 주문 정보가 변경되었거나 요청이 거절되었습니다. 선택한 수량은 유지했습니다. 최신 내역과 남은 수량을 확인해 주세요.';
    byId('takeout-reload').disabled = busy || offline() || authBlocked || Boolean(latestStatus?.inFlight);
    byId('takeout-reload').textContent = latestStatus?.inFlight ? '읽는 중…' : '새로고침';
    byId('takeout-pagination').querySelectorAll('button').forEach(button => {
      button.disabled = busy || offline() || authBlocked || Boolean(latestStatus?.inFlight);
    });
  }
  function onLiveStatus(status) {
    latestStatus = status;
    if (status.lastError || !status.running || offline()) {
      fresh = false; blockedAt = status.applied.at;
      if (model.total()) model.invalidate();
    } else if (status.applied.at && status.applied.at !== blockedAt && model.snapshot()) fresh = true;
    const text = status.ended ? '로그인 화면으로 이동합니다' : offline() ? '오프라인 · 연결 후 최신 내용을 확인해 주세요'
      : !status.running ? '탭이 보이지 않아 갱신을 멈췄습니다'
      : status.lastError ? '읽기 실패 · 이전 수량 유지 · 5초마다 다시 읽음'
      : !status.polling ? '실시간 연결' : '연결 확인 중 · 5초마다 다시 읽음';
    byId('takeout-live').textContent = text + (status.applied.at ? ` · 마지막 확인 ${dateTime(status.applied.at)}` : '');
    updateControls();
  }
  function authLost() {
    authBlocked = true; fresh = false; updateControls();
    window.location.assign(page.dataset.loginUrl);
  }
  const live = window.BazaarLive.create({window, document, EventSource: window.EventSource,
    fetch: snapshotFetch, snapshotUrl: page.dataset.snapshotUrl, streamUrl: page.dataset.streamUrl,
    onApply: drawSnapshot, onStatus: onLiveStatus, onAuthLost: authLost});

  async function complete() {
    if (!editable() || model.invalid() || !model.total()) return;
    const payload = model.payload();
    pendingPayload = Object.freeze({...payload, request_id: window.BazaarRequestId.create(),
      items: Object.freeze(payload.items.map(item => Object.freeze(item)))});
    return sendPending();
  }
  async function sendPending() {
    const payload = pendingPayload, wasRetry = uncertain;
    const expectedQuantity = payload.items.reduce((sum, item) => sum + item.quantity, 0);
    busy = true; blockOldReads(); notice(''); byId('takeout-error').textContent = ''; updateControls();
    let confirmed = false, refused = false;
    try {
      const csrf = document.cookie.split('; ').find(part => part.startsWith('csrftoken='))?.split('=')[1] || '';
      const response = await window.BazaarAuth.fetch(page.dataset.completeUrl, {
        method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
        body: JSON.stringify(payload),
      });
      refused = [400, 401, 403, 409].includes(response.status);
      if (response.status === 401 || response.status === 403) {
        authBlocked = true;
        throw new Error('로그인 또는 포장 모니터링 권한을 확인해 주세요. 선택한 수량은 유지했습니다.');
      }
      const text = await response.text(); let body = null;
      try { body = JSON.parse(text); } catch (_) { /* A refusal can have a plain text body. */ }
      if (!response.ok) throw new Error(refused
        ? (typeof body?.detail === 'string' ? body.detail : response.status === 400 ? text.slice(0, 500) : '남은 수량이 변경되었습니다. 최신 내용을 확인해 주세요.')
        : '서버에서 완료 결과를 확인하지 못했습니다. 완료 결과 다시 확인을 눌러 주세요.');
      if (body?.completed_qty !== expectedQuantity || !Array.isArray(body.completed_orders)
          || body.completed_orders.some(id => !Number.isSafeInteger(id) || id <= 0)) {
        throw new Error('완료 결과를 확인하지 못했습니다. 완료 결과 다시 확인을 눌러 주세요.');
      }
      confirmed = true; uncertain = false; pendingPayload = null; model.succeeded();
      notice(`${expectedQuantity}개 완료를 반영했습니다.`);
    } catch (error) {
      // A received 400/409 is a definitive refusal even if its body was lost.
      // 401/403 preserve the attempt but block every action for authentication.
      if (refused && !authBlocked) pendingPayload = null;
      uncertain = !refused;
      model.invalidate();
      byId('takeout-error').textContent = error instanceof TypeError
        ? '연결이 끊겨 완료 결과를 확인하지 못했습니다. 자동으로 다시 요청하지 않습니다.' : error.message;
      if (error.name === 'AuthenticationLost') authBlocked = true;
    } finally {
      busy = false; blockOldReads(); renderMenus(); updateControls();
      if (!confirmed) byId('takeout-error').focus({preventScroll: true});
      else if (wasRetry) byId('takeout-selection-title').focus({preventScroll: true});
      // A successful or refused write uses exactly the same read scheduler.
      if (!authBlocked) live.refetch('write');
    }
  }
  DOM.delegate(byId('takeout-menus'), 'click', '[data-step]', (event, button) => {
    if (!editable() || button.disabled) return;
    const row = model.rows().find(menu => menu.key === button.dataset.menuKey);
    model.set(row.key, row.quantity + Number(button.dataset.step));
    notice(''); renderMenus();
  });
  byId('takeout-submit').addEventListener('click', complete);
  byId('takeout-retry').addEventListener('click', () => {
    if (retryable()) return sendPending();
  });
  byId('takeout-review').addEventListener('click', () => {
    if (pendingPayload || byId('takeout-review').disabled || !model.stale()) return;
    model.review(); uncertain = false; byId('takeout-error').textContent = '';
    notice(model.invalid() ? '선택 수량이 남은 수량보다 많습니다. 수량을 줄인 뒤 완료해 주세요.' : '최신 내용을 확인했습니다. 선택한 수량을 검토한 뒤 완료해 주세요.');
    renderMenus();
    const correction = model.rows().find(row => row.quantity > row.remaining_qty);
    const control = correction && [...byId('takeout-menus').querySelectorAll('[data-step]')]
      .find(node => node.dataset.menuKey === correction.key && node.dataset.step === '-1');
    (control || byId('takeout-selection-title')).focus({preventScroll: true});
  });
  byId('takeout-reload').addEventListener('click', () => {
    if (!byId('takeout-reload').disabled) live.refetch('manual');
  });
  DOM.delegate(byId('takeout-pagination'), 'click', '[data-history-page]', (event, button) => {
    if (button.disabled) return;
    historyPage = Number(button.dataset.historyPage); blockOldReads(); updateControls(); live.refetch('history');
  });
  window.addEventListener('offline', () => {
    blockOldReads(); if (model.total()) model.invalidate();
    if (latestStatus) onLiveStatus(latestStatus); else updateControls();
  });
  window.addEventListener('online', () => { blockOldReads(); updateControls(); live.refetch('online'); });
  window.addEventListener('beforeunload', event => {
    if (busy || pendingPayload || model.total()) { event.preventDefault(); event.returnValue = ''; }
  });
  live.start();
})();

(function () {
  'use strict';
  const page = document.getElementById('order-page');
  if (!page) return;
  const DOM = window.BazaarDom;
  const state = window.BazaarOrderState;
  const order = state.createOrder(() => window.BazaarRequestId.create());
  const byId = id => document.getElementById(id);
  const dialog = byId('checkout');
  const menus = new Map();
  const labels = {DINE_IN: '홀', TAKEOUT: '포장'};
  const won = n => n.toLocaleString('ko-KR') + '원';
  const payInputs = ['cash-in', 'cash-mixed', 'ticket-mixed'];
  let mode = 'DINE_IN';
  let saving = false;
  let loading = false;
  const value = id => byId(id).value;
  const method = () => document.querySelector('input[name="pay"]:checked').value;
  function settlement() { return state.payment(method(), ...payInputs.map(value), order.total()); }
  function notice(text) { byId('order-notice').textContent = text; }
  function fail(text) { byId('save-error').textContent = text; byId('save-error').focus(); }
  function hasDraft() { return order.items().length > 0 || ['table-number', ...payInputs].some(id => value(id).trim()); }
  function canLeave() {
    if (saving) return false;
    return !hasDraft() || window.confirm('저장하지 않은 주문이 있습니다. 나가면 입력 내용이 사라집니다. 이동할까요?');
  }
  window.BazaarOrder = Object.freeze({canLeave});
  window.addEventListener('beforeunload', event => {
    if (hasDraft() || saving) { event.preventDefault(); event.returnValue = ''; }
  });

  function button(text, action, data, label, extraClass = '') {
    return DOM.el('button', {class: 'ui-button ' + extraClass, text,
      attrs: {type: 'button', 'aria-label': label || text}, data: {action, ...data}});
  }
  function renderMenus() {
    const rows = [...menus.values()].map(menu => {
      const qty = order.selection(mode, menu.id);
      const data = {id: menu.id};
      const minus = button('−', 'select-dec', data, menu.name + ' 담을 수량 줄이기', 'step');
      const plus = button('+', 'select-inc', data, menu.name + ' 담을 수량 늘리기', 'step');
      minus.disabled = qty <= 1; plus.disabled = qty >= 99;
      return DOM.el('article', {class: 'menu-tile', data}, [
        DOM.el('div', {class: 'menu-heading'}, [DOM.el('h2', {class: 'menu-name', text: menu.name}), DOM.el('span', {class: 'menu-price', text: won(menu.price)})]),
        DOM.el('div', {class: 'quantity-controls'}, [minus, DOM.el('output', {text: qty, attrs: {'aria-label': menu.name + ' 담을 수량'}}), plus,
          DOM.el('span', {class: 'ui-muted', text: '개'}), button('담기', 'add', data, menu.name + ' 담기', 'add')]),
      ]);
    });
    DOM.render(byId('menu-grid'), rows.length ? rows : DOM.el('p', {class: 'ui-muted', text: '등록된 메뉴가 없습니다. 관리자에게 문의해 주세요.'}));
  }
  function restoreFocus(container, selector) { container.querySelector(selector)?.focus({preventScroll: true}); }
  function renderCart() {
    DOM.render(byId('cart-items'), order.items().map(row => {
      const data = {id: row.id, mode: row.mode};
      const itemLabel = labels[row.mode] + ' ' + row.name;
      return DOM.el('article', {class: 'order-item', data}, [
        DOM.el('div', {class: 'cart-heading'}, [DOM.el('strong', {text: labels[row.mode] + ' · ' + row.name}), DOM.el('span', {text: won(row.price * row.qty)})]),
        DOM.el('div', {class: 'quantity-controls'}, [button('−', 'dec', data, itemLabel + ' 수량 줄이기', 'step'), DOM.el('output', {text: row.qty, attrs: {'aria-label': itemLabel + ' 주문 수량'}}),
          button('+', 'inc', data, itemLabel + ' 수량 늘리기', 'step'), DOM.el('span', {class: 'ui-muted', text: '개'}), button('삭제', 'remove', data, itemLabel + ' 삭제', 'remove')]),
      ]);
    }));
    if (!order.items().length) DOM.render(byId('cart-items'), DOM.el('p', {class: 'checkout-empty', text: '담은 메뉴가 없습니다. 돌아가서 메뉴를 담아 주세요.'}));
    updateSummary();
  }
  function updateSummary() {
    const counts = order.counts();
    document.querySelectorAll('.menu-tab').forEach(tab => {
      tab.textContent = labels[tab.dataset.mode] + ' ' + counts[tab.dataset.mode] + '개';
      tab.setAttribute('aria-pressed', String(tab.dataset.mode === mode));
    });
    byId('cart-title').textContent = '담은 메뉴 · ' + (counts.DINE_IN + counts.TAKEOUT) + '개';
    byId('order-summary').textContent = `홀 ${counts.DINE_IN}개 · 포장 ${counts.TAKEOUT}개 / 총 ${won(order.total())}`;
    byId('btn-checkout').disabled = saving || !order.items().length;
    byId('table-help').textContent = counts.DINE_IN ? '홀·혼합 주문은 식당 테이블 번호를 입력하세요.' : '포장만 주문할 때는 101–120번';
    updatePayment();
  }
  function updatePayment() {
    const mixed = method() === 'CASH_TICKET';
    byId('single-amount-row').hidden = mixed;
    byId('mixed-amount-row').hidden = !mixed;
    byId('single-amount-label').textContent = method() === 'TICKET' ? '받은 식권 금액' : '받은 현금';
    const payment = settlement();
    byId('total-amount').textContent = won(order.total());
    byId('change-amount').textContent = won(payment.change);
    byId('payment-error').textContent = payment.error;
    byId('btn-submit').textContent = saving ? '주문 저장 중…' : won(order.total()) + ' · 주문 저장';
    byId('btn-submit').disabled = saving || !order.items().length || Boolean(payment.error);
  }
  function closeCheckout() {
    if (saving) return;
    dialog.close();
    if (order.items().length) byId('btn-checkout').focus();
    else document.querySelector('.menu-tab[aria-pressed="true"]').focus();
  }
  function reset() {
    order.reset();
    ['table-number', ...payInputs].forEach(id => { byId(id).value = ''; });
    document.querySelector('input[name="pay"][value="CASH"]').checked = true;
    mode = 'DINE_IN'; byId('mode-hint').textContent = '홀 · 수량을 선택한 뒤 담아 주세요';
    renderMenus(); renderCart();
  }
  function setBusy(busy) {
    saving = busy;
    // Saving uses a fixed payload. Do not let controls change that payload in flight.
    document.querySelectorAll('.serving-page button, .checkout button, .checkout input').forEach(control => { control.disabled = busy; });
    dialog.setAttribute('aria-busy', String(busy));
    if (!busy) { renderMenus(); updateSummary(); }
    else updatePayment();
  }
  async function submit() {
    if (saving) return;
    const items = order.items();
    if (!items.length) return fail('메뉴를 담아 주세요.');
    const table = value('table-number').trim();
    if (!/^[0-9]+$/.test(table) || Number(table) < 1) return fail('테이블 번호를 입력해 주세요.');
    const hasHall = items.some(row => row.mode === 'DINE_IN');
    if (!hasHall && (Number(table) < 101 || Number(table) > 120)) return fail('포장 주문 번호는 101~120번으로 입력해 주세요.');
    const payment = settlement();
    if (payment.error) return fail(payment.error);
    const payload = {floor: 'B1', order_type: hasHall ? 'DINE_IN' : 'TAKEOUT', is_takeout: !hasHall,
      payment_method: method(), received_amount: payment.received,
      received_cash_amount: payment.cash, received_ticket_amount: payment.ticket,
      table_number: table, note: '', items: items.map(row => ({menu_item_id: row.id, qty: row.qty, mode: row.mode}))};
    const requestId = order.attempt(payload);
    setBusy(true); byId('save-error').textContent = '';
    try {
      const csrf = document.cookie.split('; ').find(part => part.startsWith('csrftoken='))?.split('=')[1] || '';
      const response = await window.BazaarAuth.fetch(page.dataset.orderUrl, {method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf}, body: JSON.stringify({...payload, request_id: requestId})});
      const responseText = await response.text();
      let data = null;
      try { data = JSON.parse(responseText); } catch (_) { /* Plain-text validation errors are part of the existing API. */ }
      if (!response.ok) {
        // Django's HttpResponseBadRequest uses text/html even for these text bodies.
        // fail() renders through textContent, so returned text never becomes markup.
        const validation = response.status === 400 ? responseText.slice(0, 500) : '';
        throw new Error(data?.detail || validation || '주문을 저장하지 못했습니다. 입력을 확인하고 다시 시도해 주세요.');
      }
      if (!data?.id) throw new Error('저장 결과를 확인하지 못했습니다. 입력은 유지됩니다. 같은 내용으로 다시 저장해 주세요.');
      reset();
      // Clearing the saved draft is deliberately after the successful response.
      setBusy(false); closeCheckout(); notice('주문이 접수되었습니다. 다음 주문을 담아 주세요.');
    } catch (error) {
      fail(error instanceof TypeError ? '연결이 끊겼습니다. 입력은 유지됩니다. 같은 내용으로 다시 저장해 주세요.' : error.message);
    } finally { setBusy(false); }
  }

  async function loadMenus() {
    if (loading) return;
    loading = true; byId('menu-grid').setAttribute('aria-busy', 'true');
    try {
      const response = await window.BazaarAuth.fetch(page.dataset.menuUrl + '?scope=KITCHEN', {credentials: 'same-origin'});
      if (!response.ok) throw new Error('메뉴를 불러오지 못했습니다.');
      const data = await response.json();
      menus.clear();
      (data.items || []).forEach(menu => menus.set(String(menu.id), menu));
      renderMenus();
    } catch (error) {
      DOM.render(byId('menu-grid'), [DOM.el('p', {class: 'ui-error', text: '메뉴를 불러오지 못했습니다. 연결을 확인해 주세요.'}), button('다시 불러오기', 'retry', {})]);
    } finally { loading = false; byId('menu-grid').setAttribute('aria-busy', 'false'); }
  }
  DOM.delegate(byId('menu-grid'), 'click', '[data-action]', (event, target) => {
    if (saving) return;
    if (target.dataset.action === 'retry') { loadMenus(); return; }
    const menu = menus.get(target.dataset.id);
    if (!menu) return;
    try {
      if (target.dataset.action === 'add') {
        const qty = order.selection(mode, menu.id); order.add(mode, menu);
        notice(`${labels[mode]} · ${menu.name} ${qty}개를 담았습니다.`); renderCart();
      } else order.select(mode, menu.id, order.selection(mode, menu.id) + (target.dataset.action === 'select-inc' ? 1 : -1));
      renderMenus();
      restoreFocus(byId('menu-grid'), `[data-id="${menu.id}"][data-action="${target.dataset.action}"]`);
    } catch (error) { notice(error.message); }
  });
  DOM.delegate(byId('cart-items'), 'click', '[data-action]', (event, target) => {
    if (saving) return;
    const {mode: itemMode, id, action} = target.dataset;
    try {
      if (action === 'remove') order.remove(itemMode, id); else order.change(itemMode, id, action === 'inc' ? 1 : -1);
      renderCart();
      const next = byId('cart-items').querySelector(`[data-action="${action}"][data-mode="${itemMode}"][data-id="${id}"]`);
      (next || byId('cart-items').querySelector('button') || byId('btn-back')).focus({preventScroll: true});
    } catch (error) { fail(error.message); }
  });
  DOM.delegate(byId('menu-tabs'), 'click', '[data-mode]', (event, tab) => {
    if (saving) return;
    mode = tab.dataset.mode;
    byId('mode-hint').textContent = labels[mode] + ' · 수량을 선택한 뒤 담아 주세요';
    renderMenus(); updateSummary();
  });
  byId('btn-checkout').addEventListener('click', () => {
    byId('save-error').textContent = ''; renderCart(); dialog.showModal(); byId('table-number').focus();
  });
  byId('btn-back').addEventListener('click', closeCheckout);
  dialog.addEventListener('cancel', event => { event.preventDefault(); closeCheckout(); });
  byId('btn-submit').addEventListener('click', submit);
  byId('btn-reset').addEventListener('click', () => {
    if (!saving && window.confirm('담은 메뉴와 결제 입력을 모두 비울까요?')) { reset(); closeCheckout(); notice('주문을 비웠습니다.'); }
  });
  payInputs.forEach(id => byId(id).addEventListener('input', () => {
    // Preserve the existing cash+ticket shorthand without silently rounding.
    const pair = value('cash-in').split('+');
    const shorthand = id === 'cash-in' && pair.length === 2 && pair.every(part => part.trim() && Number.isFinite(state.amount(part)));
    if (shorthand) {
      byId('cash-mixed').value = String(state.amount(pair[0])); byId('ticket-mixed').value = String(state.amount(pair[1]));
      byId('cash-in').value = ''; document.querySelector('input[name="pay"][value="CASH_TICKET"]').checked = true;
    }
    byId('save-error').textContent = ''; updatePayment();
    if (shorthand) {
      const ticket = byId('ticket-mixed'); ticket.focus();
      ticket.setSelectionRange(ticket.value.length, ticket.value.length);
    }
  }));
  document.querySelectorAll('input[name="pay"]').forEach(input => input.addEventListener('change', updatePayment));
  renderCart(); loadMenus();
})();

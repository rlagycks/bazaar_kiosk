/* UI estimates only. The server remains authoritative for price and payment. */
(function (root) {
  'use strict';
  const MAX_QTY = 99;
  const MAX_AMOUNT = 10000000;
  const key = (mode, id) => mode + ':' + id;
  const won = value => value.toLocaleString('ko-KR');

  function amount(value) {
    const raw = String(value ?? '').trim().replace(/,/g, '');
    if (!raw) return 0;
    if (!/^[0-9]{1,12}$/.test(raw)) return NaN;
    const number = Number(raw);
    return Number.isSafeInteger(number) && number <= MAX_AMOUNT ? number : NaN;
  }

  function payment(method, single, mixedCash, mixedTicket, total) {
    const cash = method === 'TICKET' ? 0 : amount(method === 'CASH_TICKET' ? mixedCash : single);
    const ticket = method === 'CASH' ? 0 : amount(method === 'CASH_TICKET' ? mixedTicket : single);
    let error = '';
    if (!Number.isFinite(cash) || !Number.isFinite(ticket)) error = '금액은 0~10,000,000원의 정수로 입력하세요.';
    else if (total > MAX_AMOUNT) error = '주문 합계가 너무 큽니다.';
    else if (method === 'CASH_TICKET' && (!cash || !ticket)) error = '현금과 식권 금액을 모두 입력해 주세요.';
    else if (cash + ticket < total) error = won(total - cash - ticket) + '원이 부족합니다.';
    return {cash, ticket, received: cash + ticket, error,
      change: error ? 0 : Math.max(0, cash - Math.max(0, total - ticket))};
  }

  function createOrder(makeId) {
    const cart = new Map();
    const selected = new Map();
    let attemptKey = null;
    let fingerprint = null;
    function select(mode, id, qty) {
      if (!Number.isInteger(qty) || qty < 1 || qty > MAX_QTY) throw new Error('수량은 1~99개로 선택해 주세요.');
      selected.set(key(mode, id), qty);
    }
    function selection(mode, id) { return selected.get(key(mode, id)) || 1; }
    function add(mode, menu) {
      const k = key(mode, menu.id);
      const qty = (cart.get(k)?.qty || 0) + selection(mode, menu.id);
      if (qty > MAX_QTY) throw new Error('같은 메뉴는 홀·포장 각각 99개까지 담을 수 있습니다.');
      cart.set(k, {...menu, mode, qty});
      selected.set(k, 1);
    }
    function change(mode, id, delta) {
      const k = key(mode, id);
      const row = cart.get(k);
      if (!row) return;
      const qty = row.qty + delta;
      if (qty > MAX_QTY) throw new Error('수량은 99개 이하여야 합니다.');
      if (qty <= 0) cart.delete(k); else cart.set(k, {...row, qty});
    }
    function items() { return Array.from(cart.values(), row => ({...row})); }
    function counts() {
      const counts = {DINE_IN: 0, TAKEOUT: 0};
      cart.forEach(row => { counts[row.mode] += row.qty; });
      return counts;
    }
    function total() { return items().reduce((sum, row) => sum + row.price * row.qty, 0); }
    function attempt(payload) {
      const next = JSON.stringify(payload);
      if (!attemptKey || fingerprint !== next) {
        attemptKey = makeId();
        fingerprint = next;
      }
      return attemptKey;
    }
    function reset() { cart.clear(); selected.clear(); attemptKey = fingerprint = null; }
    return Object.freeze({select, selection, add, change, items, counts, total, attempt, reset,
      remove: (mode, id) => cart.delete(key(mode, id))});
  }
  const api = Object.freeze({createOrder, payment, amount});
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.BazaarOrderState = api;
})(typeof window === 'undefined' ? globalThis : window);

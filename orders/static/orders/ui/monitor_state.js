(function (root) {
  'use strict';
  function totals(order) {
    return order.items.reduce((sum, item) => ({qty: sum.qty + item.qty, prepared: sum.prepared + item.prepared_qty}), {qty: 0, prepared: 0});
  }
  function label(order) {
    if (order.status === 'CANCELLED') return '취소';
    if (order.status === 'READY') return order.departed_at ? '서빙 출발' : '기존 완료 · 출발 미확인';
    const sum = totals(order);
    return sum.qty > 0 && sum.prepared === sum.qty ? '준비 완료 · 출발 대기' : '준비 중';
  }
  function kind(order) { return order.items.some(item => item.service_mode === 'DINE_IN') ? '식당' : '포장'; }
  function editor(order) {
    const original = JSON.parse(JSON.stringify(order));
    const quantities = new Map(original.items.map(item => [item.id, item.prepared_qty]));
    function set(id, raw) {
      const item = original.items.find(row => row.id === id);
      if (!item || original.status === 'CANCELLED') throw new Error('수정할 수 없는 주문입니다.');
      if (!/^[0-9]+$/.test(String(raw))) throw new Error('준비 수량은 정수로 입력하세요.');
      const value = Number(raw);
      if (!Number.isSafeInteger(value) || value < 0 || value > item.qty) throw new Error(`준비 수량은 0~${item.qty}개로 입력하세요.`);
      quantities.set(id, value);
    }
    function items() { return original.items.map(item => ({...item, prepared_qty: quantities.get(item.id)})); }
    function dirty() { return original.items.some(item => quantities.get(item.id) !== item.prepared_qty); }
    function payload(action) {
      const result = {action, expected_version: original.monitor_version};
      if (action === 'progress') result.items = items().map(item => ({id: item.id, prepared_qty: item.prepared_qty}));
      return result;
    }
    return Object.freeze({original, set, items, dirty, payload,
      conflicts: latest => !latest || latest.monitor_version !== original.monitor_version});
  }
  const api = Object.freeze({totals, label, kind, editor});
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.BazaarMonitorState = api;
})(typeof window === 'undefined' ? globalThis : window);

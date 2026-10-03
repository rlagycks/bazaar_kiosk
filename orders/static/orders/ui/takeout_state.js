(function (root) {
  'use strict';
  // The completion token is opaque: equality is the only valid comparison.
  function create() {
    let snapshot = null, needsReview = false;
    const selected = new Map();
    function total() { return [...selected.values()].reduce((sum, row) => sum + row.quantity, 0); }
    function apply(data) {
      if (data.unchanged) return;
      if (data.complete !== true || typeof data.completion_version !== 'string' || !data.completion_version
          || !Array.isArray(data.menus) || !Array.isArray(data.history?.orders)
          || !Number.isSafeInteger(data.remaining_total) || data.remaining_total < 0) {
        throw new Error('포장 메뉴 정보를 확인하지 못했습니다. 다시 불러와 주세요.');
      }
      const keys = new Set();
      for (const menu of data.menus) {
        if (typeof menu.key !== 'string' || !menu.key || keys.has(menu.key)
            || typeof menu.name !== 'string' || !Number.isSafeInteger(menu.remaining_qty) || menu.remaining_qty < 0) {
          throw new Error('포장 메뉴 정보를 확인하지 못했습니다. 다시 불러와 주세요.');
        }
        keys.add(menu.key);
      }
      if (total() && snapshot && snapshot.completion_version !== data.completion_version) needsReview = true;
      snapshot = data;
    }
    function rows() {
      const menus = snapshot?.menus || [];
      return menus.map(menu => ({...menu, quantity: selected.get(menu.key)?.quantity || 0, missing: false}))
        .concat([...selected.values()].filter(row => !menus.some(menu => menu.key === row.key))
          .map(row => ({...row, remaining_qty: 0, missing: true})));
    }
    function set(key, quantity) {
      if (needsReview) throw new Error('변경된 남은 수량을 먼저 확인해 주세요.');
      const row = rows().find(menu => menu.key === key);
      if (!row || !Number.isSafeInteger(quantity) || quantity < 0
          || (quantity > row.remaining_qty && quantity >= row.quantity)) {
        throw new Error('남은 수량 안에서 완료 수량을 선택해 주세요.');
      }
      if (quantity === 0) selected.delete(key);
      else selected.set(key, {...row, quantity});
    }
    function invalid() { return rows().some(row => row.quantity > row.remaining_qty); }
    function payload() {
      if (!snapshot || needsReview || invalid() || !total() || !Number.isSafeInteger(total())) {
        throw new Error('최신 남은 수량과 선택한 완료 수량을 확인해 주세요.');
      }
      return {expected_version: snapshot.completion_version,
        items: rows().filter(row => row.quantity > 0).map(row => ({key: row.key, quantity: row.quantity}))};
    }
    return Object.freeze({apply, rows, set, total, invalid, payload,
      snapshot: () => snapshot, stale: () => needsReview,
      invalidate: () => { needsReview = true; },
      review: () => { if (snapshot) needsReview = false; },
      succeeded: () => { selected.clear(); needsReview = false; },
    });
  }
  const api = Object.freeze({create});
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.BazaarTakeoutState = api;
})(typeof window === 'undefined' ? globalThis : window);

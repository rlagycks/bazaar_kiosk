// ---- 공통 유틸 (모든 페이지에서 사용) ----
export const KRW = (n=0) => Number(n||0).toLocaleString('ko-KR');
export const moneyParse = (s='') => {
  const v = String(s).replace(/[^\d]/g, '');
  return v ? parseInt(v, 10) : 0;
};

// 쿠키에서 csrftoken 얻기
export function getCSRF() {
  const match = document.cookie.match(/(^|;\s*)csrftoken=([^;]*)/);
  return match ? decodeURIComponent(match[2]) : '';
}

// JSON POST
export async function postJSON(url, data) {
  const r = await fetch(url, {
    method: 'POST',
    headers: {'Content-Type':'application/json','X-CSRFToken': getCSRF()},
    body: JSON.stringify(data)
  });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

// JSON GET
export async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

// 합계 계산
export function sumCart(cart) {
  return cart.reduce((acc, it) => acc + (Number(it.unit_price||it.price||0) * Number(it.qty||0)), 0);
}

// 안전 리셋: 총액/거스름돈/입력값/장바구니 영역을 즉시 0/빈값으로 업데이트
export function resetMoneyUI({totalSel, changeSel, cashSel, recentSel, itemsSel}) {
  const $total  = document.querySelector(totalSel);
  const $change = changeSel ? document.querySelector(changeSel) : null;
  const $cash   = cashSel   ? document.querySelector(cashSel)   : null;
  const $items  = itemsSel  ? document.querySelector(itemsSel)  : null;
  if ($total)  $total.textContent  = `${KRW(0)}원`;
  if ($change) $change.textContent = `${KRW(0)}원`;
  if ($cash)   $cash.value = '';
  if ($items)  $items.innerHTML = '';
  if (recentSel) {
    const $recent = document.querySelector(recentSel);
    if ($recent) $recent.innerHTML = '';
  }
}
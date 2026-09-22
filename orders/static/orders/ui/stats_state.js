(function (root) {
  'use strict';
  const count = (value, signed = false) => Number.isSafeInteger(value) && (signed || value >= 0);
  const day = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && !Number.isNaN(Date.parse(value + 'T00:00:00Z')) && new Date(value + 'T00:00:00Z').toISOString().slice(0, 10) === value;
  const money = value => value.toLocaleString('ko-KR') + '원';
  function periodText(period) {
    const labels = {event_day: '최근 행사일', today: '오늘', explicit: '선택 기간'};
    const dates = period.start_date === period.end_date ? period.start_date : period.start_date + ' ~ ' + period.end_date;
    return (labels[period.basis] || '조회 기간') + ' ' + dates + (period.label ? ' · ' + period.label : '') + ' · 한국 시간';
  }
  function validate(data) {
    const bad = () => { throw new Error('통계 응답을 확인할 수 없습니다. 다시 조회해 주세요.'); };
    if (!data || !data.period || !day(data.period.start_date) || !day(data.period.end_date) || data.period.start_date > data.period.end_date) bad();
    if (!data.summary || !data.payment || !Array.isArray(data.menu) || !Array.isArray(data.hourly)) bad();
    for (const key of ['orders','items','revenue','cancelled_orders','legacy_unsplit_orders','unattributed_orders','unattributed_amount']) if (!count(data.summary[key])) bad();
    for (const key of ['cash','ticket','change','net_cash']) if (!count(data.payment[key],key === 'net_cash')) bad();
    for (const row of data.menu) if (!row || typeof row.name !== 'string' || !count(row.qty) || !count(row.amount)) bad();
    for (const row of data.hourly) if (!row || !day(row.date) || typeof row.hour !== 'string' || !/^([01]\d|2[0-3]):00$/.test(row.hour) || !count(row.orders) || !count(row.revenue)) bad();
    return data;
  }
  function ratio(payment) {
    const total = payment.cash + payment.ticket;
    const cash = total ? Math.round(payment.cash / total * 100) : 0;
    return {cash, ticket: total ? 100 - cash : 0};
  }
  const api = Object.freeze({validate,periodText,money,ratio});
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.BazaarStatsState = api;
})(typeof window === 'undefined' ? globalThis : window);

/* Shared API authentication. Access credentials live only in this closure. */
(function () {
  'use strict';
  const nativeFetch = window.fetch.bind(window);
  const refreshURL = '/orders/auth/refresh/';
  const pageIdentity = document.currentScript?.dataset || {};
  const expectedAccount = pageIdentity.authAccount;
  const expectedSession = pageIdentity.authSession;
  let accessToken = null;
  let pendingRefresh = null;
  let authenticationLost = false;

  function csrfToken() {
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function loginRequired() {
    accessToken = null;
    authenticationLost = true;
    window.location.assign('/orders/login/');
    // Named so a caller that schedules its own reads (the kitchen board,
    // 10D2) can tell "the page is already leaving" from a failed read it
    // should retry. The message is unchanged.
    const error = new Error('로그인이 필요합니다.');
    error.name = 'AuthenticationLost';
    throw error;
  }

  async function requestRefresh() {
    for (let attempt = 0; attempt < 5; attempt += 1) {
      const response = await nativeFetch(refreshURL, {
        method: 'POST', credentials: 'same-origin', cache: 'no-store',
        redirect: 'error', headers: {'X-CSRFToken': csrfToken()}
      });
      if (response.status === 401) return loginRequired();
      if (response.status === 409 && attempt < 4) {
        await new Promise(resolve => window.setTimeout(resolve, 100 * (2 ** attempt)));
        continue;
      }
      if (!response.ok) throw new Error('인증 갱신 실패: HTTP ' + response.status);
      const data = await response.json();
      if (typeof data.access_token !== 'string' || !data.access_token) {
        throw new Error('인증 응답을 확인할 수 없습니다.');
      }
      // Cookies are shared across tabs. Never carry this page's pending actions
      // into an account or login session selected in a different tab.
      if (data.account_id !== expectedAccount || data.session_id !== expectedSession) {
        return loginRequired();
      }
      accessToken = data.access_token;
      return accessToken;
    }
  }

  function refresh() {
    if (!pendingRefresh) {
      const run = () => requestRefresh();
      pendingRefresh = (window.navigator.locks
        ? window.navigator.locks.request('bazaar-refresh', run)
        : run()).finally(() => { pendingRefresh = null; });
    }
    return pendingRefresh;
  }

  async function authenticatedFetch(input, options) {
    const url = new URL(input instanceof Request ? input.url : input, window.location.href);
    if (url.origin !== window.location.origin) {
      throw new TypeError('인증 요청은 같은 출처에만 전송할 수 있습니다.');
    }
    if (authenticationLost || !expectedAccount || !expectedSession) return loginRequired();
    // Clone before sending so an explicit 401 can safely replay a request body.
    // Network errors propagate unchanged; a possibly accepted write is not replayed.
    const source = new Request(input instanceof Request ? input : url, Object.assign({}, options, {
      credentials: 'same-origin', cache: 'no-store', redirect: 'error'
    }));
    const send = (token) => {
      if (authenticationLost || !token) return loginRequired();
      const headers = new Headers(source.headers);
      headers.set('Authorization', 'Bearer ' + token);
      if (!['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(source.method)) {
        headers.set('X-CSRFToken', csrfToken());
      }
      return nativeFetch(new Request(source.clone(), {headers}));
    };
    const sentToken = accessToken || await refresh();
    const response = await send(sentToken);
    if (response.status !== 401) return response;
    // Another simultaneous request may already have replaced the failed token.
    if (accessToken === sentToken) await refresh();
    const retried = await send(accessToken);
    if (retried.status === 401) return loginRequired();
    return retried;
  }

  window.BazaarAuth = Object.freeze({fetch: authenticatedFetch});
})();

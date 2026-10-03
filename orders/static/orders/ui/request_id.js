/* Naming one attempt to create an order (6A).
 *
 * The id is minted when the volunteer presses 저장 and kept until that order
 * is actually saved, so pressing again after a lost response retries the same
 * attempt instead of creating a second order. Editing the order abandons the
 * id: the server refuses a used id carrying different contents, and that
 * refusal is the point -- it says the edit was not saved.
 *
 * `crypto.randomUUID` is unavailable outside a secure context, and this kiosk
 * may well be served over plain HTTP on the venue's LAN (TLS is 12A1). Falling
 * back to `getRandomValues`, which has no such restriction, keeps ordering
 * working there; the last resort keeps it working at all.
 */
(function () {
  'use strict';

  const HEX = '0123456789abcdef';

  function fromRandomValues() {
    const bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    // Version 4, variant 1: not required by the server, but it keeps the ids
    // recognisable as UUIDs in logs rather than anonymous hex.
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    let out = '';
    for (let i = 0; i < 16; i += 1) {
      if (i === 4 || i === 6 || i === 8 || i === 10) out += '-';
      out += HEX[bytes[i] >> 4] + HEX[bytes[i] & 0x0f];
    }
    return out;
  }

  function fromTimeAndMath() {
    // Only if the page has no crypto at all -- effectively a browser old
    // enough not to expose window.crypto. Weaker, and it does not need to be
    // strong: an id is not a secret and the server still requires a matching
    // account and order before it replays anything. The cost of a collision
    // here is a refused order (409), never someone else's order.
    let out = 'r-' + Date.now().toString(16);
    for (let i = 0; i < 16; i += 1) {
      out += HEX[Math.floor(Math.random() * 16)];
    }
    return out;
  }

  function create() {
    const crypto = window.crypto;
    if (crypto && typeof crypto.randomUUID === 'function') {
      try {
        return crypto.randomUUID();
      } catch (error) {
        // Some browsers expose it and throw outside a secure context.
      }
    }
    if (crypto && typeof crypto.getRandomValues === 'function') {
      return fromRandomValues();
    }
    return fromTimeAndMath();
  }

  window.BazaarRequestId = Object.freeze({create: create});
})();

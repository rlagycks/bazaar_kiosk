/* The kitchen board's one scheduler (10D2, D-061).
 *
 * Everything that decides *when* the board reads lives here, and nothing
 * else on the page may read at all. One `EventSource` on the kitchen stream,
 * one snapshot read at a time, and one rule for polling:
 *
 *   poll while NOT (stream open AND hub healthy AND a complete snapshot applied)
 *
 * That is D-019 verbatim. A heartbeat is not evidence -- `ready` and every
 * heartbeat say whether the hub last managed to read the database, and a
 * beat carrying `hub_ok: false` keeps polling exactly as a dead connection
 * does. A `change` frame carries no such word, but it is one: the hub only
 * dispatches after a read that succeeded (PR #80 architecture review).
 *
 * Order data reaches the board only through 10C's snapshot (D-058: the stream
 * carries no payload). A write's own response is never applied; the write
 * asks this scheduler for a read instead. So the two lists that used to race
 * -- a whole-list read and a single-order read -- are now one list, read at
 * most once at a time, and BK-R033's "late list overwrites a newer single"
 * has nothing left to happen between.
 *
 * A late response is still possible across a pause: the tab is hidden with a
 * read in flight, shown again, and the fresh read lands first. Every read
 * belongs to an epoch and a pause starts a new one, so the old answer is
 * dropped rather than applied over the newer.
 *
 * Only a visible tab holds a stream (user decision, D-061). The browser
 * limits connections per origin and, before TLS (12A1), HTTP/1.1 makes a
 * stream cost one of them; hidden tabs are also where a stale board would
 * be looked at least. Hiding the tab closes the stream and stops the poll;
 * showing it opens a fresh stream and reads once.
 *
 * Losing authentication ends the scheduler for good. The stream says so with
 * `closed: revoked|reauthenticate`; the authenticated fetch says so by
 * throwing `AuthenticationLost` after it has already sent the page to login.
 * Either way nothing else is read, nothing is applied, and no timer survives.
 */
(function () {
  'use strict';

  const DEFAULTS = Object.freeze({
    pollMs: 5000,
    reconnectMinMs: 2000,
    reconnectMaxMs: 30000,
    // Every tab that lost the same server would otherwise come back at the
    // same tick. The delay is shortened by up to this fraction; never
    // lengthened, so the documented cap holds (PR #80 security review).
    reconnectJitter: 0.2,
    // Missing two heartbeats in a row is a dead connection. A cable pulled
    // without a FIN never fires `error`; this is the only thing that notices.
    silenceBeats: 2,
    // What to assume when `ready` does not say. The server always sends
    // `heartbeat_ms` (its default is 15s); without an assumption a frame that
    // lost the field would disarm silence detection with no sign of it.
    heartbeatFallbackMs: 15000,
  });
  const CLOSED_FOR_GOOD = ['revoked', 'reauthenticate'];

  function create(options) {
    const settings = Object.assign({}, DEFAULTS, options || {});
    const win = settings.window;
    const doc = settings.document;
    const EventSourceImpl = settings.EventSource;
    const fetchImpl = settings.fetch;
    const streamUrl = String(settings.streamUrl);
    const snapshotUrl = String(settings.snapshotUrl);
    const onApply = settings.onApply;
    const onStatus = settings.onStatus;
    const onAuthLost = settings.onAuthLost;
    const random = typeof settings.random === 'function' ? settings.random : Math.random;

    if (new URL(streamUrl, win.location.href).origin !== win.location.origin) {
      throw new TypeError('스트림은 같은 출처에만 연결할 수 있습니다.');
    }

    let source = null;
    let stream = 'closed';      // 'closed' | 'connecting' | 'open'
    let hubOk = false;
    let heartbeatMs = null;
    let running = false;        // visible and not ended
    let ended = false;          // authentication lost: nothing runs again
    let epoch = 0;              // a pause starts a new one; older reads are late
    let issued = 0;
    let appliedSeq = 0;
    let inFlight = false;
    let wanted = false;         // a read was asked for while one was in flight
    let applied = {version: null, complete: false, at: null};
    let lastError = null;
    let reconnectDelay = settings.reconnectMinMs;
    const timers = {poll: null, reconnect: null, silence: null};

    function clearTimer(name) {
      if (timers[name] !== null) {
        win.clearTimeout(timers[name]);
        timers[name] = null;
      }
    }

    function state() {
      return {
        stream, hubOk, running, ended, inFlight,
        lastError: lastError === null ? null : String(lastError.message || lastError),
        applied: {version: applied.version, complete: applied.complete, at: applied.at},
        polling: needsPolling(),
        heartbeatMs,
      };
    }

    function report() {
      if (typeof onStatus === 'function') onStatus(state());
    }

    // ---- the rule ----
    function needsPolling() {
      if (!running) return false;
      return !(stream === 'open' && hubOk && applied.complete && applied.version !== null
               && lastError === null);
    }

    function reconcile() {
      if (needsPolling()) {
        if (timers.poll === null && !inFlight) {
          timers.poll = win.setTimeout(pollDue, settings.pollMs);
        }
      } else {
        clearTimer('poll');
      }
      report();
    }

    function pollDue() {
      timers.poll = null;
      refetch('poll');
    }

    // ---- reading ----
    function readUrl() {
      if (applied.version === null) return snapshotUrl;
      const joiner = snapshotUrl.indexOf('?') === -1 ? '?' : '&';
      return snapshotUrl + joiner + 'since=' + encodeURIComponent(applied.version);
    }

    function refetch(reason) {
      if (!running || ended) return;
      if (inFlight) {
        wanted = true;
        return;
      }
      inFlight = true;
      wanted = false;
      const seq = ++issued;
      const myEpoch = epoch;
      report();
      Promise.resolve()
        .then(() => fetchImpl(readUrl(), {credentials: 'same-origin'}))
        .then(response => {
          if (myEpoch !== epoch || seq <= appliedSeq) return null;
          if (!response.ok) throw new Error('HTTP ' + response.status);
          return response.json();
        })
        .then(data => {
          if (data === null || myEpoch !== epoch || seq <= appliedSeq) return;
          appliedSeq = seq;
          lastError = null;
          const now = new Date();
          if (data.unchanged) {
            // The server confirmed the version we hold, at this instant.
            applied = {version: applied.version, complete: applied.complete, at: now};
            return;
          }
          // Draw first, then record. The other order commits a version whose
          // data never reached the screen: the next `since=` read comes back
          // `unchanged`, `lastError` clears, polling stops, and the board sits
          // on a stale render under a status line saying live (PR #80
          // architecture review). Failing here leaves `applied` where it was,
          // so the next read asks for the whole list again.
          if (typeof onApply === 'function') onApply(data);
          applied = {
            version: typeof data.version === 'string' ? data.version : null,
            complete: data.complete === true,
            at: now,
          };
        })
        .catch(error => {
          if (myEpoch !== epoch) return;
          if (error && error.name === 'AuthenticationLost') {
            end();
            return;
          }
          lastError = error;
        })
        .then(() => {
          if (myEpoch !== epoch || ended) return;
          inFlight = false;
          if (wanted) {
            refetch(reason + '+queued');
          } else {
            reconcile();
          }
        });
    }

    // ---- the stream ----
    function frame(event) {
      try {
        return JSON.parse(event.data);
      } catch (error) {
        return {};
      }
    }

    function armSilence() {
      clearTimer('silence');
      if (heartbeatMs === null) return;   // no stream open
      timers.silence = win.setTimeout(silenceDue, heartbeatMs * settings.silenceBeats + 1);
    }

    function silenceDue() {
      timers.silence = null;
      dropStream();
      scheduleReconnect();
      reconcile();
    }

    function dropStream() {
      if (source !== null) {
        source.close();
        source = null;
      }
      stream = 'closed';
      hubOk = false;
      clearTimer('silence');
    }

    function reconnectDue() {
      timers.reconnect = null;
      connect();
      reconcile();
    }

    function scheduleReconnect() {
      if (timers.reconnect !== null || !running || ended) return;
      if (typeof EventSourceImpl !== 'function') return;
      const base = reconnectDelay;
      reconnectDelay = Math.min(base * 2, settings.reconnectMaxMs);
      const delay = base - Math.round(base * settings.reconnectJitter * random());
      timers.reconnect = win.setTimeout(reconnectDue, delay);
    }

    function connect() {
      if (source !== null || !running || ended) return;
      // A browser without `EventSource` still gets a board: the poll carries
      // it, and the status line says it is polling rather than live.
      if (typeof EventSourceImpl !== 'function') return;
      const es = new EventSourceImpl(streamUrl);
      source = es;
      stream = 'connecting';
      hubOk = false;

      es.addEventListener('ready', event => {
        if (source !== es) return;
        const payload = frame(event);
        stream = 'open';
        hubOk = payload.hub_ok === true;
        heartbeatMs = Number(payload.heartbeat_ms) > 0
          ? Number(payload.heartbeat_ms) : settings.heartbeatFallbackMs;
        reconnectDelay = settings.reconnectMinMs;
        armSilence();
        // Something may have changed between the page's first read and the
        // stream opening; the stream only reports what happens after.
        refetch('ready');
        reconcile();
      });
      es.addEventListener('change', () => {
        if (source !== es) return;
        // The frame says nothing about the hub, but its arrival does: the hub
        // dispatches only after a read of the database that succeeded. Without
        // this a board whose `ready` caught the hub before its first read, on
        // a kitchen busy enough that no heartbeat gets a word in, would poll
        // every 5s for as long as the rush lasted.
        hubOk = true;
        armSilence();
        refetch('change');
      });
      es.addEventListener('heartbeat', event => {
        if (source !== es) return;
        const payload = frame(event);
        hubOk = payload.hub_ok === true;
        armSilence();
        reconcile();
      });
      es.addEventListener('closed', event => {
        if (source !== es) return;
        const reason = String(frame(event).reason || '');
        dropStream();
        if (CLOSED_FOR_GOOD.indexOf(reason) !== -1) {
          end();
          return;
        }
        // `unverified`, or anything this version does not know: the server
        // could not say who we are, which is not our cue to leave. Back off.
        scheduleReconnect();
        reconcile();
      });
      es.addEventListener('error', () => {
        if (source !== es) return;
        if (es.readyState === 2 /* CLOSED */) {
          // The browser gave up: a non-200, a wrong content type, a refusal.
          // It will not retry on its own, so the bounded reconnect does.
          dropStream();
          scheduleReconnect();
        } else {
          // CONNECTING: the browser is already retrying. Nothing to open, but
          // until `ready` comes back the board is on its own.
          stream = 'connecting';
          hubOk = false;
          clearTimer('silence');
        }
        reconcile();
      });
    }

    // ---- lifecycle ----
    function resume() {
      if (ended || running) return;
      running = true;
      epoch += 1;
      inFlight = false;
      wanted = false;
      lastError = null;
      // A tab shown again starts over: the failures that escalated the
      // delay belonged to a stream that no longer exists.
      reconnectDelay = settings.reconnectMinMs;
      connect();
      refetch('visible');
      reconcile();
    }

    function pause() {
      if (!running) return;
      running = false;
      epoch += 1;            // a read still in flight is now late
      inFlight = false;
      wanted = false;
      dropStream();
      clearTimer('poll');
      clearTimer('reconnect');
      report();
    }

    function end() {
      pause();
      ended = true;
      report();
      if (typeof onAuthLost === 'function') onAuthLost();
    }

    function visible() {
      return !doc.hidden;
    }

    let started = false;
    function start() {
      if (started || ended) return;
      started = true;
      doc.addEventListener('visibilitychange', () => {
        if (visible()) resume(); else pause();
      });
      // BFCache: a page put away with an open stream cannot be cached, and a
      // page brought back has missed everything. Close on the way out and
      // read once on the way back in.
      win.addEventListener('pagehide', () => pause());
      win.addEventListener('pageshow', () => { if (visible()) resume(); });
      if (visible()) resume(); else report();
    }

    return Object.freeze({start, refetch, state});
  }

  window.BazaarLive = Object.freeze({create});
})();

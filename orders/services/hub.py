"""One poller per worker, and what it is allowed to tell each screen (10D1).

A request is authorized once and is then over. A stream is authorized once and
then stays open all evening, so every guarantee the rest of this system gets
from re-reading the database per request has to be re-established here on
purpose. That is BK-R038, and it is most of this file.

**Shape.** One task per event loop -- one per uvicorn worker -- polls
`revisions.state()`, which is a single row and needs no transaction. Screens
do not poll; they hold a subscription. Without this the detection cost would
be O(open screens), which is the thing 10C's measurement warned about.

**Revalidation before every event (user decision, D-060).** The alternative
offered was a fixed ~15s re-check, which is cheaper and bounds revocation at
the interval. The stronger form was chosen, so a logged-out volunteer stops
receiving at the next event rather than up to fifteen seconds later. The cost
that makes it affordable is that the check is *batched*: one change waking N
screens re-reads N device rows in **one** query, not N. The semantics are
unchanged -- nothing is dispatched without a fresh read -- but the cost is
per change rather than per change per screen.

**Scope discrimination, and why it does not reopen D-059.** The 10D1 card asks
that a screen not learn the rate of changes it cannot see; D-059 accepted
exactly that leak for the *version*, because closing it there meant splitting
the counter row and therefore ordering a second write lock -- a deadlock risk
bought for nothing. The hub is not the counter. It compares what each distinct
scope can actually see, on the read side, where there is no lock to order. The
distinct scopes are few (hall, takeout, everything), so this costs a bounded
number of reads per change regardless of how many screens are open, and it
removes the wasted refetches 10C measured at the same time.

The comparison is made against the snapshot the screen would itself fetch,
not against a cheaper set of columns chosen by hand. A fingerprint that missed
a field -- `prepared_qty` is the easy one to forget -- would leave a board
frozen with no error anywhere, which is a worse failure than the leak it is
closing.

**Health is not a heartbeat.** D-019 settles that a client stops polling on
hub health plus a complete snapshot, never on "a frame arrived". So the two
are separate facts and `health()` is what the stream puts in every beat.

**Connections.** Every database call here is `thread_sensitive`, so the whole
hub runs on one asgiref thread and holds exactly one connection for the life
of the worker. That is deliberate and it is the opposite of 10A's advice for
streams: a stream releases its connection because there is one per screen,
while the hub keeps one because there is one per worker. `CONN_MAX_AGE` only
acts at request boundaries and a hub tick is not a request.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import deque
from dataclasses import dataclass, field

from asgiref.sync import sync_to_async
from django.conf import settings


# Why a screen was cut off. The client needs to tell "log in again" from
# "you are behind" apart, because only one of them is its fault.
CLOSED_REVOKED = "revoked"
CLOSED_REAUTH = "reauthenticate"
CLOSED_UNVERIFIED = "unverified"

# A queue is per screen, so it is the one thing here that grows with the number
# of screens. Under a convergence contract a backlog is meaningless anyway --
# every entry says the same thing, "refetch" -- so the ceiling is small on
# purpose and overflowing collapses to one notice rather than growing
# (BK-R040).
MAX_QUEUED_EVENTS = 8

# How many consecutive failed reads before the hub stops claiming to be
# healthy. It keeps the streams open and keeps beating -- the beat is what
# carries `hub_ok: false` to the screen, which is how the screen learns to go
# back to fetching for itself (D-019). Saying nothing would look exactly like
# a quiet kitchen.
MAX_CONSECUTIVE_FAILURES = 3


def poll_seconds() -> float:
    return float(getattr(settings, "HUB_POLL_SECONDS", 1.0))


def heartbeat_seconds() -> float:
    return float(getattr(settings, "HUB_HEARTBEAT_SECONDS", 15.0))


@dataclass
class Health:
    ok: bool
    stale_ms: int | None
    failures: int

    def as_frame(self) -> dict:
        return {"hub_ok": self.ok, "stale_ms": self.stale_ms,
                "failures": self.failures}


@dataclass
class Subscription:
    """One screen's claim on the hub.

    `permissions` is what the caller held when the stream opened. The hub
    re-reads it before every dispatch and ends the stream when it differs,
    rather than quietly narrowing: the events carry no payload, so there is
    nothing in a queued event to re-judge against a new permission set. The
    old scope's queue is discarded by the stream ending, which is what the
    card asks for.
    """

    session_id: str
    permissions: tuple
    _queue: deque = field(default_factory=deque)
    _wake: asyncio.Event = field(default_factory=asyncio.Event)
    overflowed: bool = False
    closed_reason: str | None = None

    def scope_key(self) -> tuple:
        return tuple(sorted(str(code) for code in self.permissions))

    def offer(self, event: dict) -> None:
        if len(self._queue) >= MAX_QUEUED_EVENTS:
            # Dropping is safe -- every entry means the same thing -- but
            # dropping silently is not: the screen would wait for a change
            # that has already happened. The flag is what the stream turns
            # into one "start over".
            self.overflowed = True
        else:
            self._queue.append(event)
        self._wake.set()

    def close(self, reason: str) -> None:
        self.closed_reason = reason
        self._wake.set()

    def pending(self) -> int:
        return len(self._queue)

    async def next_event(self, timeout: float):
        """The next event, or None when `timeout` passes with nothing."""
        if not self._queue and self.closed_reason is None and not self.overflowed:
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                return None
        self._wake.clear()
        if self._queue:
            return self._queue.popleft()
        return None


# ---------- the database side, all of it synchronous on one thread ----------

def _read_state():
    """The marker, as one row. Named so a test can break it on purpose."""
    from orders.services import revisions

    return revisions.state()


def _still_allowed(session_ids):
    """Fresh permissions per session, in one query. Missing means revoked.

    This is the batching that makes "revalidate before every event"
    affordable. `validate_access` answers the same question for one caller and
    one request; this asks it for everyone about to be told the same thing.
    """
    from django.utils import timezone
    from orders.models import AuthDevice

    now = timezone.now()
    rows = (AuthDevice.objects.select_related("account")
            .filter(pk__in=list(session_ids)))
    allowed = {}
    for device in rows:
        account = device.account
        if (device.revoked_at is not None or device.expires_at <= now
                or account is None or not account.is_active):
            continue
        allowed[str(device.id)] = tuple(sorted(account.permissions))
    return allowed


def _scope_view(permissions):
    """What this scope can see right now, as (digest, version).

    The digest is taken over the snapshot the screen would itself fetch --
    the same serialization, from the same one-instant read -- so it cannot
    drift away from what is drawn. A cheaper digest over hand-picked columns
    would, and a missed field leaves a board frozen with nothing logged.
    """
    from orders.services import snapshots
    from orders.views import serializers

    taken = snapshots.waiting(permissions)
    body = json.dumps([serializers.order(o) for o in taken.orders],
                      separators=(",", ":"), sort_keys=True, default=str)
    return hashlib.blake2s(body.encode("utf-8"), digest_size=16).hexdigest(), taken.version


# ---------- the hub itself ----------

class _Hub:
    def __init__(self):
        self.subscriptions: list[Subscription] = []
        self.task: asyncio.Task | None = None
        self.state = None
        self.views: dict[tuple, str] = {}
        self.last_ok: float | None = None
        self.failures = 0

    def health(self) -> Health:
        stale = None if self.last_ok is None else int(
            (time.monotonic() - self.last_ok) * 1000
        )
        return Health(
            ok=self.failures < MAX_CONSECUTIVE_FAILURES and self.last_ok is not None,
            stale_ms=stale, failures=self.failures,
        )

    def add(self, subscription: Subscription) -> None:
        self.subscriptions.append(subscription)
        if self.task is None or self.task.done():
            self.task = asyncio.ensure_future(self._run())

    def remove(self, subscription: Subscription) -> None:
        if subscription in self.subscriptions:
            self.subscriptions.remove(subscription)

    async def _run(self) -> None:
        while self.subscriptions:
            try:
                state = await sync_to_async(_read_state, thread_sensitive=True)()
            except Exception:
                # The hub cannot see the board. It does **not** end the streams
                # for this: a screen that is cut off reconnects, finds the same
                # broken hub, and loops. D-019 puts the decision on the client
                # instead -- it stops polling on hub health plus a complete
                # snapshot -- so the honest thing is to stay open and say so,
                # and let the screen go back to fetching for itself.
                #
                # Failing to *authorize* is the opposite case and is handled in
                # `_dispatch`: not knowing who someone is means sending them
                # nothing, ever.
                self.failures += 1
            else:
                self.last_ok = time.monotonic()
                self.failures = 0
                if state != self.state:
                    first = self.state is None
                    self.state = state
                    if not first:
                        await self._dispatch()
                    else:
                        await self._prime()
            await asyncio.sleep(poll_seconds())

    def _close_all(self, reason: str) -> None:
        for subscription in list(self.subscriptions):
            subscription.close(reason)
            self.remove(subscription)

    async def _prime(self) -> None:
        """Record what each scope sees now, so the first change is a change."""
        for key, permissions in self._scopes().items():
            try:
                digest, _ = await sync_to_async(
                    _scope_view, thread_sensitive=True)(permissions)
            except Exception:
                return
            self.views[key] = digest

    def _scopes(self) -> dict[tuple, tuple]:
        return {s.scope_key(): s.permissions for s in self.subscriptions}

    async def _dispatch(self) -> None:
        watching = list(self.subscriptions)
        if not watching:
            return
        try:
            fresh = await sync_to_async(_still_allowed, thread_sensitive=True)(
                [s.session_id for s in watching]
            )
        except Exception:
            # Fail closed, and this one *does* end the streams. The bound the
            # card asks for is zero events: nothing goes out that was not
            # authorized by a read that just succeeded, and a connection that
            # cannot be re-authorized is not one to keep open.
            self._close_all(CLOSED_UNVERIFIED)
            return

        survivors = []
        for subscription in watching:
            held = fresh.get(subscription.session_id)
            if held is None:
                subscription.close(CLOSED_REVOKED)
                self.remove(subscription)
            elif held != tuple(sorted(str(c) for c in subscription.permissions)):
                subscription.close(CLOSED_REAUTH)
                self.remove(subscription)
            else:
                survivors.append(subscription)

        for key, permissions in {s.scope_key(): s.permissions
                                 for s in survivors}.items():
            try:
                digest, version = await sync_to_async(
                    _scope_view, thread_sensitive=True)(permissions)
            except Exception:
                self.failures += 1
                continue
            if self.views.get(key) == digest:
                # This scope cannot see what changed. Saying nothing is the
                # card's "발생 빈도 정보 노출 거부" and 10C's wasted refetch,
                # closed by the same comparison.
                continue
            self.views[key] = digest
            for subscription in survivors:
                if subscription.scope_key() == key:
                    subscription.offer({"version": version})


async def _prime_for_measurement(subscriptions) -> None:
    """A hub with these subscribers, primed. See `scripts/hub_fanout.py`.

    The measurement drives one dispatch at a time rather than letting the
    poller decide when, so that "queries per change" is a count and not a
    sample. It uses the real `_dispatch`, so a change to the batching shows up
    in the numbers instead of only in the harness.
    """
    hub = _Hub()
    hub.subscriptions = list(subscriptions)
    await hub._prime()
    _measured[0] = hub


async def _dispatch_for_measurement(subscriptions) -> None:
    hub = _measured[0]
    hub.subscriptions = list(subscriptions)
    await hub._dispatch()


_measured: list = [None]

_hubs: dict[int, _Hub] = {}


def _for_this_loop() -> _Hub:
    key = id(asyncio.get_running_loop())
    hub = _hubs.get(key)
    if hub is None:
        hub = _hubs[key] = _Hub()
    return hub


def subscribe(session_id: str, permissions) -> Subscription:
    subscription = Subscription(session_id=session_id,
                                permissions=tuple(permissions))
    _for_this_loop().add(subscription)
    return subscription


def unsubscribe(subscription: Subscription) -> None:
    hub = _hubs.get(id(asyncio.get_running_loop()))
    if hub is None:
        return
    hub.remove(subscription)
    if not hub.subscriptions:
        # Nothing is watching, so nothing should be polling. The task notices
        # on its next tick; dropping the hub here keeps a test's loop from
        # being kept alive by a poller nobody asked for.
        _hubs.pop(id(asyncio.get_running_loop()), None)


def health() -> Health:
    hub = _hubs.get(id(asyncio.get_running_loop()))
    return hub.health() if hub else Health(ok=False, stale_ms=None, failures=0)

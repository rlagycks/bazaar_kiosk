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

**Connections, and a claim this file used to get wrong.** An earlier version
said the hub holds exactly one connection for the life of the worker because
every call is `thread_sensitive`. That is false. Django wraps every request in
`ThreadSensitiveContext`, which gives `thread_sensitive=True` a *per-request*
single-worker executor, and this task inherits the context of whichever
request started it -- so the hub runs on that stream's thread, shares its
connection, and silently migrates to a fresh thread and connection when that
request ends. Under `AsyncClient` there is no such context at all, so the
tests never see the production shape.

What is true is the direction: detection is one poller per worker rather than
one per screen, so the *number* of connections does not follow the number of
open screens. That is the property 10C handed over, and it holds either way.
The rule for streams is still the opposite of the hub's -- a stream releases
its connection because there is one per screen -- and `CONN_MAX_AGE` only acts
at request boundaries, which a hub tick is not.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import weakref
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


def revalidate_seconds() -> float:
    """How often everyone is re-checked even when nothing is cooking.

    Its own setting rather than the heartbeat's. The heartbeat is a display
    knob -- it is what `ready` advertises to the screen -- and tuning it for
    the browser would otherwise move revocation latency and this worker's
    database load with it.
    """
    return float(getattr(settings, "HUB_REVALIDATE_SECONDS", 15.0))


@dataclass
class Health:
    ok: bool
    stale_ms: int | None
    failures: int

    def as_frame(self) -> dict:
        return {"hub_ok": self.ok, "stale_ms": self.stale_ms,
                "failures": self.failures}


@dataclass(eq=False)
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

    def identity_key(self) -> tuple:
        """Everything the account holds. Changes when the role changes."""
        return tuple(sorted(str(code) for code in self.permissions))

    def scope_key(self) -> tuple:
        """What actually narrows the read -- three outcomes, not a power set.

        `scope.visible()` collapses every permission set to all / dine-in /
        takeout and ignores the rest, so `{HALL_MONITOR}` and
        `{HALL_MONITOR, SERVING}` see byte-identical boards. Grouping by the
        raw set made them two groups and paid for a full snapshot twice; with
        four codes a mixed roster could reach a dozen groups, and the cost
        argument for this whole design assumes three.

        This is *not* the comparison that detects a role change -- that one
        stays on `identity_key`, or gaining an unrelated permission would go
        unnoticed.
        """
        from orders.roles import HALL_MONITOR, STATS, TAKEOUT_MONITOR

        held = frozenset(str(code) for code in self.permissions)
        if STATS in held or {HALL_MONITOR, TAKEOUT_MONITOR} <= held:
            return ("ALL",)
        if HALL_MONITOR in held:
            return ("HALL",)
        if TAKEOUT_MONITOR in held:
            return ("TAKEOUT",)
        return ()

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

    The condition itself is `authentication.device_is_current`, deliberately
    not a copy of it. The first version of this function listed the conditions
    again and left out the credential fingerprint, which is the entire
    mechanism by which rotating the shared event password logs every device
    out (D-045) -- so a rotation stopped every request and none of the open
    streams. A security review caught it; sharing the predicate is what stops
    the next divergence.
    """
    from django.utils import timezone
    from orders.authentication import device_is_current
    from orders.models import AuthDevice

    now = timezone.now()
    rows = (AuthDevice.objects.select_related("account")
            .filter(pk__in=list(session_ids)))
    return {
        str(device.id): tuple(sorted(device.account.permissions))
        for device in rows if device_is_current(device, now)
    }


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
    # `total` and `complete` are in the digest because `MAX_QUEUE` can cut the
    # list: above that bound a change confined to the tail would leave the
    # visible rows identical and the board would stop updating, silently. 10C's
    # per-screen polling had no such hole -- the global version always moved --
    # so leaving them out would make the hub a regression at exactly the
    # boundary the queue bound was written for.
    body = json.dumps(
        {"orders": [serializers.order(o) for o in taken.orders],
         "total": taken.total, "complete": taken.complete},
        separators=(",", ":"), sort_keys=True,
    )
    digest = hashlib.blake2s(body.encode("utf-8"), digest_size=16).hexdigest()
    if not taken.complete:
        # A cut list cannot promise that equal digests mean an unchanged
        # board, so it does not get to be compared at all.
        digest = f"{digest}:incomplete:{time.monotonic_ns()}"
    return digest, taken.version


# ---------- the hub itself ----------

class _Hub:
    def __init__(self):
        self.subscriptions: list[Subscription] = []
        self.task: asyncio.Task | None = None
        self.state = None
        self.views: dict[tuple, str] = {}
        self.last_ok: float | None = None
        self.last_checked: float | None = None
        self.failures = 0

    def health(self) -> Health:
        stale = None if self.last_ok is None else int(
            (time.monotonic() - self.last_ok) * 1000
        )
        # The staleness term is what makes this honest. `failures` only moves
        # when a read *fails*; if the poller stops running at all -- cancelled,
        # an exception escaping the loop, a hub that never started -- then
        # `failures` stays 0 and `last_ok` stays set, and without this the
        # frame would say `hub_ok: true` forever while nothing polled. 10D2
        # stops polling on that word, so the result would be a frozen board
        # with no error anywhere: the failure this module exists to prevent.
        ok = (self.last_ok is not None
              and self.failures < MAX_CONSECUTIVE_FAILURES
              # Three ticks, with a floor so a very short poll interval
              # cannot make this flap between beats.
              and stale <= int(max(3 * poll_seconds(), 0.5) * 1000))
        return Health(ok=ok, stale_ms=stale, failures=self.failures)

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
                elif self._revalidation_is_due():
                    # "Before every event" bounds revocation by the *next
                    # event*, which on a quiet board is not a bound at all: a
                    # logged-out screen would stay attached, receiving
                    # heartbeats, until somebody happened to cook something.
                    # So the same check also runs on the heartbeat cadence.
                    # It costs one query per beat for the whole worker, and it
                    # is the user's chosen policy made true rather than
                    # weakened -- the change-triggered pass still runs first.
                    await self._revalidate()
            await asyncio.sleep(poll_seconds())

    def _revalidation_is_due(self) -> bool:
        if not self.subscriptions:
            return False
        due = revalidate_seconds()
        return (self.last_checked is None
                or time.monotonic() - self.last_checked >= due)

    async def _revalidate(self) -> None:
        """Drop anyone who may no longer watch. Sends nothing to the rest."""
        self.last_checked = time.monotonic()
        watching = list(self.subscriptions)
        if not watching:
            return
        try:
            fresh = await sync_to_async(_still_allowed, thread_sensitive=True)(
                [s.session_id for s in watching]
            )
        except Exception:
            self._close_all(CLOSED_UNVERIFIED)
            return
        for subscription in watching:
            held = fresh.get(subscription.session_id)
            if held is None:
                subscription.close(CLOSED_REVOKED)
                self.remove(subscription)
            elif held != subscription.identity_key():
                subscription.close(CLOSED_REAUTH)
                self.remove(subscription)

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

        self.last_checked = time.monotonic()
        survivors = []
        for subscription in watching:
            held = fresh.get(subscription.session_id)
            if held is None:
                subscription.close(CLOSED_REVOKED)
                self.remove(subscription)
            elif held != subscription.identity_key():
                subscription.close(CLOSED_REAUTH)
                self.remove(subscription)
            else:
                survivors.append(subscription)

        for key, permissions in {s.scope_key(): s.permissions
                                 for s in survivors}.items():
            try:
                digest, _version = await sync_to_async(
                    _scope_view, thread_sensitive=True)(permissions)
            except Exception:
                # `self.state` has already moved past this change, so without
                # forgetting the digest the next comparison would match and
                # this change would be lost for good -- no event, no
                # `hub_ok: false`, nothing logged. Forgetting makes the next
                # comparison differ, so the next change delivers both.
                self.views.pop(key, None)
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
                    # Deliberately empty. An earlier version sent the snapshot
                    # version, which handed back the very thing the scope
                    # comparison had just withheld: the counter is global, so a
                    # takeout screen correctly not woken by twenty hall changes
                    # would see its next version jump by twenty and could read
                    # the gap as the count of what it was not told about. The
                    # screen has no decision to make with a version here --
                    # under D-058 it refetches the snapshot, which carries its
                    # own -- so sending one was decoration that leaked.
                    subscription.offer({})


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

# Keyed on the loop *object*, weakly. `id(loop)` is an address, and once a
# loop is collected a new one can be allocated there -- the new loop would then
# find the dead loop's hub, whose task is neither None nor done, so no poller
# would start and every screen on it would get heartbeats and never a change.
# One long-lived loop per worker makes that unlikely in a deployment and
# routine in a test suite, where every async case gets a fresh loop.
_hubs: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, _Hub]" = (
    weakref.WeakKeyDictionary()
)


def _for_this_loop() -> _Hub:
    loop = asyncio.get_running_loop()
    hub = _hubs.get(loop)
    if hub is None:
        hub = _hubs[loop] = _Hub()
    return hub


def subscribe(session_id: str, permissions) -> Subscription:
    subscription = Subscription(session_id=session_id,
                                permissions=tuple(permissions))
    _for_this_loop().add(subscription)
    return subscription


def unsubscribe(subscription: Subscription) -> None:
    # Not `get_running_loop()`: a response's resource closer can run outside
    # the loop that opened the stream, and raising there would leave the
    # worker slot claimed -- the exact leak this call exists to prevent. So
    # the subscription is found wherever it is.
    hub = None
    try:
        hub = _hubs.get(asyncio.get_running_loop())
    except RuntimeError:
        pass
    if hub is None:
        for candidate in list(_hubs.values()):
            if subscription in candidate.subscriptions:
                hub = candidate
                break
    if hub is None:
        return
    hub.remove(subscription)
    if not hub.subscriptions:
        # Nothing is watching, so nothing should be polling. The task notices
        # on its next tick; dropping the hub here keeps a test's loop from
        # being kept alive by a poller nobody asked for.
        for key, candidate in list(_hubs.items()):
            if candidate is hub:
                _hubs.pop(key, None)


def health() -> Health:
    hub = _hubs.get(asyncio.get_running_loop())
    return hub.health() if hub else Health(ok=False, stale_ms=None, failures=0)

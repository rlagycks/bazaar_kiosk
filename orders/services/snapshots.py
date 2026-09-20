"""The waiting list and the version it belongs to, from one instant (10C).

10B gave the board a number that moves when anything it draws changes. That
number only becomes usable when a screen can say *which* data it goes with,
and that is not free: under Django's default autocommit, reading the version
and reading the orders are two statements and therefore two different
PostgreSQL snapshots. A change committing between them produces a pair that
was never true together --

* orders first, version second: the new order is in the data and the version
  is the newer one, so the screen stores a version ahead of what it shows and
  will not refetch until something *else* changes;
* version first, orders second: the data is newer than the version, so the
  screen refetches once more than it needed to. Safe, but it is not the
  "same instant" the phase card asks for.

So a snapshot is one REPEATABLE READ transaction (user decision, D-019). Both
reads see one instant and the version is a true statement about the rows
beside it.

**The version is compared, never ordered.** It is `generation:value:scope`,
and each part answers a way a screen could otherwise be wrong:

* `generation` -- a restored database hands out values screens have already
  seen, and the hazard is the **collision**, not the repetition. Receiving a
  change twice is harmless under a convergence contract; what is not harmless
  is the counter climbing back up to a value a screen is still holding, so
  that its next poll matches, answers `unchanged`, and leaves pre-restore
  data on the wall indefinitely. A new generation makes the whole version
  differ however the number lands (12A3 rotates it);
* `value` -- 10B's marker;
* `scope` -- permissions are read from the database on every request and
  decide which orders exist for a caller, so a version minted for one set of
  permissions says nothing about another. A cursor from a different scope is
  refused and the caller gets the whole list instead of a wrong "unchanged".

**`complete` is not `has_more` inverted for decoration.** `MAX_QUEUE` can cut
the list, and a version attached to a cut list is not a promise that the
screen holds everything. Saying so is what keeps convergence honest at the
boundary where the kitchen is busiest.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from django.db import connection, transaction

from orders.models import FloorChoices, OrderStatus
from orders.services import queues, revisions

# `selectors` lives under `views/` although it is a query module, so this
# makes `orders.services` depend on `orders.views`. That is a layering debt
# and step 11 moves the module; it is not an import cycle -- `orders.views`
# imports nothing at package level and `selectors` reaches back only for
# `services.scope`, which `services/__init__` binds before it binds this
# module. An earlier version deferred this import into the function body and
# blamed a cycle; there is none, and deferring did not change the direction.
#
# Calling it is right either way: the alternative is a second copy of the
# kitchen board's query, and `test_snapshot_consistency.py` pins that this
# endpoint and the board's own query string select the same orders.
from orders.views import selectors

CURSOR_ABSENT = "absent"
CURSOR_ACCEPTED = "accepted"
CURSOR_REJECTED = "rejected"


@dataclass(frozen=True)
class Snapshot:
    version: str
    orders: list = field(default_factory=list)
    total: int = 0
    has_more: bool = False
    complete: bool = True
    unchanged: bool = False
    cursor: str = CURSOR_ABSENT
    # Whether this snapshot got its own isolation level. See `_isolate`.
    isolated: bool = True


def scope_digest(permissions) -> str:
    """A short, stable fingerprint of the permissions a snapshot was built for.

    Sorted, so the same set always gives the same digest whatever order it
    arrived in. Hashed rather than listed to keep the version short and
    opaque-looking, **not as a secret**: the key space is a handful of
    permission codes, the hash is unkeyed, and anyone can enumerate it. That
    is fine because nothing is defended by it. The digest never narrows a
    queryset -- `waiting()` filters by the caller's own server-checked
    permissions -- so forging one buys an attacker nothing but a wrong
    `unchanged` served to themselves.
    """
    material = ",".join(sorted(str(code) for code in permissions))
    return hashlib.blake2s(material.encode("utf-8"), digest_size=8).hexdigest()


def version_from(value: int, permissions, *, generation: str | None = None) -> str:
    """Assemble a version. Separate from reading one so tests can predict it."""
    if generation is None:
        generation = revisions.state()[0]
    return f"{generation}:{value}:{scope_digest(permissions)}"


def version_for(permissions) -> str:
    """The current version for these permissions, read outside a snapshot."""
    generation, value = revisions.state()
    return version_from(value, permissions, generation=generation)


def _same_lineage_and_scope(since: str, version: str) -> bool:
    """Whether a version a caller sent can be compared with this one at all.

    Only the first and last parts have to match: a different generation means
    a restored database, and a different scope means different permissions.
    In both cases the number in the middle is meaningless and the caller gets
    the whole list rather than a wrong "nothing changed".
    """
    mine = version.split(":")
    theirs = str(since).split(":")
    if len(theirs) != 3 or len(mine) != 3:
        return False
    return theirs[0] == mine[0] and theirs[2] == mine[2]


def _isolate(ours: bool) -> None:
    """One instant for everything read after this, when the transaction is ours.

    PostgreSQL only accepts `SET TRANSACTION` before a transaction's first
    query, so this only works when we opened the transaction ourselves. Nested
    inside someone else's, it cannot.

    **Nested, the same-instant guarantee is genuinely lost.** An earlier
    version of this docstring claimed it was moot because an enclosing
    transaction "has its own snapshot"; that is false, and a review was right
    to call it out. Nothing in this repository raises the isolation level, so
    every `transaction.atomic()` here is READ COMMITTED, where PostgreSQL
    takes a *new* snapshot at the start of every statement -- two successive
    SELECTs in one such transaction can straddle a commit exactly as they
    would under autocommit.

    What keeps that from mattering is not this function but `waiting()`'s
    **read order**, which is therefore load-bearing rather than incidental.
    The version is read first and the orders second, so the only way the pair
    can be wrong is *data newer than its version* -- the screen refetches once
    more than it needed to and converges. The reverse order would produce a
    version newer than its data, which is permanent staleness: the screen
    stores a version it does not yet show and stops asking. So nesting
    degrades this from "one instant" to "at most one extra refetch", never to
    a missed change. `test_snapshot_consistency.py` pins that direction.

    That is why the answer is to report rather than refuse. The first version
    raised, and the only thing it achieved was making the endpoint unreachable
    from every `TestCase` in the repository. Still, the contract this module
    sells is the stronger one, so `snapshot_waiting` logs when it is not being
    met and `test_required_settings.py` pins that no deployment setting wraps
    a request in a transaction.
    """
    # `ours` is decided *before* the transaction is opened. Asking
    # `in_atomic_block` here would always say yes -- we are inside the block we
    # just opened -- and the SET would never run, which is what the first
    # version of this function did until a test caught it.
    if not ours:
        return
    with connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")


def waiting(permissions, since: str | None = None, *, _pause=None) -> Snapshot:
    """Everything still to cook that these permissions may see, and its version.

    `_pause` is a test seam: a pair of events used to hold the transaction
    open between reading the version and reading the orders, so that the
    "same instant" claim is forced rather than hoped for. Nothing in
    production passes it.
    """
    # Asked before the transaction is opened: once inside, `in_atomic_block`
    # is true whoever opened it. `get_autocommit()` is the second half --
    # what PostgreSQL actually requires is that no data statement has run in
    # this transaction, and autocommit being already off means one may have,
    # with `in_atomic_block` still False. No request reaches that state today;
    # without this the SET would raise `ActiveSqlTransaction` as a 500.
    isolated = not connection.in_atomic_block and connection.get_autocommit()

    with transaction.atomic():
        _isolate(isolated)
        generation, value = revisions.state()
        version = version_from(value, permissions, generation=generation)

        if since:
            if not _same_lineage_and_scope(since, version):
                cursor_state = CURSOR_REJECTED
            elif since == version:
                # Same instant as the one the caller already holds. Nothing to
                # send, and no query to run -- which is the whole reason the
                # marker exists.
                return Snapshot(version=version, unchanged=True,
                                cursor=CURSOR_ACCEPTED, isolated=isolated)
            else:
                cursor_state = CURSOR_ACCEPTED
        else:
            cursor_state = CURSOR_ABSENT

        if _pause is not None:  # pragma: no cover - exercised by one test
            reached, released = _pause
            reached.set()
            released.wait(timeout=10)

        page = queues.waiting(selectors.visible_orders(
            permissions, floor=FloorChoices.B1,
            status=OrderStatus.PREPARING, types=[],
        ))

    return Snapshot(
        version=version,
        orders=page.orders,
        total=page.total,
        has_more=page.has_more,
        complete=not page.has_more,
        unchanged=False,
        cursor=cursor_state,
        isolated=isolated,
    )

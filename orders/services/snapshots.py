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
  seen. With `>` a screen would never refetch again; with a generation the
  whole version differs and `!=` is all a screen needs (12A3 rotates it);
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
    arrived in. Hashed rather than listed because it travels to the browser in
    a version string, and the set of permissions an account holds is not
    something a version needs to spell out.
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

    Nested it is also *moot*: an enclosing transaction has its own snapshot
    already, and the commits this isolation level exists to keep out are not
    visible inside one anyway. Which is why the answer is to report rather
    than to refuse -- the first version raised, and the only thing that
    achieved was making the endpoint unreachable from every `TestCase` in the
    repository, a cost paid for a guarantee that was not being lost.

    What must not happen is production quietly ending up here, so the caller
    carries the answer out on the `Snapshot` and
    `test_snapshot_consistency.py` pins that no deployment setting wraps a
    request in a transaction.
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
    # is true whoever opened it.
    isolated = not connection.in_atomic_block

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

        # Imported here, not at module scope. `selectors` lives under `views/`
        # although it is a query module, so a service importing it at import
        # time would make `orders.services` depend on `orders.views` while
        # both are still being set up. Calling it is right -- the alternative
        # is a second copy of the kitchen board's query, which would drift --
        # and moving it into `services/` belongs with step 11's cleanup.
        from orders.views import selectors

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

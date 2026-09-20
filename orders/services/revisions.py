"""Moving the marker, and the rules that make it trustworthy (10B, D-019).

Three rules, each of which a test pins:

1. **Only inside a transaction.** The marker says "something committed". Moving
   it from code that then fails would send every screen to refetch a change
   that does not exist, and nothing would ever undo it.

2. **Locked last.** The counter row is the last row a writer locks that any
   other writer could also be holding. Order creation locks the number
   counter; cooking progress locks the order and then its item. If the marker
   were taken first, two writers acquiring in opposite directions would
   deadlock -- exactly the reversal the blueprint asked to be reproduced.
   Taken last, it cannot be the middle of a cycle.

   Stated precisely, because the first version of this sentence said "nothing
   is acquired after it" and that was not true: Django writes an admin
   `LogEntry` after `save_related` returns, and `marker_contention.py` is not
   the only thing that could add a write later. What matters is narrower and
   is what holds -- no row another writer contends for is taken afterwards.
   The admin used to break even the narrow version by marking in `save_model`
   and then writing inline items; that is fixed in `orders/admin.py` and the
   reason is recorded there (PR #77 security review).

3. **The value is opaque.** It is not a count of changes and nothing should
   read it as one: one admin save that rewrites the note, three lines and the
   total moves it by one, and so does one new order. A reader compares it with
   the value it holds and refetches when they differ -- that is the entire
   protocol, and it is what "latest state converges" (D-019) means as opposed
   to replaying transitions.

What this deliberately does *not* do is stamp a revision onto each order row.
Rule 2 forbids it: the marker's value does not exist until the end of the
transaction, and PostgreSQL cannot defer a CHECK, so a row could not be
inserted already carrying one. Convergence does not need it either -- 10C's
snapshot carries the marker for the whole read, not per row. If an incremental
protocol is ever wanted, that is a new decision and a new column.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction

from orders.models import BOARD, ChangeRevision


class NotInTransaction(RuntimeError):
    """Raised when the marker would move for work that has not committed."""

    def __init__(self):
        super().__init__(
            "변경 표시는 트랜잭션 안에서만 옮길 수 있습니다. "
            "쓰기와 같은 transaction.atomic() 블록에서 호출하세요."
        )


def current() -> int:
    """The last committed value. What a screen holds and compares.

    Zero when the row has somehow not been created yet, which reads as "older
    than everything" -- so a screen refetches once rather than believing it is
    up to date.
    """
    value = (
        ChangeRevision.objects.filter(scope=BOARD)
        .values_list("value", flat=True)
        .first()
    )
    return int(value or 0)


def _counter() -> ChangeRevision:
    """The counter row, locked for the rest of this transaction.

    The row is created by migration 0028, so the create below is a fallback
    for a database that predates it or had the row removed by hand. It runs in
    a savepoint because two writers can reach it at once and the loser of that
    race must be able to continue rather than lose its whole transaction.
    """
    row = ChangeRevision.objects.select_for_update().filter(scope=BOARD).first()
    if row is not None:
        return row
    try:
        with transaction.atomic():
            ChangeRevision.objects.create(scope=BOARD, value=0)
    except IntegrityError:
        # Someone else created it between the read and the insert. Their row is
        # the one to lock. Only this one exception is expected here: catching
        # anything else would swallow a missing table, a missing INSERT grant
        # or a connection failure, and re-raise it one line later as an opaque
        # DoesNotExist -- from *every* write endpoint at once, since nearly all
        # of them mark. The cause has to stay visible (PR #77 security review).
        pass
    return ChangeRevision.objects.select_for_update().get(scope=BOARD)


def mark() -> int:
    """Record that something a screen can see has changed. Returns the new value.

    Call this once, as the last thing in the writing transaction.
    """
    if not transaction.get_connection().in_atomic_block:
        raise NotInTransaction()
    row = _counter()
    row.value += 1
    row.save(update_fields=["value"])
    return row.value


def save_and_mark(instance, **fields) -> int:
    """Change display state outside the order tables, and say so.

    Menu prices, tables and event days are edited through the admin, which has
    its own marked path. This is the same operation for code -- a management
    task, a shell, a future endpoint -- so that neither route is the one that
    quietly leaves the board stale.
    """
    if not fields:
        # `update_fields=None` is a full-row save, so calling this with nothing
        # to change would write every field from whatever the in-memory object
        # happens to hold -- overwriting a concurrent edit with stale values
        # while looking like a no-op. Say so instead (PR #77 code review).
        raise ValueError("save_and_mark() needs at least one field to change; "
                         "to announce a change without writing, call mark().")
    with transaction.atomic():
        for name, value in fields.items():
            setattr(instance, name, value)
        instance.save(update_fields=list(fields))
        return mark()


def delete_and_mark(instance) -> int:
    """Remove display state, and say so."""
    with transaction.atomic():
        instance.delete()
        return mark()

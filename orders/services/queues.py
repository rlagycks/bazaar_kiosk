"""How many orders a listing returns, and in which direction (8B, D-055).

The order list answered two different questions with one shape: newest
first, cut at the caller's `limit`. For a look back that is right. For the
kitchen board it was backwards -- the orders it dropped were the ones that
had waited longest, and the response said nothing about them, so a busy
evening quietly hid the work that was most overdue (BK-R009).

So the two questions are separated here:

* **waiting** -- orders still being prepared. A work queue: oldest first,
  and complete. The caller's `limit` cannot shorten it, because a queue is
  not a page and a volunteer asking for one screenful must not thereby stop
  being told what is outstanding.
* **looking back** -- anything else. A page: newest first, `limit` honoured.

Both report the true total and whether the page holds all of it, so a cut is
always something the screen can say out loud rather than an absence.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import QuerySet

# The queue is complete in every situation this kitchen can reach: a bazaar
# that has 500 orders outstanding at once has stopped cooking. The bound is
# here so one screen refresh cannot ask the database for an unbounded row
# count, and when it bites the remainder is reported, never dropped.
MAX_QUEUE = 500

# Which contract answered. The response carries it so a caller whose `limit`
# was ignored learns that from the answer rather than from this file.
QUEUE = "queue"
PAGE = "page"

DEFAULT_PAGE = 50
MAX_PAGE = 200


@dataclass(frozen=True)
class Page:
    """A slice of a listing, and the size of the thing it was cut from."""

    orders: list
    total: int
    has_more: bool


def _page(queryset: QuerySet, ordering: tuple[str, ...], size: int) -> Page:
    """One slice, and a count only when the slice did not hold everything.

    Reading `size + 1` rows answers "is there more?" from the rows
    themselves. When the answer is no -- the kitchen board's ordinary case,
    and every history page shorter than its limit -- the total is the number
    of rows in hand and no `COUNT(*)` runs at all. That matters because this
    endpoint is polled, and counting means fully evaluating the `Exists`
    semi-join over every order item rather than stopping at the limit
    (measured at ~25-60ms on a 100k-order table; PR #73 DB review).

    It also removes a race in that case. A separate count is its own
    statement under READ COMMITTED, so a status change landing between the
    two could report a total that disagreed with the rows beside it. Here the
    two come from one statement. When the bound does bite the count still
    runs separately, and then `total` is a figure for the screen to show, not
    something the rows have to agree with.
    """
    rows = list(queryset.order_by(*ordering)[:size + 1])
    if len(rows) <= size:
        return Page(orders=rows, total=len(rows), has_more=False)
    return Page(orders=rows[:size], total=queryset.count(), has_more=True)


def waiting(queryset: QuerySet) -> Page:
    """Everything still to cook, longest wait first."""
    return _page(queryset, ("created_at", "id"), MAX_QUEUE)


def looking_back(queryset: QuerySet, limit: int) -> Page:
    """A page of what already happened, most recent first."""
    return _page(queryset, ("-created_at", "-id"), clean_limit(limit))


def clean_limit(value) -> int:
    """A page size from a query string, bounded."""
    try:
        size = int(value)
    except (TypeError, ValueError):
        return DEFAULT_PAGE
    return max(1, min(size, MAX_PAGE))

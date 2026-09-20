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

DEFAULT_PAGE = 50
MAX_PAGE = 200


@dataclass(frozen=True)
class Page:
    """A slice of a listing, and the size of the thing it was cut from."""

    orders: list
    total: int
    has_more: bool


def _page(queryset: QuerySet, ordering: tuple[str, ...], size: int) -> Page:
    total = queryset.count()
    orders = list(queryset.order_by(*ordering)[:size])
    return Page(orders=orders, total=total, has_more=total > len(orders))


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

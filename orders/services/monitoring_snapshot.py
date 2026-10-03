"""UI-05B: waiting work and all-status history from one PostgreSQL instant.

History includes every date and status, newest first, in fixed 50-row pages.
An out-of-range page stays empty and retains its requested page number;
clients can return to min(page - 1, pages) when has_previous is true.
Only truncating the waiting queue makes complete false. History pagination
is deliberate and does not prevent a monitor from quiescing its SSE polling.

On unchanged, both orders arrays are empty (retain the previously drawn
rows); count is the number of waiting rows transmitted, hence zero. Totals,
navigation and queue completeness still describe the current snapshot.
"""

from __future__ import annotations

from django.db import connection, transaction

from orders.models import FloorChoices, OrderStatus
from orders.roles import HALL_MONITOR, TAKEOUT_MONITOR
from orders.services import queues, revisions, scope, snapshots
from orders.views import selectors, serializers


HISTORY_PAGE_SIZE = 50
MAX_PAGE_NUMBER = 1_000_000
REPRESENTATION_VERSION = "monitoring-v1"
REQUIRED_PERMISSIONS = {
    scope.HALL: frozenset((HALL_MONITOR,)),
    scope.TAKEOUT: frozenset((TAKEOUT_MONITOR,)),
    "ALL": frozenset((HALL_MONITOR, TAKEOUT_MONITOR)),
}


def read(permissions, *, mode: str = "ALL", page: int = 1,
         since: str | None = None) -> dict:
    """Authorize, narrow before either limit, and fully serialize atomically.

The HTTP guard supplies freshly checked server permissions. STATS never
substitutes for a monitor permission here, even though the shared generic
order selector intentionally allows STATS to read everything.

Unlike the legacy waiting service, do not silently degrade to READ COMMITTED
when nested. The endpoint opts out of ATOMIC_REQUESTS, and service callers
must let this function own its transaction to preserve the read contract.
"""
    if mode not in REQUIRED_PERMISSIONS:
        raise ValueError("scope must be HALL, TAKEOUT or ALL")
    if type(page) is not int or not 1 <= page <= MAX_PAGE_NUMBER:
        raise ValueError("page must be an integer between 1 and 1000000")
    held = frozenset(permissions)
    required = REQUIRED_PERMISSIONS[mode]
    if not required <= held:
        raise PermissionError("monitor permission required for the requested scope")

    isolated = not connection.in_atomic_block and connection.get_autocommit()
    if not isolated:
        raise RuntimeError("monitoring snapshot must own its REPEATABLE READ transaction")

    with transaction.atomic():
        snapshots._isolate(isolated)
        generation, value = revisions.state()
        # Keep the common generation:value:digest form, but this representation
        # cannot be confused with waiting-only, another page, or another mode.
        cursor_scope = (*held, f"representation={REPRESENTATION_VERSION}",
                        f"mode={mode}", f"page={page}")
        version = snapshots.version_from(value, cursor_scope, generation=generation)
        cursor = snapshots.CURSOR_ABSENT
        if since:
            cursor = (snapshots.CURSOR_ACCEPTED
                      if snapshots._same_lineage_and_scope(since, version)
                      else snapshots.CURSOR_REJECTED)
        unchanged = bool(since) and since == version

        # First apply the actual server monitor permissions (without STATS's
        # generic read bypass), then the explicitly requested classification.
        visible = selectors.visible_orders(
            held & REQUIRED_PERMISSIONS["ALL"], floor=FloorChoices.B1,
            status="", types=[],
        )
        visible = scope.visible(visible, required)
        waiting = visible.filter(status=OrderStatus.PREPARING)
        if unchanged:
            waiting_orders = []
            waiting_total = waiting.count()
            has_more = waiting_total > queues.MAX_QUEUE
        else:
            queue = queues.waiting(waiting)
            waiting_orders = [serializers.order(order) for order in queue.orders]
            waiting_total = queue.total
            has_more = queue.has_more

        history_total = visible.count()
        pages = (history_total + HISTORY_PAGE_SIZE - 1) // HISTORY_PAGE_SIZE
        history_orders = []
        if not unchanged and page <= pages:
            offset = (page - 1) * HISTORY_PAGE_SIZE
            history_orders = [
                serializers.order(order)
                for order in visible.order_by("-created_at", "-id")[offset:offset + HISTORY_PAGE_SIZE]
            ]

        # No model instances or lazy relation reads may leave this block.
        return {
            "version": version,
            "unchanged": unchanged,
            "cursor": cursor,
            "orders": waiting_orders,
            "count": len(waiting_orders),
            "total": waiting_total,
            "has_more": has_more,
            "complete": not has_more,
            "history": {
                "orders": history_orders,
                "total": history_total,
                "page": page,
                "pages": pages,
                "has_previous": page > 1 and pages > 0,
                "has_next": page < pages,
            },
        }

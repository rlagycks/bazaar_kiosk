"""The one place an order's status changes (6B, D-050).

Two writers used to disagree about what an order may become. The status
endpoint saved whatever it was sent -- a cancelled order revived with one PATCH
-- while the cooking endpoint refused to touch a cancelled order at all.
Neither took a lock, so a cancel racing a progress update could be lost.

Both go through here now, and here there is a table:

    PREPARING -> READY, CANCELLED
    READY     -> PREPARING, CANCELLED
    CANCELLED -> (nothing)

Cancelling is final because a cancelled order leaves the sales figures (D-048)
and bringing it back would move money again. READY may step back because the
kitchen mistypes and nothing about the money changes.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import F

from django.utils import timezone

from orders.models import Order, OrderStatus, OrderType
from orders.services import audit, revisions

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    OrderStatus.PREPARING: frozenset({OrderStatus.READY, OrderStatus.CANCELLED}),
    OrderStatus.READY: frozenset({OrderStatus.PREPARING, OrderStatus.CANCELLED}),
    # Deliberately empty: this is the user's decision, not an oversight.
    OrderStatus.CANCELLED: frozenset(),
}

_REFUSAL_REASON = {
    OrderStatus.CANCELLED: "취소된 주문은 상태를 바꿀 수 없습니다.",
}


class TransitionRefused(Exception):
    """The order cannot become what the caller asked for."""

    def __init__(self, current: str, target: str):
        self.current = current
        self.target = target
        self.detail = _REFUSAL_REASON.get(
            current, f"{current} 상태에서 {target}(으)로 바꿀 수 없습니다."
        )
        super().__init__(self.detail)


def locked(order_id: int) -> Order:
    """The order, held for the rest of the caller's transaction.

    Every status decision reads the current value first, so the read and the
    write have to be one step. Without the lock two requests both read
    PREPARING and the later write wins, which is how a cancel used to vanish.
    """
    return Order.objects.select_for_update().get(pk=order_id)


def mixed_not_ready(order: Order) -> bool:
    """A mixed order is READY only with both sides prepared and the hall
    part departed (D-075). Pure orders keep their old transition rules."""
    items = list(order.items.all())
    mixed = {i.service_mode for i in items} == {OrderType.DINE_IN, OrderType.TAKEOUT}
    return mixed and (order.departed_at is None or any(i.remaining_qty for i in items))


def change(order: Order, target: str) -> bool:
    """Apply a status change. Returns whether anything changed.

    Asking for the status the order already has is not an error: a client
    retrying a request it never saw answered would otherwise be told its order
    is in conflict with itself.
    """
    if order.status == target:
        return False
    if target not in ALLOWED_TRANSITIONS.get(order.status, frozenset()):
        raise TransitionRefused(order.status, target)
    if target == OrderStatus.READY and mixed_not_ready(order):
        # D-075: older status endpoints/admin actions cannot bypass either
        # side. The hall caller records departure before this transition.
        raise TransitionRefused(order.status, target)
    order.status = target
    fields = ["status", "updated_at"]
    if target == OrderStatus.PREPARING:
        order.departed_at = None
        fields.append("departed_at")
    order.save(update_fields=fields)
    return True


def sync_from_items(order: Order, actor=None) -> bool:
    """Bring the status in line with the quantities after any line write.

    D-076 (user decision 2026-10-03) replaces UI-05B's explicit-only
    departure: preparing every quantity *is* the completion. For every writer
    (hall monitor, takeout batch, old quantity endpoint, admin line edits):

    * every hall line prepared records the hall departure -- for a mixed order
      this takes it off the hall list while takeout is still waiting; a hall
      line falling short again clears it;
    * every line prepared makes the order READY; anything short reopens a
      READY order. A reopened pure takeout order has no departure to keep.

    The explicit "완료 · 서빙 출발" action stays as the one-step shortcut that
    fills the hall lines. Records the DEPARTED event for a mixed order (the
    pure hall departure is told by its READY event); callers still record
    STATUS. Returns whether the order row changed so callers can mark it.
    """
    if order.status == OrderStatus.CANCELLED:
        return False
    # Python ordering keeps a caller's prefetched, locked rows (takeout batch).
    items = sorted(order.items.all(), key=lambda item: item.pk)
    hall = [item for item in items if item.service_mode == OrderType.DINE_IN]
    mixed = bool(hall) and len(hall) != len(items)
    pending = any(item.prepared_qty < item.qty for item in items)
    status, departed_at = order.status, order.departed_at
    if hall and any(item.prepared_qty < item.qty for item in hall):
        departed_at = None
    elif hall and departed_at is None and status != OrderStatus.READY:
        # An already READY order without one predates UI-05B: stamping "now"
        # would invent a departure time (PR #103 review).
        departed_at = timezone.now()
    if pending and status == OrderStatus.READY:
        status = OrderStatus.PREPARING
        if not hall:
            departed_at = None
    elif not pending and status == OrderStatus.PREPARING:
        status = OrderStatus.READY
    if (status, departed_at) == (order.status, order.departed_at):
        return False
    departed = order.departed_at is None and departed_at is not None
    order.status, order.departed_at = status, departed_at
    order.save(update_fields=["status", "departed_at", "updated_at"])
    if departed and mixed:
        audit.record_departure(order, actor)
    return True


def is_closed(order: Order) -> bool:
    return order.status == OrderStatus.CANCELLED


@transaction.atomic
def change_by_id(order_id: int, target: str) -> Order:
    """Lock, decide, write. The transaction is what makes it one step.

    No production caller today -- both endpoints lock the order themselves and
    call `change` -- but it owns its transaction, so it owns the marker too
    (10B). Leaving it unmarked would make it a trap for whoever wires it up:
    the status would change and no screen would hear about it.
    """
    order = locked(order_id)
    if change(order, target):
        revisions.mark()
    return order

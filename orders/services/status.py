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

from orders.models import Order, OrderStatus, OrderType
from orders.services import revisions

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


def sync_from_items(order: Order) -> None:
    """Bring the status in line with the quantities after any line write.

    UI-05B separates food preparation from explicit serving departure, so a
    pure hall order is never completed by quantities alone. D-075 adds the
    takeout side, for every writer (takeout batch, monitor, old quantity
    endpoint, admin line edits):

    * incomplete quantities reopen READY; reopening only takeout keeps an
      already served hall part's departure;
    * a pure takeout order whose quantities are all prepared is READY -- it
      has no serving departure;
    * a mixed order is READY once every quantity is prepared *and* its hall
      part has departed; a READY mixed order without that departure (an
      admin edit that added a hall line) goes back to PREPARING.

    Without the promotion an order finished outside the takeout batch would
    sit PREPARING with nothing left on any screen (PR review H1).
    """
    if order.status == OrderStatus.CANCELLED:
        return
    items = list(order.items.order_by("id"))
    pending = [item for item in items if item.prepared_qty < item.qty]
    modes = {item.service_mode for item in items}
    has_hall, has_takeout = OrderType.DINE_IN in modes, OrderType.TAKEOUT in modes
    if pending:
        if order.status == OrderStatus.READY:
            order.status = OrderStatus.PREPARING
            if not has_hall or any(item.service_mode == OrderType.DINE_IN for item in pending):
                order.departed_at = None
            order.save(update_fields=["status", "departed_at", "updated_at"])
        elif order.status == OrderStatus.PREPARING and order.departed_at is not None and any(
                item.service_mode == OrderType.DINE_IN for item in pending):
            order.departed_at = None
            order.save(update_fields=["departed_at", "updated_at"])
        return
    if not has_takeout:
        return  # pure hall: departure stays explicit
    hall_done = not has_hall or order.departed_at is not None
    if order.status == OrderStatus.PREPARING and hall_done:
        order.status = OrderStatus.READY
        order.save(update_fields=["status", "updated_at"])
    elif order.status == OrderStatus.READY and not hall_done:
        order.status = OrderStatus.PREPARING
        order.save(update_fields=["status", "updated_at"])


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

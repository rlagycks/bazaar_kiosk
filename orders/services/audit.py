"""Record who changed an order (D-051). Call inside the change's transaction."""
from __future__ import annotations

from orders.models import Account, Order, OrderEvent, OrderEventKind, OrderItem


def record_created(order: Order, actor: Account | None) -> OrderEvent:
    return OrderEvent.objects.create(order=order, actor=actor, kind=OrderEventKind.CREATED,
                                     to_status=order.status)


def record_status(order: Order, actor: Account | None, *, previous: str) -> OrderEvent:
    return OrderEvent.objects.create(order=order, actor=actor, kind=OrderEventKind.STATUS,
                                     from_status=previous, to_status=order.status)


def record_progress(order: Order, item: OrderItem, actor: Account | None) -> OrderEvent:
    return OrderEvent.objects.create(order=order, actor=actor, kind=OrderEventKind.PROGRESS,
                                     item=item, prepared_qty=item.prepared_qty)


def record_items(order: Order, actor: Account | None) -> OrderEvent:
    """The lines were changed after the fact (7B); the order row carries the
    new total, this row carries that it happened and by whom."""
    return OrderEvent.objects.create(order=order, actor=actor, kind=OrderEventKind.ITEMS,
                                     to_status=order.status)

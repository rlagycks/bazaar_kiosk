"""Which orders a monitor may see and change (D-051).

The hall and takeout monitors are separate permissions, so the boundary
between them is the server's, not a display filter. The rule is the one the
kitchen screen already used: an order with any dine-in item belongs to the
hall (a mixed order is a hall order); an order whose items are all takeout is
a takeout order. The two are exclusive and together cover everything.

STATS reads everything. An account holding both monitor permissions sees
everything a kitchen used to.
"""
from __future__ import annotations

from django.db.models import Exists, OuterRef, QuerySet

from orders.models import Order, OrderItem, OrderType
from orders.roles import HALL_MONITOR, STATS, TAKEOUT_MONITOR

HALL = "HALL"
TAKEOUT = "TAKEOUT"


def classify(order: Order) -> str:
    """HALL when any item is dine-in, TAKEOUT otherwise."""
    items = order.items.all()
    if any(item.service_mode == OrderType.DINE_IN for item in items):
        return HALL
    return TAKEOUT


def _has_dine_in_item():
    return Exists(
        OrderItem.objects.filter(order_id=OuterRef("pk"), service_mode=OrderType.DINE_IN)
    )


def visible(queryset: QuerySet, permissions) -> QuerySet:
    """Narrow an order queryset to what these permissions may read."""
    held = frozenset(permissions)
    if STATS in held or (HALL_MONITOR in held and TAKEOUT_MONITOR in held):
        return queryset
    if HALL_MONITOR in held:
        return queryset.filter(_has_dine_in_item())
    if TAKEOUT_MONITOR in held:
        return queryset.filter(~_has_dine_in_item())
    return queryset.none()


def may_read(order: Order, permissions) -> bool:
    held = frozenset(permissions)
    if STATS in held:
        return True
    return may_change(order, held)


def may_change(order: Order, permissions) -> bool:
    """Only a monitor of the order's own classification may change it."""
    held = frozenset(permissions)
    needed = HALL_MONITOR if classify(order) == HALL else TAKEOUT_MONITOR
    return needed in held

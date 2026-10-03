"""The reads the API performs (9, BK-R024).

The list query was assembled inline in the request handler, so the shape of
what the kitchen board asks for could only be seen by reading around the
HTTP branching. It is one function here. The scope narrowing (D-051) stays
first, before any filter and before any cut, which is the property 8B's
tests pin.
"""

from __future__ import annotations

from django.db.models import QuerySet

from orders.models import FloorChoices, Order, OrderStatus
from orders.services import scope

STATUSES = (OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.CANCELLED)


def base() -> QuerySet:
    return (
        Order.objects.select_related("table")
        .prefetch_related("items", "items__menu_item")
    )


def visible_orders(permissions, *, floor: str, status: str, types: list[str]) -> QuerySet:
    """The order list a caller may see, filtered but not yet cut.

    `floor` is validated by the caller: only B1 exists, and anything else is
    a refusal rather than an empty page.
    """
    qs = scope.visible(base(), permissions)
    if floor == FloorChoices.B1:
        qs = qs.filter(floor=floor)
    if status in STATUSES:
        qs = qs.filter(status=status)
    if types:
        qs = qs.filter(order_type__in=types)
    return qs

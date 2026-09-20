"""Recomputing an order's total from its lines.

No production caller today: the order endpoint computes the total before it
writes anything (D-054), and the admin goes through `order_edits`. It is kept
because it is the rescue path -- the thing to reach for when a total and its
lines have been made to disagree -- and step 11 decides whether to keep it.

10B gave it a transaction and a mark. It had neither, which meant calling it
wrote `total_price` outside any transaction and left every screen showing the
old total with no way to learn otherwise. A rescue that silently breaks the
board is not one.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Sum, F

from orders.models import Order
from orders.services import revisions


def recalc_totals(order: Order) -> None:
    with transaction.atomic():
        agg = order.items.aggregate(total=Sum(F("qty") * F("unit_price")))
        total = int(agg["total"] or 0)
        Order.objects.filter(pk=order.pk).update(total_price=total)
        order.total_price = total
        revisions.mark()

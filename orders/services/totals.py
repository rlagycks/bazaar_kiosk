from __future__ import annotations
from django.db.models import Sum, F
from orders.models import Order


def recalc_totals(order: Order) -> None:
    agg = order.items.aggregate(total=Sum(F("qty") * F("unit_price")))
    total = int(agg["total"] or 0)
    Order.objects.filter(pk=order.pk).update(total_price=total)
    order.total_price = total
"""An order as the API returns it (9, BK-R024).

Moved out of the view module unchanged. Every field, and the reading of the
old money shapes (7C, D-054), is exactly what the view produced before --
this is where the response contract lives now, so a change to it is visible
as a change to this file rather than buried in a request handler.
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from orders.models import NumberSeries, Order, PaymentMethod
from orders.services import payments


def order(o: Order) -> dict[str, Any]:
    cash_amount = o.received_cash_amount
    ticket_amount = o.received_ticket_amount
    if cash_amount is None:
        cash_amount = o.received_amount if o.payment_method == PaymentMethod.CASH else 0
    if ticket_amount is None:
        ticket_amount = o.received_amount if o.payment_method == PaymentMethod.TICKET else 0
    # 7A: stored at creation since 0026; older rows are computed the old way.
    change_amount = o.change_amount
    if change_amount is None:
        change_amount = payments.change_for(cash=cash_amount, ticket=ticket_amount, total=o.total_price)
    return {
        "id": o.id,
        "floor": o.floor,
        "order_type": o.order_type,
        "status": o.status,
        "order_no": o.order_no,
        "order_date": o.order_date.isoformat() if o.order_date else None,
        # D-047: the kitchen shows practice orders, marked; sales leave them out.
        "number_series": o.number_series,
        "is_practice": o.number_series == NumberSeries.PRACTICE,
        "table": ({"id": o.table_id, "number": o.table.number, "name": o.table.name} if o.table_id else None),
        "is_takeout": o.is_takeout,
        "payment_method": o.payment_method,
        "received_amount": o.received_amount,
        "received_cash_amount": cash_amount or 0,
        "received_ticket_amount": ticket_amount or 0,
        "total_price": o.total_price,
        "note": o.note,
        "change_amount": change_amount,
        "created_at": timezone.localtime(o.created_at).isoformat(),
        "items": [
            {
                "id": i.id,
                "menu_item": {"id": i.menu_item_id, "name": i.menu_item.name, "price": i.unit_price},
                "menu_item_name": i.menu_item.name,
                "qty": i.qty,
                "unit_price": i.unit_price,
                "line_total": i.qty * (i.unit_price or 0),
                "service_mode": i.service_mode,
                "prepared_qty": i.prepared_qty,
                "remaining_qty": i.remaining_qty,
                "is_prepared": i.is_prepared,
            }
            for i in o.items.all()
        ],
    }

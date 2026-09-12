from __future__ import annotations
from django.db import connection, IntegrityError, NotSupportedError
from django.utils import timezone

from orders.models import Order, FloorChoices


def allocate_floor_order_no(order: Order) -> None:
    """Allocate through PostgreSQL sequences; unsupported backends fail closed."""
    if connection.vendor != "postgresql":
        raise NotSupportedError("Order numbering requires PostgreSQL")
    _allocate_via_sequence(order)


def _sequence_name(floor: str | None) -> str:
    floor_code = (floor or FloorChoices.B1).lower()
    return f"orders_floor_{floor_code}_seq"


def _allocate_via_sequence(order: Order) -> None:
    seq_name = _sequence_name(order.floor)
    today = timezone.localdate()
    while True:
        with connection.cursor() as cursor:
            cursor.execute("SELECT nextval(%s)", [seq_name])
            next_no = cursor.fetchone()[0]
        try:
            Order.objects.filter(pk=order.pk).update(order_no=next_no, order_date=today)
        except IntegrityError as exc:
            message = exc.__cause__.diag.constraint_name if getattr(exc.__cause__, "diag", None) else str(exc)
            if message and "uq_floor_date_no" in message:
                continue
            raise
        order.order_no = next_no
        order.order_date = today
        break

from __future__ import annotations
from django.db import connection, transaction, IntegrityError
from django.db.models import F
from django.utils import timezone

from orders.models import FloorOrderCounter, Order, FloorChoices


def allocate_floor_order_no(order: Order, max_retries: int = 3) -> None:
    """
    Allocate an order number for the given order.

    * PostgreSQL: uses dedicated SEQUENCE per floor to avoid row-level lock contention.
    * Others (e.g. SQLite): falls back to legacy FloorOrderCounter logic.
    """
    if connection.vendor == "postgresql":
        _allocate_via_sequence(order)
    else:
        _allocate_via_counter(order, max_retries=max_retries)


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


def _allocate_via_counter(order: Order, *, max_retries: int) -> None:
    today = timezone.localdate()
    for attempt in range(max_retries):
        try:
            with transaction.atomic():
                fc, _ = FloorOrderCounter.objects.get_or_create(
                    date=today, floor=order.floor, defaults={"last_no": 0}
                )
                FloorOrderCounter.objects.filter(pk=fc.pk).update(last_no=F("last_no") + 1)
                fc.refresh_from_db(fields=["last_no"])

                Order.objects.filter(pk=order.pk).update(order_no=fc.last_no, order_date=today)
                order.order_no = fc.last_no
                order.order_date = today
            return
        except IntegrityError:
            if attempt == max_retries - 1:
                raise

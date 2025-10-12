from __future__ import annotations
from django.db import transaction, IntegrityError
from django.db.models import F
from django.utils import timezone

from orders.models import FloorOrderCounter, Order


def allocate_floor_order_no(order: Order, max_retries: int = 3) -> None:
    """층별 · 당일 연속 주문번호 부여 (SQLite/PG 공통, FOR UPDATE 없이 F() 증가)"""
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

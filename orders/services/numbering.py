"""Order number allocation (D-047).

The number a customer is called by. Two rules decide it:

* the series -- an order created on a day registered in EventDay belongs to the
  event, everything else is a rehearsal and counts in its own series;
* the scope -- numbers restart at 1 each year, per floor, per series.

Allocation takes a row lock on the counter and holds it until the surrounding
transaction ends. That serialises concurrent orders, which is what makes the
numbers both unique and gap-free: the previous sequence-based allocation
advanced even when the order was rolled back, leaving holes in numbers that get
read aloud and written on paper.
"""

from __future__ import annotations

from django.db import (
    IntegrityError,
    NotSupportedError,
    connection,
    transaction,
)
from django.db.transaction import TransactionManagementError
from django.db.models import Max
from django.utils import timezone

from orders.models import EventDay, FloorChoices, NumberSeries, Order, OrderNumberCounter

# A conflict means a row already holds the number the counter offered, which
# only happens if orders were written without going through this function. Each
# retry resyncs the counter past every existing number, so one retry is enough
# in practice; the bound stops an unforeseen loop rather than papering over it.
MAX_ATTEMPTS = 5


def series_for(day) -> str:
    """Which series a given day belongs to. Public: screens warn with it."""
    if EventDay.objects.filter(date=day).exists():
        return NumberSeries.REAL
    return NumberSeries.PRACTICE


def allocate_floor_order_no(order: Order) -> None:
    """Assign order_no, order_date and number_series; unsupported backends fail closed."""
    if connection.vendor != "postgresql":
        raise NotSupportedError("Order numbering requires PostgreSQL")
    if not connection.in_atomic_block:
        # The counter lock must live as long as the order it numbers. Outside a
        # transaction it would be released immediately and a rolled-back order
        # would still consume its number.
        raise TransactionManagementError(
            "Order numbering must run inside the transaction that creates the order"
        )

    today = timezone.localdate()
    floor = order.floor or FloorChoices.B1
    series = series_for(today)

    for _ in range(MAX_ATTEMPTS):
        counter = _locked_counter(series, today.year, floor)
        next_no = counter.last_no + 1
        try:
            # A savepoint: a conflict must not poison the caller's transaction,
            # which is the request transaction that also holds the order rows.
            with transaction.atomic():
                Order.objects.filter(pk=order.pk).update(
                    order_no=next_no, order_date=today, number_series=series
                )
        except IntegrityError as exc:
            if not _is_number_conflict(exc):
                raise
            _resync(counter, series, today.year, floor)
            continue
        OrderNumberCounter.objects.filter(pk=counter.pk).update(last_no=next_no)
        order.order_no = next_no
        order.order_date = today
        order.number_series = series
        return

    raise IntegrityError(
        f"Could not allocate an order number for {floor}/{series}/{today.year} "
        f"after {MAX_ATTEMPTS} attempts"
    )


def _locked_counter(series: str, year: int, floor: str) -> OrderNumberCounter:
    """The counter row for this scope, locked for the rest of the transaction."""
    counter = (
        OrderNumberCounter.objects.select_for_update()
        .filter(series=series, year=year, floor=floor)
        .first()
    )
    if counter is not None:
        return counter
    # First order of the year in this series. Seed from whatever numbers exist
    # so a restored or imported row is not handed out a second time.
    try:
        with transaction.atomic():
            return OrderNumberCounter.objects.create(
                series=series, year=year, floor=floor,
                last_no=_max_existing(series, year, floor),
            )
    except IntegrityError:
        # Another transaction created it first; its INSERT blocked us until it
        # committed, so the row is there now and only needs locking.
        return (
            OrderNumberCounter.objects.select_for_update()
            .get(series=series, year=year, floor=floor)
        )


def _max_existing(series: str, year: int, floor: str) -> int:
    return (
        Order.objects.filter(
            floor=floor, number_series=series, order_date__year=year
        ).aggregate(highest=Max("order_no"))["highest"]
        or 0
    )


def _resync(counter: OrderNumberCounter, series: str, year: int, floor: str) -> None:
    highest = _max_existing(series, year, floor)
    counter.last_no = max(counter.last_no, highest)
    OrderNumberCounter.objects.filter(pk=counter.pk).update(last_no=counter.last_no)


def _is_number_conflict(exc: IntegrityError) -> bool:
    cause = getattr(exc, "__cause__", None)
    diag = getattr(cause, "diag", None)
    name = getattr(diag, "constraint_name", None) if diag else None
    return "uq_floor_series_year_no" in (name or str(exc))

"""The sales report: which days, and what the figures mean (8C, D-053).

The dashboard used to be pinned to one date whatever was asked (BK-R006),
grouped menu lines by their current name so two items called the same thing
became one row (BK-R034), and read cash as the amount handed over with no
account of the change given back.

Now:

* **Period.** With nothing asked, the most recent registered event day that
  is not in the future; today when none is registered (the user's choice,
  D-053). An explicit `start_date`/`end_date` is honoured, inclusive, and a
  malformed or inverted one is refused rather than replaced. Days are the
  order's `order_date`, which numbering assigns in Asia/Seoul (D-047), so
  an order taken at 00:10 belongs to the day the tag says, not to UTC.
* **Revenue.** Event-series orders that are PREPARING or READY. Cancelled
  orders and rehearsals are not revenue (D-047/D-048); cancelled ones are
  counted aside so the operator can see them.
* **Money.** `cash` and `ticket` are what was received; `change` is what
  went back (stored since 7A, derived the same way for older rows); the
  till keeps `net_cash = cash - change`. Rows from before the split fields
  are read the way the order detail reads them and counted, not rewritten
  (D-012 stays open; 7C owns the data).
* **Menu.** Grouped by menu id. The name shown is the menu's current name
  because no name snapshot exists yet (D-008 open); the amount is the price
  the line was sold at.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from django.db.models import Case, Count, F, IntegerField, Q, Sum, Value, When
from django.db.models.functions import Coalesce, Greatest, TruncHour
from django.utils import timezone

from orders.models import (
    EventDay, FloorChoices, NumberSeries, Order, OrderItem, OrderStatus, PaymentMethod,
)

REVENUE_STATUSES = (OrderStatus.PREPARING, OrderStatus.READY)


class PeriodError(ValueError):
    """The requested period cannot be used. The message is for the caller."""


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    basis: str            # "event_day" | "today" | "explicit"
    label: str = ""       # the event day's memo when basis is event_day

    def as_dict(self, floor: str | None) -> dict:
        return {
            "start_date": self.start.isoformat(),
            "end_date": self.end.isoformat(),
            "floor": floor or None,
            "basis": self.basis,
            "label": self.label,
        }


def today(now: datetime | None = None) -> date:
    """Today in the project's time zone (Asia/Seoul), never the server's clock."""
    return timezone.localtime(now or timezone.now()).date()


def _parse_day(raw, field: str) -> date | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise PeriodError(f"{field} 값이 올바르지 않습니다.")
    text = raw.strip()
    if text == "":
        raise PeriodError(f"{field} 값이 비어 있습니다.")
    try:
        return date.fromisoformat(text) if len(text) == 10 else _refuse(field)
    except ValueError:
        return _refuse(field)


def _refuse(field: str):
    raise PeriodError(f"{field}은(는) YYYY-MM-DD 형식이어야 합니다.")


def resolve_period(params, *, today: date | None = None) -> Period:
    """The days the report covers, from the request's parameters."""
    start = _parse_day(params.get("start_date"), "start_date")
    end = _parse_day(params.get("end_date"), "end_date")
    if start or end:
        start = start or end
        end = end or start
        if start > end:
            raise PeriodError("start_date가 end_date보다 늦습니다.")
        return Period(start, end, "explicit")
    day = today or globals()["today"]()
    event = EventDay.objects.filter(date__lte=day).order_by("-date").first()
    if event is not None:
        return Period(event.date, event.date, "event_day", event.label)
    return Period(day, day, "today")


def clean_floor(raw) -> str:
    floor = (raw or "").upper()
    if floor and floor not in FloorChoices.values:
        raise PeriodError("유효하지 않은 floor 값입니다.")
    return floor


# Money as the order detail reads it: the split fields when present, else the
# single legacy figure attributed by payment method. Expressed in SQL so the
# sums are one query and agree with the detail view row for row.
_CASH = Coalesce(
    F("received_cash_amount"),
    Case(When(payment_method=PaymentMethod.CASH, then=F("received_amount")), default=Value(0)),
    Value(0), output_field=IntegerField(),
)
_TICKET = Coalesce(
    F("received_ticket_amount"),
    Case(When(payment_method=PaymentMethod.TICKET, then=F("received_amount")), default=Value(0)),
    Value(0), output_field=IntegerField(),
)
_CHANGE = Coalesce(
    F("change_amount"),
    Greatest(Value(0), _CASH - Greatest(Value(0), Coalesce(F("total_price"), Value(0)) - _TICKET)),
    output_field=IntegerField(),
)
_LEGACY_UNSPLIT = Q(received_cash_amount__isnull=True) & Q(received_ticket_amount__isnull=True)


def dashboard(period: Period, floor: str = "") -> dict:
    """The report for one period, as the counter screen renders it."""
    in_period = Q(order_date__gte=period.start, order_date__lte=period.end, number_series=NumberSeries.REAL)
    if floor:
        in_period &= Q(floor=floor)
    orders = Order.objects.filter(in_period, status__in=REVENUE_STATUSES)
    cancelled = Order.objects.filter(in_period, status=OrderStatus.CANCELLED).count()

    totals = orders.aggregate(
        orders=Count("id"),
        revenue=Coalesce(Sum("total_price"), Value(0)),
        cash=Coalesce(Sum(_CASH), Value(0)),
        ticket=Coalesce(Sum(_TICKET), Value(0)),
        change=Coalesce(Sum(_CHANGE), Value(0)),
        legacy_unsplit=Count("id", filter=_LEGACY_UNSPLIT),
    )

    items = OrderItem.objects.filter(order__in=orders)
    item_totals = items.aggregate(count=Coalesce(Sum("qty"), Value(0)))
    menu = [
        {"menu_item_id": row["menu_item_id"], "name": row["menu_item__name"],
         "qty": row["qty_sum"], "amount": row["amount"] or 0}
        for row in items.values("menu_item_id", "menu_item__name")
        .annotate(qty_sum=Sum("qty"),
                  amount=Sum(F("qty") * F("unit_price"), output_field=IntegerField()))
        .order_by("-qty_sum", "menu_item__name", "menu_item_id")
    ]

    seoul = timezone.get_current_timezone()
    hourly = [
        {"hour": timezone.localtime(row["hour"], seoul).strftime("%H:%M") if row["hour"] else "",
         "orders": row["orders"] or 0, "revenue": row["revenue"] or 0}
        for row in orders.annotate(hour=TruncHour("created_at", tzinfo=seoul))
        .values("hour").annotate(orders=Count("id"), revenue=Sum("total_price")).order_by("hour")
    ]

    received = totals["cash"] + totals["ticket"]
    return {
        "period": period.as_dict(floor),
        "summary": {
            "orders": totals["orders"],
            "items": item_totals["count"],
            "revenue": totals["revenue"],
            "cancelled_orders": cancelled,
            "legacy_unsplit_orders": totals["legacy_unsplit"],
        },
        "payment": {
            "cash": totals["cash"],
            "ticket": totals["ticket"],
            "change": totals["change"],
            "net_cash": totals["cash"] - totals["change"],
            "cash_ratio": totals["cash"] / received if received else 0.0,
            "ticket_ratio": totals["ticket"] / received if received else 0.0,
        },
        "menu": menu,
        "hourly": hourly,
    }

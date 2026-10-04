"""Which orders are still today's work, and which day a history page shows (D-077).

A waiting list is for the work in front of the kitchen. An order left
PREPARING from a rehearsal or an earlier day is not that work: it pushed
itself to the head of every oldest-first queue and, on the takeout monitor,
absorbed completions meant for today's orders. So every waiting list and the
takeout allocation read only orders received today. Older orders stay in the
history, which a monitor can narrow to one day.

The day is the receipt time in Asia/Seoul, the same rule numbering uses for
`order_date`. It is read from `created_at` because every order has one,
including rows from before numbering assigned `order_date`.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from django.db.models import QuerySet
from django.utils import timezone

# fromisoformat alone also accepts week dates such as 2026-W01-1.
_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# A bounded range keeps bounds() away from date.max overflow (9999-12-31).
FIRST_YEAR, LAST_YEAR = 2000, 2100


def today() -> date:
    # From now(), as reporting.today does: localdate() is what numbering
    # tests patch, and that patch says nothing about which orders are waiting.
    return timezone.localtime(timezone.now(), timezone.get_default_timezone()).date()


def bounds(day: date) -> tuple[datetime, datetime]:
    """[start, end) of one Seoul calendar day as aware datetimes."""
    zone = timezone.get_default_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), zone)
    end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min), zone)
    return start, end


def received_on(queryset: QuerySet, day: date) -> QuerySet:
    start, end = bounds(day)
    return queryset.filter(created_at__gte=start, created_at__lt=end)


def current(queryset: QuerySet, day: date | None = None) -> QuerySet:
    """Only orders received today (or on `day`, for tests)."""
    return received_on(queryset, day or today())


def parse_day(raw: str | None) -> date | None:
    """An optional YYYY-MM-DD history filter. Empty means every day."""
    if raw in (None, ""):
        return None
    if not isinstance(raw, str) or not _DAY.fullmatch(raw):
        raise ValueError("date는 YYYY-MM-DD 형식이어야 합니다.")
    try:
        day = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("date는 YYYY-MM-DD 형식이어야 합니다.") from exc
    if not FIRST_YEAR <= day.year <= LAST_YEAR:
        raise ValueError(f"date는 {FIRST_YEAR}~{LAST_YEAR}년이어야 합니다.")
    return day

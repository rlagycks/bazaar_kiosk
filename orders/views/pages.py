# FILE: orders/views/pages.py
from __future__ import annotations
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from orders.models import NumberSeries
from orders.services import series_for
from orders.roles import HALL_MONITOR, SERVING, STATS, TAKEOUT_MONITOR
from .guards import require_permissions


def _account_context(request) -> dict[str, object]:
    """D-051: the screens show who is signed in and link only to the kitchen
    views this account may open."""
    held = getattr(request, "auth_permissions", frozenset())
    return {
        "account_name": getattr(request, "auth_account", None) and request.auth_account.name,
        "can_monitor_hall": HALL_MONITOR in held,
        "can_monitor_takeout": TAKEOUT_MONITOR in held,
        "can_monitor_all": HALL_MONITOR in held and TAKEOUT_MONITOR in held,
    }


def _event_day_context() -> dict[str, object]:
    """D-047: forgetting to register the day turns the whole event into a
    rehearsal, and nothing else on screen would say so. Every ordering screen
    carries the flag."""
    today = timezone.localdate()
    return {
        "is_event_day": series_for(today) == NumberSeries.REAL,
        "today": today,
    }


def _history_context(request):
    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        page = 1
    return {"history_page": max(1, min(page, 1_000_000))}

@ensure_csrf_cookie
@require_permissions(SERVING)
def order_page(request):
    return render(request, "orders/order.html", _event_day_context() | _account_context(request))

@require_permissions(STATS)
def b1_counter_page(request):
    return render(request, "orders/b1_counter.html", _event_day_context() | _account_context(request))


@ensure_csrf_cookie
@require_permissions(all_of=(HALL_MONITOR, TAKEOUT_MONITOR))
def kitchen_overview_page(request):
    context = _event_day_context() | _account_context(request) | _history_context(request) | {
        "page_title": "전체 모니터링",
        "page_hint": "모든 주문을 한 화면에서 관리하세요.",
        "mode_scope": "ALL",
    }
    return render(request, "orders/kitchen_supervisor.html", context)


@ensure_csrf_cookie
@require_permissions(HALL_MONITOR)
def kitchen_hall_page(request):
    context = _event_day_context() | _account_context(request) | _history_context(request) | {
        "page_title": "식당 모니터링",
        "page_hint": "식당 주문 · 혼합 주문 포함",
        "mode_scope": "HALL",
    }
    return render(request, "orders/kitchen_supervisor.html", context)


@ensure_csrf_cookie
@require_permissions(TAKEOUT_MONITOR)
def kitchen_takeout_page(request):
    context = _event_day_context() | _account_context(request) | _history_context(request) | {
        "page_title": "포장 모니터링",
        "page_hint": "포장만 있는 주문",
        "mode_scope": "TAKEOUT",
    }
    return render(request, "orders/kitchen_supervisor.html", context)

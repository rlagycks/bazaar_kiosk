# FILE: orders/views/pages.py
from __future__ import annotations
from django.conf import settings
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from orders.models import NumberSeries
from orders.services import series_for
from orders.roles import HALL_MONITOR, SERVING, STATS, TAKEOUT_MONITOR
from .guards import require_permissions


def _supabase_context() -> dict[str, str]:
    return {
        "supabase_url": settings.SUPABASE_URL,
        "supabase_anon_key": settings.SUPABASE_ANON_KEY,
    }


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

@ensure_csrf_cookie
@require_permissions(SERVING)
def order_page(request):
    return render(request, "orders/order.html", _supabase_context() | _event_day_context() | _account_context(request))

@require_permissions(STATS)
def b1_counter_page(request):
    return render(request, "orders/b1_counter.html", _supabase_context() | _event_day_context() | _account_context(request))


@ensure_csrf_cookie
@require_permissions(all_of=(HALL_MONITOR, TAKEOUT_MONITOR))
def kitchen_overview_page(request):
    context = _supabase_context() | _event_day_context() | _account_context(request) | {
        "page_title": "주방 총괄",
        "page_hint": "모든 주문을 한 화면에서 관리하세요.",
        "mode_scope": "ALL",
    }
    return render(request, "orders/kitchen_supervisor.html", context)


@ensure_csrf_cookie
@require_permissions(HALL_MONITOR)
def kitchen_hall_page(request):
    context = _supabase_context() | _event_day_context() | _account_context(request) | {
        "page_title": "홀 총괄",
        "page_hint": "홀 주문과 홀+포장 주문을 관리하세요.",
        "mode_scope": "HALL",
    }
    return render(request, "orders/kitchen_supervisor.html", context)


@ensure_csrf_cookie
@require_permissions(TAKEOUT_MONITOR)
def kitchen_takeout_page(request):
    context = _supabase_context() | _event_day_context() | _account_context(request) | {
        "page_title": "포장 총괄",
        "page_hint": "순수 포장 주문을 관리하세요.",
        "mode_scope": "TAKEOUT",
    }
    return render(request, "orders/kitchen_supervisor.html", context)
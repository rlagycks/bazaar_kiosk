# FILE: orders/views/pages.py
from __future__ import annotations
from django.conf import settings
from django.shortcuts import render
from .auth import require_roles


def _supabase_context() -> dict[str, str]:
    return {
        "supabase_url": settings.SUPABASE_URL,
        "supabase_anon_key": settings.SUPABASE_ANON_KEY,
    }

@require_roles("ORDER")
def order_page(request):
    return render(request, "orders/order.html", _supabase_context())

@require_roles("B1_COUNTER")
def b1_counter_page(request):
    return render(request, "orders/b1_counter.html", _supabase_context())


@require_roles("KITCHEN", "KITCHEN_HALL", "KITCHEN_TAKEOUT")
def kitchen_overview_page(request):
    context = _supabase_context() | {
        "page_title": "주방 총괄",
        "page_hint": "모든 주문을 한 화면에서 관리하세요.",
        "mode_scope": "ALL",
    }
    return render(request, "orders/kitchen_supervisor.html", context)


@require_roles("KITCHEN_HALL")
def kitchen_hall_page(request):
    context = _supabase_context() | {
        "page_title": "홀 총괄",
        "page_hint": "홀 주문과 홀+포장 주문을 관리하세요.",
        "mode_scope": "HALL",
    }
    return render(request, "orders/kitchen_supervisor.html", context)


@require_roles("KITCHEN_TAKEOUT")
def kitchen_takeout_page(request):
    context = _supabase_context() | {
        "page_title": "포장 총괄",
        "page_hint": "순수 포장 주문을 관리하세요.",
        "mode_scope": "TAKEOUT",
    }
    return render(request, "orders/kitchen_supervisor.html", context)

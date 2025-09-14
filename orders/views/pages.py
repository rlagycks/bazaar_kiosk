# FILE: orders/views/pages.py
from __future__ import annotations
from django.shortcuts import render
from .auth import require_roles

@require_roles("ORDER")
def order_page(request):
    return render(request, "orders/order.html")

@require_roles("B1_COUNTER")
def b1_counter_page(request):
    return render(request, "orders/b1_counter.html")

@require_roles("F1_COUNTER")
def f1_counter_page(request):
    return render(request, "orders/f1_counter.html")

@require_roles("KITCHEN")
def kitchen_page(request):
    return render(request, "orders/kitchen.html")

@require_roles("F1_BOOTH")
def f1_booth_page(request):
    return render(request, "orders/f1_booth.html")
from __future__ import annotations
from django.shortcuts import render


# 주문(모바일): 지하 주문서
def order_page(request):
    return render(request, "orders/order.html")


# 지하 카운터(노트북)
def b1_counter_page(request):
    return render(request, "orders/b1_counter.html")


# 1층 카운터(노트북)
def f1_counter_page(request):
    return render(request, "orders/f1_counter.html")


# 지하 주방(태블릿)
def kitchen_page(request):
    return render(request, "orders/kitchen.html")


# 1층 부스(태블릿)
def f1_booth_page(request):
    return render(request, "orders/f1_booth.html")
# FILE: orders/views/auth.py
from __future__ import annotations
from functools import wraps
from django.conf import settings
from django.shortcuts import render, redirect
from django.urls import reverse

ROLE_TO_URLNAME = {
    "ORDER":       "orders:order",
    "B1_COUNTER":  "orders:b1-counter",
    "F1_COUNTER":  "orders:f1-counter",
    "KITCHEN":     "orders:kitchen",
    "F1_BOOTH":    "orders:f1-booth",
}

def login_view(request):
    roles = ["ORDER", "B1_COUNTER", "F1_COUNTER", "KITCHEN", "F1_BOOTH"]
    if request.method == "POST":
        role = (request.POST.get("role") or "").upper()
        pin  = (request.POST.get("pin") or "").strip()
        expected = settings.ROLE_PINS.get(role)
        if expected and pin == expected and role in ROLE_TO_URLNAME:
            request.session["role"] = role
            return redirect(reverse(ROLE_TO_URLNAME[role]))
        return render(request, "orders/login.html", {
            "roles": roles,
            "error": "역할 또는 PIN이 올바르지 않습니다.",
            "last_role": role,
        }, status=200)
    return render(request, "orders/login.html", {"roles": roles})

def logout_view(request):
    request.session.flush()
    return redirect(reverse("orders:login"))

def require_roles(*allowed_roles: str):
    allowed = {r.upper() for r in allowed_roles if r}
    def deco(viewfunc):
        @wraps(viewfunc)
        def _wrapped(request, *args, **kwargs):
            role = request.session.get("role")
            if not role or (allowed and role.upper() not in allowed):
                return redirect(reverse("orders:login"))
            return viewfunc(request, *args, **kwargs)
        return _wrapped
    return deco

def require_role(role: str):
    return require_roles(role)
# FILE: orders/views/auth.py
from __future__ import annotations
from functools import wraps
from django.conf import settings
from django.shortcuts import render, redirect
from django.urls import reverse

ROLE_DEFINITIONS = [
    ("ORDER",          "서빙",       "서빙 · 주문 입력",       "orders:order"),
    ("B1_COUNTER",     "지하 카운터", "결제 · 모니터링",        "orders:b1-counter"),
    ("KITCHEN",        "주방",        "메뉴별 대기 수량 확인",   "orders:kitchen-monitor"),
    ("KITCHEN_LEAD",   "주방 총괄",   "조리 진행 · 완료 처리",  "orders:kitchen"),
]

ROLE_TO_URLNAME = {code: urlname for code, _, _, urlname in ROLE_DEFINITIONS}
ROLE_LABELS = {code: label for code, label, *_ in ROLE_DEFINITIONS}

def login_view(request):
    role_codes = [code for code, *_ in ROLE_DEFINITIONS]
    role_choices = [(code, ROLE_LABELS.get(code, code)) for code in role_codes]
    role_cards = [
        {
            "code": code,
            "label": label,
            "desc": desc,
            "next": reverse(urlname),
        }
        for code, label, desc, urlname in ROLE_DEFINITIONS
    ]
    if request.method == "POST":
        role = (request.POST.get("role") or "").upper()
        pin  = (request.POST.get("pin") or "").strip()
        expected = settings.ROLE_PINS.get(role)
        if expected and pin == expected and role in ROLE_TO_URLNAME:
            request.session["role"] = role
            return redirect(reverse(ROLE_TO_URLNAME[role]))
        return render(request, "orders/login.html", {
            "roles": role_codes,
            "role_choices": role_choices,
            "role_cards": role_cards,
            "error": "역할 또는 PIN이 올바르지 않습니다.",
            "last_role": role,
        }, status=200)
    return render(request, "orders/login.html", {
        "roles": role_codes,
        "role_choices": role_choices,
        "role_cards": role_cards,
    })

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

# FILE: orders/views/auth.py
from __future__ import annotations
from functools import wraps
from django.conf import settings
from django.shortcuts import render, redirect
from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables

ROLE_DEFINITIONS = [
    ("ORDER",           "주문(서빙)",   "테이블 주문 · 서빙 전용 화면", "orders:order"),
    ("B1_COUNTER",      "주방 카운터",  "결제 · 주문 현황 모니터링",    "orders:b1-counter"),
    ("KITCHEN",         "주방",        "모든 주문을 한 화면에서 확인",  "orders:kitchen"),
    ("KITCHEN_HALL",    "홀 총괄",      "홀 주문 · 혼합 주문 집중 관리", "orders:kitchen-hall"),
    ("KITCHEN_TAKEOUT", "포장 총괄",    "포장 주문만 모아서 확인",      "orders:kitchen-takeout"),
]

ROLE_TO_URLNAME = {code: urlname for code, _, _, urlname in ROLE_DEFINITIONS}
ROLE_LABELS = {code: label for code, label, *_ in ROLE_DEFINITIONS}

@sensitive_variables("pin", "expected")
@sensitive_post_parameters("pin")
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


# 주방 계정은 D-034로 1개로 단일화하기로 했으나 아직 구현 전이다. 세 역할이 오늘도
# 같은 주방 화면과 같은 기능을 공유하므로, 단일화 전까지 "주방"은 이 셋 전부를 뜻한다.
KITCHEN_ROLES = ("KITCHEN", "KITCHEN_HALL", "KITCHEN_TAKEOUT")
COUNTER_ROLES = ("B1_COUNTER",)


def require_api_roles(*allowed_roles: str):
    """Authorize an API endpoint from the session role, answering in JSON.

    Pages redirect to the login screen. An API must not: the caller parses JSON
    and a redirect arrives as an HTML login page, so the browser reports a parse
    error instead of a permission problem.

    Both "no session" and "wrong role" answer 403 while identification is
    session-based. Splitting them into 401/403 only becomes meaningful once
    D-035's token refresh exists, so that choice belongs to 4A2 (D-036 미결).

    Passing no role names means "any authenticated account". That is the
    anonymous block D-036 approved, without inventing a role restriction for
    the endpoints whose subject D-040 left undecided.
    """
    allowed = {r.upper() for r in allowed_roles if r}

    def deco(viewfunc):
        @wraps(viewfunc)
        def _wrapped(request, *args, **kwargs):
            role = request.session.get("role")
            if not role or role.upper() not in ROLE_TO_URLNAME:
                return JsonResponse({"detail": "로그인이 필요합니다."}, status=403)
            if allowed and role.upper() not in allowed:
                # Name neither the caller's role nor the allowed set: a rejected
                # client has no use for it and it maps the permission model.
                return JsonResponse({"detail": "권한이 없습니다."}, status=403)
            return viewfunc(request, *args, **kwargs)
        return _wrapped
    return deco

# FILE: orders/views/auth.py
from __future__ import annotations
from functools import wraps
from django.conf import settings
from django.shortcuts import render, redirect
from django.urls import reverse
from django.http import JsonResponse
from django.middleware.csrf import rotate_token
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
            # Start a clean session at the privilege transition. `flush` rather
            # than `cycle_key` because the latter carries the old contents into
            # the new key: only `role` lives here today, but anything an
            # anonymous caller could plant would otherwise ride across the
            # boundary. This also matches what logout does.
            request.session.flush()
            # The session key is only half the credential pair. Django's own
            # login rotates the CSRF token alongside it; without this the secret
            # bound to the fresh session is still the pre-login one.
            rotate_token(request)
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
    rotate_token(request)
    return redirect(reverse("orders:login"))

def csrf_failure(request, reason=""):
    """Answer a CSRF rejection in the caller's language.

    `CsrfViewMiddleware` runs outside every view decorator, so a tokenless write
    never reaches `require_api_roles` and Django's default answers with an HTML
    page. The API clients parse JSON, so that arrives as a parse error rather
    than a permission problem -- the exact failure the JSON 403 exists to avoid.
    Pages keep the HTML page, which is what a browser navigation should show.

    The JSON branch does not return the reason string: it names the check that
    failed and is of no use to a legitimate client. The HTML branch hands it to
    Django's view, which renders it only under DEBUG, as Django does by default.
    """
    if _targets_the_api(request):
        return JsonResponse({"detail": "요청이 만료되었습니다. 새로고침 후 다시 시도해 주세요."}, status=403)
    from django.views.csrf import csrf_failure as django_csrf_failure

    return django_csrf_failure(request, reason=reason)


def _targets_the_api(request) -> bool:
    """True when this path is served by orders.views.api.

    Resolved from the URLconf rather than matched against a path prefix: the
    prefix would silently stop being true if a route moved, and this decides
    whether a caller gets JSON or HTML.

    The marker is the guard itself, not the module name. Any view wearing
    `require_api_roles` answers in JSON, so it must be refused in JSON too, and
    an API view added outside `orders.views.api` stays correct with no edit
    here. `functools.wraps` carries the attribute out through `cache_page` and
    `require_http_methods`.
    """
    from django.urls import Resolver404, resolve

    try:
        match = resolve(request.path_info)
    except Resolver404:
        return False
    return getattr(match.func, "answers_in_json", False) is True


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
_HTTP_METHODS = frozenset(
    ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE")
)

KITCHEN_ROLES = ("KITCHEN", "KITCHEN_HALL", "KITCHEN_TAKEOUT")
COUNTER_ROLES = ("B1_COUNTER",)

# Reading an order exposes its money: total_price, payment_method, the cash and
# ticket split, change, and per-item unit_price. Those are the same figures the
# stats endpoints are restricted to, so leaving the read open would undo that
# restriction rather than stay neutral on it. Creating an order stays open to
# every account -- the ordering screen posts, it never reads back.
ORDER_READ_ROLES = KITCHEN_ROLES + COUNTER_ROLES


def require_api_roles(*allowed_roles: str, by_method: dict[str, tuple[str, ...]] | None = None):
    """Authorize an API endpoint from the session role, answering in JSON.

    Pages redirect to the login screen. An API must not: the caller parses JSON
    and a redirect arrives as an HTML login page, so the browser reports a parse
    error instead of a permission problem.

    Both "no session" and "wrong role" answer 403 while identification is
    session-based. Splitting them into 401/403 only becomes meaningful once
    D-035's token refresh exists, so that choice belongs to 4A2 (D-036 미결).

    `by_method` narrows individual HTTP methods, for a route whose methods have
    different subjects. `orders-collection` is the case: reading orders exposes
    money, creating one does not. Method names are validated, because a mistyped
    key would never match and would leave that method on the endpoint default --
    which is the open sentinel for the one endpoint using this. HEAD inherits
    GET's subject: it is GET without a body and has to clear the same bar.
    Any other method absent from the mapping falls back to `allowed_roles`.

    Passing no role names means "any authenticated account". That is the
    anonymous block D-036 approved, without inventing a role restriction for
    the endpoints whose subject D-040 left undecided. Because that sentinel is
    an empty set, a restriction that collapses to empty by accident would read
    as the sentinel and open the endpoint. Both mistakes raise at import time
    instead: naming roles and getting no restriction is never intended.
    """
    if any(isinstance(r, str) and len(r) == 1 for r in allowed_roles):
        # A bare string splatted into *allowed_roles* arrives as characters.
        raise ValueError(
            "require_api_roles() was given single characters, which usually "
            "means a bare string was splatted. Pass role names."
        )
    allowed = {r.upper() for r in allowed_roles if r}
    if allowed_roles and not allowed:
        raise ValueError(
            "require_api_roles() was given role names that resolve to nothing. "
            "Pass no arguments to mean 'any authenticated account'."
        )
    per_method = {}
    for method, names in (by_method or {}).items():
        key = method.upper()
        if key not in _HTTP_METHODS:
            raise ValueError(
                f"require_api_roles(by_method=...) got an unknown method {method!r}."
            )
        if isinstance(names, str):
            raise ValueError(
                f"require_api_roles(by_method=...) got a bare string for {key}. "
                "Pass a tuple of role names."
            )
        narrowed = {r.upper() for r in names if r}
        if not narrowed:
            raise ValueError(
                f"require_api_roles(by_method=...) gave {key} no roles. "
                "Omit the method to fall back to the endpoint default."
            )
        per_method[key] = narrowed
    if "GET" in per_method:
        # require_http_methods happens to 405 HEAD today, but that decorator
        # sits inside this one. Relying on it would make the restriction a side
        # effect of an unrelated list rather than something this guard enforces.
        per_method.setdefault("HEAD", per_method["GET"])
    unknown = (allowed | set().union(*per_method.values(), set())) - set(ROLE_TO_URLNAME)
    if unknown:
        # A typo would otherwise build a set nothing matches and lock every
        # role out of the endpoint, silently, until someone hits it in service.
        raise ValueError(f"require_api_roles() got unknown roles: {sorted(unknown)}")

    def deco(viewfunc):
        @wraps(viewfunc)
        def _wrapped(request, *args, **kwargs):
            role = request.session.get("role")
            if not role or role.upper() not in ROLE_TO_URLNAME:
                return JsonResponse({"detail": "로그인이 필요합니다."}, status=403)
            required = per_method.get(request.method.upper(), allowed)
            if required and role.upper() not in required:
                # Name neither the caller's role nor the allowed set: a rejected
                # client has no use for it and it maps the permission model.
                return JsonResponse({"detail": "권한이 없습니다."}, status=403)
            return viewfunc(request, *args, **kwargs)

        # Marks this view as one that answers in JSON, so csrf_failure refuses
        # it in JSON too. See _targets_the_api.
        _wrapped.answers_in_json = True
        return _wrapped
    return deco

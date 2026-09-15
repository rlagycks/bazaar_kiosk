# FILE: orders/views/guards.py
"""Authorization guards and the CSRF rejection format.

Split out of `auth.py` so that the identification flow (logging in, and in 4A2
issuing and refreshing tokens) and the enforcement of what an identified caller
may do are separate files. They change for different reasons and, per BLUEPRINT
4A2, edits to the login flow have to be serialized against other phases.

`csrf_failure` lives here rather than with the login views because it completes
this file's contract: `require_api_roles` marks a view as answering in JSON, and
this is what honours that marker when the refusal comes from the middleware
instead of from the guard.
"""
from __future__ import annotations

from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.utils.cache import patch_cache_control
from django.views.decorators.debug import sensitive_variables
from django.shortcuts import redirect
from django.urls import reverse

from orders.roles import ROLE_TO_URLNAME
from orders.authentication import AuthError, validate_access, refresh_identity

_HTTP_METHODS = frozenset(
    ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE")
)


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
    """True when this path is served by a view that answers in JSON.

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
        @sensitive_variables()
        def _wrapped(request, *args, **kwargs):
            try:
                role, session_id = refresh_identity(request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME, ""))
                request.auth_role = role
                request.auth_session_id = session_id
            except AuthError:
                return redirect(reverse("orders:login"))
            if allowed and role.upper() not in allowed:
                return redirect(reverse("orders:login"))
            response = viewfunc(request, *args, **kwargs)
            patch_cache_control(response, private=True, no_store=True)
            return response
        return _wrapped
    return deco

def require_role(role: str):
    return require_roles(role)


def require_api_roles(*allowed_roles: str, by_method: dict[str, tuple[str, ...]] | None = None):
    """Authorize an API endpoint using only the access Bearer JWT, answering in JSON.

    Pages redirect to the login screen. An API must not: the caller parses JSON
    and a redirect arrives as an HTML login page, so the browser reports a parse
    error instead of a permission problem.

    Missing/invalid credentials answer 401; valid credentials with a denied
    role answer 403. Legacy Django session roles and refresh cookies never
    authenticate API calls. HTML guards separately validate refresh cookies
    without rotating them, allowing ordinary server-rendered navigation.

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
        @sensitive_variables()
        def _wrapped(request, *args, **kwargs):
            try:
                authorization = request.headers.get("Authorization", "")
                scheme, token = authorization.split(" ", 1)
                if scheme.lower() != "bearer" or not token or " " in token:
                    raise AuthError()
                role = validate_access(token)
            except (AuthError, ValueError):
                response = JsonResponse({"detail": "로그인이 필요합니다."}, status=401)
                response["WWW-Authenticate"] = "Bearer"
                patch_cache_control(response, private=True, no_store=True)
                return response
            required = per_method.get(request.method.upper(), allowed)
            if required and role.upper() not in required:
                # Name neither the caller's role nor the allowed set: a rejected
                # client has no use for it and it maps the permission model.
                return JsonResponse({"detail": "권한이 없습니다."}, status=403)
            response = viewfunc(request, *args, **kwargs)
            patch_cache_control(response, private=True, no_store=True)
            return response

        # Marks this view as one that answers in JSON, so csrf_failure refuses
        # it in JSON too. See _targets_the_api.
        _wrapped.answers_in_json = True
        return _wrapped
    return deco

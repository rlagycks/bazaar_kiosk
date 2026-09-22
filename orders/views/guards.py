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

from asgiref.sync import iscoroutinefunction, sync_to_async
from django.conf import settings
from django.http import JsonResponse
from django.utils.cache import patch_cache_control
from django.views.decorators.debug import sensitive_variables
from django.shortcuts import redirect
from django.urls import reverse

from orders.roles import PERMISSION_CODES
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


def _attach(request, identity):
    """What the views and templates may know about the caller."""
    request.auth_account = identity.account
    request.auth_permissions = identity.permissions
    request.auth_session_id = identity.session_id


def _authorize(request, required_default, per_method):
    """Identify an API caller and decide whether this call is allowed.

    Returns the refusal to send, or `None` when the call may proceed. Split out
    of the wrapper in 10A so the synchronous and asynchronous wrappers reach
    the decision through the same code rather than through two copies of it:
    an authorization rule that exists twice is one edit away from existing in
    one and a half places.
    """
    try:
        authorization = request.headers.get("Authorization", "")
        scheme, token = authorization.split(" ", 1)
        if scheme.lower() != "bearer" or not token or " " in token:
            raise AuthError()
        identity = validate_access(token)
    except (AuthError, ValueError):
        response = JsonResponse({"detail": "로그인이 필요합니다."}, status=401)
        response["WWW-Authenticate"] = "Bearer"
        patch_cache_control(response, private=True, no_store=True)
        return response
    # The view needs to know who is acting: 6A stores it with the order
    # attempt, D-051 records it on every change. The HTML guard attaches the
    # same three attributes.
    _attach(request, identity)
    required = per_method.get(request.method.upper(), required_default)
    if required and not (required & identity.permissions):
        # Name neither the caller's permissions nor the allowed set: a
        # rejected client has no use for it and it maps the model.
        return JsonResponse({"detail": "권한이 없습니다."}, status=403)
    return None


def _permitted(held, *, any_of, all_of) -> bool:
    if all_of and not set(all_of) <= held:
        return False
    if any_of and not (set(any_of) & held):
        return False
    return True


def _check_names(names, where):
    unknown = set(names) - set(PERMISSION_CODES)
    if unknown:
        # A typo would otherwise build a set nothing matches and lock every
        # account out of the view, silently, until someone hits it in service.
        raise ValueError(f"{where} got unknown permissions: {sorted(unknown)}")
    if any(isinstance(n, str) and len(n) == 1 for n in names):
        raise ValueError(f"{where} was given single characters, which usually "
                         "means a bare string was splatted. Pass permission codes.")


def require_permissions(*any_of: str, all_of: tuple[str, ...] = ()):
    """Authorize a page: the refresh cookie identifies the account, whose
    current permission set must contain every code in `all_of` and at least
    one of `any_of` (when given). No codes at all means any signed-in account.
    Pages redirect to the login screen on refusal; APIs answer JSON.
    """
    _check_names(any_of, "require_permissions()")
    _check_names(all_of, "require_permissions(all_of=...)")

    def deco(viewfunc):
        @wraps(viewfunc)
        @sensitive_variables()
        def _wrapped(request, *args, **kwargs):
            try:
                identity = refresh_identity(request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME, ""))
            except AuthError:
                return redirect(reverse("orders:login"))
            _attach(request, identity)
            if not _permitted(identity.permissions, any_of=any_of, all_of=all_of):
                return redirect(reverse("orders:login"))
            response = viewfunc(request, *args, **kwargs)
            patch_cache_control(response, private=True, no_store=True)
            return response
        return _wrapped
    return deco


def require_api_permissions(*allowed: str, by_method: dict[str, tuple[str, ...]] | None = None):
    """Authorize an API endpoint using only the access Bearer JWT, answering in JSON.

    Pages redirect to the login screen. An API must not: the caller parses JSON
    and a redirect arrives as an HTML login page, so the browser reports a parse
    error instead of a permission problem.

    Missing/invalid credentials answer 401; valid credentials whose account
    holds none of the named permissions answer 403. Legacy Django session roles and refresh cookies never
    authenticate API calls. HTML guards separately validate refresh cookies
    without rotating them, allowing ordinary server-rendered navigation.

    `by_method` narrows individual HTTP methods, for a route whose methods have
    different subjects. `orders-collection` is the case: reading orders exposes
    money, creating one does not. Method names are validated, because a mistyped
    key would never match and would leave that method on the endpoint default --
    which is the open sentinel for the one endpoint using this. HEAD inherits
    GET's subject: it is GET without a body and has to clear the same bar.
    Any other method absent from the mapping falls back to `allowed_roles`.

    Passing no permission codes means "any authenticated account". That is
    the anonymous block D-036 approved, kept for the endpoints D-051 leaves
    open to every account. Because that sentinel is an empty set, a
    restriction that collapses to empty by accident would read as the
    sentinel and open the endpoint. Both mistakes raise at import time
    instead: naming permissions and getting no restriction is never intended.
    """
    _check_names(allowed, "require_api_permissions()")
    required_default = {code.upper() for code in allowed if code}
    if allowed and not required_default:
        raise ValueError(
            "require_api_permissions() was given codes that resolve to nothing. "
            "Pass no arguments to mean 'any authenticated account'."
        )
    per_method = {}
    for method, names in (by_method or {}).items():
        key = method.upper()
        if key not in _HTTP_METHODS:
            raise ValueError(
                f"require_api_permissions(by_method=...) got an unknown method {method!r}."
            )
        if isinstance(names, str):
            raise ValueError(
                f"require_api_permissions(by_method=...) got a bare string for {key}. "
                "Pass a tuple of permission codes."
            )
        _check_names(names, "require_api_permissions(by_method=...)")
        narrowed = {r.upper() for r in names if r}
        if not narrowed:
            raise ValueError(
                f"require_api_permissions(by_method=...) gave {key} no permissions. "
                "Omit the method to fall back to the endpoint default."
            )
        per_method[key] = narrowed
    if "GET" in per_method:
        # require_http_methods happens to 405 HEAD today, but that decorator
        # sits inside this one. Relying on it would make the restriction a side
        # effect of an unrelated list rather than something this guard enforces.
        per_method.setdefault("HEAD", per_method["GET"])
    def deco(viewfunc):
        @wraps(viewfunc)
        @sensitive_variables()
        def _wrapped(request, *args, **kwargs):
            refusal = _authorize(request, required_default, per_method)
            if refusal is not None:
                return refusal
            response = viewfunc(request, *args, **kwargs)
            patch_cache_control(response, private=True, no_store=True)
            return response

        @wraps(viewfunc)
        @sensitive_variables()
        async def _awrapped(request, *args, **kwargs):
            # 10A: the same decision, reached the same way. Identifying a
            # caller reads the database, which is synchronous, so it is handed
            # to the request's own thread -- `thread_sensitive` is what keeps
            # every sync step of one request on one thread and one connection,
            # instead of scattering them across a pool where each would open
            # its own.
            refusal = await sync_to_async(_authorize, thread_sensitive=True)(
                request, required_default, per_method
            )
            if refusal is not None:
                return refusal
            response = await viewfunc(request, *args, **kwargs)
            patch_cache_control(response, private=True, no_store=True)
            return response

        if iscoroutinefunction(viewfunc):
            # `_awrapped` is a real coroutine function, so Django's handler
            # sees an async view and calls it in the running loop rather than
            # adapting it -- which is the whole point of having two wrappers.
            _wrapped = _awrapped

        # Marks this view as one that answers in JSON, so csrf_failure refuses
        # it in JSON too. See _targets_the_api.
        _wrapped.answers_in_json = True
        return _wrapped
    return deco

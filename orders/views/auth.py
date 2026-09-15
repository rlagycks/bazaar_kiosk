"""Shared-account login and device-scoped JWT refresh/logout endpoints."""
from django.conf import settings
from django.middleware.csrf import rotate_token
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_http_methods, require_POST

from orders.authentication import (
    AuthError, RefreshInProgress, issue_tokens, rotate_refresh, revoke_refresh,
)
from orders.login_security import attempt_login
from orders.roles import ROLE_TO_URLNAME


@sensitive_variables()
def _set_refresh_cookie(response, pair):
    if pair.refresh_token is None:
        return
    response.set_cookie(
        settings.JWT_REFRESH_COOKIE_NAME, pair.refresh_token,
        max_age=max(0, int((pair.expires_at - timezone.now()).total_seconds())),
        httponly=True, secure=settings.JWT_COOKIE_SECURE, samesite='Strict',
        path=settings.JWT_REFRESH_COOKIE_PATH,
    )


def _refresh_cookie(request):
    return request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME, '')


@never_cache
@ensure_csrf_cookie
@require_http_methods(['GET', 'POST'])
@sensitive_variables()
@sensitive_post_parameters('password', 'pin')
def login_view(request):
    if request.method == 'GET':
        return render(request, 'orders/login.html')
    account_id = request.POST.get('account_id', '').strip()
    password = request.POST.get('password', '')
    if not settings.ROLE_ACCOUNTS or settings.LOGIN_MAX_FAILURES < 1:
        return render(request, 'orders/login.html', {'error': '로그인 설정을 확인해 주세요.'}, status=503)
    if not account_id or len(account_id) > 128 or len(password) > 1024:
        return render(request, 'orders/login.html', {'error': '계정 또는 비밀번호가 올바르지 않습니다.'}, status=200)
    # REMOTE_ADDR is the directly connected peer. Never trust arbitrary X-Forwarded-For.
    role, retry = attempt_login(account_id, password, request.META.get('REMOTE_ADDR', ''))
    if role:
        # Switching accounts in a browser retires its previous device credential.
        try:
            revoke_refresh(_refresh_cookie(request))
        except AuthError:
            pass
        request.session.flush()
        rotate_token(request)
        pair = issue_tokens(role)
        response = redirect(reverse(ROLE_TO_URLNAME[role]))
        _set_refresh_cookie(response, pair)
        return response
    response = render(request, 'orders/login.html', {
        'error': ('로그인 시도가 많습니다. 잠시 후 다시 시도해 주세요.' if retry
                  else '계정 또는 비밀번호가 올바르지 않습니다.'),
    }, status=429 if retry else 200)
    if retry:
        response['Retry-After'] = str(retry)
    return response


@never_cache
@require_POST
@sensitive_variables()
def refresh_view(request):
    try:
        pair = rotate_refresh(_refresh_cookie(request))
    except RefreshInProgress:
        return JsonResponse({'detail': '인증 갱신 중입니다. 다시 시도해 주세요.'}, status=409)
    except AuthError:
        response = JsonResponse({'detail': '로그인이 필요합니다.'}, status=401)
        response['WWW-Authenticate'] = 'Bearer'
        return response
    response = JsonResponse({'access_token': pair.access_token, 'role': pair.role, 'session_id': pair.session_id,
                             'expires_in': min(900, max(0, int((pair.expires_at - timezone.now()).total_seconds())))})
    _set_refresh_cookie(response, pair)
    return response


refresh_view.answers_in_json = True


@never_cache
@require_POST
@sensitive_variables()
def logout_view(request):
    try:
        revoke_refresh(_refresh_cookie(request))
    except AuthError:
        pass
    request.session.flush()
    rotate_token(request)
    response = redirect(reverse('orders:login'))
    response.delete_cookie(settings.JWT_REFRESH_COOKIE_NAME,
                           path=settings.JWT_REFRESH_COOKIE_PATH, samesite='Strict')
    return response

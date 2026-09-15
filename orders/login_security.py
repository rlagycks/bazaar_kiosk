"""Database-backed failure budget per account identifier and direct peer IP."""
from datetime import timedelta
import hashlib
import hmac
import math

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from orders.authentication import authenticate_credentials
from orders.models import LoginAttempt


@sensitive_variables()
def attempt_login(account_id, password, peer_ip):
    key = hmac.new(settings.SECRET_KEY.encode(),
                   (account_id + '\0' + peer_ip).encode(), hashlib.sha256).hexdigest()
    now = timezone.now()
    with transaction.atomic():
        LoginAttempt.objects.get_or_create(key=key, defaults={'window_started_at': now})
        attempt = LoginAttempt.objects.select_for_update().get(pk=key)
        if attempt.blocked_until and attempt.blocked_until > now:
            return None, max(1, math.ceil((attempt.blocked_until - now).total_seconds()))
        if now - attempt.window_started_at >= timedelta(seconds=settings.LOGIN_WINDOW_SECONDS):
            attempt.window_started_at = now
            attempt.failures = 0
            attempt.blocked_until = None
        role = authenticate_credentials(account_id, password)
        if role:
            attempt.failures = 0
            attempt.blocked_until = None
        else:
            attempt.failures += 1
            if attempt.failures >= settings.LOGIN_MAX_FAILURES:
                attempt.blocked_until = now + timedelta(seconds=settings.LOGIN_BLOCK_SECONDS)
        attempt.save()
        retry = settings.LOGIN_BLOCK_SECONDS if attempt.blocked_until else 0
        return role, retry

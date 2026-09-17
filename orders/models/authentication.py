"""One revocable, absolute-lifetime login per browser device."""
import uuid

from django.db import models


class AuthDevice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=32)
    account_id = models.CharField(max_length=150)
    credential_fingerprint = models.CharField(max_length=64)
    refresh_jti_hash = models.CharField(max_length=64)
    previous_jti_hash = models.CharField(max_length=64, blank=True)
    rotated_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)


class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    window_started_at = models.DateTimeField()
    failures = models.PositiveIntegerField(default=0)
    blocked_until = models.DateTimeField(null=True, blank=True)

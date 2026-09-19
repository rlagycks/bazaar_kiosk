"""Personal accounts (D-051) and one revocable, absolute-lifetime login per
browser device."""
import uuid

from django.db import models

from orders.roles import HALL_MONITOR, SERVING, STATS, TAKEOUT_MONITOR


class Account(models.Model):
    """One person, identified by the name they type at login.

    The event password is shared (D-051); the name is what the audit trail
    records and what the permissions hang off. Deleting an account is refused
    wherever it is referenced -- deactivate it instead, so the orders it
    created keep their author.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True, verbose_name="이름")
    can_serve = models.BooleanField(default=False, verbose_name="서빙")
    can_monitor_hall = models.BooleanField(default=False, verbose_name="식당 모니터링")
    can_monitor_takeout = models.BooleanField(default=False, verbose_name="포장 모니터링")
    can_view_stats = models.BooleanField(default=False, verbose_name="누적·통계")
    is_active = models.BooleanField(default=True, verbose_name="활성")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "계정"
        verbose_name_plural = "계정"

    def __str__(self):
        return self.name

    @property
    def permissions(self) -> frozenset[str]:
        held = []
        if self.can_serve:
            held.append(SERVING)
        if self.can_monitor_hall:
            held.append(HALL_MONITOR)
        if self.can_monitor_takeout:
            held.append(TAKEOUT_MONITOR)
        if self.can_view_stats:
            held.append(STATS)
        return frozenset(held)


class AuthDevice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Null only for rows issued before 0025, which that migration revokes.
    account = models.ForeignKey(
        Account, null=True, blank=True, on_delete=models.PROTECT, related_name="devices",
    )
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

"""Who did what to an order (D-051).

Append-only. Each row is written in the same transaction as the change it
describes, so a row exists exactly when the change committed. Nothing here is
a source of truth for the order's state -- that is the order row -- it is the
record of how it got there.
"""
from __future__ import annotations

from django.db import models

from .authentication import Account
from .core import Order, OrderItem


class OrderEventKind(models.TextChoices):
    CREATED = "CREATED", "주문 생성"
    STATUS = "STATUS", "상태 변경"
    PROGRESS = "PROGRESS", "조리 진행"
    ITEMS = "ITEMS", "품목 수정"  # 7B: lines changed after the order was taken


class OrderEvent(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="events")
    # Null only for rows written by paths that have no account (none today);
    # PROTECT so an account with history cannot be deleted, only deactivated.
    actor = models.ForeignKey(
        Account, null=True, blank=True, on_delete=models.PROTECT, related_name="order_events",
    )
    kind = models.CharField(max_length=10, choices=OrderEventKind.choices)
    from_status = models.CharField(max_length=10, blank=True, default="")
    to_status = models.CharField(max_length=10, blank=True, default="")
    item = models.ForeignKey(
        OrderItem, null=True, blank=True, on_delete=models.PROTECT, related_name="events",
    )
    prepared_qty = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "주문 이력"
        verbose_name_plural = "주문 이력"

    def __str__(self):
        return f"{self.order_id} {self.kind} by {self.actor_id}"

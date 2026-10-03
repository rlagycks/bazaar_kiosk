from __future__ import annotations
from django.db import models

from .core import Order


class OrderRequest(models.Model):
    """One attempt to create an order, named by the client (6A, BK-R012).

    The row is written in the same transaction as the order it names, so it
    exists exactly when that order does: a rejected or rolled-back attempt
    leaves its id free to try again, and a committed one makes every later
    replay of that id return the same order instead of a second one.

    There is no expiry. An expired id would quietly become a duplicate for the
    one caller that needed it most -- a phone retrying long after a lost
    response. The table grows by one row per order, which for an event this
    size is nothing.
    """

    key = models.CharField(max_length=64, unique=True, verbose_name="요청 ID")
    # D-051: the account that made the attempt, as its UUID string. Two
    # screens colliding on one id is a conflict, not a replay.
    actor = models.CharField(max_length=64, blank=True, default="")
    fingerprint = models.CharField(max_length=64)
    # PROTECT, not CASCADE: deleting an order would otherwise silently drop the
    # record that stops a late retry from recreating it. Whether orders may be
    # deleted at all is still D-011, so the safe default is to make a deletion
    # fail loudly and surface that decision rather than cascade quietly.
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="requests")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.key} -> order {self.order_id}"

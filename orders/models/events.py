from __future__ import annotations
from django.db import models


class EventDay(models.Model):
    """A day the bazaar actually runs (D-047).

    Orders created on a registered day get real numbers; every other day is a
    rehearsal and gets the practice series. The registry is deliberately the
    only switch: a separate "practice mode" toggle can be left on by mistake,
    and a wrong number is only visible after the fact.
    """

    date = models.DateField(unique=True, verbose_name="행사일")
    label = models.CharField(max_length=60, blank=True, default="", verbose_name="메모")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "행사일"
        verbose_name_plural = "행사일"

    def __str__(self):
        return f"{self.date}{' ' + self.label if self.label else ''}"

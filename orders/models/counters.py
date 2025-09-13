from __future__ import annotations
from django.db import models


class FloorOrderCounter(models.Model):
    date = models.DateField(db_index=True)
    floor = models.CharField(max_length=2)  # "B1" / "F1"
    last_no = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = (("date", "floor"),)
        indexes = [models.Index(fields=["date", "floor"])]
        ordering = ["-date", "floor"]

    def __str__(self):
        return f"{self.date} {self.floor} last={self.last_no}"
from __future__ import annotations
from django.db import models

from .core import NumberSeries


class FloorOrderCounter(models.Model):
    """Superseded by OrderNumberCounter (D-047); kept until step 11 cleanup."""

    date = models.DateField(db_index=True)
    floor = models.CharField(max_length=2)  # 현재는 "B1"만 사용
    last_no = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = (("date", "floor"),)
        indexes = [models.Index(fields=["date", "floor"])]
        ordering = ["-date", "floor"]

    def __str__(self):
        return f"{self.date} {self.floor} last={self.last_no}"


class OrderNumberCounter(models.Model):
    """The last number handed out for one series, year and floor (D-047).

    A table rather than a sequence: a sequence advances even when the order
    that asked for the number is rolled back, which leaves a hole in numbers
    that are read aloud and printed. A locked row is gap-free, and it is the
    natural place to hold "this year, this series" -- neither of which a
    sequence can express without creating one sequence per year.
    """

    series = models.CharField(max_length=8, choices=NumberSeries.choices)
    year = models.PositiveIntegerField()
    floor = models.CharField(max_length=2)
    last_no = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["series", "year", "floor"], name="uq_number_counter_scope"
            ),
        ]
        ordering = ["-year", "series", "floor"]

    def __str__(self):
        return f"{self.year} {self.series} {self.floor} last={self.last_no}"

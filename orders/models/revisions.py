"""The one number a screen compares against (10B, D-019).

A row, not a sequence. A sequence hands out numbers that survive a rollback,
so a reader could see the marker move for a change that never committed and
refetch forever; and a sequence gives no way to say "later number, earlier
commit" is impossible, which is precisely the guarantee this has to make.

A locked row gives both. Taking the next value means holding the row until
commit, so a writer that took a later value cannot commit before the one that
took an earlier value -- the inversion that would let a reader step over a
change it never fetched. `OrderNumberCounter` (D-047) uses the same mechanism
for order numbers, for a related reason.

`scope` exists so this can be split later without changing shape. Today there
is exactly one row, and that is deliberate: an event day being registered
changes what every order on every screen displays without writing to a single
order row, so a marker scoped per order -- or per floor -- would not notice it.
One number for one board is the honest granularity while there is one board.
"""

from __future__ import annotations

from django.db import models

# The only scope today. A constant rather than a default, so a second one
# cannot appear by leaving an argument out.
BOARD = "board"


class ChangeRevision(models.Model):
    scope = models.CharField(max_length=32, unique=True, default=BOARD)
    # Big, because it counts changes rather than rows and is never reset. At
    # one change a second it outlives the universe; at the rate a bazaar
    # produces them the question does not arise.
    value = models.BigIntegerField(default=0)

    class Meta:
        verbose_name = "변경 표시"
        verbose_name_plural = "변경 표시"
        constraints = [
            models.CheckConstraint(
                name="change_revision_never_decreases",
                condition=models.Q(value__gte=0),
            ),
        ]

    def __str__(self):
        return f"{self.scope}={self.value}"

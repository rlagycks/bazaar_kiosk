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
is exactly one row.

Two arguments, and only the second one reaches the conclusion. An event day
being registered changes what every order on every screen displays without
writing to a single order row, so a marker scoped *per order* cannot work --
but that rules out per-order, not per-screen; a `{hall, takeout, stats}` split
where cross-cutting edits bump all three would have handled it too. The reason
there is one row is the plainer one: there is one board, the screens are few,
and waking a screen that did not need waking costs a refetch nobody notices at
this size. That cost has not been measured, and it is what decides when to
split (PR #77 architecture review).
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
            # Named for what it does. An earlier name said "never decreases",
            # which `value >= 0` does not enforce at all -- `SET value = 3` on
            # a row holding 5 passes it. Monotonicity is a property of
            # `revisions.mark()` being the only writer, which a test pins;
            # promising it here would have left the next reader trusting the
            # database for something the database was not checking
            # (PR #77 architecture review).
            models.CheckConstraint(
                name="change_revision_is_not_negative",
                condition=models.Q(value__gte=0),
            ),
        ]

    def __str__(self):
        return f"{self.scope}={self.value}"

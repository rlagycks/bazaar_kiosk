"""10B: the change marker, and the one row that holds it (D-019).

Forward-only in effect and safe on a database that already has orders in it:
nothing existing is read, rewritten or re-keyed. The row starts at 0, which
every screen reads as "older than anything", so the first connection after
this migration fetches once and is then current. That is the correct
behaviour, not a gap.

Rolling back drops the table. An older application does not know the marker
exists, so it neither reads nor writes it; what it loses is the ability to
tell a screen that something changed, which is the state it was already in
before this phase. No order data is touched either way.
"""

from django.db import migrations, models

# Duplicated rather than imported: a migration has to keep meaning what it
# meant on the day it ran, and importing the constant would let a later rename
# rewrite history.
BOARD = "board"


def create_the_counter_row(apps, schema_editor):
    ChangeRevision = apps.get_model("orders", "ChangeRevision")
    ChangeRevision.objects.get_or_create(scope=BOARD, defaults={"value": 0})


def remove_the_counter_row(apps, schema_editor):
    ChangeRevision = apps.get_model("orders", "ChangeRevision")
    ChangeRevision.objects.filter(scope=BOARD).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0027_orderevent_kind_items"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChangeRevision",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "scope",
                    models.CharField(default="board", max_length=32, unique=True),
                ),
                ("value", models.BigIntegerField(default=0)),
            ],
            options={
                "verbose_name": "변경 표시",
                "verbose_name_plural": "변경 표시",
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("value__gte", 0)),
                        name="change_revision_is_not_negative",
                    )
                ],
            },
        ),
        migrations.RunPython(create_the_counter_row, remove_the_counter_row),
    ]

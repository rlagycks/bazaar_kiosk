# D-047: numbers now restart per year, per series. The 0020 sequence cannot
# express either scope and advances on rollback, so allocation moves to a
# locked counter row and the sequence is dropped here. The 0020 repair and its
# tests stay in history untouched.

import django.db.models.functions.datetime
from django.db import migrations, models


def drop_floor_sequence(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP SEQUENCE IF EXISTS orders_floor_b1_seq")


def restore_floor_sequence(apps, schema_editor):
    """Reverse: recreate the sequence 0020 left, positioned past existing rows."""
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("CREATE SEQUENCE IF NOT EXISTS orders_floor_b1_seq")
        cursor.execute(
            """
            SELECT setval(
                'orders_floor_b1_seq',
                GREATEST(COALESCE((SELECT MAX(order_no) FROM orders_order WHERE floor = 'B1'), 0), 1),
                COALESCE((SELECT MAX(order_no) FROM orders_order WHERE floor = 'B1'), 0) > 0
            )
            """
        )


def classify_existing_orders(apps, schema_editor):
    """Existing numbered orders were event orders (D-047 backfill).

    Before this migration every recorded order counted as a sale, so the new
    column's PRACTICE default would quietly drop all of them out of the sales
    figures. D-037 says no such rows should exist on the production database,
    but that decision is void the moment any are found, so the migration does
    the right thing either way instead of relying on it.
    """
    Order = apps.get_model("orders", "Order")
    Order.objects.using(schema_editor.connection.alias).filter(
        order_no__isnull=False
    ).update(number_series="REAL")


def unclassify_existing_orders(apps, schema_editor):
    """Reverse: the column is dropped right after this, so restore the default."""
    Order = apps.get_model("orders", "Order")
    Order.objects.using(schema_editor.connection.alias).update(number_series="PRACTICE")


def refuse_colliding_legacy_numbers(apps, schema_editor):
    """Stop before the new constraint turns legacy day-reset numbers into a crash.

    Numbering used to restart every calendar day, so two orders from different
    days of the same year may share a number. The new uniqueness is per year,
    which those rows violate. Renumbering them here is forbidden (the blueprint
    rules out bulk reassignment), so the migration fails with an explanation
    rather than a bare unique-violation from AddConstraint.
    """
    Order = apps.get_model("orders", "Order")
    rows = (
        Order.objects.using(schema_editor.connection.alias)
        .filter(order_no__isnull=False, order_date__isnull=False)
        .values_list("floor", "number_series", "order_date", "order_no")
    )
    seen, collisions = {}, []
    for floor, series, order_date, order_no in rows:
        key = (floor, series, order_date.year, order_no)
        if key in seen:
            collisions.append(key)
        seen[key] = True
    if collisions:
        raise RuntimeError(
            "Existing orders share a number within one year, which the D-047 "
            "contract forbids: "
            + ", ".join(
                f"floor={f} series={s} year={y} no={n}" for f, s, y, n in sorted(set(collisions))[:10]
            )
            + ". These come from the old per-day numbering. Decide how to "
            "reconcile them (D-008/D-037) before applying this migration; "
            "renumbering them automatically is out of scope here."
        )


def allow_colliding_legacy_numbers(apps, schema_editor):
    """Reverse of a check is a no-op: nothing was written."""


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0021_auth_device"),
    ]

    operations = [
        migrations.CreateModel(
            name="EventDay",
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
                ("date", models.DateField(unique=True, verbose_name="행사일")),
                (
                    "label",
                    models.CharField(
                        blank=True, default="", max_length=60, verbose_name="메모"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "행사일",
                "verbose_name_plural": "행사일",
                "ordering": ["-date"],
            },
        ),
        migrations.CreateModel(
            name="OrderNumberCounter",
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
                    "series",
                    models.CharField(
                        choices=[("REAL", "행사"), ("PRACTICE", "연습")], max_length=8
                    ),
                ),
                ("year", models.PositiveIntegerField()),
                ("floor", models.CharField(max_length=2)),
                ("last_no", models.PositiveIntegerField(default=0)),
            ],
            options={
                "ordering": ["-year", "series", "floor"],
            },
        ),
        migrations.RemoveConstraint(
            model_name="order",
            name="uq_floor_date_no",
        ),
        migrations.AddField(
            model_name="order",
            name="number_series",
            field=models.CharField(
                choices=[("REAL", "행사"), ("PRACTICE", "연습")],
                db_index=True,
                default="PRACTICE",
                max_length=8,
            ),
        ),
        migrations.RunPython(classify_existing_orders, unclassify_existing_orders),
        migrations.RunPython(
            refuse_colliding_legacy_numbers, allow_colliding_legacy_numbers
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.UniqueConstraint(
                models.F("floor"),
                models.F("number_series"),
                django.db.models.functions.datetime.ExtractYear("order_date"),
                models.F("order_no"),
                condition=models.Q(("order_no__isnull", False)),
                name="uq_floor_series_year_no",
            ),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=models.Q(("order_no__isnull", True))
                | models.Q(("order_date__isnull", False)),
                name="orders_number_needs_date",
            ),
        ),
        migrations.AddConstraint(
            model_name="ordernumbercounter",
            constraint=models.UniqueConstraint(
                fields=("series", "year", "floor"), name="uq_number_counter_scope"
            ),
        ),
        migrations.RunPython(drop_floor_sequence, restore_floor_sequence),
    ]

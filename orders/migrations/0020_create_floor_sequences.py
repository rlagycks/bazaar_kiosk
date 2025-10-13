from __future__ import annotations
from django.db import migrations


def create_sequences(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("CREATE SEQUENCE IF NOT EXISTS orders_floor_b1_seq")
        cursor.execute(
            """
            SELECT setval(
                'orders_floor_b1_seq',
                COALESCE((SELECT MAX(order_no) FROM orders_order WHERE floor = 'B1'), 0),
                true
            )
            """
        )


def drop_sequences(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP SEQUENCE IF EXISTS orders_floor_b1_seq")


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0019_remove_order_orders_table_rule_and_more"),
    ]

    operations = [
        migrations.RunPython(create_sequences, drop_sequences),
    ]

"""Frozen pre-repair copy of orders.0020, used only to build already-applied DBs.

Django never loads this module as a migration: it lives outside orders/migrations.
The regression suite patches these operations onto the repaired migration so a
database created by the original code can be verified as a no-op afterwards.
Its bytes are the original file at develop 3604ccad7add5c760c3b1cecfaa7032706ddc01c
(sha256 b2ccbd94aea0c5bab15af7dc365e413bbebfb037e36edfef11d37b2056531ea6).
"""

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

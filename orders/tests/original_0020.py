"""Frozen pre-repair copy of orders.0020. Never edit it to match the repair.

Django never loads this module as a migration: it lives outside orders/migrations,
and the loader only scans an app's migrations package. The regression suite patches
these operations onto the repaired migration for two purposes: building a database
that the original code migrated, so the repaired file can be shown to be a no-op on
it, and proving that the original statements still fail with SQLSTATE 22003 on an
empty database, which is why D-P07 changed them.
Everything below this docstring is byte-identical to the original file at develop
3604ccad7add5c760c3b1cecfaa7032706ddc01c, whose whole-file sha256 was
b2ccbd94aea0c5bab15af7dc365e413bbebfb037e36edfef11d37b2056531ea6. This file's own
hash differs because of this docstring, so compare the body, not the file.
test_frozen_copy_still_holds_the_pre_repair_statements guards the statements.
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

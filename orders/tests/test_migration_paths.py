"""Pin the repaired 0020 sequence paths and the 0019 failures that remain open.

These unittest cases deliberately request no runner-managed database: each case
owns a disposable DB through pg_support and creates fixtures exclusively from
historical model states. D-P07 repaired 0020 only, so the four 0019 constraint
cases still assert failure and row preservation until that policy is decided.
"""

import importlib
import inspect
from contextlib import contextmanager
from datetime import date
from unittest import TestCase, skipUnless
from unittest.mock import patch

from django.conf import settings
from django.db import DataError, IntegrityError, ProgrammingError
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

from orders.tests import original_0020


M18 = ("orders", "0018_alter_order_floor_alter_order_order_type_and_more")
M19 = ("orders", "0019_remove_order_orders_table_rule_and_more")
M20 = ("orders", "0020_create_floor_sequences")


@skipUnless(
    settings.SETTINGS_MODULE == "bazaar_kiosk.settings_test_pg",
    "requires explicit PostgreSQL test settings",
)
class MigrationPathTests(TestCase):
    def setUp(self):
        # Lazy import also permits SQLite discovery before PG support is installed.
        from orders.tests.pg_support import migration_database

        self.connection = self.enterContext(migration_database())
        self.assertEqual(self.connection.vendor, "postgresql")

    def migrate(self, target):
        # Rebuild the loader after every migration, including a failed attempt.
        executor = MigrationExecutor(self.connection)
        executor.migrate([target])
        return executor.loader.project_state([target]).apps

    def history(self):
        return list(
            MigrationRecorder(self.connection).migration_qs.order_by("id")
            .values_list("id", "app", "name", "applied")
        )

    def assert_head(self, target):
        executor = MigrationExecutor(self.connection)
        expected = {
            node for node in executor.loader.graph.forwards_plan(target)
            if node[0] == "orders"
        }
        actual = {
            node for node in executor.loader.applied_migrations
            if node[0] == "orders"
        }
        self.assertEqual(actual, expected)

    def snapshot(self, apps):
        rows = {
            model._meta.label: list(
                model.objects.using(self.connection.alias).order_by("pk").values()
            )
            for model in apps.get_app_config("orders").get_models()
        }
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT conrelid::regclass::text, conname, contype,
                       convalidated, pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE connamespace = 'public'::regnamespace
                ORDER BY conrelid::regclass::text, conname
                """
            )
            constraints = cursor.fetchall()
        self.assertTrue(any(row[1] == "orders_table_rule" for row in constraints))
        return rows, self.history(), constraints

    def fixture(self, apps, *, floor="B1", order_type="DINE_IN",
                with_table=True, order_no=None, source="ORDER", table_number=1):
        alias = self.connection.alias
        table = apps.get_model("orders", "Table").objects.using(alias).create(
            number=table_number, name="migration fixture"
        )
        order = apps.get_model("orders", "Order").objects.using(alias).create(
            floor=floor, order_type=order_type, source=source,
            table_id=table.pk if with_table else None,
            order_no=order_no, order_date=date(2026, 9, 7),
            is_takeout=order_type == "TAKEOUT", note="preserve historical row",
            total_price=4300, received_amount=4300, payment_method="CASH",
            received_cash_amount=4300, received_ticket_amount=0,
        )
        menu = apps.get_model("orders", "MenuItem").objects.using(alias).create(
            name="migration menu", price=4300
        )
        apps.get_model("orders", "OrderItem").objects.using(alias).create(
            order_id=order.pk, menu_item_id=menu.pk, qty=1,
            unit_price=4300, service_mode=order_type,
        )
        return order

    def assert_database_error(self, error, sqlstate, constraint=None):
        cause = error.__cause__
        self.assertIsNotNone(cause)
        self.assertEqual(
            getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None),
            sqlstate,
        )
        if constraint is not None:
            self.assertEqual(cause.diag.constraint_name, constraint)

    def assert_sequence_absent(self):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.orders_floor_b1_seq')")
            self.assertIsNone(cursor.fetchone()[0])

    def assert_sequence_state(self, last_value, is_called):
        # Pin setval's own arguments: nextval alone cannot tell (1, False) from a
        # bare CREATE SEQUENCE, so a dropped setval would otherwise go unnoticed.
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT last_value, is_called FROM orders_floor_b1_seq")
            self.assertEqual(cursor.fetchone(), (last_value, is_called))

    def assert_next_number(self, expected):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT nextval('orders_floor_b1_seq')")
            self.assertEqual(cursor.fetchone()[0], expected)

    def assert_orders_tables_empty(self, apps):
        for model in apps.get_app_config("orders").get_models():
            with self.subTest(model=model._meta.label):
                self.assertEqual(model.objects.using(self.connection.alias).count(), 0)

    @contextmanager
    def original_0020_operations(self):
        """Run 0020 with the pre-repair operations, then restore the repaired ones."""
        repaired = importlib.import_module(
            "orders.migrations.0020_create_floor_sequences"
        )
        operations = list(original_0020.Migration.operations)
        with patch.object(repaired.Migration, "operations", operations):
            yield

    def assert_constraint_failure_preserves(self, apps, start, target):
        before = self.snapshot(apps)
        self.assert_head(start)
        with self.assertRaises(IntegrityError) as caught:
            self.migrate(target)
        self.assert_database_error(caught.exception, "23514", "orders_table_rule")
        self.assertEqual(self.snapshot(apps), before)
        self.assert_head(start)

    def test_empty_database_installs_every_app_and_starts_at_one(self):
        # Deliberately migrates every leaf, not just orders: this is the path the
        # Django test runner takes when it builds its own empty PostgreSQL database,
        # which 0020 used to break. assert_head still scopes correctness to orders.
        self.assertEqual(self.connection.introspection.table_names(), [])
        self.assert_sequence_absent()
        executor = MigrationExecutor(self.connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        self.assert_head(M20)
        apps = MigrationExecutor(self.connection).loader.project_state([M20]).apps
        self.assert_orders_tables_empty(apps)
        self.assert_sequence_state(1, False)
        self.assert_next_number(1)

    def test_original_0020_still_fails_on_an_empty_database(self):
        # Pins why D-P07 changed the SQL: the pre-repair statement is the cause.
        self.assertEqual(self.connection.introspection.table_names(), [])
        with self.original_0020_operations():
            with self.assertRaises(DataError) as caught:
                self.migrate(M20)
        self.assert_database_error(caught.exception, "22003")
        self.assert_head(M19)
        self.assert_sequence_absent()

    def test_frozen_copy_still_holds_the_pre_repair_statements(self):
        # Without this, "repairing" the frozen copy would quietly turn the two
        # tests that depend on it into duplicates of the repaired-path tests.
        source = inspect.getsource(original_0020.create_sequences)
        self.assertIn("CREATE SEQUENCE IF NOT EXISTS orders_floor_b1_seq", source)
        self.assertIn("COALESCE((SELECT MAX(order_no)", source)
        self.assertNotIn("GREATEST", source)

    def test_null_order_number_is_preserved_and_sequence_starts_at_one(self):
        apps = self.migrate(M19)
        order = self.fixture(apps)
        self.assertIsNone(order.order_no)
        self.assertIsNotNone(order.table_id)
        before = self.snapshot(apps)[0]
        self.assert_sequence_absent()
        self.migrate(M20)
        self.assert_head(M20)
        self.assertEqual(self.snapshot(apps)[0], before)
        self.assert_sequence_state(1, False)
        self.assert_next_number(1)

    def test_zero_order_number_is_preserved_and_next_number_is_one(self):
        apps = self.migrate(M19)
        self.fixture(apps, order_no=0)
        before = self.snapshot(apps)[0]
        self.migrate(M20)
        self.assert_head(M20)
        self.assertEqual(self.snapshot(apps)[0], before)
        self.assert_sequence_state(1, False)
        self.assert_next_number(1)

    def test_database_migrated_by_original_0020_is_not_replayed_or_rewound(self):
        apps = self.migrate(M19)
        self.fixture(apps, order_no=40)
        with self.original_0020_operations():
            self.migrate(M20)
        self.assert_sequence_state(40, True)
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT setval('orders_floor_b1_seq', 100, true)")
        before = self.snapshot(apps)
        self.assertEqual(MigrationExecutor(self.connection).migration_plan([M20]), [])
        self.migrate(M20)
        self.assertEqual(self.snapshot(apps), before)
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT nextval('orders_floor_b1_seq')")
            self.assertEqual(cursor.fetchone()[0], 101)

    def test_unrecorded_existing_sequence_fails_without_rewind(self):
        apps = self.migrate(M19)
        self.fixture(apps, order_no=40)
        with self.connection.cursor() as cursor:
            cursor.execute("CREATE SEQUENCE orders_floor_b1_seq START WITH 100")
        before = self.snapshot(apps)
        with self.assertRaises(ProgrammingError) as caught:
            self.migrate(M20)
        self.assert_database_error(caught.exception, "42P07")
        self.assertEqual(self.snapshot(apps), before)
        self.assert_head(M19)
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT last_value, is_called FROM orders_floor_b1_seq")
            self.assertEqual(cursor.fetchone(), (100, False))

    def test_failure_after_sequence_initialization_leaves_no_partial_migration(self):
        apps = self.migrate(M19)
        self.fixture(apps, order_no=40)
        before = self.snapshot(apps)

        class InjectedFailure(Exception):
            pass

        def fail_after_setval(execute, sql, params, many, context):
            result = execute(sql, params, many, context)
            if "setval(" in sql:
                raise InjectedFailure("synthetic failure after sequence initialization")
            return result

        with self.connection.execute_wrapper(fail_after_setval):
            with self.assertRaises(InjectedFailure):
                self.migrate(M20)
        self.assert_sequence_absent()
        self.assert_head(M19)
        self.assertEqual(self.snapshot(apps), before)
        self.migrate(M20)
        self.assert_head(M20)
        self.assert_sequence_state(40, True)
        self.assert_next_number(41)

    def test_positive_40_upgrades_to_0020_and_reapplication_is_noop(self):
        apps = self.migrate(M19)
        self.fixture(apps, order_no=40)
        before_rows = self.snapshot(apps)[0]
        self.migrate(M20)
        self.assert_head(M20)
        self.assertEqual(self.snapshot(apps)[0], before_rows)
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT nextval('orders_floor_b1_seq')")
            self.assertEqual(cursor.fetchone()[0], 41)
        before = self.snapshot(apps)
        executor = MigrationExecutor(self.connection)
        self.assertEqual(executor.migration_plan([M20]), [])
        self.migrate(M20)
        self.assertEqual(self.snapshot(apps), before)
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT last_value, is_called FROM orders_floor_b1_seq")
            self.assertEqual(cursor.fetchone(), (41, True))
            cursor.execute("SELECT nextval('orders_floor_b1_seq')")
            self.assertEqual(cursor.fetchone()[0], 42)

    def test_highest_number_wins_when_several_orders_exist(self):
        # 0019 forces floor='B1' on every row, so the migration's WHERE clause can
        # never exclude a row here; what MAX must survive is several rows and a NULL.
        apps = self.migrate(M19)
        self.fixture(apps, order_no=7, table_number=1)
        self.fixture(apps, order_no=40, table_number=2)
        self.fixture(apps, order_no=None, table_number=3)
        before = self.snapshot(apps)[0]
        self.migrate(M20)
        self.assert_head(M20)
        self.assertEqual(self.snapshot(apps)[0], before)
        self.assert_sequence_state(40, True)
        self.assert_next_number(41)

    def test_reverse_drops_the_sequence_and_forward_reinitialises_from_max(self):
        # Pins the documented reverse caveat: rows survive, but a number consumed
        # before the reverse is handed out again afterwards. Not a recovery path.
        apps = self.migrate(M19)
        self.fixture(apps, order_no=40)
        self.migrate(M20)
        self.assert_next_number(41)
        rows = self.snapshot(apps)[0]

        self.migrate(M19)
        self.assert_head(M19)
        self.assert_sequence_absent()
        self.assertEqual(self.snapshot(apps)[0], rows)

        self.migrate(M20)
        self.assert_head(M20)
        self.assertEqual(self.snapshot(apps)[0], rows)
        self.assert_sequence_state(40, True)
        self.assert_next_number(41)

    def test_0018_b1_takeout_without_table_cannot_upgrade_to_0019(self):
        apps = self.migrate(M18)
        self.fixture(apps, order_type="TAKEOUT", with_table=False)
        self.assert_constraint_failure_preserves(apps, M18, M19)

    def test_0018_f1_outside_choices_can_be_inserted_but_blocks_0019(self):
        apps = self.migrate(M18)
        Order = apps.get_model("orders", "Order")
        self.assertNotIn("F1", dict(Order._meta.get_field("floor").choices))
        order = self.fixture(apps, floor="F1", order_type="TAKEOUT", with_table=False)
        stored = Order.objects.using(self.connection.alias).get(pk=order.pk)
        self.assertEqual(stored.floor, "F1")
        self.assert_constraint_failure_preserves(apps, M18, M19)

    def test_0018_booth_outside_choices_can_be_inserted_but_blocks_0019(self):
        apps = self.migrate(M18)
        Order = apps.get_model("orders", "Order")
        for field in ("order_type", "source"):
            self.assertNotIn("BOOTH", dict(Order._meta.get_field(field).choices))
        order = self.fixture(
            apps, order_type="BOOTH", source="BOOTH", with_table=False,
        )
        stored = Order.objects.using(self.connection.alias).get(pk=order.pk)
        self.assertEqual((stored.order_type, stored.source), ("BOOTH", "BOOTH"))
        self.assert_constraint_failure_preserves(apps, M18, M19)

    def test_0019_takeout_with_table_cannot_reverse_to_0018(self):
        apps = self.migrate(M19)
        self.fixture(apps, order_type="TAKEOUT", with_table=True)
        self.assert_constraint_failure_preserves(apps, M19, M18)

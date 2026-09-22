"""Pin the repaired 0020 sequence paths and the 0019 failures that remain open.

These unittest cases deliberately request no runner-managed database: each case
owns a disposable DB through pg_support and creates fixtures exclusively from
historical model states. D-P07 repaired 0020 only, so the four 0019 constraint
cases still assert failure and row preservation until that policy is decided.
"""

import importlib
import inspect
from contextlib import contextmanager
from datetime import date, timedelta
from django.utils import timezone
from unittest import TestCase
from unittest.mock import patch

from django.conf import settings
from django.db import DataError, IntegrityError, ProgrammingError
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

from orders.tests import original_0020


M18 = ("orders", "0018_alter_order_floor_alter_order_order_type_and_more")
M19 = ("orders", "0019_remove_order_orders_table_rule_and_more")
M20 = ("orders", "0020_create_floor_sequences")
M21 = ("orders", "0021_auth_device")
M22 = ("orders", "0022_eventday_ordernumbercounter_and_more")
M23 = ("orders", "0023_orderrequest")
M24 = ("orders", "0024_order_uq_active_takeout_slot")
M25 = ("orders", "0025_account_permissions_audit")
M26 = ("orders", "0026_order_change_amount")
M27 = ("orders", "0027_orderevent_kind_items")
M28 = ("orders", "0028_change_revision")
M29 = ("orders", "0029_revision_generation")
M30 = ("orders", "0030_order_departed_at")
M31 = ("orders", "0031_takeout_voucher")


class MigrationPathTests(TestCase):
    def setUp(self):
        # Each migration path owns an independent database.
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

    def test_departure_column_preserves_history_without_backfill_and_reverses(self):
        apps = self.migrate(M29)
        alias = self.connection.alias
        order = self.fixture(apps)
        historical_order = apps.get_model("orders", "Order")
        historical_order.objects.using(alias).filter(pk=order.pk).update(status="READY")
        before = historical_order.objects.using(alias).get(pk=order.pk)
        previous_updated = before.updated_at
        target = M30
        apps = self.migrate(target)
        current = apps.get_model("orders", "Order").objects.using(alias).get(pk=order.pk)
        self.assertEqual(current.status, "READY")
        self.assertIsNone(current.departed_at)
        self.assertEqual(current.updated_at, previous_updated)
        self.assertEqual(current.note, before.note)
        # The previous app can still read/write its old fields on the new schema.
        before.note = "old app remains compatible"
        before.save(using=alias, update_fields=["note"])
        apps = self.migrate(M29)
        restored = apps.get_model("orders", "Order").objects.using(alias).get(pk=order.pk)
        self.assertEqual(restored.status, "READY")
        self.assertEqual(restored.note, "old app remains compatible")
        apps = self.migrate(target)
        self.assertIsNone(apps.get_model("orders", "Order").objects.using(alias).get(pk=order.pk).departed_at)

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
        """A fresh install holds no data -- with one deliberate exception.

        10B's change marker is a counter, not a record: migration 0028 seeds
        the single row it counts on, at zero. Asserting its exact contents
        rather than skipping it keeps this check honest, because "the marker
        row exists and starts at zero" is itself a property of a fresh install
        that something could break.
        """
        for model in apps.get_app_config("orders").get_models():
            with self.subTest(model=model._meta.label):
                rows = model.objects.using(self.connection.alias)
                if model._meta.label == "orders.ChangeRevision":
                    self.assertEqual(list(rows.values_list("scope", "value")), [("board", 0)])
                    continue
                self.assertEqual(rows.count(), 0)

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

    def test_empty_database_installs_every_app_and_ends_without_the_sequence(self):
        # Deliberately migrates every leaf, not just orders: this is the path the
        # Django test runner takes when it builds its own empty PostgreSQL database,
        # which 0020 used to break. assert_head still scopes correctness to orders.
        self.assertEqual(self.connection.introspection.table_names(), [])
        self.assert_sequence_absent()
        executor = MigrationExecutor(self.connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        leaf = M31
        self.assert_head(leaf)
        apps = MigrationExecutor(self.connection).loader.project_state([leaf]).apps
        self.assert_orders_tables_empty(apps)
        # D-047 replaced the sequence with a counter row, so a fresh database
        # must end with no sequence at all. 0020's own paths are asserted above
        # at their own target and are unaffected.
        self.assert_sequence_absent()

    def test_the_numbering_change_reverses_back_to_the_sequence(self):
        """0022 is reversible: stepping back restores the 0020 sequence."""
        self.migrate(M22)
        self.assert_sequence_absent()
        self.migrate(M21)
        self.assert_sequence_state(1, False)
        self.assert_next_number(1)

    def legacy_order(self, apps, *, order_no, order_date, table_number):
        """An order written under the old per-day numbering contract."""
        alias = self.connection.alias
        table = apps.get_model("orders", "Table").objects.using(alias).create(
            number=table_number, name="legacy fixture"
        )
        return apps.get_model("orders", "Order").objects.using(alias).create(
            floor="B1", order_type="DINE_IN", source="ORDER", table_id=table.pk,
            order_no=order_no, order_date=order_date, is_takeout=False,
            total_price=4300, received_amount=4300, payment_method="CASH",
            received_cash_amount=4300, received_ticket_amount=0,
        )

    def test_orders_written_before_the_change_stay_in_the_sales_figures(self):
        """The new column defaults to PRACTICE, and the dashboard counts only
        REAL. Without a backfill every historical order would silently drop out
        of the sales totals -- so 0022 classifies them."""
        apps = self.migrate(M21)
        self.legacy_order(apps, order_no=7, order_date=date(2025, 10, 18), table_number=1)
        self.legacy_order(apps, order_no=8, order_date=date(2026, 9, 7), table_number=2)
        after = self.migrate(M22)
        series = sorted(
            after.get_model("orders", "Order").objects.using(self.connection.alias)
            .values_list("order_no", "number_series")
        )
        self.assertEqual(series, [(7, "REAL"), (8, "REAL")])

    def test_numbers_repeated_across_days_of_one_year_stop_the_migration(self):
        """Numbering used to restart daily, so the same number can appear on two
        days of one year. The new uniqueness is yearly, and those rows violate
        it. Renumbering them is out of scope, so the migration refuses with an
        explanation instead of a bare unique violation."""
        apps = self.migrate(M21)
        self.legacy_order(apps, order_no=1, order_date=date(2025, 10, 18), table_number=1)
        self.legacy_order(apps, order_no=1, order_date=date(2025, 10, 19), table_number=2)
        with self.assertRaises(RuntimeError) as caught:
            self.migrate(M22)
        self.assertIn("floor=B1 series=REAL year=2025 no=1", str(caught.exception))
        # Nothing half-applied: the head is still the previous migration and the
        # rows are untouched.
        self.assert_head(M21)
        rows = (
            MigrationExecutor(self.connection).loader.project_state([M21]).apps
            .get_model("orders", "Order").objects.using(self.connection.alias)
            .values_list("order_no", "order_date")
        )
        self.assertEqual(
            sorted(rows),
            [(1, date(2025, 10, 18)), (1, date(2025, 10, 19))],
        )

    def test_the_same_number_on_two_days_is_fine_in_different_years(self):
        apps = self.migrate(M21)
        self.legacy_order(apps, order_no=1, order_date=date(2025, 10, 18), table_number=1)
        self.legacy_order(apps, order_no=1, order_date=date(2026, 10, 17), table_number=2)
        self.migrate(M22)
        self.assert_head(M22)

    def test_auth_tables_upgrade_and_reverse_preserve_existing_orders(self):
        apps = self.migrate(M20)
        self.fixture(apps, order_no=7)
        models = list(apps.get_app_config("orders").get_models())
        def rows():
            return {model._meta.label: list(model.objects.order_by("pk").values())
                    for model in models}
        before = rows()
        self.migrate(("orders", "0021_auth_device"))
        self.assertEqual(rows(), before)
        self.assertIn("orders_authdevice", self.connection.introspection.table_names())
        self.assertIn("orders_loginattempt", self.connection.introspection.table_names())
        # Schema reversibility only: reverting the old auth app is NOT a safe
        # operational rollback because its legacy sessions may become valid.
        self.migrate(M20)
        self.assertEqual(rows(), before)
        self.assertNotIn("orders_authdevice", self.connection.introspection.table_names())
        self.assertNotIn("orders_loginattempt", self.connection.introspection.table_names())

    def active_takeout_pair(self, apps, *, table_number=101):
        """Two live takeout orders holding one tag: what a database written
        before D-050 may contain, and exactly what 0024 forbids."""
        alias = self.connection.alias
        table = apps.get_model("orders", "Table").objects.using(alias).create(
            number=table_number, name="takeout tag"
        )
        order_model = apps.get_model("orders", "Order")
        return [
            order_model.objects.using(alias).create(
                floor="B1", order_type="TAKEOUT", source="ORDER", status=status,
                table_id=table.pk, is_takeout=True, total_price=4300,
                received_amount=4300, payment_method="CASH",
                received_cash_amount=4300, received_ticket_amount=0,
            )
            for status in ("PREPARING", "READY")
        ]

    def test_0023_active_takeout_orders_sharing_a_tag_cannot_upgrade_to_0024(self):
        """0024 fails closed on legacy duplicates and leaves every row in place.

        A deployment that hits this has to release the tag (cancel or hand
        over one of the orders) and migrate again; ORDER_STATE.md carries the
        query that finds such rows before the migration is run.
        """
        apps = self.migrate(M23)
        self.active_takeout_pair(apps)
        before = self.snapshot(apps)
        with self.assertRaises(IntegrityError) as caught:
            self.migrate(M24)
        self.assert_database_error(caught.exception, "23505", "uq_active_takeout_slot")
        self.assertEqual(self.snapshot(apps), before)
        self.assert_head(M23)

    def test_0024_applies_once_the_duplicate_tag_is_released_and_reverses_cleanly(self):
        apps = self.migrate(M23)
        first, _ = self.active_takeout_pair(apps)
        first.status = "CANCELLED"
        first.save(update_fields=["status"])
        before = self.snapshot(apps)
        self.migrate(M24)
        self.assert_head(M24)
        # Rows only: the history now records 0024 and pg_constraint does not
        # list a unique index, so the full snapshot is compared after reverting.
        self.assertEqual(self.snapshot(apps)[0], before[0])
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_active_takeout_slot'")
            definition = cursor.fetchone()[0]
        self.assertIn("UNIQUE", definition)
        self.assertIn("WHERE", definition)
        # Schema reversibility only; the business rule is not something to
        # roll back once the event has run on it.
        self.migrate(M23)
        self.assert_head(M23)
        self.assertEqual(self.snapshot(apps), before)

    def test_0025_revokes_every_shared_account_device_and_keeps_orders(self):
        """D-051: nobody keeps a session across the change to personal
        accounts, and nothing that was ordered goes missing."""
        apps = self.migrate(M24)
        alias = self.connection.alias
        order = self.fixture(apps, order_no=3)
        apps.get_model("orders", "OrderRequest").objects.using(alias).create(
            key="attempt-0000-0001", role="ORDER", fingerprint="f" * 64, order_id=order.pk,
        )
        device_model = apps.get_model("orders", "AuthDevice")
        device_model.objects.using(alias).create(
            role="ORDER", account_id="order", credential_fingerprint="a" * 64,
            refresh_jti_hash="b" * 64, expires_at=timezone.now() + timedelta(hours=1),
        )
        after = self.migrate(M25)
        self.assert_head(M25)
        device = after.get_model("orders", "AuthDevice").objects.using(alias).get()
        self.assertIsNotNone(device.revoked_at)
        self.assertIsNone(device.account_id)
        kept = after.get_model("orders", "Order").objects.using(alias).get(pk=order.pk)
        self.assertEqual(kept.order_no, 3)
        self.assertIsNone(kept.created_by_id)
        request = after.get_model("orders", "OrderRequest").objects.using(alias).get()
        self.assertEqual(request.actor, "ORDER")
        columns = {
            column.name for column in
            self.connection.introspection.get_table_description(
                self.connection.cursor().cursor, "orders_authdevice")
        }
        self.assertNotIn("role", columns)
        self.assertIn("account_id", columns)
        self.assertIn("orders_account", self.connection.introspection.table_names())
        self.assertIn("orders_orderevent", self.connection.introspection.table_names())
        # Schema reversibility only: the old application must not be restored.
        self.migrate(M24)
        self.assert_head(M24)
        self.assertEqual(
            apps.get_model("orders", "Order").objects.using(alias).get(pk=order.pk).order_no, 3
        )

    def test_0026_adds_the_change_column_without_backfilling_old_rows(self):
        """7A (D-048): the change is stored from now on. Rows from before keep
        NULL -- the API computes those -- and nothing about them is rewritten.
        Rolling the column back leaves the order as it was."""
        apps = self.migrate(M25)
        alias = self.connection.alias
        order = self.fixture(apps, order_no=5)
        apps.get_model("orders", "Order").objects.using(alias).filter(pk=order.pk).update(
            received_amount=10000, received_cash_amount=10000, total_price=4300,
        )
        after = self.migrate(M26)
        self.assert_head(M26)
        kept = after.get_model("orders", "Order").objects.using(alias).get(pk=order.pk)
        self.assertIsNone(kept.change_amount)
        self.assertEqual((kept.received_cash_amount, kept.total_price, kept.order_no), (10000, 4300, 5))
        self.migrate(M25)
        self.assert_head(M25)
        columns = {
            column.name for column in
            self.connection.introspection.get_table_description(
                self.connection.cursor().cursor, "orders_order")
        }
        self.assertNotIn("change_amount", columns)
        self.assertEqual(
            apps.get_model("orders", "Order").objects.using(alias).get(pk=order.pk).received_cash_amount, 10000
        )

    def test_0028_adds_the_change_marker_without_touching_existing_orders(self):
        """10B (D-019): the marker arrives at zero and nothing else moves.

        A database that already holds orders gets one new row in one new table.
        No order is read, rewritten or re-keyed. Zero is the correct starting
        value, not a gap: every screen reads it as older than anything it could
        be holding, so the first connection after the migration fetches once
        and is current from then on.

        Rolling back drops the table. The older application does not know the
        marker exists, so it neither reads nor writes it; what it loses is the
        ability to say that something changed -- the state it was already in
        before this phase. The orders are still there, unchanged, either way.
        """
        apps = self.migrate(M27)
        alias = self.connection.alias
        order = self.fixture(apps, order_no=9)
        before = self.snapshot(apps)

        after = self.migrate(M28)
        self.assert_head(M28)
        markers = list(
            after.get_model("orders", "ChangeRevision").objects.using(alias)
            .values_list("scope", "value")
        )
        self.assertEqual(markers, [("board", 0)])
        kept = after.get_model("orders", "Order").objects.using(alias).get(pk=order.pk)
        self.assertEqual(kept.order_no, 9)

        back = self.migrate(M27)
        self.assert_head(M27)
        self.assertNotIn("orders_changerevision", self.connection.introspection.table_names())
        self.assertEqual(self.snapshot(back), before)

    def test_0029_gives_the_marker_a_lineage_without_disturbing_it(self):
        """10C (D-019): the column that makes a restore visible to a screen.

        Additive. The marker's value is untouched and no order is read, so the
        only thing that changes is that every version handed out from now on
        says which lineage it belongs to.

        Rolling back drops the column. Versions from the older application
        have no generation in them, so a screen holding one cannot match a new
        one and fetches once -- which is the safe direction. That property is
        the entire reason for the column, so it is worth stating that it holds
        in both directions rather than only forwards.
        """
        apps = self.migrate(M28)
        alias = self.connection.alias
        order = self.fixture(apps, order_no=11)
        marker = apps.get_model("orders", "ChangeRevision").objects.using(alias)
        marker.filter(scope="board").update(value=7)

        after = self.migrate(M29)
        self.assert_head(M29)
        rows = list(
            after.get_model("orders", "ChangeRevision").objects.using(alias)
            .values_list("scope", "value", "generation")
        )
        self.assertEqual(len(rows), 1)
        scope, value, generation = rows[0]
        self.assertEqual((scope, value), ("board", 7), "the value is not disturbed")
        self.assertIsNotNone(generation)
        self.assertEqual(
            after.get_model("orders", "Order").objects.using(alias).get(pk=order.pk).order_no, 11
        )

        back = self.migrate(M28)
        self.assert_head(M28)
        columns = {
            column.name for column in
            self.connection.introspection.get_table_description(
                self.connection.cursor().cursor, "orders_changerevision")
        }
        self.assertNotIn("generation", columns)
        self.assertEqual(
            back.get_model("orders", "ChangeRevision").objects.using(alias)
            .get(scope="board").value, 7
        )

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

    # ---- 0031 (D-069): takeout orders stop holding a table or a tag ----
    # Before it, a takeout row without a table is refused by `orders_table_rule`
    # and two live takeout rows on one tag by `uq_active_takeout_slot`; after
    # it, both are ordinary data. Reversal restores the schema only while no
    # such rows exist -- they are the new contract's data, not a mistake.

    def takeout_row(self, apps, *, table_id=None, status="PREPARING"):
        return apps.get_model("orders", "Order").objects.using(self.connection.alias).create(
            floor="B1", order_type="TAKEOUT", source="ORDER", status=status,
            table_id=table_id, is_takeout=True, total_price=4300,
            received_amount=4300, payment_method="CASH",
            received_cash_amount=4300, received_ticket_amount=0,
        )

    def test_0030_refuses_a_takeout_order_without_a_table(self):
        apps = self.migrate(M30)
        with self.assertRaises(IntegrityError) as caught:
            self.takeout_row(apps)
        self.assert_database_error(caught.exception, "23514", "orders_table_rule")

    def test_0031_lets_takeout_orders_share_or_lack_a_table_and_reverses_cleanly(self):
        apps = self.migrate(M30)
        before = self.snapshot(apps)
        self.migrate(M31)
        self.assert_head(M31)
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_indexes WHERE indexname = 'uq_active_takeout_slot'")
            self.assertIsNone(cursor.fetchone(), "the slot index is gone")
        first, second = self.active_takeout_pair(apps)      # one tag, two live orders
        loose = self.takeout_row(apps)                         # no table at all
        self.assertIsNone(loose.table_id)
        for row in (first, second, loose):
            row.delete()
        apps.get_model("orders", "Table").objects.using(self.connection.alias).filter(number=101).delete()
        self.migrate(M30)
        self.assert_head(M30)
        self.assertEqual(self.snapshot(apps), before)

    def test_0031_does_not_reverse_over_voucher_rows(self):
        apps = self.migrate(M31)
        self.takeout_row(apps)
        with self.assertRaises(IntegrityError) as caught:
            self.migrate(M30)
        self.assert_database_error(caught.exception, "23514", "orders_table_rule")
        self.assert_head(M31)

    def test_0031_does_not_reverse_over_takeout_rows_sharing_a_tag(self):
        """The other constraint reversal restores: one tag, two live orders."""
        apps = self.migrate(M31)
        self.active_takeout_pair(apps)
        with self.assertRaises(IntegrityError) as caught:
            self.migrate(M30)
        self.assert_database_error(caught.exception, "23505", "uq_active_takeout_slot")
        self.assert_head(M31)

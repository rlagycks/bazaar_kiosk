"""Copy into the isolated candidate's orders/tests, never apply to the source tree.

Requires the proposal patch and the original 0020 copied as original_0020.py.
The inherited four constraint failures remain expected: this is not all of 1B.
"""

import importlib
from unittest.mock import patch

from django.db import ProgrammingError, IntegrityError
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory

from orders.tests.test_migration_paths import MigrationPathTests, M18, M19, M20
from orders.tests import original_0020
from orders.views import api


class SequenceCandidateTests(MigrationPathTests):
    # Replace these inherited failure cases with the named success cases below.
    # unittest collects only callable test attributes; the original suite is intact.
    test_empty_database_to_0020_fails_and_rolls_back_sequence_ddl = None
    test_0019_null_order_number_fails_0020_without_losing_rows = None

    def test_empty_database_installs_and_starts_at_one(self):
        executor = MigrationExecutor(self.connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        self.assert_head(M20)
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM orders_order")
            self.assertEqual(cursor.fetchone()[0], 0)
            cursor.execute("SELECT last_value, is_called FROM orders_floor_b1_seq")
            self.assertEqual(cursor.fetchone(), (1, False))
            cursor.execute("SELECT nextval('orders_floor_b1_seq')")
            self.assertEqual(cursor.fetchone()[0], 1)

    def test_null_order_number_is_preserved_and_sequence_starts_at_one(self):
        apps = self.migrate(M19)
        self.fixture(apps)
        before = self.snapshot(apps)[0]
        self.migrate(M20)
        self.assert_head(M20)
        self.assertEqual(self.snapshot(apps)[0], before)
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT nextval('orders_floor_b1_seq')")
            self.assertEqual(cursor.fetchone()[0], 1)

    def test_existing_original_0020_is_not_replayed_or_rewound(self):
        apps = self.migrate(M19)
        self.fixture(apps, order_no=40)
        candidate = importlib.import_module("orders.migrations.0020_create_floor_sequences")
        with patch.object(candidate.Migration, "operations", original_0020.Migration.operations):
            self.migrate(M20)
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT setval('orders_floor_b1_seq', 100, true)")
        before = self.snapshot(apps)
        self.migrate(M20)
        self.assertEqual(self.snapshot(apps), before)
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT nextval('orders_floor_b1_seq')")
            self.assertEqual(cursor.fetchone()[0], 101)

    def test_zero_order_number_is_preserved_and_next_number_is_one(self):
        apps = self.migrate(M19)
        self.fixture(apps, order_no=0)
        before = self.snapshot(apps)[0]
        self.migrate(M20)
        self.assertEqual(self.snapshot(apps)[0], before)
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT nextval('orders_floor_b1_seq')")
            self.assertEqual(cursor.fetchone()[0], 1)

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

        def fail_after_setval(execute, query, params, many, context):
            result = execute(query, params, many, context)
            if "SELECT setval(" in query:
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

    def test_not_valid_preserves_legacy_but_breaks_existing_status_updates(self):
        # Explore the SQL policy in this disposable DB, not an approved migration.
        apps = self.migrate(M18)
        order = self.fixture(apps, order_type="TAKEOUT", with_table=False)
        before_rows = self.snapshot(apps)[0]
        with self.connection.cursor() as cursor:
            cursor.execute("ALTER TABLE orders_order DROP CONSTRAINT orders_table_rule")
            cursor.execute("""
                ALTER TABLE orders_order ADD CONSTRAINT orders_table_rule
                CHECK (floor = 'B1' AND order_type IN ('DINE_IN', 'TAKEOUT')
                       AND table_id IS NOT NULL) NOT VALID
            """)
        self.assertEqual(self.snapshot(apps)[0], before_rows)
        request = RequestFactory().patch(
            "/", {"status": "READY"}, content_type="application/json"
        )
        request.session = {"role": "KITCHEN"}
        with self.assertRaises(IntegrityError) as caught:
            api.order_status(request, order.pk)
        self.assert_database_error(caught.exception, "23514", "orders_table_rule")
        self.assertEqual(self.snapshot(apps)[0], before_rows)
        with self.connection.cursor() as cursor:
            with self.assertRaises(IntegrityError):
                cursor.execute("ALTER TABLE orders_order VALIDATE CONSTRAINT orders_table_rule")

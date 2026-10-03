"""UI-05B monitoring reads against PostgreSQL, including a concurrent commit."""

from datetime import timedelta
from itertools import product
import threading
import uuid
from unittest.mock import patch

from django.db import connection, transaction
from django.test import Client, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from orders.models import ChangeRevision, MenuItem, Order, OrderItem, Table
from orders.roles import HALL_MONITOR, PERMISSION_CODES, TAKEOUT_MONITOR
from orders.services import monitoring_snapshot, revisions, snapshots
from orders.tests.auth_support import AUTH_SETTINGS, login_client, make_account
from orders.views import serializers


BOTH = (HALL_MONITOR, TAKEOUT_MONITOR)


@override_settings(**AUTH_SETTINGS)
class MonitoringSnapshotTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, "postgresql")
        self.table = Table.objects.create(number=41, name="Original table")
        self.menu = MenuItem.objects.create(name="Original meal", price=1000)
        with transaction.atomic():
            revisions.mark()

    def make_order(self, *, modes=("DINE_IN",), status="PREPARING"):
        # Deliberately use DINE_IN at order level even for takeout items:
        # classification must follow the actual items, not the header.
        order = Order.objects.create(
            table=self.table, floor="B1", order_type="DINE_IN", status=status,
            total_price=1000 * len(modes), payment_method="CASH",
            received_cash_amount=1000 * len(modes),
        )
        OrderItem.objects.bulk_create([
            OrderItem(order=order, menu_item=self.menu, qty=1,
                      unit_price=1000, service_mode=mode)
            for mode in modes
        ])
        return order

    def make_many(self, count, *, mode="DINE_IN", status="PREPARING"):
        rows = Order.objects.bulk_create([
            Order(table=self.table, floor="B1", order_type="DINE_IN",
                  status=status, total_price=1000, payment_method="CASH",
                  received_cash_amount=1000)
            for _ in range(count)
        ])
        OrderItem.objects.bulk_create([
            OrderItem(order=row, menu_item=self.menu, qty=1, unit_price=1000,
                      service_mode=mode)
            for row in rows
        ])
        return rows

    def read(self, *, permissions=BOTH, mode="ALL", page=1, since=None):
        return monitoring_snapshot.read(permissions, mode=mode, page=page, since=since)

    def client_as(self, alias="BOTH_MONITORS"):
        client = Client()
        login_client(client, alias)
        return client

    def get(self, client, **params):
        return client.get(reverse("orders:snapshot-monitoring"), params)

    @staticmethod
    def ids(rows):
        return [row["id"] for row in rows]

    def test_all_sixteen_permission_sets_for_each_requested_scope(self):
        hall = self.make_order()
        takeout = self.make_order(modes=("TAKEOUT",))
        mixed = self.make_order(modes=("TAKEOUT", "DINE_IN"))
        client = self.client_as("BOTH_MONITORS")
        expected = {"HALL": {hall.pk, mixed.pk}, "TAKEOUT": {takeout.pk},
                    "ALL": {hall.pk, mixed.pk, takeout.pk}}
        required = {"HALL": {HALL_MONITOR}, "TAKEOUT": {TAKEOUT_MONITOR},
                    "ALL": set(BOTH)}
        for flags in product((False, True), repeat=len(PERMISSION_CODES)):
            held = {code for code, enabled in zip(PERMISSION_CODES, flags) if enabled}
            make_account("both-monitors", *held)
            for mode in required:
                with self.subTest(permissions=held, scope=mode):
                    response = self.get(client, scope=mode)
                    if not required[mode] <= held:
                        self.assertEqual(response.status_code, 403)
                        continue
                    self.assertEqual(response.status_code, 200)
                    data = response.json()
                    self.assertEqual(set(self.ids(data["orders"])), expected[mode])
                    self.assertEqual(set(self.ids(data["history"]["orders"])), expected[mode])
                    self.assertEqual(data["total"], len(expected[mode]))
                    self.assertEqual(data["history"]["total"], len(expected[mode]))

    def test_unauthenticated_and_non_get_requests(self):
        self.assertEqual(self.get(Client(), scope="ALL").status_code, 401)
        client = self.client_as()
        self.assertEqual(client.post(reverse("orders:snapshot-monitoring")).status_code, 405)

    def test_invalid_scope_and_page_are_400(self):
        client = self.client_as()
        for mode in ("", "STATS", "DINE_IN", "hall", "UNKNOWN"):
            with self.subTest(scope=mode):
                self.assertEqual(self.get(client, scope=mode).status_code, 400)
        for page in ("", "0", "-1", "1.5", "abc", "1000001", "9" * 5000):
            with self.subTest(page=page[:30]):
                self.assertEqual(self.get(client, scope="ALL", page=page).status_code, 400)

    def test_service_also_enforces_authorization(self):
        for held, mode in (((), "ALL"), (("STATS",), "HALL"),
                           ((HALL_MONITOR,), "ALL"), ((HALL_MONITOR,), "TAKEOUT")):
            with self.subTest(held=held, mode=mode), self.assertRaises(PermissionError):
                self.read(permissions=held, mode=mode)

    def test_default_response_contract_and_cache_policy(self):
        self.make_order()
        response = self.get(self.client_as())
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        data = response.json()
        self.assertEqual(set(data), {"version", "unchanged", "cursor", "orders", "count",
                                    "total", "has_more", "complete", "history"})
        self.assertEqual(set(data["history"]), {"orders", "total", "page", "pages",
                                                "has_previous", "has_next"})
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["history"]["page"], 1)
        self.assertEqual(data["cursor"], "absent")

    def test_waiting_oldest_first_history_all_statuses_newest_first_and_all_dates(self):
        old = self.make_order()
        ready = self.make_order(status="READY")
        cancelled = self.make_order(status="CANCELLED")
        recent = self.make_order()
        stamp = timezone.now()
        Order.objects.filter(pk=old.pk).update(
            created_at=stamp - timedelta(days=400), order_date=(stamp - timedelta(days=400)).date())
        Order.objects.exclude(pk=old.pk).update(created_at=stamp)
        data = self.read()
        self.assertEqual(self.ids(data["orders"]), [old.pk, recent.pk])
        self.assertEqual(self.ids(data["history"]["orders"]),
                         [recent.pk, cancelled.pk, ready.pk, old.pk])
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["history"]["total"], 4)

    def test_history_exact_pages_and_navigation_do_not_make_waiting_incomplete(self):
        rows = self.make_many(101, status="READY")
        ordered = [row.pk for row in reversed(rows)]
        for page, size in ((1, 50), (2, 50), (3, 1)):
            with self.subTest(page=page):
                data = self.read(page=page)
                history = data["history"]
                self.assertEqual(self.ids(history["orders"]), ordered[(page - 1) * 50:page * 50])
                self.assertEqual(len(history["orders"]), size)
                self.assertEqual(history["total"], 101)
                self.assertEqual(history["pages"], 3)
                self.assertEqual(history["page"], page)
                self.assertEqual(history["has_previous"], page > 1)
                self.assertEqual(history["has_next"], page < 3)
                self.assertTrue(data["complete"])
                self.assertFalse(data["has_more"])

    def test_empty_and_out_of_range_pages_have_exact_totals_and_distinct_cursors(self):
        empty = self.read()
        self.assertEqual(empty["history"], {"orders": [], "total": 0, "page": 1,
                                           "pages": 0, "has_previous": False, "has_next": False})
        self.make_many(51, status="CANCELLED")
        first = self.read()
        outside = self.read(page=1000000, since=first["version"])
        self.assertFalse(outside["unchanged"])
        self.assertEqual(outside["cursor"], "rejected")
        self.assertEqual(outside["history"], {"orders": [], "total": 51, "page": 1000000,
                                             "pages": 2, "has_previous": True, "has_next": False})
        self.assertTrue(self.read(page=1000000, since=outside["version"])["unchanged"])
        self.assertFalse(self.read(page=2, since=outside["version"])["unchanged"])

    def test_more_than_500_waiting_orders_discloses_truncation_even_when_unchanged(self):
        rows = self.make_many(501)
        data = self.read()
        self.assertEqual(self.ids(data["orders"]), [row.pk for row in rows[:500]])
        self.assertEqual(data["count"], 500)
        self.assertEqual(data["total"], 501)
        self.assertTrue(data["has_more"])
        self.assertFalse(data["complete"])
        self.assertEqual(data["history"]["total"], 501)
        again = self.read(since=data["version"])
        self.assertTrue(again["unchanged"])
        self.assertEqual(again["total"], 501)
        self.assertTrue(again["has_more"])
        self.assertFalse(again["complete"])

    def test_exactly_500_waiting_is_complete(self):
        self.make_many(500)
        data = self.read()
        self.assertEqual(data["count"], 500)
        self.assertTrue(data["complete"])
        self.assertFalse(data["has_more"])

    def test_requested_classification_is_applied_before_both_limits(self):
        self.make_many(501, mode="TAKEOUT")
        hall = self.make_order(modes=("TAKEOUT", "DINE_IN"))
        self.make_many(51, mode="TAKEOUT", status="CANCELLED")
        for held in (BOTH, (*BOTH, "STATS")):
            data = self.read(permissions=held, mode="HALL")
            self.assertEqual(self.ids(data["orders"]), [hall.pk])
            self.assertEqual(self.ids(data["history"]["orders"]), [hall.pk])
            self.assertEqual(data["total"], 1)
            self.assertEqual(data["history"]["total"], 1)
            self.assertTrue(data["complete"])

    def test_cursors_reject_other_scope_page_permissions_and_waiting_representation(self):
        self.make_order()
        self.make_order(modes=("TAKEOUT",))
        held = self.read(mode="HALL")["version"]
        for options in ({"mode": "TAKEOUT"}, {"mode": "ALL"},
                        {"mode": "HALL", "page": 2},
                        {"mode": "HALL", "permissions": (HALL_MONITOR,)},
                        {"mode": "HALL", "permissions": (*BOTH, "STATS")}):
            with self.subTest(options=options):
                data = self.read(since=held, **options)
                self.assertEqual(data["cursor"], "rejected")
                self.assertFalse(data["unchanged"])
        old_waiting = snapshots.waiting(BOTH).version
        data = self.read(since=old_waiting)
        self.assertEqual(data["cursor"], "rejected")
        self.assertFalse(data["unchanged"])
        self.assertEqual(len(data["history"]["orders"]), 2)

    def test_representation_version_change_rejects_cursor(self):
        held = self.read()["version"]
        with patch.object(monitoring_snapshot, "REPRESENTATION_VERSION", "future"):
            data = self.read(since=held)
        self.assertEqual(data["cursor"], "rejected")
        self.assertFalse(data["unchanged"])

    def test_restore_generation_rejects_matching_counter(self):
        held = self.read()["version"]
        ChangeRevision.objects.update(generation=uuid.uuid4())
        data = self.read(since=held)
        self.assertEqual(data["cursor"], "rejected")
        self.assertFalse(data["unchanged"])

    def test_matching_cursor_retains_metadata_and_skips_serialization(self):
        self.make_many(51, status="READY")
        self.make_order()
        held = self.read()
        with patch.object(serializers, "order", side_effect=AssertionError("must not serialize")):
            with CaptureQueriesContext(connection) as captured:
                data = self.read(since=held["version"])
        self.assertTrue(data["unchanged"])
        self.assertEqual(data["cursor"], "accepted")
        self.assertEqual(data["orders"], [])
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["total"], 1)
        self.assertTrue(data["complete"])
        self.assertEqual(data["history"], {**held["history"], "orders": []})
        selects = [q["sql"] for q in captured if q["sql"].startswith("SELECT")]
        self.assertEqual(len(selects), 3)

    def test_malformed_or_stale_cursor_always_returns_current_data(self):
        self.make_order(status="CANCELLED")
        for cursor in ("nonsense", "a:b:c:d", "123"):
            data = self.read(since=cursor)
            self.assertEqual(data["cursor"], "rejected")
            self.assertFalse(data["unchanged"])
            self.assertEqual(len(data["history"]["orders"]), 1)
        held = self.read()["version"]
        with transaction.atomic():
            revisions.mark()
        data = self.read(since=held)
        self.assertEqual(data["cursor"], "accepted")
        self.assertFalse(data["unchanged"])

    def test_data_counts_related_rows_and_revision_share_one_repeatable_read(self):
        row = self.make_order()
        held = self.read()["version"]
        original_state = revisions.state
        original_serializer = serializers.order
        errors = []

        def write():
            try:
                with transaction.atomic():
                    Order.objects.filter(pk=row.pk).update(status="READY", note="new")
                    OrderItem.objects.filter(order=row).update(prepared_qty=1)
                    MenuItem.objects.filter(pk=self.menu.pk).update(name="new meal")
                    Table.objects.filter(pk=self.table.pk).update(name="new table")
                    self.make_order(status="CANCELLED")
                    revisions.mark()
            except Exception as exc:
                errors.append(exc)
            finally:
                connection.close()

        def read_then_commit():
            state = original_state()
            writer = threading.Thread(target=write, daemon=True)
            writer.start()
            writer.join(timeout=10)
            self.assertFalse(writer.is_alive(), "writer blocked on snapshot reader")
            self.assertEqual(errors, [])
            return state

        def serialize_inside_snapshot(order):
            self.assertTrue(connection.in_atomic_block)
            with connection.cursor() as cursor:
                cursor.execute("SHOW transaction_isolation")
                self.assertEqual(cursor.fetchone()[0], "repeatable read")
            # A fresh query, even if a future serializer grows a lazy read,
            # must see the same old state as the prefetched rows.
            self.assertEqual(Order.objects.get(pk=order.pk).status, "PREPARING")
            return original_serializer(order)

        with patch.object(revisions, "state", side_effect=read_then_commit):
            with patch.object(serializers, "order", side_effect=serialize_inside_snapshot):
                data = self.read()
        self.assertEqual(data["version"], held)
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["history"]["total"], 1)
        for rows in (data["orders"], data["history"]["orders"]):
            self.assertEqual(self.ids(rows), [row.pk])
            self.assertEqual(rows[0]["status"], "PREPARING")
            self.assertEqual(rows[0]["note"], "")
            self.assertEqual(rows[0]["table"]["name"], "Original table")
            self.assertEqual(rows[0]["items"][0]["prepared_qty"], 0)
            self.assertEqual(rows[0]["items"][0]["menu_item_name"], "Original meal")
        after = self.read(since=held)
        self.assertFalse(after["unchanged"])
        self.assertEqual(after["total"], 0)
        self.assertEqual(after["history"]["total"], 2)

    def test_service_refuses_an_existing_read_committed_transaction(self):
        with transaction.atomic():
            Order.objects.count()
            with self.assertRaises(RuntimeError):
                self.read()

    def test_query_count_is_bounded_and_serialized_result_has_no_lazy_reads(self):
        self.make_order()
        with CaptureQueriesContext(connection) as small:
            self.read()
        self.make_many(500)
        with CaptureQueriesContext(connection) as large:
            data = self.read()
        small_selects = [q for q in small if q["sql"].startswith("SELECT")]
        large_selects = [q for q in large if q["sql"].startswith("SELECT")]
        self.assertLessEqual(len(large_selects), len(small_selects) + 1)
        self.assertLessEqual(len(large_selects), 9)
        sql = "\n".join(q["sql"] for q in large)
        self.assertIn("LIMIT 501", sql)
        self.assertIn("LIMIT 50", sql)
        with self.assertNumQueries(0):
            self.assertEqual(len(data["orders"]), 500)
            self.assertEqual(len(data["history"]["orders"]), 50)
            for order in data["orders"] + data["history"]["orders"]:
                self.assertEqual(order["table"]["name"], "Original table")
                self.assertEqual(order["items"][0]["menu_item_name"], "Original meal")

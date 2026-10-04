"""D-077: waiting lists and takeout allocation are today's; history can pick a day."""
from datetime import date, timedelta
import uuid
from unittest.mock import patch

from django.db import connection
from django.test import Client, SimpleTestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from orders.models import MenuItem, Order, OrderItem, Table
from orders.roles import HALL_MONITOR, TAKEOUT_MONITOR
from orders.services import hub, monitoring_snapshot, takeout_monitoring, workday
from orders.tests.auth_support import AUTH_SETTINGS, login_client

BOTH = (HALL_MONITOR, TAKEOUT_MONITOR)


class WorkdayTests(SimpleTestCase):
    def test_bounds_are_the_seoul_calendar_day(self):
        start, end = workday.bounds(date(2026, 10, 4))
        self.assertEqual(start.isoformat(), "2026-10-04T00:00:00+09:00")
        self.assertEqual(end.isoformat(), "2026-10-05T00:00:00+09:00")

    def test_parse_day_accepts_only_calendar_dates(self):
        self.assertIsNone(workday.parse_day(None))
        self.assertIsNone(workday.parse_day(""))
        self.assertEqual(workday.parse_day("2026-10-04"), date(2026, 10, 4))
        for raw in ("2026-W40-1", "20261004", "2026-02-30", "2026-10-4", " 2026-10-04", "x" * 10,
                    "9999-12-31", "0001-01-01", "1999-12-31", "2101-01-01"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                workday.parse_day(raw)


@override_settings(**AUTH_SETTINGS)
class TodayOnlyWaitingTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, "postgresql")
        self.table = Table.objects.create(number=7, name="T7")
        self.menu = MenuItem.objects.create(name="추어탕", price=8000)

    def order(self, *modes, qty=1, days_ago=0):
        order = Order.objects.create(table=self.table, floor="B1", order_type="DINE_IN",
                                     status="PREPARING")
        for mode in modes or ("DINE_IN",):
            OrderItem.objects.create(order=order, menu_item=self.menu, qty=qty,
                                     unit_price=8000, service_mode=mode)
        if days_ago:
            Order.objects.filter(pk=order.pk).update(
                created_at=timezone.now() - timedelta(days=days_ago))
        return order

    def ids(self, rows):
        return sorted(row["id"] for row in rows)

    def test_monitor_waiting_lists_leave_out_earlier_days_but_history_keeps_them(self):
        old_hall, old_takeout = self.order(days_ago=1), self.order("TAKEOUT", days_ago=1)
        hall, takeout = self.order(), self.order("TAKEOUT")
        for mode, permissions, expected in (("ALL", BOTH, [hall.pk, takeout.pk]),
                                            ("HALL", (HALL_MONITOR,), [hall.pk]),
                                            ("TAKEOUT", (TAKEOUT_MONITOR,), [takeout.pk])):
            with self.subTest(mode=mode):
                data = monitoring_snapshot.read(permissions, mode=mode)
                self.assertEqual(self.ids(data["orders"]), expected)
                self.assertEqual(data["total"], len(expected))
                self.assertEqual(data["history"]["total"], 2 * len(expected))
        data = monitoring_snapshot.read(BOTH)
        self.assertIn(old_hall.pk, self.ids(data["history"]["orders"]))
        self.assertIn(old_takeout.pk, self.ids(data["history"]["orders"]))
        self.assertIsNone(data["history"]["date"])

    def test_history_can_be_narrowed_to_one_day(self):
        old = self.order(days_ago=1)
        today = self.order()
        yesterday = workday.today() - timedelta(days=1)
        data = monitoring_snapshot.read(BOTH, day=yesterday)
        self.assertEqual(self.ids(data["history"]["orders"]), [old.pk])
        self.assertEqual(data["history"]["date"], yesterday.isoformat())
        self.assertEqual(self.ids(data["orders"]), [today.pk])  # the queue stays today's
        takeout = takeout_monitoring.read((TAKEOUT_MONITOR,), day=yesterday)
        self.assertEqual(takeout["history"]["total"], 0)

    def test_version_moves_at_midnight_and_with_the_history_filter(self):
        first = monitoring_snapshot.read(BOTH)["version"]
        self.assertTrue(monitoring_snapshot.read(BOTH, since=first)["unchanged"])
        other_day = monitoring_snapshot.read(BOTH, day=workday.today())["version"]
        self.assertNotEqual(first, other_day)
        tomorrow = workday.today() + timedelta(days=1)
        with patch.object(workday, "today", return_value=tomorrow):
            self.assertFalse(monitoring_snapshot.read(BOTH, since=first)["unchanged"])

    def test_hub_digest_moves_at_midnight(self):
        self.order(days_ago=1)
        before, _ = hub._scope_view(frozenset(BOTH))
        tomorrow = workday.today() + timedelta(days=1)
        with patch.object(workday, "today", return_value=tomorrow):
            after, _ = hub._scope_view(frozenset(BOTH))
        self.assertNotEqual(before, after)

    def test_takeout_completion_goes_to_todays_orders_not_a_leftover(self):
        leftover = self.order("TAKEOUT", qty=2, days_ago=1)
        fresh = self.order("TAKEOUT", qty=2)
        data = takeout_monitoring.read((TAKEOUT_MONITOR,))
        self.assertEqual(data["remaining_total"], 2)
        self.assertEqual(data["total"], 1)
        client = Client()
        login_client(client, "TAKEOUT_MONITOR")
        response = client.post(reverse("orders:takeout-complete"), {
            "request_id": str(uuid.uuid4()), "expected_version": data["completion_version"],
            "items": [{"key": f"menu:{self.menu.pk}", "quantity": 2}]}, content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["completed_orders"], [fresh.pk])
        fresh.refresh_from_db()
        leftover.refresh_from_db()
        self.assertEqual(fresh.status, "READY")
        self.assertEqual((leftover.status, leftover.items.get().prepared_qty), ("PREPARING", 0))

    def test_a_takeout_batch_read_before_midnight_is_refused_after_it(self):
        self.order("TAKEOUT", qty=2)
        version = takeout_monitoring.read((TAKEOUT_MONITOR,))["completion_version"]
        tomorrow = workday.today() + timedelta(days=1)
        with patch.object(workday, "today", return_value=tomorrow):
            self.assertNotEqual(takeout_monitoring.read((TAKEOUT_MONITOR,))["completion_version"], version)

    def test_takeout_stream_digest_is_stable_within_a_day_and_moves_at_midnight(self):
        self.order("TAKEOUT", qty=2, days_ago=1)
        self.order("TAKEOUT", qty=1)
        first = takeout_monitoring.stream_digest()
        self.assertEqual(takeout_monitoring.stream_digest(), first)
        tomorrow = workday.today() + timedelta(days=1)
        with patch.object(workday, "today", return_value=tomorrow):
            self.assertNotEqual(takeout_monitoring.stream_digest(), first)

    def test_a_receipt_replayed_after_midnight_returns_its_stored_result(self):
        fresh = self.order("TAKEOUT", qty=1)
        client = Client()
        login_client(client, "TAKEOUT_MONITOR")
        body = {"request_id": str(uuid.uuid4()),
                "expected_version": takeout_monitoring.read((TAKEOUT_MONITOR,))["completion_version"],
                "items": [{"key": f"menu:{self.menu.pk}", "quantity": 1}]}
        url = reverse("orders:takeout-complete")
        first = client.post(url, body, content_type="application/json")
        self.assertEqual(first.status_code, 200, first.content)
        tomorrow = workday.today() + timedelta(days=1)
        with patch.object(workday, "today", return_value=tomorrow):
            again = client.post(url, body, content_type="application/json")
        self.assertEqual((again.status_code, again.json()), (200, first.json()))
        self.assertEqual(fresh.items.get().prepared_qty, 1)

    def test_endpoints_validate_the_date_and_pages_carry_it(self):
        client = Client()
        login_client(client, "BOTH_MONITORS")
        for raw in ("2026-W40-1", "9999-12-31"):
            bad = client.get(reverse("orders:snapshot-monitoring"), {"date": raw})
            self.assertEqual(bad.status_code, 400, raw)
        good = client.get(reverse("orders:snapshot-monitoring"), {"date": "2026-10-04"})
        self.assertEqual(good.json()["history"]["date"], "2026-10-04")
        page = client.get(reverse("orders:kitchen"), {"date": "2026-10-04"})
        self.assertContains(page, "page=1&amp;date=2026-10-04")
        self.assertContains(page, 'data-history-date="2026-10-04"')
        ignored = client.get(reverse("orders:kitchen"), {"date": "<script>"})
        self.assertNotContains(ignored, "&amp;date=")
        takeout = Client()
        login_client(takeout, "TAKEOUT_MONITOR")
        self.assertEqual(takeout.get(reverse("orders:snapshot-takeout"), {"date": "nope"}).status_code, 400)
        page = takeout.get(reverse("orders:kitchen-takeout"), {"date": "2026-10-04"})
        self.assertContains(page, "page=1&amp;date=2026-10-04")

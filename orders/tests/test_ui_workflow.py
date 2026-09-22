"""Joined UI-11 journeys through real, authenticated public HTTP endpoints.

Only catalog/event/account fixtures use the ORM. Orders, preparation, departure,
reopening, cancellation, snapshots and reports all use the production views.
TransactionTestCase lets the snapshot own its real PostgreSQL transaction.
Run with the verified local fixture launcher; never against an operating DB.
"""

import re
import uuid

from django.conf import settings
from django.db import connection
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from orders.models import EventDay, MenuItem, Table
from orders.tests.auth_support import AUTH_SETTINGS, login_client


@override_settings(**AUTH_SETTINGS)
class UIWorkflowTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        db = connection.settings_dict
        if (settings.SETTINGS_MODULE != "bazaar_kiosk.settings_test_pg"
                or connection.vendor != "postgresql"
                or db["HOST"] != "127.0.0.1"
                or db["USER"] != "bk_test_runner"
                or not re.fullmatch(r"bk_test_app_[0-9a-f]{32}", db["NAME"])):
            raise RuntimeError("UI workflows require a disposable local PostgreSQL application test DB")
        super().setUpClass()

    def setUp(self):
        self.day = timezone.localdate()
        Table.objects.create(number=7)
        Table.objects.create(number=105)
        self.meal = MenuItem.objects.create(name="식사", price=5000)
        self.soup = MenuItem.objects.create(name="국", price=2000)
        self.clients = {}
        for role in ("SERVING", "HALL_MONITOR", "TAKEOUT_MONITOR", "STATS"):
            client = Client(enforce_csrf_checks=True)
            login_client(client, role)
            client.defaults["HTTP_X_CSRFTOKEN"] = client.cookies["csrftoken"].value
            self.clients[role] = client

    def create_order(self, *, takeout=False, qty=1, mixed=False):
        # Mixed: 2 meals + 1 takeaway soup = 12,000; cash 10,000 + ticket
        # 5,000 yields change 3,000. Plain takeaway: one meal, change 5,000.
        items = [{"menu_item_id": self.meal.pk, "qty": qty,
                  "service_mode": "TAKEOUT" if takeout else "DINE_IN"}]
        if mixed:
            items.append({"menu_item_id": self.soup.pk, "qty": 1, "service_mode": "TAKEOUT"})
        response = self.clients["SERVING"].post(
            reverse("orders:orders-collection"),
            {"request_id": str(uuid.uuid4()), "floor": "B1",
             "order_type": "TAKEOUT" if takeout else "DINE_IN",
             "table_number": "105" if takeout else "7",
             "payment_method": "CASH_TICKET" if mixed else "CASH",
             "received_cash_amount": 10000, "received_ticket_amount": 5000 if mixed else 0,
             "items": items}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def snapshot(self, role, scope, *, since=None):
        params = {"scope": scope}
        if since is not None:
            params["since"] = since
        response = self.clients[role].get(reverse("orders:snapshot-monitoring"), params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def row(self, snapshot, order_id, *, history=False):
        rows = snapshot["history"]["orders"] if history else snapshot["orders"]
        matches = [row for row in rows if row["id"] == order_id]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def act(self, role, row, action, *, quantities=None, expected=200):
        payload = {"action": action, "expected_version": row["monitor_version"]}
        if quantities is not None:
            self.assertEqual(len(quantities), len(row["items"]))
            payload["items"] = [{"id": item["id"], "prepared_qty": quantity}
                                for item, quantity in zip(row["items"], quantities)]
        response = self.clients[role].patch(
            reverse("orders:monitor-order-action", args=[row["id"]]),
            payload, content_type="application/json",
        )
        self.assertEqual(response.status_code, expected, response.content)

    def report(self):
        response = self.clients["STATS"].get(
            reverse("orders:stats-dashboard"), {"start_date": self.day.isoformat()},
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def assert_report(self, data, *, orders, items, revenue, cash, ticket, change, net, cancelled=0):
        self.assertEqual(data["summary"], {
            "orders": orders, "items": items, "revenue": revenue, "cancelled_orders": cancelled,
            "legacy_unsplit_orders": 0, "unattributed_orders": 0, "unattributed_amount": 0,
        })
        received = cash + ticket
        self.assertEqual(data["payment"], {
            "cash": cash, "ticket": ticket, "change": change, "net_cash": net,
            "cash_ratio": cash / received if received else 0.0,
            "ticket_ratio": ticket / received if received else 0.0,
        })
        self.assertEqual(sum(row["orders"] for row in data["hourly"]), orders)
        self.assertEqual(sum(row["revenue"] for row in data["hourly"]), revenue)

    def test_serving_to_scoped_monitors_then_depart_reopen_cancel_updates_sales(self):
        EventDay.objects.create(date=self.day, label="합성 행사")
        empty = self.snapshot("HALL_MONITOR", "HALL")
        mixed = self.create_order(qty=2, mixed=True)
        takeout = self.create_order(takeout=True)
        self.assertFalse(mixed["is_practice"])
        self.assertEqual((mixed["total_price"], mixed["received_cash_amount"],
                          mixed["received_ticket_amount"], mixed["change_amount"]),
                         (12000, 10000, 5000, 3000))
        self.assertEqual((takeout["total_price"], takeout["change_amount"]), (5000, 5000))

        hall = self.snapshot("HALL_MONITOR", "HALL", since=empty["version"])
        packing = self.snapshot("TAKEOUT_MONITOR", "TAKEOUT")
        self.assertFalse(hall["unchanged"])
        self.assertNotEqual(hall["version"], empty["version"])
        self.assertEqual([row["id"] for row in hall["orders"]], [mixed["id"]])
        self.assertEqual([row["id"] for row in packing["orders"]], [takeout["id"]])
        initial = self.row(hall, mixed["id"])
        self.assertEqual({item["service_mode"] for item in initial["items"]}, {"DINE_IN", "TAKEOUT"})
        self.assertTrue(initial["monitor_version"])
        report = self.report()
        self.assert_report(report, orders=2, items=4, revenue=17000,
                           cash=20000, ticket=5000, change=8000, net=12000)
        self.assertEqual(report["menu"], [
            {"menu_item_id": self.meal.pk, "name": "식사", "qty": 3, "amount": 15000},
            {"menu_item_id": self.soup.pk, "name": "국", "qty": 1, "amount": 2000},
        ])

        self.act("HALL_MONITOR", initial, "progress", quantities=[1, 0])
        progressed = self.snapshot("HALL_MONITOR", "HALL", since=hall["version"])
        partial = self.row(progressed, mixed["id"])
        self.assertFalse(progressed["unchanged"])
        self.assertNotEqual(partial["monitor_version"], initial["monitor_version"])
        self.assertEqual(partial["status"], "PREPARING")
        self.assertIsNone(partial["departed_at"])
        self.assertEqual([item["prepared_qty"] for item in partial["items"]], [1, 0])
        self.assertEqual(self.report(), report)
        self.act("HALL_MONITOR", initial, "depart", expected=409)

        self.act("HALL_MONITOR", partial, "depart")
        departed = self.snapshot("HALL_MONITOR", "HALL", since=progressed["version"])
        self.assertEqual(departed["orders"], [])
        ready = self.row(departed, mixed["id"], history=True)
        self.assertEqual(ready["status"], "READY")
        self.assertIsNotNone(ready["departed_at"])
        self.assertEqual([item["prepared_qty"] for item in ready["items"]], [2, 1])
        self.assertEqual(self.report(), report)

        self.act("HALL_MONITOR", ready, "reopen")
        reopened = self.row(self.snapshot("HALL_MONITOR", "HALL"), mixed["id"])
        self.assertEqual(reopened["status"], "PREPARING")
        self.assertIsNone(reopened["departed_at"])
        self.assertEqual([item["prepared_qty"] for item in reopened["items"]], [2, 1])
        self.assertEqual(self.report(), report)
        self.act("HALL_MONITOR", reopened, "cancel")
        cancelled = self.snapshot("HALL_MONITOR", "HALL")
        self.assertEqual(cancelled["orders"], [])
        final = self.row(cancelled, mixed["id"], history=True)
        self.assertEqual(final["status"], "CANCELLED")
        self.act("HALL_MONITOR", final, "reopen", expected=409)
        remaining = self.report()
        self.assert_report(remaining, orders=1, items=1, revenue=5000,
                           cash=10000, ticket=0, change=5000, net=5000, cancelled=1)
        self.assertEqual(remaining["menu"], [
            {"menu_item_id": self.meal.pk, "name": "식사", "qty": 1, "amount": 5000},
        ])
        self.act("TAKEOUT_MONITOR", self.row(packing, takeout["id"]), "depart")
        packed = self.snapshot("TAKEOUT_MONITOR", "TAKEOUT")
        self.assertEqual(packed["orders"], [])
        self.assertEqual(self.row(packed, takeout["id"], history=True)["status"], "READY")
        self.assertEqual(self.report(), remaining)

    def test_role_boundary_refusals_leave_other_scopes_and_sales_unchanged(self):
        EventDay.objects.create(date=self.day)
        mixed = self.create_order(qty=2, mixed=True)
        takeout = self.create_order(takeout=True)
        hall = self.snapshot("HALL_MONITOR", "HALL")
        packing = self.snapshot("TAKEOUT_MONITOR", "TAKEOUT")
        report = self.report()
        for role, scope in (("HALL_MONITOR", "TAKEOUT"), ("TAKEOUT_MONITOR", "HALL"),
                            ("STATS", "ALL"), ("SERVING", "HALL")):
            with self.subTest(reader=role, scope=scope):
                response = self.clients[role].get(reverse("orders:snapshot-monitoring"), {"scope": scope})
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json(), {"detail": "권한이 없습니다."})
        for role, row in (("TAKEOUT_MONITOR", self.row(hall, mixed["id"])),
                          ("HALL_MONITOR", self.row(packing, takeout["id"])),
                          ("SERVING", self.row(hall, mixed["id"])),
                          ("STATS", self.row(packing, takeout["id"]))):
            with self.subTest(writer=role):
                self.act(role, row, "cancel", expected=403)
        for role in ("SERVING", "HALL_MONITOR", "TAKEOUT_MONITOR"):
            with self.subTest(report_reader=role):
                self.assertEqual(self.clients[role].get(reverse("orders:stats-dashboard")).status_code, 403)
        self.assertEqual(self.snapshot("HALL_MONITOR", "HALL"), hall)
        self.assertEqual(self.snapshot("TAKEOUT_MONITOR", "TAKEOUT"), packing)
        self.assertEqual(self.report(), report)
        # The original version is still usable by the rightful monitor.
        self.act("TAKEOUT_MONITOR", self.row(packing, takeout["id"]), "depart")
        ready = self.row(self.snapshot("TAKEOUT_MONITOR", "TAKEOUT"), takeout["id"], history=True)
        self.assertEqual(ready["status"], "READY")
        self.assertEqual(self.report(), report)

    def test_practice_takeout_can_be_prepared_and_departed_but_never_counts_as_sales(self):
        # No EventDay fixture: the public creation endpoint selects PRACTICE.
        created = self.create_order(takeout=True, qty=2)
        self.assertTrue(created["is_practice"])
        packing = self.snapshot("TAKEOUT_MONITOR", "TAKEOUT")
        row = self.row(packing, created["id"])
        self.assertTrue(row["is_practice"])
        empty_report = self.report()
        self.assert_report(empty_report, orders=0, items=0, revenue=0,
                           cash=0, ticket=0, change=0, net=0)
        self.assertEqual(empty_report["menu"], [])
        self.assertEqual(empty_report["hourly"], [])
        self.act("TAKEOUT_MONITOR", row, "progress", quantities=[1])
        partial = self.row(self.snapshot("TAKEOUT_MONITOR", "TAKEOUT"), created["id"])
        self.assertEqual(partial["status"], "PREPARING")
        self.assertEqual(partial["items"][0]["prepared_qty"], 1)
        self.act("TAKEOUT_MONITOR", partial, "depart")
        departed = self.snapshot("TAKEOUT_MONITOR", "TAKEOUT")
        self.assertEqual(departed["orders"], [])
        ready = self.row(departed, created["id"], history=True)
        self.assertEqual(ready["status"], "READY")
        self.assertIsNotNone(ready["departed_at"])
        self.assertTrue(ready["is_practice"])
        self.assertEqual(self.report(), empty_report)
        self.act("TAKEOUT_MONITOR", ready, "cancel")
        cancelled = self.row(self.snapshot("TAKEOUT_MONITOR", "TAKEOUT"), created["id"], history=True)
        self.assertEqual(cancelled["status"], "CANCELLED")
        self.assertEqual(self.report(), empty_report)

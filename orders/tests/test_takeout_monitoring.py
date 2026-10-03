"""Menu-level completion: FIFO, isolation, retry and the read-only history."""
import threading
import uuid
from unittest.mock import patch

from django.db import connection, transaction
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse

from orders.models import MenuItem, Order, OrderItem, Table
from orders.roles import TAKEOUT_MONITOR
from orders.services import audit, revisions, takeout_monitoring as service, monitoring_actions, monitoring_snapshot, hub
from orders.services import status as status_service
from orders.tests.auth_support import AUTH_SETTINGS, login_client


@override_settings(**AUTH_SETTINGS)
class TakeoutMonitoringTests(TransactionTestCase):
    def setUp(self):
        self.menu = MenuItem.objects.create(name="추어탕", price=8000)
        self.other = MenuItem.objects.create(name="오리탕", price=9000)
        self.client = Client()
        login_client(self.client, "TAKEOUT_MONITOR")

    def order(self, *lines, status="PREPARING"):
        order = Order.objects.create(order_type="TAKEOUT", status=status)
        for menu, qty in lines or [(self.menu, 2)]:
            OrderItem.objects.create(order=order, menu_item=menu, qty=qty,
                                     unit_price=menu.price, service_mode="TAKEOUT")
        return order

    def read(self, **kwargs):
        return service.read((TAKEOUT_MONITOR,), **kwargs)

    def body(self, *lines):
        return {"request_id": str(uuid.uuid4()),
                "expected_version": self.read()["completion_version"],
                "items": [{"key": f"menu:{menu.pk}", "quantity": qty}
                          for menu, qty in lines or [(self.menu, 1)]]}

    def send(self, body, client=None):
        return (client or self.client).post(reverse("orders:takeout-complete"), body,
                                           content_type="application/json")

    def test_fifo_partial_then_complete_keeps_history_and_money(self):
        first = self.order((self.menu, 2), (self.other, 1))
        second = self.order((self.menu, 3))
        before = self.read()["history"]
        result = self.send(self.body((self.menu, 3)))
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json(), {"completed_qty": 3, "completed_orders": []})
        self.assertEqual(list(first.items.values_list("prepared_qty", flat=True)), [2, 0])
        self.assertEqual(second.items.get().prepared_qty, 1)
        result = self.send(self.body((self.other, 1)))
        self.assertEqual(result.json()["completed_orders"], [first.pk])
        first.refresh_from_db()
        self.assertEqual(first.status, "READY")
        self.assertIsNone(first.departed_at)  # completion is not a serving departure
        self.assertEqual(self.read()["history"], before)
        self.assertEqual(list(first.events.values_list("actor__name", flat=True)),
                         ["takeout", "takeout", "takeout"])
        self.assertEqual(first.total_price, 0)

    def test_aggregate_includes_catalog_zeroes_inactive_pending_and_custom_lines(self):
        self.menu.is_active = False
        self.menu.save()
        order = self.order()
        OrderItem.objects.create(order=order, menu_item=self.menu, custom_name="추어탕",
                                 line_amount=100, qty=3, service_mode="TAKEOUT")
        for name in ("특별 국", "특별국"):
            OrderItem.objects.create(order=order, custom_name=name, line_amount=100,
                                     qty=1, service_mode="TAKEOUT")
        data = self.read()
        rows = {row["key"]: row for row in data["menus"]}
        self.assertEqual(rows[f"menu:{self.menu.pk}"]["remaining_qty"], 5)
        self.assertEqual(rows[f"menu:{self.other.pk}"]["remaining_qty"], 0)
        customs = [row for row in rows.values() if row["is_custom"]]
        self.assertEqual(len(customs), 1)
        self.assertEqual(customs[0]["remaining_qty"], 2)
        body = {"request_id": str(uuid.uuid4()), "expected_version": data["completion_version"],
                "items": [{"key": customs[0]["key"], "quantity": 2}]}
        self.assertEqual(self.send(body).status_code, 200)

    def test_mixed_takeout_included_but_hall_ready_cancelled_excluded_from_remaining(self):
        self.order(status="READY")
        self.order(status="CANCELLED")
        mixed = self.order()
        OrderItem.objects.create(order=mixed, menu_item=self.other, qty=9,
                                 unit_price=9000, service_mode="DINE_IN")
        self.order()
        data = self.read()
        self.assertEqual(data["remaining_total"], 4)
        self.assertEqual(data["history"]["total"], 4)
        row = next(o for o in data["history"]["orders"] if o["id"] == mixed.pk)
        self.assertEqual([i["menu_item_name"] for i in row["items"]], [self.menu.name])

    def test_same_request_replays_its_receipt_and_another_device_cannot_double_complete(self):
        order = self.order((self.menu, 5))
        body = self.body()
        first = self.send(body)
        self.assertEqual(first.status_code, 200)
        before = revisions.current()
        # The same attempt again (its answer was lost): the stored result, nothing applied.
        replay = self.send(body)
        self.assertEqual((replay.status_code, replay.json()), (200, first.json()))
        # Another device that read the same version is a different attempt: refused.
        self.assertEqual(self.send({**body, "request_id": str(uuid.uuid4())}).status_code, 409)
        self.assertEqual(order.items.get().prepared_qty, 1)
        self.assertEqual(revisions.current(), before)

    def test_a_request_id_cannot_be_reused_for_other_content_or_by_another_account(self):
        order = self.order((self.menu, 5))
        body = self.body()
        self.assertEqual(self.send(body).status_code, 200)
        changed = {**body, "items": [{"key": f"menu:{self.menu.pk}", "quantity": 2}]}
        self.assertEqual(self.send(changed).status_code, 409)
        other = Client()
        login_client(other, "BOTH_MONITORS")
        self.assertEqual(self.send(body, other).status_code, 409)
        self.assertEqual(order.items.get().prepared_qty, 1)

    def test_a_new_order_or_hall_progress_does_not_refuse_a_pending_batch(self):
        """User decision 2026-10-03: only takeout work marked done invalidates
        the completion version (PR review H2)."""
        # Production always has the counter row (0028); a flushed test database
        # does not, and its first mark() would start a new generation.
        with transaction.atomic():
            revisions.mark()
        first = self.order((self.menu, 2))
        order, hall, client = self.mixed()
        body = self.body((self.menu, 2))
        self.order((self.menu, 4))  # arrives while the operator is choosing
        self.assertEqual(self.hall_action(order, client, "progress", items=[{"id": hall.pk, "prepared_qty": 1}]).status_code, 200)
        self.assertEqual(self.send(body).status_code, 200)
        first.refresh_from_db()
        self.assertEqual((first.status, first.items.get().prepared_qty), ("READY", 2))  # oldest first

    def test_insufficient_or_unknown_menu_rejects_entire_batch(self):
        order = self.order((self.menu, 2), (self.other, 1))
        body = self.body((self.menu, 1), (self.other, 2))
        for key in (f"menu:{self.other.pk}", "menu:999999"):
            body["items"][1]["key"] = key
            self.assertEqual(self.send(body).status_code, 409)
        self.assertEqual(list(order.items.values_list("prepared_qty", flat=True)), [0, 0])
        self.assertEqual(order.events.count(), 0)

    def test_malformed_payloads_do_not_mutate(self):
        order = self.order()
        good = self.body()
        invalid = [[], {}, {**good, "extra": 1}, {**good, "items": []},
                   {**good, "items": good["items"] * 2},
                   {**good, "expected_version": 1}]
        for value in (-1, 0, True, 1.5, "1", None, 2**63):
            invalid.append({**good, "items": [{"key": f"menu:{self.menu.pk}", "quantity": value}]})
        for body in invalid:
            with self.subTest(body=body):
                self.assertEqual(self.send(body).status_code, 400)
        self.assertEqual(order.items.get().prepared_qty, 0)

    def test_failed_audit_rolls_back_all_items_status_and_revision(self):
        order = self.order((self.menu, 1), (self.other, 1))
        body = self.body((self.menu, 1), (self.other, 1))
        before = revisions.current()
        with patch.object(audit, "record_status", side_effect=RuntimeError("synthetic failure")):
            with self.assertRaises(RuntimeError):
                self.send(body)
        order.refresh_from_db()
        self.assertEqual(order.status, "PREPARING")
        self.assertEqual(list(order.items.values_list("prepared_qty", flat=True)), [0, 0])
        self.assertEqual(order.events.count(), 0)
        self.assertEqual(revisions.current(), before)

    def test_permissions_csrf_and_method_guards(self):
        self.order()
        body = self.body()
        self.assertEqual(self.send(body, Client()).status_code, 401)
        for role in ("HALL_MONITOR", "SERVING", "STATS"):
            client = Client()
            login_client(client, role)
            self.assertEqual(self.send(body, client).status_code, 403)
            self.assertEqual(client.get(reverse("orders:snapshot-takeout")).status_code, 403)
        client = Client(enforce_csrf_checks=True)
        login_client(client, "TAKEOUT_MONITOR")
        self.assertEqual(self.send(body, client).status_code, 403)
        client.defaults["HTTP_X_CSRFTOKEN"] = client.cookies["csrftoken"].value
        self.assertEqual(self.send(body, client).status_code, 200)
        self.assertEqual(self.client.get(reverse("orders:takeout-complete")).status_code, 405)

    def test_history_all_statuses_pages_no_status_or_prepared_fields(self):
        for i in range(51):
            self.order(status=("READY" if i % 2 else "CANCELLED"))
        data = self.read()
        self.assertEqual(data["history"]["total"], 51)
        self.assertEqual(len(data["history"]["orders"]), 50)
        self.assertEqual(len(self.read(page=2)["history"]["orders"]), 1)
        for order in data["history"]["orders"]:
            self.assertNotIn("status", order)
            self.assertNotIn("departed_at", order)
            self.assertNotIn("prepared_qty", order["items"][0])
        unchanged = self.read(since=data["version"])
        self.assertTrue(unchanged["unchanged"])
        self.assertEqual(unchanged["menus"], [])
        self.assertEqual(unchanged["history"]["orders"], [])
        self.assertEqual(self.read(page=2, since=data["version"])["cursor"], "rejected")
        self.assertTrue(self.read(page=999)["history"]["has_previous"])

    def test_more_than_500_waiting_is_not_truncated(self):
        orders = Order.objects.bulk_create([Order(order_type="TAKEOUT") for _ in range(501)])
        OrderItem.objects.bulk_create([OrderItem(order=o, menu_item=self.menu, qty=2,
                                                unit_price=8000, service_mode="TAKEOUT") for o in orders])
        data = self.read()
        self.assertEqual(data["remaining_total"], 1002)
        self.assertTrue(data["complete"])
        self.assertFalse(data["has_more"])

    def test_read_refuses_nested_transaction_and_bad_pages(self):
        with transaction.atomic(), self.assertRaises(RuntimeError):
            self.read()
        for value in ("0", "-1", "1.5", "9" * 5000, "1000001"):
            self.assertEqual(self.client.get(reverse("orders:snapshot-takeout"), {"page": value}).status_code, 400)

    def race(self, bodies):
        barrier = threading.Barrier(len(bodies))
        results, errors = [], []
        def worker(body):
            try:
                client = Client()
                client.cookies = self.client.cookies.copy()
                client.defaults = self.client.defaults.copy()
                barrier.wait(timeout=5)
                results.append(self.send(body, client).status_code)
            except Exception as exc:
                errors.append(exc)
            finally:
                connection.close()
        threads = [threading.Thread(target=worker, args=(body,)) for body in bodies]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        return sorted(results)

    def test_two_concurrent_batches_have_one_winner(self):
        order = self.order((self.menu, 5))
        body = self.body()
        self.assertEqual(self.race([body, {**body, "request_id": str(uuid.uuid4())}]), [200, 409])
        self.assertEqual(order.items.get().prepared_qty, 1)

    def test_the_same_request_racing_itself_applies_once_and_answers_both(self):
        order = self.order((self.menu, 5))
        body = self.body()
        self.assertEqual(self.race([body, body]), [200, 200])
        self.assertEqual(order.items.get().prepared_qty, 1)
        self.assertEqual(order.events.filter(kind="PROGRESS").count(), 1)

    def mixed(self):
        order = self.order((self.menu, 2))
        hall = OrderItem.objects.create(order=order, menu_item=self.other, qty=3,
                                       unit_price=9000, service_mode="DINE_IN")
        client = Client()
        login_client(client, "HALL_MONITOR")
        return order, hall, client

    def hall_action(self, order, client, action="depart", **kwargs):
        order.refresh_from_db()
        return client.patch(reverse("orders:monitor-order-action", args=[order.pk]),
                            {"action": action, "expected_version": monitoring_actions.monitor_version(order), **kwargs},
                            content_type="application/json")

    def test_mixed_hall_then_takeout_only_completes_after_both(self):
        order, hall, client = self.mixed()
        self.assertEqual(self.hall_action(order, client).status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "PREPARING")
        self.assertIsNotNone(order.departed_at)
        self.assertEqual(order.items.get(service_mode="TAKEOUT").prepared_qty, 0)
        hall_view = monitoring_snapshot.read(("HALL_MONITOR",), mode="HALL")
        self.assertEqual(hall_view["orders"], [])
        self.assertEqual([i["id"] for i in hall_view["history"]["orders"][0]["items"]], [hall.pk])
        self.assertTrue(order.events.filter(kind="DEPARTED", actor__name="hall").exists())
        self.assertEqual(self.send(self.body((self.menu, 2))).status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "READY")

    def test_mixed_takeout_then_hall_and_preparation_is_not_departure(self):
        order, hall, client = self.mixed()
        self.assertEqual(self.send(self.body((self.menu, 2))).status_code, 200)
        self.assertEqual(self.hall_action(order, client, "progress", items=[{"id": hall.pk, "prepared_qty": 3}]).status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "PREPARING")
        self.assertIsNone(order.departed_at)
        self.assertEqual(self.hall_action(order, client).status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "READY")

    def test_hall_cannot_edit_takeout_via_either_progress_endpoint_or_force_ready(self):
        order, hall, client = self.mixed()
        takeout = order.items.get(service_mode="TAKEOUT")
        self.assertEqual(client.patch(reverse("orders:order-item-progress", args=[takeout.pk]),
                                     {"prepared_qty": 2}, content_type="application/json").status_code, 403)
        self.assertEqual(self.hall_action(order, client, "progress", items=[
            {"id": hall.pk, "prepared_qty": 3}, {"id": takeout.pk, "prepared_qty": 2}]).status_code, 400)
        self.assertEqual(client.patch(reverse("orders:order-status", args=[order.pk]),
                                     {"status": "READY"}, content_type="application/json").status_code, 409)

    def test_takeout_reduction_preserves_hall_departure_and_completion_recovers(self):
        order, hall, client = self.mixed()
        self.hall_action(order, client)
        self.send(self.body((self.menu, 2)))
        takeout = order.items.get(service_mode="TAKEOUT")
        self.assertEqual(self.client.patch(reverse("orders:order-item-progress", args=[takeout.pk]),
                                         {"prepared_qty": 1}, content_type="application/json").status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "PREPARING")
        self.assertIsNotNone(order.departed_at)
        self.assertEqual(self.send(self.body()).status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "READY")

    def test_sse_detects_empty_catalog_changes_mixed_lines_and_old_history_edits(self):
        before = hub._scope_view((TAKEOUT_MONITOR,))[0]
        with transaction.atomic():
            revisions.save_and_mark(self.menu, name="새 추어탕")
        self.assertNotEqual(hub._scope_view((TAKEOUT_MONITOR,))[0], before)
        order, hall, client = self.mixed()
        before = hub._scope_view((TAKEOUT_MONITOR,))[0]
        self.send(self.body())
        self.assertNotEqual(hub._scope_view((TAKEOUT_MONITOR,))[0], before)
        order.status = "CANCELLED"
        order.save()
        for _ in range(51):
            self.order(status="READY")
        before = hub._scope_view((TAKEOUT_MONITOR,))[0]
        item = order.items.get(service_mode="TAKEOUT")
        item.qty += 1
        item.save()
        self.assertNotEqual(hub._scope_view((TAKEOUT_MONITOR,))[0], before)

    # ---- PR review H1: every writer reconciles the status (D-075) -------------

    def test_pure_takeout_finished_outside_the_batch_becomes_ready(self):
        order = self.order((self.menu, 2))
        item = order.items.get()
        self.assertEqual(self.client.patch(reverse("orders:order-item-progress", args=[item.pk]),
                                         {"prepared_qty": 2}, content_type="application/json").status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "READY")
        self.assertIsNone(order.departed_at)
        self.assertTrue(order.events.filter(kind="STATUS", to_status="READY").exists())

    def test_departed_mixed_order_finished_outside_the_batch_becomes_ready(self):
        order, hall, client = self.mixed()
        self.assertEqual(self.hall_action(order, client).status_code, 200)
        takeout = order.items.get(service_mode="TAKEOUT")
        self.assertEqual(self.client.patch(reverse("orders:order-item-progress", args=[takeout.pk]),
                                         {"prepared_qty": 2}, content_type="application/json").status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "READY")
        self.assertIsNotNone(order.departed_at)

    def test_reconciliation_rules_for_each_shape(self):
        pure_hall = self.order((self.menu, 1))
        pure_hall.items.update(service_mode="DINE_IN", prepared_qty=1)
        status_service.sync_from_items(pure_hall)
        pure_hall.refresh_from_db()
        self.assertEqual(pure_hall.status, "PREPARING")  # hall departure stays explicit
        ready = self.order((self.menu, 1), status="READY")
        ready.items.update(prepared_qty=1)
        OrderItem.objects.create(order=ready, menu_item=self.other, qty=1, prepared_qty=1,
                                 unit_price=9000, service_mode="DINE_IN")
        status_service.sync_from_items(ready)  # became mixed without a hall departure
        ready.refresh_from_db()
        self.assertEqual(ready.status, "PREPARING")
        cancelled = self.order((self.menu, 1), status="CANCELLED")
        cancelled.items.update(prepared_qty=1)
        status_service.sync_from_items(cancelled)
        cancelled.refresh_from_db()
        self.assertEqual(cancelled.status, "CANCELLED")

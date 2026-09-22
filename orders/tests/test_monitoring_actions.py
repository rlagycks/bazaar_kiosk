"""UI-05B: atomic monitoring writes, departure proof, and optimistic conflicts."""
import threading
from unittest.mock import patch

from django.db import IntegrityError, connection, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from orders.models import Order, OrderItem
from orders.services import monitoring_actions, revisions, scope
from orders.tests.auth_support import AUTH_SETTINGS, login_client
from orders.tests.test_status import StatusFixture
from orders.views import serializers


class MonitoringFixture(StatusFixture):
    def setUp(self):
        super().setUp()
        self.order, self.item = self.make_order()
        self.second = OrderItem.objects.create(
            order=self.order, menu_item=self.menu, qty=3, unit_price=8000,
        )

    def token(self):
        return monitoring_actions.monitor_version(Order.objects.get(pk=self.order.pk))

    def payload(self, action="progress", **overrides):
        body = {"action": action, "expected_version": self.token()}
        if action == "progress":
            body["items"] = [{"id": self.item.pk, "prepared_qty": 2},
                             {"id": self.second.pk, "prepared_qty": 3}]
        return {**body, **overrides}

    def send(self, body=..., *, client=None):
        return (client or self.client_kitchen).patch(
            reverse("orders:monitor-order-action", args=[self.order.pk]),
            self.payload() if body is ... else body, content_type="application/json",
        )

    def state(self):
        self.order.refresh_from_db()
        return (self.order.status, self.order.departed_at,
                list(self.order.items.values_list("prepared_qty", flat=True)),
                self.order.events.count(), revisions.current())


@override_settings(**AUTH_SETTINGS)
class MonitoringActionTests(MonitoringFixture, TestCase):
    def test_progress_all_prepared_stays_preparing_without_departure(self):
        response = self.send()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {"id": self.order.pk, "status": "PREPARING"})
        self.assertEqual(self.state()[:3], ("PREPARING", None, [2, 3]))
        self.assertEqual(list(self.order.events.values_list("kind", "actor__name")),
                         [("PROGRESS", "kitchen"), ("PROGRESS", "kitchen")])

    def test_depart_bulk_completes_and_audits_once_in_one_transaction(self):
        with patch.object(revisions, "mark", wraps=revisions.mark) as marked:
            before = timezone.now()
            response = self.send(self.payload("depart"))
            self.assertEqual(response.status_code, 200, response.content)
            marked.assert_called_once_with()
        status, departed, quantities, _, _ = self.state()
        self.assertEqual((status, quantities), ("READY", [2, 3]))
        self.assertGreaterEqual(departed, before)
        self.assertEqual(list(self.order.events.order_by("id").values_list("kind", "actor__name")),
                         [("PROGRESS", "kitchen"), ("PROGRESS", "kitchen"), ("STATUS", "kitchen")])

    def test_reopen_keeps_quantities_and_clears_departure(self):
        self.send(self.payload("depart"))
        self.assertEqual(self.send(self.payload("reopen")).status_code, 200)
        self.assertEqual(self.state()[:3], ("PREPARING", None, [2, 3]))

    def test_reducing_ready_quantity_reopens_and_clears_departure(self):
        self.send(self.payload("depart"))
        body = self.payload()
        body["items"][1]["prepared_qty"] = 2
        self.assertEqual(self.send(body).status_code, 200)
        self.assertEqual(self.state()[:3], ("PREPARING", None, [2, 2]))

    def test_no_op_has_no_events_marker_or_version_changes(self):
        self.send()
        before, token = self.state(), self.token()
        with patch.object(revisions, "mark", wraps=revisions.mark) as marked:
            self.assertEqual(self.send().status_code, 200)
            marked.assert_not_called()
        self.assertEqual(self.state(), before)
        self.assertEqual(self.token(), token)

    def test_progress_round_trip_rejects_the_original_version(self):
        original = self.payload(items=[{"id": self.item.pk, "prepared_qty": 1},
                                       {"id": self.second.pk, "prepared_qty": 0}])
        timestamps = [Order.objects.get(pk=self.order.pk).updated_at]
        for quantity in (1, 0):
            body = self.payload(items=[{"id": self.item.pk, "prepared_qty": quantity},
                                       {"id": self.second.pk, "prepared_qty": 0}])
            self.assertEqual(self.send(body).status_code, 200)
            self.order.refresh_from_db()
            timestamps.append(self.order.updated_at)
        self.assertEqual(self.state()[:3], ("PREPARING", None, [0, 0]))
        before = self.state()
        self.assertEqual(self.send(original).status_code, 409)
        self.assertEqual(self.state(), before)
        self.assertNotEqual(self.token(), original["expected_version"])
        self.assertLess(timestamps[0], timestamps[1])
        self.assertLess(timestamps[1], timestamps[2])

    def test_legacy_progress_round_trip_rejects_the_original_monitor_version(self):
        original = self.payload("depart")
        timestamps = [Order.objects.get(pk=self.order.pk).updated_at]
        for quantity in (1, 0):
            self.assertEqual(self.progress(self.item, {"prepared_qty": quantity}).status_code, 200)
            self.order.refresh_from_db()
            timestamps.append(self.order.updated_at)
        self.assertEqual(self.state()[:3], ("PREPARING", None, [0, 0]))
        before = self.state()
        self.assertEqual(self.send(original).status_code, 409)
        self.assertEqual(self.state(), before)
        self.assertLess(timestamps[0], timestamps[1])
        self.assertLess(timestamps[1], timestamps[2])

    def test_legacy_quantity_noop_keeps_monitor_version_and_audit_unchanged(self):
        before, token = self.state(), self.token()
        self.assertEqual(self.progress(self.item, {"prepared_qty": 0}).status_code, 200)
        self.assertEqual(self.state(), before)
        self.assertEqual(self.token(), token)

    def test_progress_failure_rolls_back_quantities_and_order_version_for_both_apis(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                before, token = self.state(), self.token()
                with patch.object(revisions, "mark", side_effect=RuntimeError("injected")):
                    with self.assertRaisesRegex(RuntimeError, "injected"):
                        if legacy:
                            self.progress(self.item, {"prepared_qty": 1})
                        else:
                            self.send()
                self.assertEqual(self.state(), before)
                self.assertEqual(self.token(), token)

    def test_retry_stale_depart_or_cancel_conflicts_but_fresh_retry_is_noop(self):
        for action in ("depart", "cancel"):
            body = self.payload(action)
            self.assertEqual(self.send(body).status_code, 200)
            before = self.state()
            self.assertEqual(self.send(body).status_code, 409)
            self.assertEqual(self.send(self.payload(action)).status_code, 200)
            self.assertEqual(self.state(), before)

    def test_cancel_is_final(self):
        self.send(self.payload("cancel"))
        before = self.state()
        for action in ("progress", "depart", "reopen"):
            self.assertEqual(self.send(self.payload(action)).status_code, 409)
            self.assertEqual(self.state(), before)

    def test_old_ready_has_no_departure_proof_and_cannot_be_retroactively_stamped(self):
        Order.objects.filter(pk=self.order.pk).update(status="READY")
        data = serializers.order(Order.objects.get(pk=self.order.pk))
        self.assertIsNone(data["departed_at"])
        self.assertEqual(data["monitor_version"], self.token())
        self.assertEqual(self.send(self.payload("depart")).status_code, 409)
        self.assertIsNone(self.state()[1])

    def test_strict_validation_never_partially_saves(self):
        valid = self.payload()
        bad_bodies = [[], None, {}, {**valid, "action": True}, {**valid, "action": "oops"},
                      {**valid, "expected_version": False}, {**valid, "expected_version": ""},
                      {**valid, "unexpected": 1}, {**valid, "items": []},
                      {**valid, "items": valid["items"][:1]},
                      {**valid, "items": [valid["items"][0]] * 2}]
        foreign, foreign_item = self.make_order()
        for field, values in (("id", [True, 1.0, "1", None, foreign_item.pk]),
                              ("prepared_qty", [True, 1.0, "1", None, -1, 4])):
            for value in values:
                rows = [dict(row) for row in valid["items"]]
                rows[1][field] = value
                bad_bodies.append({**valid, "items": rows})
        bad_bodies.extend([{**valid, "items": [valid["items"][0], {}]},
                           {**valid, "items": [valid["items"][0], {**valid["items"][1], "qty": 9}]}])
        before = self.state()
        for body in bad_bodies:
            with self.subTest(body=body):
                response = self.send(body)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertEqual(self.state(), before)

    def test_stale_item_or_order_edit_conflicts_before_any_write(self):
        for field, value in (("prepared_qty", 1), ("qty", 4), ("unit_price", 7000),
                             ("service_mode", "TAKEOUT")):
            body = self.payload("depart")
            OrderItem.objects.filter(pk=self.item.pk).update(**{field: value})
            before = self.state()
            self.assertEqual(self.send(body).status_code, 409)
            self.assertEqual(self.state(), before)
        body = self.payload("depart")
        Order.objects.filter(pk=self.order.pk).update(note="edited")
        self.assertEqual(self.send(body).status_code, 409)

    def test_hash_is_stable_sorted_and_uses_source_fields_only(self):
        order = Order.objects.prefetch_related("items").get(pk=self.order.pk)
        token = monitoring_actions.monitor_version(order)
        order._prefetched_objects_cache["items"] = list(reversed(list(order.items.all())))
        self.assertEqual(monitoring_actions.monitor_version(order), token)
        self.menu.name = "A renamed menu"
        self.menu.save()
        self.assertEqual(self.token(), token)

    def test_failure_after_item_audit_rolls_back_everything(self):
        before = self.state()
        with patch("orders.services.monitoring_actions.audit.record_status", side_effect=RuntimeError("injected")):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                self.send(self.payload("depart"))
        self.assertEqual(self.state(), before)

    def test_failure_after_revision_mark_rolls_back_everything(self):
        before = self.state()
        original = revisions.mark
        def fail_after_mark():
            original()
            raise RuntimeError("injected")
        with patch.object(revisions, "mark", side_effect=fail_after_mark):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                self.send(self.payload("depart"))
        self.assertEqual(self.state(), before)

    def test_auth_permissions_and_order_scope(self):
        before = self.state()
        anonymous = Client()
        self.assertEqual(self.send(client=anonymous).status_code, 401)
        for alias in ("SERVING", "STATS", "TAKEOUT_MONITOR"):
            client = Client()
            login_client(client, alias)
            self.assertEqual(self.send(client=client).status_code, 403)
        self.assertEqual(self.state(), before)
        hall = Client()
        login_client(hall, "HALL_MONITOR")
        with patch.object(scope, "may_change", wraps=scope.may_change) as check:
            self.assertEqual(self.send(client=hall).status_code, 200)
            self.assertEqual(check.call_args.args[0].pk, self.order.pk)

    def test_departure_keeps_takeout_slot_constraint(self):
        Order.objects.filter(pk=self.order.pk).update(order_type="TAKEOUT", is_takeout=True)
        self.order.items.update(service_mode="TAKEOUT")
        self.assertEqual(self.send(self.payload("depart")).status_code, 200)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Order.objects.create(table=self.table, floor="B1", order_type="TAKEOUT")

    def test_shape_validation_rejects_nonprogress_item_edits_and_missing_version(self):
        before = self.state()
        for action in ("depart", "reopen", "cancel"):
            self.assertEqual(self.send(self.payload(action, items=[{"id": self.item.pk, "prepared_qty": 1}])).status_code, 400)
            self.assertEqual(self.send({"action": action}).status_code, 400)
        self.assertEqual(self.state(), before)

    def test_scope_check_follows_order_lock(self):
        calls = []
        original_lock, original_scope = monitoring_actions.status_service.locked, scope.may_change
        def locked(order_id):
            order = original_lock(order_id)
            calls.append("locked")
            return order
        def permitted(order, permissions):
            calls.append("scope")
            return original_scope(order, permissions)
        with patch.object(monitoring_actions.status_service, "locked", side_effect=locked), patch.object(scope, "may_change", side_effect=permitted):
            self.assertEqual(self.send().status_code, 200)
        self.assertEqual(calls, ["locked", "scope"])

    def test_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        login_client(client, "KITCHEN")
        before = self.state()
        self.assertEqual(self.send(client=client).status_code, 403)
        self.assertEqual(self.state(), before)
        client.defaults["HTTP_X_CSRFTOKEN"] = client.cookies["csrftoken"].value
        self.assertEqual(self.send(client=client).status_code, 200)


@override_settings(**AUTH_SETTINGS)
class ConcurrentMonitoringTests(MonitoringFixture, TransactionTestCase):
    def race(self, actions):
        barrier = threading.Barrier(len(actions))
        results, errors = [], []
        token = self.token()
        def worker(action):
            try:
                client = Client()
                client.cookies = self.client_kitchen.cookies.copy()
                client.defaults = self.client_kitchen.defaults.copy()
                body = {"action": action, "expected_version": token}
                if action == "progress":
                    body["items"] = [{"id": self.item.pk, "prepared_qty": 1},
                                     {"id": self.second.pk, "prepared_qty": 0}]
                barrier.wait(timeout=5)
                response = self.send(body, client=client)
                results.append((action, response.status_code))
            except Exception as exc:
                errors.append(exc)
            finally:
                connection.close()
        threads = [threading.Thread(target=worker, args=(action,)) for action in actions]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(sorted(code for _, code in results), [200, 409])
        return dict(results)

    def test_two_departures_have_one_winner_and_one_status_event(self):
        self.race(["depart", "depart"])
        self.assertEqual(self.state()[0], "READY")
        self.assertEqual(self.order.events.filter(kind="STATUS").count(), 1)

    def test_two_progress_saves_have_one_winner_and_one_progress_event(self):
        self.race(["progress", "progress"])
        self.assertEqual(self.state()[:3], ("PREPARING", None, [1, 0]))
        self.assertEqual(self.order.events.filter(kind="PROGRESS").count(), 1)

    def test_cancel_racing_depart_has_one_winner_and_never_revives_cancel(self):
        outcomes = self.race(["depart", "cancel"])
        self.assertEqual(self.state()[0], "CANCELLED" if outcomes["cancel"] == 200 else "READY")
        self.assertEqual(self.send(self.payload("cancel")).status_code, 200)
        self.assertEqual(self.send(self.payload("depart")).status_code, 409)
        self.assertEqual(self.state()[0], "CANCELLED")

    def test_depart_waits_for_item_edit_then_rejects_stale_version(self):
        token = self.token()
        entered = threading.Event()
        outcomes, errors = [], []
        original = monitoring_actions.status_service.locked
        def locked(order_id):
            entered.set()
            return original(order_id)
        def depart():
            try:
                client = Client()
                client.cookies = self.client_kitchen.cookies.copy()
                client.defaults = self.client_kitchen.defaults.copy()
                outcomes.append(self.send({"action": "depart", "expected_version": token}, client=client).status_code)
            except Exception as exc:
                errors.append(exc)
            finally:
                connection.close()
        with patch.object(monitoring_actions.status_service, "locked", side_effect=locked):
            with transaction.atomic():
                Order.objects.select_for_update().get(pk=self.order.pk)
                thread = threading.Thread(target=depart)
                thread.start()
                self.assertTrue(entered.wait(timeout=5))
                OrderItem.objects.filter(pk=self.item.pk).update(qty=4)
            thread.join(timeout=15)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(outcomes, [409])
        self.assertEqual(self.state()[:4], ("PREPARING", None, [0, 0], 0))

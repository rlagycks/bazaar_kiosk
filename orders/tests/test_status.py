"""6B: what an order's status may become, and who decides it (D-050).

Two writers used to disagree. `order_status` saved whatever it was sent, so a
cancelled order came back to life with a single PATCH; `order_item_progress`
refused to touch a cancelled order at all. Neither locked the order, so a
cancel and a progress update racing each other could end either way.

The contract these tests pin:

* cancelling is final -- nothing brings an order back (D-050, user decision);
* READY may go back to PREPARING, because the kitchen mistypes and the money
  does not move;
* the same status again is a no-op, not an error, so a retry is safe;
* a refused transition is 409: it is a conflict with the order's state, not a
  malformed request;
* when item quantities change, the status they imply wins.
"""

import threading
import uuid

from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from orders.models import MenuItem, Order, OrderItem, OrderStatus, Table
from orders.tests.auth_support import ROLE_ACCOUNTS, login_client

PREPARING, READY, CANCELLED = (
    OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.CANCELLED
)


class StatusFixture:
    def setUp(self):
        super().setUp()
        self.table = Table.objects.create(number=11)
        self.menu = MenuItem.objects.create(name="Bowl", price=8000)
        self.client_kitchen = self.client_class()
        login_client(self.client_kitchen, "KITCHEN")

    def make_order(self, *, status=PREPARING, qty=2, prepared=0):
        order = Order.objects.create(
            table=self.table, floor="B1", order_type="DINE_IN", status=status,
            total_price=8000 * qty, payment_method="CASH",
            received_cash_amount=8000 * qty,
        )
        item = OrderItem.objects.create(
            order=order, menu_item=self.menu, qty=qty, unit_price=8000,
            prepared_qty=prepared,
        )
        return order, item

    def set_status(self, order, status):
        return self.client_kitchen.patch(
            reverse("orders:order-status", args=[order.id]),
            {"status": status}, content_type="application/json",
        )

    def progress(self, item, payload):
        return self.client_kitchen.patch(
            reverse("orders:order-item-progress", args=[item.id]),
            payload, content_type="application/json",
        )


@override_settings(ROLE_ACCOUNTS=ROLE_ACCOUNTS, JWT_COOKIE_SECURE=False)
class TransitionTableTests(StatusFixture, TestCase):
    def assert_status(self, order, expected):
        order.refresh_from_db()
        self.assertEqual(order.status, expected)

    def test_every_allowed_transition_is_accepted(self):
        for start, target in (
            (PREPARING, READY),
            (PREPARING, CANCELLED),
            (READY, PREPARING),
            (READY, CANCELLED),
        ):
            with self.subTest(start=start, target=target):
                order, _ = self.make_order(status=start)
                response = self.set_status(order, target)
                self.assertEqual(response.status_code, 200, response.content)
                self.assert_status(order, target)

    def test_a_cancelled_order_never_comes_back(self):
        """The user's decision: cancelling is final. Reviving one would move
        money back into the sales figures it was taken out of (D-048)."""
        for target in (PREPARING, READY):
            with self.subTest(target=target):
                order, _ = self.make_order(status=CANCELLED)
                response = self.set_status(order, target)
                self.assertEqual(response.status_code, 409, response.content)
                self.assert_status(order, CANCELLED)

    def test_the_same_status_again_is_accepted_and_changes_nothing(self):
        """A retried PATCH must not fail: the screen would report an error for
        a request that asked for the state the order is already in."""
        for status in (PREPARING, READY, CANCELLED):
            with self.subTest(status=status):
                order, _ = self.make_order(status=status)
                before = Order.objects.get(pk=order.pk).updated_at
                response = self.set_status(order, status)
                self.assertEqual(response.status_code, 200, response.content)
                self.assert_status(order, status)
                self.assertEqual(Order.objects.get(pk=order.pk).updated_at, before)

    def test_a_refused_transition_says_what_the_order_is(self):
        order, _ = self.make_order(status=CANCELLED)
        body = self.set_status(order, PREPARING).json()
        self.assertEqual(body["status"], CANCELLED)
        self.assertIn("취소", body["detail"])

    def test_an_unknown_status_is_still_a_bad_request(self):
        """A value that is not a status at all is malformed input (400), not a
        conflict with the order's state (409)."""
        order, _ = self.make_order()
        for bad in ("DONE", "", "preparing ", None, 3):
            with self.subTest(status=bad):
                response = self.set_status(order, bad)
                self.assertEqual(response.status_code, 400, response.content)


@override_settings(ROLE_ACCOUNTS=ROLE_ACCOUNTS, JWT_COOKIE_SECURE=False)
class CancelledOrdersAreClosedTests(StatusFixture, TestCase):
    def test_cooking_progress_on_a_cancelled_order_is_refused(self):
        order, item = self.make_order(status=CANCELLED)
        response = self.progress(item, {"done": True})
        self.assertEqual(response.status_code, 409, response.content)
        item.refresh_from_db()
        self.assertEqual(item.prepared_qty, 0)

    def test_finishing_every_item_cannot_resurrect_a_cancelled_order(self):
        """The item writer used to have its own rule. Now both writers answer
        to the same table, so neither can undo a cancellation."""
        order, item = self.make_order(status=PREPARING, qty=1)
        self.assertEqual(self.set_status(order, CANCELLED).status_code, 200)
        self.assertEqual(self.progress(item, {"done": True}).status_code, 409)
        order.refresh_from_db()
        self.assertEqual(order.status, CANCELLED)


@override_settings(ROLE_ACCOUNTS=ROLE_ACCOUNTS, JWT_COOKIE_SECURE=False)
class ItemProgressDrivesStatusTests(StatusFixture, TestCase):
    def test_finishing_every_item_makes_the_order_ready(self):
        order, item = self.make_order(qty=2)
        self.assertEqual(self.progress(item, {"done": True}).status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, READY)

    def test_undoing_an_item_puts_the_order_back_to_preparing(self):
        """The user allowed READY -> PREPARING, and this is the same move made
        through the quantities rather than the status button."""
        order, item = self.make_order(qty=2)
        self.progress(item, {"done": True})
        self.assertEqual(self.progress(item, {"prepared_qty": 1}).status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, PREPARING)

    def test_a_manual_ready_is_recomputed_when_quantities_change(self):
        """Two writers, one answer: whatever the quantities say after a change
        is what the order is. Otherwise a manual READY would survive an item
        being taken back, which is the disagreement BK-R013 is about."""
        order, item = self.make_order(qty=2)
        self.assertEqual(self.set_status(order, READY).status_code, 200)
        self.assertEqual(self.progress(item, {"prepared_qty": 1}).status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, PREPARING)


@override_settings(ROLE_ACCOUNTS=ROLE_ACCOUNTS, JWT_COOKIE_SECURE=False)
class ConcurrentStatusTests(StatusFixture, TransactionTestCase):
    """Neither writer locked the order, so a cancel could be overwritten."""

    def test_a_cancel_racing_a_progress_update_stays_cancelled(self):
        order, item = self.make_order(qty=2)
        start = threading.Barrier(2)
        outcomes = {}
        errors = []

        def cancel():
            try:
                start.wait(timeout=5)
                outcomes["cancel"] = self.set_status(order, CANCELLED).status_code
            except Exception as exc:
                errors.append(exc)
            finally:
                connection.close()

        def finish():
            try:
                client = self.client_class()
                login_client(client, "KITCHEN")
                start.wait(timeout=5)
                outcomes["progress"] = client.patch(
                    reverse("orders:order-item-progress", args=[item.id]),
                    {"done": True}, content_type="application/json",
                ).status_code
            except Exception as exc:
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=cancel), threading.Thread(target=finish)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        self.assertEqual(errors, [])
        order.refresh_from_db()
        # Either order of arrival is fine; a cancelled order staying cancelled
        # is not. If the progress update won the race it ran first and was
        # allowed; the cancel then still applies.
        self.assertEqual(order.status, CANCELLED, outcomes)

    def test_two_cancels_at_once_do_not_error(self):
        order, _ = self.make_order()
        start = threading.Barrier(2)
        codes = []
        errors = []

        def cancel():
            try:
                client = self.client_class()
                login_client(client, "KITCHEN")
                start.wait(timeout=5)
                codes.append(client.patch(
                    reverse("orders:order-status", args=[order.id]),
                    {"status": CANCELLED}, content_type="application/json",
                ).status_code)
            except Exception as exc:
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=cancel) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        self.assertEqual(errors, [])
        self.assertEqual(codes, [200, 200], "a repeated cancel must not fail")
        order.refresh_from_db()
        self.assertEqual(order.status, CANCELLED)

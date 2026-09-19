"""6B: a takeout number identifies one waiting customer (D-050).

Takeout orders are called by a numbered tag, 101 to 120. Nothing stopped two
live orders from holding the same tag, so two customers could stand there with
number 105 and the kitchen had no way to tell whose food was whose.

The contract: a tag held by an order that has not been handed over cannot be
given out again. A cancelled order releases its tag; a READY one does not,
because READY means cooked and waiting, not collected.
"""

import threading
import uuid

from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from orders.models import MenuItem, Order, OrderStatus, Table
from orders.tests.auth_support import AUTH_SETTINGS, login_client
from orders.views import api


class TakeoutFixture:
    def setUp(self):
        super().setUp()
        api._get_table_by_number.cache_clear()
        self.addCleanup(api._get_table_by_number.cache_clear)
        for number in (7, 105, 106):
            Table.objects.create(number=number)
        self.menu = MenuItem.objects.create(name="Bowl", price=8000)
        login_client(self.client, "ORDER")

    def order_takeout(self, slot="105", client=None, request_id=None):
        return (client or self.client).post(
            reverse("orders:orders-collection"),
            {
                "request_id": request_id or str(uuid.uuid4()),
                "floor": "B1", "order_type": "TAKEOUT", "table_number": str(slot),
                "payment_method": "CASH", "received_cash_amount": 8000,
                "items": [{"menu_item_id": self.menu.id, "qty": 1}],
            },
            content_type="application/json",
        )

    def order_dine_in(self, table="7"):
        return self.client.post(
            reverse("orders:orders-collection"),
            {
                "request_id": str(uuid.uuid4()),
                "floor": "B1", "order_type": "DINE_IN", "table_number": str(table),
                "payment_method": "CASH", "received_cash_amount": 8000,
                "items": [{"menu_item_id": self.menu.id, "qty": 1}],
            },
            content_type="application/json",
        )


@override_settings(**AUTH_SETTINGS)
class TakeoutSlotTests(TakeoutFixture, TestCase):
    def test_a_free_slot_is_accepted(self):
        self.assertEqual(self.order_takeout().status_code, 201)

    def test_a_slot_in_use_is_refused(self):
        self.assertEqual(self.order_takeout().status_code, 201)
        second = self.order_takeout()
        self.assertEqual(second.status_code, 409, second.content)
        self.assertEqual(Order.objects.count(), 1)
        self.assertIn("105", second.json()["detail"])

    def test_a_cooked_but_uncollected_order_still_holds_its_slot(self):
        """READY means waiting on the counter with that tag on it."""
        created = self.order_takeout().json()
        Order.objects.filter(pk=created["id"]).update(status=OrderStatus.READY)
        self.assertEqual(self.order_takeout().status_code, 409)

    def test_a_cancelled_order_releases_its_slot(self):
        created = self.order_takeout().json()
        Order.objects.filter(pk=created["id"]).update(status=OrderStatus.CANCELLED)
        self.assertEqual(self.order_takeout().status_code, 201)
        self.assertEqual(Order.objects.count(), 2)

    def test_another_slot_is_unaffected(self):
        self.assertEqual(self.order_takeout("105").status_code, 201)
        self.assertEqual(self.order_takeout("106").status_code, 201)

    def test_a_dining_table_may_hold_several_orders(self):
        """Unchanged on purpose: one table ordering twice in an evening is
        ordinary, and the table number is not a claim ticket."""
        self.assertEqual(self.order_dine_in().status_code, 201)
        self.assertEqual(self.order_dine_in().status_code, 201)
        self.assertEqual(Order.objects.count(), 2)

    def test_the_slot_range_is_still_enforced(self):
        for slot in ("100", "121", "7"):
            with self.subTest(slot=slot):
                self.assertEqual(self.order_takeout(slot).status_code, 400)


@override_settings(**AUTH_SETTINGS)
class ConcurrentSlotTests(TakeoutFixture, TransactionTestCase):
    """Checking before inserting is not enough: both requests would look and
    both would find the slot free. The database has to hold the line."""

    def test_two_orders_for_one_slot_leave_exactly_one(self):
        clients = []
        for _ in range(2):
            client = self.client_class()
            login_client(client, "ORDER")
            clients.append(client)

        start = threading.Barrier(2)
        codes = []
        errors = []

        def submit(client):
            try:
                start.wait(timeout=5)
                codes.append(self.order_takeout(client=client).status_code)
            except Exception as exc:
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=submit, args=(c,)) for c in clients]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        self.assertEqual(errors, [])
        self.assertEqual(sorted(codes), [201, 409])
        self.assertEqual(Order.objects.count(), 1)
        # The refused request left nothing behind -- no order, and no number.
        self.assertEqual(list(Order.objects.values_list("order_no", flat=True)), [1])

    def test_a_retry_of_the_same_attempt_racing_itself_gets_its_own_order_back(self):
        """The same request_id twice at once is a retry, not a second customer.

        Both arrivals pass the replay check (nothing is committed yet) and both
        reach the insert. The loser's insert fails on the slot index because the
        winner -- its own earlier self -- now holds the tag. Answering that with
        "use another number" would send the volunteer off to create a second
        order for the same customer (2026-09-20 code review). The loser has to
        look the id up again and hand back the winner's order.
        """
        clients = []
        for _ in range(2):
            client = self.client_class()
            login_client(client, "ORDER")
            clients.append(client)
        attempt = str(uuid.uuid4())

        start = threading.Barrier(2)
        results = []
        errors = []

        def submit(client):
            try:
                start.wait(timeout=5)
                response = self.order_takeout(client=client, request_id=attempt)
                results.append((response.status_code, response.json()))
            except Exception as exc:
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=submit, args=(c,)) for c in clients]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        self.assertEqual(errors, [])
        self.assertEqual(sorted(code for code, _ in results), [200, 201])
        self.assertEqual(Order.objects.count(), 1)
        ids = {body["id"] for _, body in results}
        self.assertEqual(ids, {Order.objects.get().id})


@override_settings(**AUTH_SETTINGS)
class RefusalReachesTheScreenTests(TestCase):
    """A refusal the volunteer cannot read is a refusal they cannot act on."""

    def test_the_order_screen_shows_the_message_not_the_json(self):
        login_client(self.client, "ORDER")
        page = self.client.get(reverse("orders:order")).content.decode()
        self.assertIn("parsed.detail", page)

    def test_the_kitchen_board_shows_the_message_too(self):
        """The board is where these refusals actually land: cancelling an order
        someone else just cancelled, or finishing an item on a cancelled one.
        Fixing only the order screen left the real consumer showing raw JSON
        (2026-09-18 code review)."""
        for name in ("kitchen", "kitchen-hall", "kitchen-takeout"):
            with self.subTest(page=name):
                client = self.client_class()
                login_client(client, "KITCHEN")
                page = client.get(reverse(f"orders:{name}")).content.decode()
                self.assertIn("parsed.detail", page)

    def test_every_state_refusal_carries_a_detail_field(self):
        """409s are JSON; each one has to say something a person can act on."""
        from orders.services import status as status_service

        refused = status_service.TransitionRefused("CANCELLED", "PREPARING")
        self.assertIn("취소", refused.detail)
        other = status_service.TransitionRefused("READY", "SOMETHING")
        self.assertIn("READY", other.detail)

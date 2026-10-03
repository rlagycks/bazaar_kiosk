"""Takeout is a voucher, not a numbered tag (D-069, supersedes the slot rule of D-050).

Last year's flow gave the customer a numbered tag (101–120) and serving went
looking for the number; one tag could hold one waiting customer, and the
event ran out of tags at twenty live orders. This year the customer pays,
takes a voucher and exchanges it at the counter. Nobody is looked for, so a
takeout order holds no table and no tag: its order number is the voucher.

What is pinned here:

* a takeout-only order is accepted with no table number, and whatever the
  screen sends in that field is not a claim on a table;
* takeout orders never block each other -- READY, PREPARING, twenty of them;
* dine-in and mixed orders still need a real table;
* the same request_id racing itself still resolves to one order (the
  idempotency key now does alone what the slot index used to help with).
"""

import threading
import uuid

from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from orders.models import MenuItem, Order, OrderStatus, Table
from orders.tests.auth_support import AUTH_SETTINGS, login_client


class TakeoutFixture:
    def setUp(self):
        super().setUp()
        for number in (7, 105):
            Table.objects.create(number=number)
        self.menu = MenuItem.objects.create(name="Bowl", price=8000)
        login_client(self.client, "ORDER")

    def order_takeout(self, table_number="", client=None, request_id=None):
        return (client or self.client).post(
            reverse("orders:orders-collection"),
            {
                "request_id": request_id or str(uuid.uuid4()),
                "floor": "B1", "order_type": "TAKEOUT", "table_number": table_number,
                "payment_method": "CASH", "received_cash_amount": 8000,
                "items": [{"menu_item_id": self.menu.id, "qty": 1, "mode": "TAKEOUT"}],
            },
            content_type="application/json",
        )

    def order_dine_in(self, table="7", *, mixed=False):
        items = [{"menu_item_id": self.menu.id, "qty": 1, "mode": "DINE_IN"}]
        if mixed:
            items.append({"menu_item_id": self.menu.id, "qty": 1, "mode": "TAKEOUT"})
        return self.client.post(
            reverse("orders:orders-collection"),
            {
                "request_id": str(uuid.uuid4()),
                "floor": "B1", "order_type": "DINE_IN", "table_number": str(table),
                "payment_method": "CASH", "received_cash_amount": 8000 * len(items),
                "items": items,
            },
            content_type="application/json",
        )


@override_settings(**AUTH_SETTINGS)
class TakeoutVoucherTests(TakeoutFixture, TestCase):
    def test_a_takeout_order_needs_no_table_and_gets_a_number(self):
        response = self.order_takeout()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertIsNone(body["table"])
        self.assertEqual(body["order_no"], 1, "the order number is the voucher")
        self.assertTrue(body["is_takeout"])

    def test_a_number_typed_into_the_field_is_not_a_table_claim(self):
        for typed in ("105", "7", "999", "abc"):
            with self.subTest(typed=typed):
                response = self.order_takeout(table_number=typed)
                self.assertEqual(response.status_code, 201, response.content)
                self.assertIsNone(response.json()["table"])

    def test_takeout_orders_never_block_each_other(self):
        numbers = [self.order_takeout().json()["order_no"] for _ in range(25)]
        self.assertEqual(numbers, list(range(1, 26)))
        Order.objects.filter(order_no__lte=5).update(status=OrderStatus.READY)
        self.assertEqual(self.order_takeout().status_code, 201)
        self.assertEqual(Order.objects.count(), 26)

    def test_a_dine_in_order_still_needs_a_table(self):
        self.assertEqual(self.order_dine_in(table="").status_code, 400)
        self.assertEqual(self.order_dine_in(table="99").status_code, 400)
        self.assertEqual(self.order_dine_in(table="7").status_code, 201)

    def test_a_dine_in_order_flagged_as_takeout_is_refused_not_crashed(self):
        """The pair no screen sends used to reach the check constraint as a 500."""
        response = self.client.post(
            reverse("orders:orders-collection"),
            {
                "request_id": str(uuid.uuid4()),
                "floor": "B1", "order_type": "DINE_IN", "is_takeout": True, "table_number": "7",
                "payment_method": "CASH", "received_cash_amount": 8000,
                "items": [{"menu_item_id": self.menu.id, "qty": 1, "mode": "DINE_IN"}],
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("is_takeout", response.content.decode())
        self.assertEqual(Order.objects.count(), 0)

    def test_a_mixed_order_uses_the_hall_table(self):
        response = self.order_dine_in(table="7", mixed=True)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["table"]["number"], 7)
        self.assertEqual(self.order_dine_in(table="", mixed=True).status_code, 400)

    def test_the_database_itself_lets_takeout_rows_share_or_lack_a_table(self):
        """The constraints are the contract, not the view: no unique slot, no
        table requirement for takeout, table still required for dine-in."""
        from django.db import IntegrityError, transaction

        tag = Table.objects.get(number=105)
        for _ in range(2):
            Order.objects.create(floor="B1", order_type="TAKEOUT", is_takeout=True, table=tag,
                                 status=OrderStatus.PREPARING, total_price=8000,
                                 received_amount=8000, payment_method="CASH",
                                 received_cash_amount=8000, received_ticket_amount=0)
        Order.objects.create(floor="B1", order_type="TAKEOUT", is_takeout=True, table=None,
                             status=OrderStatus.PREPARING, total_price=8000,
                             received_amount=8000, payment_method="CASH",
                             received_cash_amount=8000, received_ticket_amount=0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Order.objects.create(floor="B1", order_type="DINE_IN", table=None,
                                 status=OrderStatus.PREPARING, total_price=8000,
                                 received_amount=8000, payment_method="CASH",
                                 received_cash_amount=8000, received_ticket_amount=0)


@override_settings(**AUTH_SETTINGS)
class ConcurrentRetryTests(TakeoutFixture, TransactionTestCase):
    def test_a_retry_of_the_same_attempt_racing_itself_gets_its_own_order_back(self):
        """The same request_id twice at once is a retry, not a second customer.

        Both arrivals pass the replay check (nothing is committed yet) and both
        reach the insert. The loser's insert fails on the idempotency key
        because the winner -- its own earlier self -- committed first. The
        loser looks the id up again and hands back the winner's order
        (2026-09-20 code review; the slot index that used to fire first is
        gone with D-069, so this key is the only line now).
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
        self.assertEqual(list(Order.objects.values_list("order_no", flat=True)), [1])


@override_settings(**AUTH_SETTINGS)
class RefusalReachesTheScreenTests(TestCase):
    """A refusal the volunteer cannot read is a refusal they cannot act on."""

    def test_the_order_screen_loads_the_controller_and_live_error_region(self):
        # JSON/plain-text refusal behavior is tested against the real extracted
        # controller in scripts/test_order_controller.cjs.
        login_client(self.client, "ORDER")
        page = self.client.get(reverse("orders:order")).content.decode()
        self.assertIn("ui/order.js", page)
        self.assertIn('id="save-error" class="ui-error" role="alert"', page)

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
                self.assertIn("ui/monitor.js", page)
                self.assertIn('id="detail-error" class="ui-error" role="alert"', page)
                self.assertIn('id="confirm-error" class="ui-error" role="alert"', page)

    def test_every_state_refusal_carries_a_detail_field(self):
        """409s are JSON; each one has to say something a person can act on."""
        from orders.services import status as status_service

        refused = status_service.TransitionRefused("CANCELLED", "PREPARING")
        self.assertIn("취소", refused.detail)
        other = status_service.TransitionRefused("READY", "SOMETHING")
        self.assertIn("READY", other.detail)

"""6A: one press of 저장, one order -- however many times the request arrives.

A phone on a bad connection is the ordinary case here, not the edge case. The
volunteer taps 저장, the response is lost, they tap again, and the kitchen gets
two identical orders and the customer is charged twice. Nothing in the server
could tell the retry from a second customer ordering the same thing.

So the client names the attempt and the server keeps that name. The contract:

* an attempt is identified by a client-generated request id;
* replaying it returns the order that was already created, never a second one;
* the same id with a different order is a conflict, not a silent overwrite;
* ids never expire, because an expired id silently becomes a duplicate.

Concurrency cases use TransactionTestCase and threads: the unique index is what
makes the parallel case safe, and an outer test transaction would hide it.
"""

import threading
import uuid

from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from orders.models import MenuItem, Order, OrderRequest, Table
from orders.tests.auth_support import ROLE_ACCOUNTS, login_client
from orders.services import idempotency
from orders.views import api


class OrderPostFixture:
    def setUp(self):
        super().setUp()
        api._get_table_by_number.cache_clear()
        self.addCleanup(api._get_table_by_number.cache_clear)
        self.table = Table.objects.create(number=9)
        self.menu = MenuItem.objects.create(name="Bowl", price=8000)
        self.other = MenuItem.objects.create(name="Soup", price=3000)

    def payload(self, *, request_id, qty=1, menu=None, note=""):
        return {
            "request_id": request_id,
            "floor": "B1",
            "order_type": "DINE_IN",
            "table_number": "9",
            "payment_method": "CASH",
            "received_cash_amount": 8000,
            "note": note,
            "items": [{"menu_item_id": (menu or self.menu).id, "qty": qty}],
        }

    def post(self, payload, client=None):
        return (client or self.client).post(
            reverse("orders:orders-collection"), payload, content_type="application/json"
        )

    def new_key(self):
        return str(uuid.uuid4())


@override_settings(ROLE_ACCOUNTS=ROLE_ACCOUNTS, JWT_COOKIE_SECURE=False)
class ReplayTests(OrderPostFixture, TestCase):
    def setUp(self):
        super().setUp()
        login_client(self.client, "ORDER")

    def test_the_same_attempt_twice_creates_one_order(self):
        key = self.new_key()
        first = self.post(self.payload(request_id=key))
        second = self.post(self.payload(request_id=key))
        self.assertEqual(first.status_code, 201, first.content)
        # 200, not 201: the caller can tell a replay from a creation, and a
        # client that counts creations does not double-count.
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(Order.objects.count(), 1)

    def test_a_replay_does_not_spend_an_order_number(self):
        key = self.new_key()
        first = self.post(self.payload(request_id=key)).json()
        self.post(self.payload(request_id=key))
        self.assertEqual(
            list(Order.objects.values_list("order_no", flat=True)), [first["order_no"]]
        )

    def test_two_different_attempts_are_two_orders(self):
        """Two customers ordering the same thing must not be merged."""
        self.post(self.payload(request_id=self.new_key()))
        self.post(self.payload(request_id=self.new_key()))
        self.assertEqual(Order.objects.count(), 2)

    def test_a_replay_still_works_after_another_order_intervenes(self):
        key = self.new_key()
        first = self.post(self.payload(request_id=key)).json()
        self.post(self.payload(request_id=self.new_key()))
        replay = self.post(self.payload(request_id=key))
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["id"], first["id"])
        self.assertEqual(Order.objects.count(), 2)

    def test_the_replay_answers_with_the_stored_order_not_a_rebuild(self):
        key = self.new_key()
        created = self.post(self.payload(request_id=key)).json()
        # The menu changes afterwards; the replay must still describe the order
        # as it was taken, and must not fail because the menu moved on.
        MenuItem.objects.filter(pk=self.menu.pk).update(price=9999, is_active=False)
        replay = self.post(self.payload(request_id=key))
        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(replay.json()["total_price"], created["total_price"])
        self.assertEqual(replay.json()["items"][0]["unit_price"], 8000)


@override_settings(ROLE_ACCOUNTS=ROLE_ACCOUNTS, JWT_COOKIE_SECURE=False)
class ConflictTests(OrderPostFixture, TestCase):
    def setUp(self):
        super().setUp()
        login_client(self.client, "ORDER")

    def test_the_same_id_with_a_different_order_is_refused(self):
        """Silently returning the first order would hide a real mistake: the
        volunteer edited the cart and believes the edit was saved."""
        key = self.new_key()
        self.post(self.payload(request_id=key))
        changed = self.post(self.payload(request_id=key, qty=3))
        self.assertEqual(changed.status_code, 409, changed.content)
        self.assertEqual(Order.objects.count(), 1)

    def test_a_different_menu_under_the_same_id_is_refused(self):
        key = self.new_key()
        self.post(self.payload(request_id=key))
        self.assertEqual(
            self.post(self.payload(request_id=key, menu=self.other)).status_code, 409
        )

    def test_a_different_note_under_the_same_id_is_refused(self):
        key = self.new_key()
        self.post(self.payload(request_id=key))
        self.assertEqual(
            self.post(self.payload(request_id=key, note="덜 맵게")).status_code, 409
        )

    def test_another_account_may_not_replay_someone_elses_id(self):
        """Answering with the stored order would hand one screen an order taken
        on another. A collision between two devices is a conflict, not a hit."""
        key = self.new_key()
        created = self.post(self.payload(request_id=key)).json()
        counter = self.client_class()
        login_client(counter, "B1_COUNTER")
        response = self.post(self.payload(request_id=key), client=counter)
        self.assertEqual(response.status_code, 409, response.content)
        # Nothing about the stored order comes back -- not its id, not its
        # contents. (Checked structurally: the escaped Korean detail string
        # contains digits, so searching the raw body for an id is meaningless.)
        body = response.json()
        self.assertEqual(set(body), {"detail"})
        self.assertNotIn("id", body)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderRequest.objects.get(key=key).order_id, created["id"])


class FingerprintTests(TestCase):
    """The digest decides whether an arrival is the same order.

    It has to ignore how the values were transported and notice every change
    that makes it a different order. A retry sending 8000 where the first
    attempt sent "8000" is the same order; a retry with another item is not.
    """

    def digest(self, **overrides):
        payload = {
            "floor": "B1", "order_type": "DINE_IN", "table_number": "9",
            "payment_method": "CASH", "received_cash_amount": 8000,
            "received_ticket_amount": 0, "note": "",
            "items": [{"menu_item_id": 3, "qty": 2, "mode": "DINE_IN"}],
        }
        payload.update(overrides)
        return idempotency.fingerprint(payload)

    def test_a_number_and_its_string_are_the_same_order(self):
        self.assertEqual(self.digest(), self.digest(received_cash_amount="8000"))

    def test_item_fields_survive_the_same_way(self):
        self.assertEqual(
            self.digest(),
            self.digest(items=[{"menu_item_id": "3", "qty": "2", "mode": "DINE_IN"}]),
        )

    def test_case_does_not_make_a_different_order(self):
        for field, value in (
            ("floor", "b1"),
            ("order_type", "dine_in"),
            ("payment_method", "cash"),
        ):
            with self.subTest(field=field):
                self.assertEqual(self.digest(), self.digest(**{field: value}))
        self.assertEqual(
            self.digest(),
            self.digest(items=[{"menu_item_id": 3, "qty": 2, "mode": "dine_in"}]),
        )

    def test_the_order_of_items_does_not_matter(self):
        two = [
            {"menu_item_id": 3, "qty": 2, "mode": "DINE_IN"},
            {"menu_item_id": 4, "qty": 1, "mode": "TAKEOUT"},
        ]
        self.assertEqual(self.digest(items=two), self.digest(items=list(reversed(two))))

    def test_a_real_change_still_changes_the_digest(self):
        base = self.digest()
        for label, change in (
            ("qty", {"items": [{"menu_item_id": 3, "qty": 3, "mode": "DINE_IN"}]}),
            ("menu", {"items": [{"menu_item_id": 4, "qty": 2, "mode": "DINE_IN"}]}),
            ("mode", {"items": [{"menu_item_id": 3, "qty": 2, "mode": "TAKEOUT"}]}),
            ("table", {"table_number": "10"}),
            ("payment", {"payment_method": "TICKET"}),
            ("cash", {"received_cash_amount": 9000}),
            ("ticket", {"received_ticket_amount": 500}),
            ("note", {"note": "덜 맵게"}),
            ("dropped item", {"items": []}),
            ("added item", {"items": [
                {"menu_item_id": 3, "qty": 2, "mode": "DINE_IN"},
                {"menu_item_id": 4, "qty": 1, "mode": "DINE_IN"},
            ]}),
        ):
            with self.subTest(change=label):
                self.assertNotEqual(base, self.digest(**change))

    def test_a_missing_amount_is_not_the_same_as_zero(self):
        """Nothing received and zero received are different claims about money."""
        self.assertNotEqual(
            self.digest(received_ticket_amount=0),
            self.digest(received_ticket_amount=None),
        )


@override_settings(ROLE_ACCOUNTS=ROLE_ACCOUNTS, JWT_COOKIE_SECURE=False)
class RequestIdValidationTests(OrderPostFixture, TestCase):
    def setUp(self):
        super().setUp()
        login_client(self.client, "ORDER")

    def test_an_order_without_a_request_id_is_refused(self):
        """Fail closed. Accepting it would leave the duplicate hole open for
        exactly the client that most needs it closed -- an old cached page."""
        payload = self.payload(request_id="")
        payload.pop("request_id")
        response = self.post(payload)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(Order.objects.count(), 0)

    def test_a_malformed_request_id_is_refused(self):
        for bad in ("", "  ", "short", "!" * 36, "x" * 200, "../../etc/passwd"):
            with self.subTest(request_id=bad):
                response = self.post(self.payload(request_id=bad))
                self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(Order.objects.count(), 0)

    def test_an_id_is_recorded_only_when_the_order_is(self):
        """A rejected order must leave its id free: the volunteer fixes the
        cart and presses again, and that must not be a conflict."""
        key = self.new_key()
        broken = self.payload(request_id=key)
        broken["items"] = [{"menu_item_id": 999999, "qty": 1}]
        self.assertEqual(self.post(broken).status_code, 400)
        self.assertEqual(OrderRequest.objects.count(), 0)
        self.assertEqual(self.post(self.payload(request_id=key)).status_code, 201)
        self.assertEqual(Order.objects.count(), 1)

    def test_ids_do_not_expire(self):
        """An expiring id silently becomes a duplicate when a slow retry lands
        after it. There is no expiry, so a late replay is still a replay."""
        from datetime import timedelta

        from django.utils import timezone

        key = self.new_key()
        created = self.post(self.payload(request_id=key)).json()
        OrderRequest.objects.filter(key=key).update(
            created_at=timezone.now() - timedelta(days=400)
        )
        replay = self.post(self.payload(request_id=key))
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["id"], created["id"])


@override_settings(ROLE_ACCOUNTS=ROLE_ACCOUNTS, JWT_COOKIE_SECURE=False)
class ParallelSubmissionTests(OrderPostFixture, TransactionTestCase):
    """A double tap sends both requests before either answers."""

    def test_two_requests_with_one_id_produce_one_order(self):
        key = self.new_key()
        clients = []
        for _ in range(2):
            client = self.client_class()
            login_client(client, "ORDER")
            clients.append(client)

        start = threading.Barrier(2)
        responses = []
        errors = []

        def submit(client):
            try:
                start.wait(timeout=5)
                responses.append(self.post(self.payload(request_id=key), client=client))
            except Exception as exc:  # surfaced below, never swallowed
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=submit, args=(c,)) for c in clients]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        self.assertEqual(errors, [])
        self.assertEqual(Order.objects.count(), 1, "a double tap created two orders")
        self.assertEqual(OrderRequest.objects.count(), 1)
        self.assertEqual(sorted(r.status_code for r in responses), [200, 201])
        ids = {r.json()["id"] for r in responses}
        self.assertEqual(len(ids), 1, "the two answers described different orders")
        # The loser's whole transaction rolled back, so it left no order rows
        # behind and did not spend an order number.
        self.assertEqual(list(Order.objects.values_list("order_no", flat=True)), [1])


@override_settings(ROLE_ACCOUNTS=ROLE_ACCOUNTS, JWT_COOKIE_SECURE=False)
class OrderScreenWiringTests(TestCase):
    """The screen has to mint and send an id, or the whole boundary is dead
    weight: every real order would be refused with 400."""

    def setUp(self):
        login_client(self.client, "ORDER")
        self.page = self.client.get(reverse("orders:order")).content.decode()

    def test_the_page_loads_the_id_helper_and_sends_the_id(self):
        self.assertIn("ui/request_id.js", self.page)
        self.assertIn("request_id: attemptId()", self.page)

    def test_the_id_is_dropped_once_the_order_is_saved(self):
        """Otherwise the next customer's order replays the previous id and the
        server answers 409 -- ordering would stop after the first sale."""
        self.assertIn("startNewAttempt()", self.page)

    def test_editing_the_order_abandons_the_attempt(self):
        """A correction after a failed save must not carry the old id, which
        would be refused as a conflict."""
        for wiring in (
            "input.addEventListener('input', startNewAttempt)",
            "els.paymentRadios.forEach(r => r.addEventListener('change', startNewAttempt))",
            "els.menu.addEventListener('click', startNewAttempt)",
            "els.cart.addEventListener('click', startNewAttempt)",
        ):
            with self.subTest(wiring=wiring):
                self.assertIn(wiring, self.page)

    def test_the_helper_does_not_depend_on_a_secure_context(self):
        """Served over plain HTTP on the venue LAN, crypto.randomUUID does not
        exist. A helper that only used it would stop every order."""
        from django.conf import settings

        helper = (
            settings.BASE_DIR / "orders/static/orders/ui/request_id.js"
        ).read_text(encoding="utf-8")
        self.assertIn("getRandomValues", helper)

"""Phase 2A: supported happy paths, not unresolved security/payment policies.

Run only with bazaar_kiosk.settings_test. SQLite results do not establish
PostgreSQL sequence, locking, migration, or concurrency guarantees.
"""

from unittest.mock import patch

from django.core.cache import cache
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from orders.models import FloorOrderCounter, MenuItem, Order, OrderItem, Table
from orders.views import api


ROLE_PINS = {
    "ORDER": "test-order-pin",
    "B1_COUNTER": "test-counter-pin",
    "KITCHEN": "test-kitchen-pin",
    "KITCHEN_HALL": "test-hall-pin",
    "KITCHEN_TAKEOUT": "test-takeout-pin",
}
ROLE_PAGES = (
    ("ORDER", "order", "orders/order.html", None),
    ("B1_COUNTER", "b1-counter", "orders/b1_counter.html", None),
    ("KITCHEN", "kitchen", "orders/kitchen_supervisor.html", "ALL"),
    ("KITCHEN_HALL", "kitchen-hall", "orders/kitchen_supervisor.html", "HALL"),
    ("KITCHEN_TAKEOUT", "kitchen-takeout", "orders/kitchen_supervisor.html", "TAKEOUT"),
)


class BaselineMixin:
    def setUp(self):
        super().setUp()
        cache.clear()
        api._get_table_by_number.cache_clear()
        self.addCleanup(cache.clear)
        self.addCleanup(api._get_table_by_number.cache_clear)

    def login_role(self, role="ORDER"):
        response = self.client.post(
            reverse("orders:login"), {"role": role, "pin": ROLE_PINS[role]}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session["role"], role)
        return response


@override_settings(ROLE_PINS=ROLE_PINS)
class LoginBaselineTests(BaselineMixin, TestCase):
    def test_each_role_redirects_to_its_rendered_page(self):
        for role, page, template, scope in ROLE_PAGES:
            with self.subTest(role=role):
                self.client.cookies.clear()
                response = self.login_role(role)
                self.assertRedirects(
                    response, reverse(f"orders:{page}"), fetch_redirect_response=False
                )
                page_response = self.client.get(response.url)
                self.assertEqual(page_response.status_code, 200)
                self.assertTemplateUsed(page_response, template)
                if scope is not None:
                    self.assertEqual(page_response.context["mode_scope"], scope)

    def test_wrong_pin_does_not_establish_a_role(self):
        for role in ROLE_PINS:
            with self.subTest(role=role):
                self.client.cookies.clear()
                response = self.client.post(
                    reverse("orders:login"), {"role": role, "pin": "wrong-test-pin"}
                )
                self.assertEqual(response.status_code, 200)
                # The current template does not render the error. Check only
                # the server context; this does not verify visible feedback.
                self.assertEqual(
                    response.context["error"], "역할 또는 PIN이 올바르지 않습니다."
                )
                self.assertTemplateUsed(response, "orders/login.html")
                self.assertNotIn("role", self.client.session)

    def test_anonymous_pages_redirect_to_login(self):
        response = self.client.get(reverse("orders:login"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "orders/login.html")
        for _, page, _, _ in ROLE_PAGES:
            with self.subTest(page=page):
                self.assertRedirects(
                    self.client.get(reverse(f"orders:{page}")),
                    reverse("orders:login"),
                )


class OrderFixtureMixin(BaselineMixin):
    def setUp(self):
        super().setUp()
        self.hall = Table.objects.create(number=7, name="Synthetic hall")
        self.takeout = Table.objects.create(number=107, name="Synthetic pickup")
        self.meal = MenuItem.objects.create(name="Synthetic meal", price=4300)
        self.side = MenuItem.objects.create(name="Synthetic side", price=1700)
        self.login_role()

    def payload(self, order_type="DINE_IN"):
        return {
            "floor": "B1",
            "order_type": order_type,
            "is_takeout": order_type == "TAKEOUT",
            "table_number": str(
                self.takeout.number if order_type == "TAKEOUT" else self.hall.number
            ),
            "source": "ORDER",
            "payment_method": "CASH",
            "received_amount": 13700,
            "note": "Synthetic order",
            "items": [
                {"menu_item_id": self.meal.pk, "qty": 2},
                {"menu_item_id": self.side.pk, "qty": 3},
            ],
        }

    def create_order(self, payload=None):
        response = self.client.post(
            reverse("orders:orders-collection"),
            self.payload() if payload is None else payload,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def detail(self, order_id):
        response = self.client.get(reverse("orders:order-detail", args=[order_id]))
        self.assertEqual(response.status_code, 200)
        return response.json()

    def assert_prices(self, data):
        self.assertEqual(data["total_price"], 13700)
        items = {row["menu_item"]["id"]: row for row in data["items"]}
        self.assertEqual(set(items), {self.meal.pk, self.side.pk})
        for menu, qty, price in ((self.meal, 2, 4300), (self.side, 3, 1700)):
            row = items[menu.pk]
            self.assertEqual(row["qty"], qty)
            self.assertEqual(row["unit_price"], price)
            self.assertEqual(row["menu_item"]["price"], price)
            self.assertEqual(row["line_total"], qty * price)


@override_settings(ROLE_PINS=ROLE_PINS)
class OrderBaselineTests(OrderFixtureMixin, TestCase):
    def test_hall_and_takeout_creation_and_retrieval(self):
        for order_type, table in (("DINE_IN", self.hall), ("TAKEOUT", self.takeout)):
            with self.subTest(order_type=order_type):
                data = self.create_order(self.payload(order_type))
                order = Order.objects.get(pk=data["id"])
                self.assertEqual(order.order_type, order_type)
                self.assertEqual(order.table_id, table.pk)
                self.assertEqual(order.is_takeout, order_type == "TAKEOUT")
                self.assertEqual(order.status, "PREPARING")
                self.assertEqual(order.source, "ORDER")
                self.assertEqual(order.total_price, 13700)
                self.assertEqual(order.received_cash_amount, 13700)
                self.assertEqual(data["table"]["number"], table.number)
                self.assert_prices(data)
                self.assertEqual(self.detail(order.pk), data)
                self.assertEqual(
                    set(order.items.values_list("service_mode", flat=True)), {order_type}
                )
                response = self.client.get(
                    reverse("orders:orders-collection"),
                    {"floor": "B1", "types": order_type},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["results"], [data])
                self.assertEqual(response.json()["count"], 1)

    def test_fully_paid_cash_ticket_and_mixed_payments(self):
        # Exact payment exercises each supported method without deciding change,
        # underpayment, or refund policies. Zero and NULL are equivalent here.
        cases = (
            ("CASH", {"received_amount": 13700}, 13700, 0),
            ("TICKET", {"received_amount": 13700}, 0, 13700),
            (
                "CASH_TICKET",
                {"received_cash_amount": 8700, "received_ticket_amount": 5000},
                8700,
                5000,
            ),
        )
        for method, amounts, cash, ticket in cases:
            with self.subTest(payment_method=method):
                payload = self.payload()
                payload.pop("received_amount")
                payload.update(payment_method=method, **amounts)
                data = self.create_order(payload)
                order = Order.objects.get(pk=data["id"])
                self.assertEqual(order.payment_method, method)
                self.assertEqual(order.received_amount, 13700)
                self.assertEqual(order.received_cash_amount or 0, cash)
                self.assertEqual(order.received_ticket_amount or 0, ticket)
                self.assertEqual(order.total_price, 13700)
                for representation in (data, self.detail(order.pk)):
                    self.assertEqual(representation["payment_method"], method)
                    self.assertEqual(representation["received_amount"], 13700)
                    self.assertEqual(representation["received_cash_amount"], cash)
                    self.assertEqual(representation["received_ticket_amount"], ticket)
                    self.assert_prices(representation)

    def test_server_prices_ignore_client_values_and_survive_menu_changes(self):
        payload = self.payload()
        payload["total_price"] = 1
        for item in payload["items"]:
            item.update(price=1, unit_price=1, line_total=1)
        data = self.create_order(payload)
        self.assert_prices(data)
        order = Order.objects.get(pk=data["id"])
        self.assertEqual(order.total_price, 13700)
        self.assertEqual(
            list(order.items.values_list("menu_item_id", "qty", "unit_price")),
            [(self.meal.pk, 2, 4300), (self.side.pk, 3, 1700)],
        )
        MenuItem.objects.filter(pk=self.meal.pk).update(price=9900)
        MenuItem.objects.filter(pk=self.side.pk).update(price=2800)
        order.refresh_from_db()
        self.assertEqual(order.total_price, 13700)
        self.assertEqual([item.line_total for item in order.items.all()], [8600, 5100])
        self.assert_prices(self.detail(order.pk))
        response = self.client.get(reverse("orders:orders-collection"))
        self.assertEqual(response.status_code, 200)
        self.assert_prices(response.json()["results"][0])

    def test_kitchen_progress_remaining_quantities_and_status_stay_in_sync(self):
        data = self.create_order()
        self.login_role("KITCHEN")
        first, second = data["items"]

        def assert_progress(prepared, remaining, status):
            current = self.detail(data["id"])
            self.assertEqual(current["status"], status)
            self.assertEqual([row["prepared_qty"] for row in current["items"]], prepared)
            self.assertEqual([row["remaining_qty"] for row in current["items"]], remaining)
            self.assertEqual(
                [row["is_prepared"] for row in current["items"]],
                [qty == 0 for qty in remaining],
            )
            self.assertEqual(Order.objects.get(pk=data["id"]).status, status)
            self.assertEqual(
                list(OrderItem.objects.filter(order_id=data["id"]).values_list(
                    "prepared_qty", flat=True
                )), prepared,
            )
            summary = self.client.get(reverse("orders:kitchen-menu-summary"))
            self.assertEqual(summary.status_code, 200)
            self.assertEqual(
                {row["menu_item_id"]: row["pending"] for row in summary.json()["items"]},
                {mid: qty for mid, qty in zip((self.meal.pk, self.side.pk), remaining) if qty},
            )

        def progress(item, payload):
            response = self.client.patch(
                reverse("orders:order-item-progress", args=[item["id"]]),
                payload, content_type="application/json",
            )
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.json(), {"id": data["id"]})

        assert_progress([0, 0], [2, 3], "PREPARING")
        progress(first, {"prepared_qty": 1})
        assert_progress([1, 0], [1, 3], "PREPARING")
        progress(first, {"done": True})
        assert_progress([2, 0], [0, 3], "PREPARING")
        progress(second, {"done": True})
        assert_progress([2, 3], [0, 0], "READY")


@override_settings(ROLE_PINS=ROLE_PINS)
class OrderAtomicBaselineTests(OrderFixtureMixin, TransactionTestCase):
    """No TestCase outer atomic block may conceal a missing request transaction."""

    def test_late_failure_rolls_back_order_items_and_counter(self):
        self.assertFalse(connection.in_atomic_block)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertEqual(FloorOrderCounter.objects.count(), 0)
        allocate = api.allocate_floor_order_no
        observed = []

        class InjectedLateFailure(Exception):
            pass

        def allocate_then_fail(order):
            # Execute real writes, including the SQLite counter, before failing.
            allocate(order)
            order.refresh_from_db()
            observed.append(order.pk)
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(order.items.count(), 2)
            self.assertEqual(order.total_price, 13700)
            self.assertIsNotNone(order.order_no)
            if connection.vendor == "sqlite":
                self.assertEqual(FloorOrderCounter.objects.count(), 1)
                self.assertEqual(FloorOrderCounter.objects.get().last_no, order.order_no)
            raise InjectedLateFailure("synthetic failure after persisted allocation")

        with patch.object(api, "allocate_floor_order_no", side_effect=allocate_then_fail):
            with self.assertRaisesRegex(InjectedLateFailure, "after persisted allocation"):
                self.client.post(
                    reverse("orders:orders-collection"), self.payload(),
                    content_type="application/json",
                )
        self.assertEqual(len(observed), 1)
        self.assertFalse(connection.in_atomic_block)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertEqual(FloorOrderCounter.objects.count(), 0)
        # A subsequent valid request must still be usable; no numbering policy asserted.
        self.create_order()
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderItem.objects.count(), 2)

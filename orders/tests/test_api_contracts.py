"""9: what the API promises about malformed input (BK-R015).

Every writing endpoint reads its body with one helper and then treats the
result as a mapping. A body that is a list, a bare string, a number or `null`
parses as valid JSON and is none of those things, so the next `.get` raised
an AttributeError and Django answered 500. The same happened one level down:
a field that should be a string arrived as a number and `.upper()` ended the
request.

A 500 is the server saying it broke. Malformed input is the caller's, and it
has to be answered with a sentence and a 4xx. That is the whole of this
module: nothing here changes what a well-formed request does.
"""

import json
import uuid

from django.test import TestCase, override_settings
from django.urls import reverse

from orders.models import MenuItem, NumberSeries, Order, OrderItem, OrderStatus, OrderType, Table
from orders.tests.auth_support import AUTH_SETTINGS, login_client

# Valid JSON that is not an object. Each one used to reach `.get`.
NOT_AN_OBJECT = ("[]", "[1, 2, 3]", '"text"', "5", "null", "true", '[{"a": 1}]')


@override_settings(**AUTH_SETTINGS)
class BodyShapeTests(TestCase):
    """Three endpoints read a body. None of them may answer 5xx for it."""

    def setUp(self):
        self.table = Table.objects.create(number=7)
        self.menu = MenuItem.objects.create(name="Meal", price=5000)
        self.order = Order.objects.create(
            table=self.table, floor="B1", order_type=OrderType.DINE_IN,
            status=OrderStatus.PREPARING, number_series=NumberSeries.REAL,
            total_price=5000, payment_method="CASH", received_amount=5000,
            received_cash_amount=5000, received_ticket_amount=0, change_amount=0,
        )
        self.item = OrderItem.objects.create(
            order=self.order, menu_item=self.menu, qty=1, unit_price=5000,
            service_mode=OrderType.DINE_IN,
        )

    def endpoints(self):
        return (
            ("POST", reverse("orders:orders-collection"), "ORDER"),
            ("PATCH", reverse("orders:order-status", args=[self.order.id]), "KITCHEN"),
            ("PATCH", reverse("orders:order-item-progress", args=[self.item.id]), "KITCHEN"),
        )

    def send(self, method, url, alias, body):
        login_client(self.client, alias)
        return self.client.generic(method, url, body, content_type="application/json")

    def test_a_body_that_is_not_an_object_is_refused_not_crashed(self):
        for method, url, alias in self.endpoints():
            for body in NOT_AN_OBJECT:
                with self.subTest(url=url, body=body):
                    response = self.send(method, url, alias, body)
                    self.assertLess(response.status_code, 500, response.content[:200])
                    self.assertGreaterEqual(response.status_code, 400)

    def test_a_deeply_nested_body_is_refused_not_crashed(self):
        """Python raises RecursionError here, not a decode error, so leaving
        it uncaught put back the very 500 this module removes. About 20k
        opening brackets, well under the body-size limit (PR #75 security
        review)."""
        deep = "[" * 20000 + "]" * 20000
        for method, url, alias in self.endpoints():
            with self.subTest(url=url):
                response = self.send(method, url, alias, deep)
                self.assertLess(response.status_code, 500, response.content[:200])
                self.assertGreaterEqual(response.status_code, 400)

    def test_a_body_that_is_not_utf8_is_refused_not_crashed(self):
        for method, url, alias in self.endpoints():
            with self.subTest(url=url):
                response = self.send(method, url, alias, b"\xff\xfe{bad}")
                self.assertLess(response.status_code, 500, response.content[:200])
                self.assertGreaterEqual(response.status_code, 400)

    def test_a_body_that_is_not_json_is_refused_not_crashed(self):
        for method, url, alias in self.endpoints():
            with self.subTest(url=url):
                response = self.send(method, url, alias, "{not json")
                self.assertLess(response.status_code, 500, response.content[:200])
                self.assertGreaterEqual(response.status_code, 400)

    def test_an_empty_body_is_refused_not_crashed(self):
        """An empty body carries no fields, so every endpoint refuses it for
        the field it needs. `< 500` alone would also pass if one of them
        started answering 200 (PR #75 review)."""
        for method, url, alias in self.endpoints():
            with self.subTest(url=url):
                response = self.send(method, url, alias, "")
                self.assertLess(response.status_code, 500, response.content[:200])
                self.assertGreaterEqual(response.status_code, 400)

    def test_a_whitespace_only_body_reads_the_same_as_before(self):
        """It is not an empty body: the old parser handed `"   "` to the
        JSON decoder and answered 400. Treating it as `{}` would be a
        widening this phase did not ask for (PR #75 security review)."""
        for method, url, alias in self.endpoints():
            with self.subTest(url=url):
                response = self.send(method, url, alias, "   ")
                self.assertLess(response.status_code, 500, response.content[:200])
                self.assertGreaterEqual(response.status_code, 400)

    def test_every_refusal_says_something_in_words(self):
        for method, url, alias in self.endpoints():
            with self.subTest(url=url):
                response = self.send(method, url, alias, "[]")
                self.assertTrue(response.content.strip(), "refused with an empty body")


@override_settings(**AUTH_SETTINGS)
class FieldTypeTests(TestCase):
    """One level down: the body is an object but a field is the wrong type."""

    def setUp(self):
        self.table = Table.objects.create(number=7)
        self.menu = MenuItem.objects.create(name="Meal", price=5000)
        login_client(self.client, "ORDER")

    def create(self, **overrides):
        body = {
            "request_id": str(uuid.uuid4()), "floor": "B1", "order_type": "DINE_IN",
            "table_number": "7", "items": [{"menu_item_id": self.menu.id, "qty": 1}],
            "payment_method": "CASH", "received_cash_amount": 5000,
        }
        body.update(overrides)
        return self.client.post(reverse("orders:orders-collection"),
                                json.dumps(body), content_type="application/json")

    def test_the_happy_request_still_works(self):
        """Everything below must refuse. This one must not."""
        self.assertEqual(self.create().status_code, 201)

    def test_a_field_of_the_wrong_type_is_refused_not_crashed(self):
        wrong = {
            "floor": [5, {"a": 1}, True],
            "order_type": [7, None, ["DINE_IN"]],
            "note": [{"a": 1}, [1, 2], 5],
            "items": ["DINE_IN", {"menu_item_id": 1}, 5, [[]], [None], ["x"]],
            "table_number": [{"a": 1}, [7]],
            "payment_method": [5, {"a": 1}],
            "request_id": [5, {"a": 1}, []],
        }
        for field, values in wrong.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    response = self.create(**{field: value})
                    self.assertLess(response.status_code, 500,
                                    f"{field}={value!r} -> {response.content[:200]}")
                    self.assertGreaterEqual(response.status_code, 400)

    def test_a_wrong_typed_item_mode_or_source_is_refused_not_crashed(self):
        """These two reached `.upper()` unguarded. One item carrying
        `"mode": 5` ended the whole request in a 500 (PR #75 code review)."""
        for value in (5, {"a": 1}, [1], True):
            with self.subTest(mode=value):
                response = self.create(
                    items=[{"menu_item_id": self.menu.id, "qty": 1, "mode": value}])
                self.assertLess(response.status_code, 500, response.content[:200])
                self.assertGreaterEqual(response.status_code, 400)
            with self.subTest(service_mode=value):
                response = self.create(
                    items=[{"menu_item_id": self.menu.id, "qty": 1, "service_mode": value}])
                self.assertLess(response.status_code, 500, response.content[:200])
            with self.subTest(source=value):
                response = self.create(source=value)
                self.assertLess(response.status_code, 500, response.content[:200])
                self.assertGreaterEqual(response.status_code, 400)

    def test_a_falsy_field_still_means_the_default_it_always_meant(self):
        """The views read these as `p.get(x) or default`, and `or` swallows
        every falsy value. An order carrying `"note": 0` was created before
        this phase, so it is created now. Refusing it would be a behaviour
        change smuggled in as a bug fix (PR #75 code review)."""
        for field in ("note", "floor", "source"):
            for value in (0, False, [], {}, ""):
                with self.subTest(field=field, value=value):
                    response = self.create(**{field: value})
                    self.assertEqual(response.status_code, 201,
                                     f"{field}={value!r} -> {response.content[:200]}")

    def test_a_falsy_table_number_is_missing_not_mistyped(self):
        """A dine-in order really does need a table, so a falsy value is
        refused -- but for being absent, with the sentence it always had,
        not for being the wrong type."""
        for value in (0, False, [], {}, ""):
            with self.subTest(value=value):
                response = self.create(table_number=value)
                self.assertEqual(response.status_code, 400)
                self.assertIn("테이블 번호가 필요합니다", response.content.decode())

    def test_an_item_entry_missing_its_fields_is_refused(self):
        for entry in ({}, {"qty": 1}, {"menu_item_id": None, "qty": 1},
                      {"menu_item_id": self.menu.id, "qty": None},
                      {"menu_item_id": self.menu.id, "qty": {"a": 1}}):
            with self.subTest(entry=entry):
                response = self.create(items=[entry])
                self.assertLess(response.status_code, 500, response.content[:200])
                self.assertGreaterEqual(response.status_code, 400)


@override_settings(**AUTH_SETTINGS)
class ReadContractTests(TestCase):
    """The query string is caller input too."""

    def setUp(self):
        Table.objects.create(number=7)
        MenuItem.objects.create(name="Meal", price=5000)
        login_client(self.client, "KITCHEN")

    def test_hostile_query_parameters_do_not_crash_the_list(self):
        for params in ({"limit": "x" * 5000}, {"limit": "9" * 40}, {"status": "＿"},
                       {"types": "," * 100}, {"floor": "b1"}, {"types": "x" * 3000},
                       {"limit": "-1"}, {"status": ""}, {"limit": ""}):
            with self.subTest(params=params):
                response = self.client.get(reverse("orders:orders-collection"), params)
                self.assertLess(response.status_code, 500, response.content[:200])


@override_settings(**AUTH_SETTINGS)
class QueryBaselineTests(TestCase):
    """9 hands over a query baseline, so an extraction that quietly costs
    more shows up as a failure rather than as a slower evening.

    These numbers are not a target. They are what the code does today; a
    change to one is a change that has to be explained in the same commit.
    """

    def setUp(self):
        self.table = Table.objects.create(number=7)
        self.menu = MenuItem.objects.create(name="Meal", price=5000)
        login_client(self.client, "KITCHEN")

    def waiting_order(self, items=1):
        order = Order.objects.create(
            table=self.table, floor="B1", order_type=OrderType.DINE_IN,
            status=OrderStatus.PREPARING, number_series=NumberSeries.REAL,
            total_price=5000, payment_method="CASH", received_amount=5000,
            received_cash_amount=5000, received_ticket_amount=0, change_amount=0,
        )
        for _ in range(items):
            OrderItem.objects.create(order=order, menu_item=self.menu, qty=1,
                                     unit_price=5000, service_mode=OrderType.DINE_IN)
        return order

    def board(self):
        return self.client.get(reverse("orders:orders-collection"),
                               {"floor": "B1", "status": "PREPARING"})

    def count_board(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as captured:
            self.assertEqual(self.board().status_code, 200)
        return len(captured)

    def test_the_board_is_a_small_fixed_number_of_queries(self):
        """Authentication, the slice, and the two prefetches. 8B removed the
        count from this path; nothing here may put it back unnoticed."""
        for _ in range(2):
            self.waiting_order(items=2)
        self.assertLessEqual(self.count_board(), 6)

    def test_twenty_orders_cost_what_two_cost(self):
        for _ in range(2):
            self.waiting_order(items=2)
        small = self.count_board()
        for _ in range(18):
            self.waiting_order(items=2)
        self.assertEqual(self.count_board(), small)

    def test_one_order_detail_is_a_bounded_number_of_queries(self):
        order = self.waiting_order(items=5)
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(reverse("orders:order-detail", args=[order.id]))
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(captured), 8, [q["sql"][:80] for q in captured])

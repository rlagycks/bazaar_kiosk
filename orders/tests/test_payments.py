"""7A: the server decides what an order costs and whether it was paid (D-048).

Before this, `int()` did the checking: `True` became 1 won, `1.9` became 1,
a 5000-won order saved fine with 0 won received, and nothing bounded the
numbers. The rules now (BK-R014, BK-R030):

* amounts and quantities are whole, non-negative, bounded integers; floats,
  booleans and decimal strings are refused, not truncated;
* the total is the server's menu price snapshot times quantity, never a
  client figure;
* received < total is refused (D-048: "아예 저장 거부");
* the change is computed here and stored with the order (D-048: "저장한다").
  Ticket surplus is not change -- tickets are not refunded in cash.
"""

import uuid

from django.db import transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from orders.models import MenuItem, Order, OrderItem, OrderRequest, Table
from orders.services import payments
from orders.tests.auth_support import AUTH_SETTINGS, login_client
from orders.views import api


class AmountParsingTests(SimpleTestCase):
    def test_whole_numbers_in_every_transport_form_are_accepted(self):
        for raw, expected in ((5000, 5000), ("5000", 5000), ("5,000", 5000),
                              (" 5000 ", 5000), (0, 0), ("0", 0)):
            with self.subTest(raw=raw):
                self.assertEqual(payments.parse_amount(raw, "금액"), expected)

    def test_missing_means_none_not_zero(self):
        """Nothing received and zero received are different claims (6A)."""
        for raw in (None, "", "   "):
            with self.subTest(raw=raw):
                self.assertIsNone(payments.parse_amount(raw, "금액"))

    def test_anything_that_is_not_a_whole_won_is_refused_not_truncated(self):
        for raw in (True, False, 1.5, 5000.0, "1.9", "5000.0", -1, "-1",
                    "abc", "1e3", [], {}, payments.MAX_AMOUNT + 1,
                    str(payments.MAX_AMOUNT + 1)):
            with self.subTest(raw=raw):
                with self.assertRaises(payments.AmountError):
                    payments.parse_amount(raw, "금액")

    def test_only_ascii_digit_strings_count_as_numbers(self):
        """`str.isdigit()` is wider than `int()`: a superscript two passes it
        and then crashes `int()`, and a 5000-digit string trips `int()`'s own
        limit. Both used to surface as a 500 (PR #69 review)."""
        for raw in ("\u00b2", "\u0661\u0662\u0663", "9" * 5000, "9" * 13, "５０００"):
            with self.subTest(raw=raw):
                with self.assertRaises(payments.AmountError):
                    payments.parse_amount(raw, "금액")

    def test_the_error_names_the_field_in_a_sentence(self):
        with self.assertRaises(payments.AmountError) as caught:
            payments.parse_amount(1.5, "현금")
        self.assertIn("현금", str(caught.exception))

    def test_quantities_are_whole_positive_and_bounded(self):
        self.assertEqual(payments.parse_qty(1), 1)
        self.assertEqual(payments.parse_qty("2"), 2)
        self.assertEqual(payments.parse_qty(payments.MAX_QTY), payments.MAX_QTY)
        for raw in (0, -1, 1.9, True, "1.5", None, "", payments.MAX_QTY + 1):
            with self.subTest(raw=raw):
                with self.assertRaises(payments.AmountError):
                    payments.parse_qty(raw)


class ReadPaymentTests(SimpleTestCase):
    def test_single_methods_read_received_amount(self):
        cash = payments.read_payment({"payment_method": "CASH", "received_amount": "5,000"})
        self.assertEqual((cash.method, cash.cash, cash.ticket), ("CASH", 5000, 0))
        ticket = payments.read_payment({"payment_method": "TICKET", "received_amount": 6000})
        self.assertEqual((ticket.method, ticket.cash, ticket.ticket), ("TICKET", 0, 6000))

    def test_single_methods_accept_their_own_field_and_check_it_against_the_total(self):
        """The screen sends both `received_cash_amount` and `received_amount`;
        tests and older callers send one or the other."""
        own = payments.read_payment({"payment_method": "CASH", "received_cash_amount": 8000})
        self.assertEqual((own.cash, own.ticket), (8000, 0))
        both = payments.read_payment({"payment_method": "CASH", "received_cash_amount": 8000,
                                      "received_amount": "8,000", "received_ticket_amount": 0})
        self.assertEqual((both.cash, both.ticket), (8000, 0))
        ticket = payments.read_payment({"payment_method": "TICKET", "received_ticket_amount": 6000})
        self.assertEqual((ticket.cash, ticket.ticket), (0, 6000))
        with self.assertRaises(payments.AmountError):
            payments.read_payment({"payment_method": "CASH", "received_cash_amount": 8000,
                                   "received_amount": 9000})

    def test_single_method_with_nothing_received_is_zero(self):
        cash = payments.read_payment({"payment_method": "CASH"})
        self.assertEqual((cash.cash, cash.ticket), (0, 0))

    def test_mixed_reads_both_fields_and_the_legacy_plus_string(self):
        explicit = payments.read_payment({
            "payment_method": "CASH_TICKET",
            "received_cash_amount": 3000, "received_ticket_amount": "2,000",
        })
        self.assertEqual((explicit.cash, explicit.ticket), (3000, 2000))
        legacy = payments.read_payment({"payment_method": "CASH_TICKET", "received_amount": "3000+2000"})
        self.assertEqual((legacy.cash, legacy.ticket), (3000, 2000))

    def test_mixed_needs_both_parts_above_zero(self):
        for payload in (
            {"payment_method": "CASH_TICKET", "received_cash_amount": 3000},
            {"payment_method": "CASH_TICKET", "received_cash_amount": 3000, "received_ticket_amount": 0},
            {"payment_method": "CASH_TICKET", "received_amount": "3000+"},
            {"payment_method": "CASH_TICKET", "received_amount": "3000"},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(payments.AmountError):
                    payments.read_payment(payload)

    def test_unknown_method_and_bad_numbers_are_refused(self):
        with self.assertRaises(payments.AmountError):
            payments.read_payment({"payment_method": "CARD", "received_amount": 5000})
        with self.assertRaises(payments.AmountError):
            payments.read_payment({"payment_method": "CASH", "received_amount": True})

    def test_method_defaults_to_cash_and_is_case_insensitive(self):
        self.assertEqual(payments.read_payment({"received_amount": 100}).method, "CASH")
        self.assertEqual(payments.read_payment({"payment_method": "ticket"}).method, "TICKET")


class SettlementTests(SimpleTestCase):
    def settle(self, method, cash, ticket, total):
        return payments.settle(payments.Payment(method, cash, ticket), total)

    def test_exact_cash_has_no_change(self):
        self.assertEqual(self.settle("CASH", 5000, 0, 5000), payments.Settlement(5000, 0))

    def test_short_payment_is_refused(self):
        for cash, ticket, total in ((0, 0, 5000), (4999, 0, 5000), (0, 4999, 5000), (2000, 2000, 5000)):
            with self.subTest(cash=cash, ticket=ticket):
                with self.assertRaises(payments.PaymentRefused):
                    self.settle("CASH_TICKET" if cash and ticket else "CASH", cash, ticket, total)

    def test_cash_surplus_is_change(self):
        self.assertEqual(self.settle("CASH", 10000, 0, 5000), payments.Settlement(10000, 5000))

    def test_ticket_surplus_is_not_change(self):
        self.assertEqual(self.settle("TICKET", 0, 6000, 5000), payments.Settlement(6000, 0))

    def test_mixed_returns_only_the_cash_beyond_what_tickets_left(self):
        self.assertEqual(self.settle("CASH_TICKET", 3000, 3000, 5000), payments.Settlement(6000, 1000))
        # Tickets already cover everything: every won of cash comes back.
        self.assertEqual(self.settle("CASH_TICKET", 1000, 6000, 5000), payments.Settlement(7000, 1000))

    def test_a_free_order_needs_nothing(self):
        self.assertEqual(self.settle("CASH", 0, 0, 0), payments.Settlement(0, 0))

    def test_the_total_is_bounded(self):
        with self.assertRaises(payments.AmountError):
            payments.order_total([(payments.MAX_AMOUNT, 2)])
        self.assertEqual(payments.order_total([(5000, 2), (1500, 1)]), 11500)


@override_settings(**AUTH_SETTINGS)
class OrderCreationMoneyTests(TestCase):
    """The rules above, as the order screen meets them."""

    def setUp(self):
        Table.objects.create(number=7)
        self.menu = MenuItem.objects.create(name="Meal", price=5000)
        login_client(self.client, "ORDER")

    def post(self, items=None, **money):
        payload = {
            "request_id": str(uuid.uuid4()),
            "floor": "B1", "order_type": "DINE_IN", "table_number": "7",
            "items": items if items is not None else [{"menu_item_id": self.menu.id, "qty": 1}],
            **money,
        }
        return self.client.post(reverse("orders:orders-collection"), payload,
                                content_type="application/json")

    def assertNothingSaved(self):
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertEqual(OrderRequest.objects.count(), 0)

    def test_short_payment_is_refused_and_nothing_is_saved(self):
        for money in (
            {"payment_method": "CASH", "received_cash_amount": 0},
            {"payment_method": "CASH", "received_cash_amount": 4999},
            {"payment_method": "CASH"},
            {"payment_method": "TICKET", "received_amount": 4000},
            {"payment_method": "CASH_TICKET", "received_cash_amount": 2000, "received_ticket_amount": 2000},
        ):
            with self.subTest(money=money):
                response = self.post(**money)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("합계보다 적습니다", response.content.decode())
                self.assertNothingSaved()

    def test_malformed_amounts_are_refused_not_truncated(self):
        for raw in (-1, 1.5, True, "1.9", "abc", 10 ** 9, [5000], "\u00b2", "9" * 5000):
            with self.subTest(raw=raw):
                response = self.post(payment_method="CASH", received_cash_amount=raw)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertNothingSaved()

    def test_malformed_quantities_are_refused_not_truncated(self):
        for qty in (0, -1, 1.9, True, "1.5", "", None, 100):
            with self.subTest(qty=qty):
                response = self.post(items=[{"menu_item_id": self.menu.id, "qty": qty}],
                                     payment_method="CASH", received_cash_amount=10 ** 7)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertNothingSaved()

    def test_mixed_without_both_parts_is_refused(self):
        response = self.post(payment_method="CASH_TICKET", received_cash_amount=5000, received_ticket_amount=0)
        self.assertEqual(response.status_code, 400)
        self.assertNothingSaved()

    def test_exact_and_surplus_cash_store_the_change(self):
        exact = self.post(payment_method="CASH", received_cash_amount=5000)
        self.assertEqual(exact.status_code, 201, exact.content)
        self.assertEqual(exact.json()["change_amount"], 0)
        surplus = self.post(payment_method="CASH", received_cash_amount=10000)
        self.assertEqual(surplus.status_code, 201, surplus.content)
        self.assertEqual(surplus.json()["change_amount"], 5000)
        stored = Order.objects.get(pk=surplus.json()["id"])
        self.assertEqual((stored.total_price, stored.received_cash_amount, stored.change_amount),
                         (5000, 10000, 5000))
        self.assertEqual(Order.objects.get(pk=exact.json()["id"]).change_amount, 0)

    def test_ticket_and_mixed_examples_match_the_contract(self):
        ticket = self.post(payment_method="TICKET", received_amount=6000)
        self.assertEqual(ticket.status_code, 201, ticket.content)
        body = ticket.json()
        self.assertEqual((body["received_ticket_amount"], body["received_cash_amount"], body["change_amount"]),
                         (6000, 0, 0))
        mixed = self.post(payment_method="CASH_TICKET", received_cash_amount=3000, received_ticket_amount=3000)
        self.assertEqual(mixed.status_code, 201, mixed.content)
        body = mixed.json()
        self.assertEqual((body["received_amount"], body["change_amount"]), (6000, 1000))
        legacy = self.post(payment_method="CASH_TICKET", received_amount="3000+3000")
        self.assertEqual(legacy.status_code, 201, legacy.content)
        self.assertEqual(legacy.json()["change_amount"], 1000)

    def test_the_total_is_the_servers_price_snapshot(self):
        """A client cannot send a total, and a later price change does not
        move an order that was already paid."""
        created = self.post(payment_method="CASH", received_cash_amount=5000, total_price=1)
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["total_price"], 5000)
        MenuItem.objects.filter(pk=self.menu.pk).update(price=9000)
        self.assertEqual(Order.objects.get(pk=created.json()["id"]).total_price, 5000)
        self.assertEqual(self.post(payment_method="CASH", received_cash_amount=5000).status_code, 400)
        self.assertEqual(self.post(payment_method="CASH", received_cash_amount=9000).status_code, 201)

    def test_an_absurd_total_is_refused(self):
        MenuItem.objects.filter(pk=self.menu.pk).update(price=payments.MAX_AMOUNT)
        response = self.post(items=[{"menu_item_id": self.menu.id, "qty": 2}],
                             payment_method="CASH", received_cash_amount=payments.MAX_AMOUNT)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertNothingSaved()

    def test_orders_written_before_7a_still_report_their_change(self):
        """Rows from before 0026 have no stored change; the API computes it
        the way it always did rather than showing 0."""
        table = Table.objects.get(number=7)
        with transaction.atomic():
            legacy = Order.objects.create(
                floor="B1", order_type="DINE_IN", table=table, payment_method="CASH",
                received_amount=10000, received_cash_amount=10000, total_price=5000,
                change_amount=None,
            )
            OrderItem.objects.create(order=legacy, menu_item=self.menu, qty=1, unit_price=5000)
        login_client(self.client, "STATS")
        detail = self.client.get(reverse("orders:order-detail", args=[legacy.id]))
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(detail.json()["change_amount"], 5000)

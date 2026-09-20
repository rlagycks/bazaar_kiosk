"""7C: old money records are read, counted and left alone (D-054).

D-037 says there is no past data to carry into the deployment, so this phase
does not restore anything. What is left is the shape: the split payment
fields have been nullable since 0017, the report has to interpret rows that
use the single `received_amount`, and nothing told an operator whether such
rows exist (BK-R007, BK-R031).

So: new orders stop producing that shape, a read-only survey says what a
database actually holds, and the detail view and the report are pinned to
read the old shapes the same way. No row is ever rewritten here.
"""

import uuid
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from orders.models import MenuItem, NumberSeries, Order, OrderItem, Table
from orders.services import legacy_audit, reporting
from orders.tests.auth_support import AUTH_SETTINGS, login_client
from orders.views import api

SEOUL = ZoneInfo("Asia/Seoul")
DAY = date(2026, 9, 19)


class LegacyFixture:
    """Rows in the shapes the schema has allowed since 0017."""

    def legacy_order(self, *, method="CASH", received=5000, cash=None, ticket=None,
                     change=None, total=5000, status="PREPARING"):
        order = Order.objects.create(
            table=self.table, floor="B1", order_type="DINE_IN", order_date=DAY, status=status,
            number_series=NumberSeries.REAL, total_price=total, payment_method=method,
            received_amount=received, received_cash_amount=cash, received_ticket_amount=ticket,
            change_amount=change,
        )
        Order.objects.filter(pk=order.pk).update(created_at=datetime.combine(DAY, time(12, 0), SEOUL))
        OrderItem.objects.create(order=order, menu_item=self.menu, qty=1, unit_price=total)
        return order


@override_settings(**AUTH_SETTINGS)
class NewOrdersAreNeverAmbiguousTests(TestCase):
    """The forward half: stop making rows that need interpreting."""

    def setUp(self):
        Table.objects.create(number=7)
        self.menu = MenuItem.objects.create(name="Meal", price=5000)
        self.free = MenuItem.objects.create(name="Water", price=0)
        login_client(self.client, "ORDER")

    def create(self, menu, **money):
        response = self.client.post(
            reverse("orders:orders-collection"),
            {"request_id": str(uuid.uuid4()), "floor": "B1", "order_type": "DINE_IN",
             "table_number": "7", "items": [{"menu_item_id": menu.id, "qty": 1}], **money},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        return Order.objects.get(pk=response.json()["id"])

    def test_every_money_field_is_a_number_not_an_absence(self):
        paid = self.create(self.menu, payment_method="CASH", received_cash_amount=5000)
        self.assertEqual(
            (paid.received_amount, paid.received_cash_amount, paid.received_ticket_amount, paid.change_amount),
            (5000, 5000, 0, 0),
        )
        ticket = self.create(self.menu, payment_method="TICKET", received_amount=6000)
        self.assertEqual(
            (ticket.received_amount, ticket.received_cash_amount, ticket.received_ticket_amount),
            (6000, 0, 6000),
        )

    def test_a_free_order_records_zero_received_not_unknown(self):
        """Zero received and nothing received are different claims; an order
        that cost nothing took nothing, and that is a number."""
        free = self.create(self.free, payment_method="CASH", received_cash_amount=0)
        self.assertEqual(
            (free.total_price, free.received_amount, free.received_cash_amount,
             free.received_ticket_amount, free.change_amount),
            (0, 0, 0, 0, 0),
        )
        self.assertEqual(legacy_audit.survey()["unsplit"]["count"], 0)

    def test_the_survey_of_a_database_of_new_orders_is_empty(self):
        self.create(self.menu, payment_method="CASH", received_cash_amount=10000)
        self.create(self.menu, payment_method="CASH_TICKET",
                    received_cash_amount=3000, received_ticket_amount=2000)
        survey = legacy_audit.survey()
        self.assertEqual(survey["orders"], 2)
        for key in ("unsplit", "mismatched"):
            self.assertEqual(survey[key]["count"], 0, key)
        self.assertEqual((survey["missing_total"], survey["no_change"]), (0, 0))
        self.assertFalse(survey["needs_attention"])


class LegacySurveyTests(LegacyFixture, TestCase):
    def setUp(self):
        self.table = Table.objects.create(number=7)
        self.menu = MenuItem.objects.create(name="Meal", price=5000)

    def test_single_method_rows_are_counted_as_interpretable(self):
        self.legacy_order(method="CASH", received=5000)
        self.legacy_order(method="TICKET", received=5000)
        survey = legacy_audit.survey()
        self.assertEqual((survey["unsplit"]["count"], survey["unsplit"]["amount"]), (2, 10000))
        self.assertEqual(survey["unsplit"]["interpretable"], {"count": 2, "amount": 10000})
        self.assertEqual(survey["unsplit"]["unattributed"], {"count": 0, "amount": 0})
        self.assertTrue(survey["needs_attention"])

    def test_mixed_rows_are_counted_as_unattributed(self):
        self.legacy_order(method="CASH_TICKET", received=5000)
        survey = legacy_audit.survey()
        self.assertEqual(survey["unsplit"]["unattributed"], {"count": 1, "amount": 5000})
        self.assertEqual(survey["unsplit"]["interpretable"], {"count": 0, "amount": 0})

    def test_a_split_that_disagrees_with_the_total_is_reported_with_the_gap(self):
        self.legacy_order(method="CASH", received=9000, cash=5000, ticket=0)
        survey = legacy_audit.survey()
        self.assertEqual(survey["mismatched"], {"count": 1, "difference": 4000})

    def test_missing_totals_and_missing_change_are_counted(self):
        self.legacy_order(method="CASH", received=None, cash=5000, ticket=0)
        self.legacy_order(method="CASH", received=5000, cash=5000, ticket=0, change=None)
        survey = legacy_audit.survey()
        self.assertEqual(survey["missing_total"], 1)
        self.assertEqual(survey["no_change"], 2)

    def test_the_survey_writes_nothing(self):
        order = self.legacy_order(method="CASH_TICKET", received=5000)
        before = Order.objects.values_list(
            "received_amount", "received_cash_amount", "received_ticket_amount",
            "change_amount", "total_price", "status",
        ).get(pk=order.pk)
        legacy_audit.survey()
        legacy_audit.survey()
        after = Order.objects.values_list(
            "received_amount", "received_cash_amount", "received_ticket_amount",
            "change_amount", "total_price", "status",
        ).get(pk=order.pk)
        self.assertEqual(before, after)
        self.assertEqual(Order.objects.count(), 1)

    def test_the_survey_is_one_query_however_many_orders_there_are(self):
        """The command runs against every order with no bound, so the cost has
        to stay flat (PR #72 code review)."""
        for _ in range(5):
            self.legacy_order(method="CASH_TICKET", received=5000)
        with self.assertNumQueries(1):
            legacy_audit.survey()

    def test_a_split_filled_on_one_side_only_is_still_compared(self):
        """One NULL side means that method took nothing. A total that does not
        match what the other side holds is a conflict, not an absence."""
        self.legacy_order(method="CASH", received=9000, cash=5000, ticket=None)
        survey = legacy_audit.survey()
        self.assertEqual(survey["mismatched"], {"count": 1, "difference": 4000})
        self.assertEqual(survey["unsplit"]["count"], 0)

    def test_one_side_null_is_counted_even_when_the_total_agrees(self):
        """The shape `api.py` wrote until this phase: a single-method order
        with the unused side NULL instead of zero. It reads correctly, so it
        is in no other bucket, and without a counter of its own a database
        full of pre-7C orders would report itself clean (PR #72 DB review)."""
        self.legacy_order(method="CASH", received=5000, cash=5000, ticket=None)
        self.legacy_order(method="TICKET", received=3000, cash=None, ticket=3000)
        self.legacy_order(method="CASH_TICKET", received=4000, cash=4000, ticket=None)
        survey = legacy_audit.survey()
        self.assertEqual(survey["half_split"], {"count": 3, "amount": 12000})
        self.assertEqual((survey["unsplit"]["count"], survey["mismatched"]["count"]), (0, 0))
        self.assertEqual(survey["missing_total"], 0)
        self.assertTrue(survey["needs_attention"])

    def test_a_fully_written_order_is_not_half_split(self):
        self.legacy_order(method="CASH", received=5000, cash=5000, ticket=0, change=0)
        self.assertEqual(legacy_audit.survey()["half_split"]["count"], 0)

    def test_amounts_near_the_column_ceiling_do_not_break_the_survey(self):
        """Two legal `PositiveIntegerField` values sum past int4. The audit
        has to survive one anomalous row rather than failing for every row;
        the 7A ceiling did not exist when these were written."""
        self.legacy_order(method="CASH_TICKET", received=5000,
                          cash=2_000_000_000, ticket=2_000_000_000, total=5000)
        survey = legacy_audit.survey()
        self.assertEqual(survey["mismatched"], {"count": 1, "difference": 3_999_995_000})

    def test_the_command_prints_the_survey_and_changes_nothing(self):
        from io import StringIO
        self.legacy_order(method="CASH", received=5000)
        self.legacy_order(method="CASH_TICKET", received=7000)
        out = StringIO()
        call_command("check_legacy_amounts", stdout=out)
        printed = out.getvalue()
        self.assertIn("2건", printed)          # the unsplit rows
        self.assertIn("7,000", printed)        # the unattributable money
        self.assertIn("고치지 않습니다", printed)  # it says so itself
        self.assertEqual(Order.objects.filter(received_cash_amount__isnull=True).count(), 2)

    def test_the_command_can_answer_in_json(self):
        from io import StringIO
        import json
        self.legacy_order(method="CASH", received=5000)
        out = StringIO()
        call_command("check_legacy_amounts", "--json", stdout=out)
        self.assertEqual(json.loads(out.getvalue())["unsplit"]["count"], 1)


@override_settings(**AUTH_SETTINGS)
class LegacyRowsReadTheSameEverywhereTests(LegacyFixture, TestCase):
    """The detail view and the report must not disagree about one row."""

    def setUp(self):
        login_client(self.client, "STATS")
        self.table = Table.objects.create(number=7)
        self.menu = MenuItem.objects.create(name="Meal", price=5000)

    def detail(self, order):
        response = self.client.get(reverse("orders:order-detail", args=[order.id]))
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def report(self):
        return reporting.dashboard(reporting.Period(DAY, DAY, "explicit"))

    def test_a_cash_row_reads_the_same_in_both(self):
        order = self.legacy_order(method="CASH", received=8000, total=5000)
        detail = self.detail(order)
        self.assertEqual((detail["received_cash_amount"], detail["received_ticket_amount"]), (8000, 0))
        self.assertEqual(detail["change_amount"], 3000)
        report = self.report()
        self.assertEqual((report["payment"]["cash"], report["payment"]["ticket"]), (8000, 0))
        self.assertEqual(report["payment"]["change"], 3000)
        self.assertEqual(report["payment"]["net_cash"], 5000)

    def test_a_ticket_row_reads_the_same_in_both(self):
        order = self.legacy_order(method="TICKET", received=6000, total=5000)
        detail = self.detail(order)
        self.assertEqual((detail["received_cash_amount"], detail["received_ticket_amount"]), (0, 6000))
        self.assertEqual(detail["change_amount"], 0)
        report = self.report()
        self.assertEqual((report["payment"]["ticket"], report["payment"]["change"]), (6000, 0))

    def test_a_mixed_row_is_zero_in_both_and_the_report_says_why(self):
        """Neither place invents a split. The report adds the one thing the
        detail cannot: how much money this affects."""
        order = self.legacy_order(method="CASH_TICKET", received=5000, total=5000)
        detail = self.detail(order)
        self.assertEqual((detail["received_cash_amount"], detail["received_ticket_amount"]), (0, 0))
        self.assertEqual(detail["received_amount"], 5000)
        report = self.report()
        self.assertEqual((report["payment"]["cash"], report["payment"]["ticket"]), (0, 0))
        self.assertEqual(report["summary"]["revenue"], 5000)
        self.assertEqual(
            (report["summary"]["unattributed_orders"], report["summary"]["unattributed_amount"]),
            (1, 5000),
        )

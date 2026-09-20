"""D-047: what an order number means, and what makes one a practice number.

This service runs one day a year. Daily resets were therefore meaningless, and
the real damage was the opposite one: rehearsal and development orders spent
the numbers the event itself would hand out. The contract these tests pin:

* a registered event day gives real numbers, starting at 1 each year;
* every other day gives practice numbers from a separate series;
* the two series never collide and never consume one another's numbers;
* a rolled-back order does not burn a number (the sequence used to).

Numbering runs inside the order-creating transaction, so the concurrency cases
use TransactionTestCase and real threads: an outer test transaction would hide
exactly the row lock that makes allocation safe.
"""

import threading
import uuid
from datetime import date
from unittest.mock import patch

from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from orders.models import (
    EventDay,
    MenuItem,
    NumberSeries,
    Order,
    OrderItem,
    OrderNumberCounter,
    Table,
)
from orders.services import allocate_floor_order_no
from orders.services import numbering
from orders.views import api
from orders.tests.auth_support import AUTH_SETTINGS, login_client

EVENT_DAY = date(2026, 10, 17)
SECOND_EVENT_DAY = date(2026, 10, 18)
NEXT_YEAR_EVENT_DAY = date(2027, 10, 16)
ORDINARY_DAY = date(2026, 5, 2)


class NumberingFixture:
    """Order rows created directly: allocation is the unit under test."""

    def setUp(self):
        super().setUp()
        self.table = Table.objects.create(number=3)

    def blank_order(self, floor="B1"):
        return Order.objects.create(
            table=self.table, floor=floor, order_type="DINE_IN",
            total_price=1000, payment_method="CASH",
        )

    def allocate_on(self, day, *, floor="B1"):
        """Allocate as if `day` were today."""
        order = self.blank_order(floor=floor)
        with transaction.atomic():
            with patch_today(day):
                allocate_floor_order_no(order)
        order.refresh_from_db()
        return order


def patch_today(day):
    return patch("orders.services.numbering.timezone.localdate", return_value=day)


class SeriesSelectionTests(NumberingFixture, TestCase):
    def test_a_registered_event_day_numbers_from_one(self):
        EventDay.objects.create(date=EVENT_DAY)
        first = self.allocate_on(EVENT_DAY)
        second = self.allocate_on(EVENT_DAY)
        self.assertEqual(
            [(first.number_series, first.order_no), (second.number_series, second.order_no)],
            [(NumberSeries.REAL, 1), (NumberSeries.REAL, 2)],
        )
        self.assertEqual(first.order_date, EVENT_DAY)

    def test_an_unregistered_day_falls_to_the_practice_series(self):
        order = self.allocate_on(ORDINARY_DAY)
        self.assertEqual(order.number_series, NumberSeries.PRACTICE)
        self.assertEqual(order.order_no, 1)

    def test_practice_orders_do_not_spend_real_numbers(self):
        """The whole point: rehearse all week, the event still opens at 1."""
        for _ in range(5):
            self.allocate_on(ORDINARY_DAY)
        EventDay.objects.create(date=EVENT_DAY)
        self.assertEqual(self.allocate_on(EVENT_DAY).order_no, 1)

    def test_a_second_event_day_in_the_same_year_continues(self):
        EventDay.objects.create(date=EVENT_DAY)
        EventDay.objects.create(date=SECOND_EVENT_DAY)
        self.allocate_on(EVENT_DAY)
        self.allocate_on(EVENT_DAY)
        self.assertEqual(self.allocate_on(SECOND_EVENT_DAY).order_no, 3)

    def test_the_next_year_starts_at_one_again(self):
        EventDay.objects.create(date=EVENT_DAY)
        EventDay.objects.create(date=NEXT_YEAR_EVENT_DAY)
        self.allocate_on(EVENT_DAY)
        self.allocate_on(EVENT_DAY)
        later = self.allocate_on(NEXT_YEAR_EVENT_DAY)
        self.assertEqual(later.order_no, 1)
        self.assertEqual(later.number_series, NumberSeries.REAL)

    def test_each_floor_counts_separately(self):
        EventDay.objects.create(date=EVENT_DAY)
        self.allocate_on(EVENT_DAY, floor="B1")
        self.assertEqual(
            OrderNumberCounter.objects.get(
                series=NumberSeries.REAL, year=EVENT_DAY.year, floor="B1"
            ).last_no,
            1,
        )


class UniquenessTests(NumberingFixture, TestCase):
    def test_the_same_number_twice_in_one_series_and_year_is_refused(self):
        EventDay.objects.create(date=EVENT_DAY)
        self.allocate_on(EVENT_DAY)
        duplicate = self.blank_order()
        with self.assertRaises(IntegrityError):
            Order.objects.filter(pk=duplicate.pk).update(
                order_no=1, order_date=EVENT_DAY, number_series=NumberSeries.REAL
            )

    def test_the_two_series_may_share_a_number_on_the_same_day(self):
        EventDay.objects.create(date=EVENT_DAY)
        real = self.allocate_on(EVENT_DAY)
        practice = self.blank_order()
        Order.objects.filter(pk=practice.pk).update(
            order_no=1, order_date=EVENT_DAY, number_series=NumberSeries.PRACTICE
        )
        practice.refresh_from_db()
        self.assertEqual((real.order_no, practice.order_no), (1, 1))

    def test_allocation_skips_a_number_already_taken_by_an_imported_row(self):
        """A counter that has not seen existing rows must not hand out a
        number those rows already hold."""
        EventDay.objects.create(date=EVENT_DAY)
        existing = self.blank_order()
        Order.objects.filter(pk=existing.pk).update(
            order_no=5, order_date=EVENT_DAY, number_series=NumberSeries.REAL
        )
        self.assertEqual(self.allocate_on(EVENT_DAY).order_no, 6)


@override_settings(**AUTH_SETTINGS)
class AllocationUnderConcurrencyTests(NumberingFixture, TransactionTestCase):
    """Real transactions: the row lock is the whole safety argument."""

    def test_a_rolled_back_order_does_not_burn_a_number(self):
        """The old sequence advanced on rollback, so a failed order left a
        hole in the printed numbers. Numbers are now gap-free."""
        EventDay.objects.create(date=EVENT_DAY)
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                order = self.blank_order()
                with patch_today(EVENT_DAY):
                    allocate_floor_order_no(order)
                raise RuntimeError("synthetic failure after allocation")
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.allocate_on(EVENT_DAY).order_no, 1)

    def test_two_concurrent_allocations_get_different_numbers(self):
        """Distinct numbers, and without falling back on conflict recovery.

        The unique constraint alone would also produce distinct numbers: a
        loser would collide, resync and retry. That is the repair path for rows
        written outside this function, not the normal one, so the test watches
        it -- removing the row lock makes this fail rather than pass quietly.
        """
        EventDay.objects.create(date=EVENT_DAY)
        # One order first, so the counter row exists: otherwise both threads
        # race on creating it and the unique index serialises them by accident,
        # which would hide a missing row lock.
        self.assertEqual(self.allocate_on(EVENT_DAY).order_no, 1)
        start = threading.Barrier(2)
        numbers = []
        errors = []
        resyncs = []
        real_resync = numbering._resync

        def watched_resync(*args, **kwargs):
            resyncs.append(args)
            return real_resync(*args, **kwargs)

        def allocate():
            try:
                order = self.blank_order()
                start.wait(timeout=5)
                with transaction.atomic():
                    with patch_today(EVENT_DAY):
                        allocate_floor_order_no(order)
                order.refresh_from_db()
                numbers.append(order.order_no)
            except Exception as exc:  # surfaced below, not swallowed
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=allocate) for _ in range(2)]
        with patch.object(numbering, "_resync", watched_resync):
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=20)
        self.assertEqual(errors, [])
        self.assertEqual(sorted(numbers), [2, 3])
        self.assertEqual(resyncs, [], "allocation collided instead of serialising")


@override_settings(**AUTH_SETTINGS)
class OrderApiNumberingTests(TestCase):
    """End to end: what the counter screen actually creates."""

    def setUp(self):
        self.table = Table.objects.create(number=4)
        self.menu = MenuItem.objects.create(name="Bowl", price=8000)
        login_client(self.client, "ORDER")

    def create_order(self):
        response = self.client.post(
            reverse("orders:orders-collection"),
            {
                "request_id": str(uuid.uuid4()),
                "floor": "B1", "order_type": "DINE_IN", "table_number": "4",
                "payment_method": "CASH", "received_cash_amount": 8000,
                "items": [{"menu_item_id": self.menu.id, "qty": 1}],
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_an_order_outside_an_event_day_is_marked_practice(self):
        data = self.create_order()
        self.assertEqual(data["number_series"], NumberSeries.PRACTICE)
        self.assertTrue(data["is_practice"])

    def test_an_order_on_a_registered_event_day_is_real(self):
        from django.utils import timezone

        EventDay.objects.create(date=timezone.localdate())
        data = self.create_order()
        self.assertEqual(data["number_series"], NumberSeries.REAL)
        self.assertFalse(data["is_practice"])
        self.assertEqual(data["order_no"], 1)

    def test_the_kitchen_still_sees_a_practice_order(self):
        """Practice orders leave the sales figures alone but must still reach
        the kitchen: rehearsal is the reason they exist."""
        created = self.create_order()
        login_client(self.client, "KITCHEN")
        response = self.client.get(reverse("orders:orders-collection"))
        self.assertEqual(response.status_code, 200)
        listed = {order["id"]: order for order in response.json()["results"]}
        self.assertIn(created["id"], listed)
        self.assertTrue(listed[created["id"]]["is_practice"])


@override_settings(**AUTH_SETTINGS)
class PracticeOrdersLeaveSalesAloneTests(TestCase):
    """D-047: practice orders are excluded from revenue and menu totals.

    8C (D-053) decides the period; these rows are created on one day and the
    report is asked for that day explicitly.
    """

    period = date(2025, 10, 18)

    def setUp(self):
        self.table = Table.objects.create(number=5)
        self.menu = MenuItem.objects.create(name="Bowl", price=1000)
        login_client(self.client, "B1_COUNTER")

    def make_order(self, series, *, status="PREPARING"):
        order = Order.objects.create(
            table=self.table, floor="B1", order_type="DINE_IN",
            order_date=self.period, status=status, number_series=series,
            total_price=1000, payment_method="CASH",
            received_amount=1000, received_cash_amount=1000, received_ticket_amount=0,
        )
        OrderItem.objects.create(order=order, menu_item=self.menu, qty=1, unit_price=1000)
        return order

    def dashboard(self):
        response = self.client.get(reverse("orders:stats-dashboard"), {
            "floor": "B1", "start_date": self.period.isoformat(), "end_date": self.period.isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # These tests are about the series, not about 8C's added counts.
        data["summary"] = {k: v for k, v in data["summary"].items() if k in ("orders", "items", "revenue")}
        data["menu"] = [{k: v for k, v in row.items() if k != "menu_item_id"} for row in data["menu"]]
        return data

    def test_a_practice_order_adds_nothing_to_the_totals(self):
        self.make_order(NumberSeries.PRACTICE)
        data = self.dashboard()
        self.assertEqual(data["summary"], {"orders": 0, "items": 0, "revenue": 0})
        self.assertEqual(data["menu"], [])
        self.assertEqual(data["payment"]["cash"], 0)
        self.assertEqual(data["hourly"], [])

    def test_a_real_order_beside_it_still_counts_once(self):
        self.make_order(NumberSeries.PRACTICE)
        self.make_order(NumberSeries.REAL)
        data = self.dashboard()
        self.assertEqual(data["summary"], {"orders": 1, "items": 1, "revenue": 1000})
        self.assertEqual(data["menu"], [{"name": "Bowl", "qty": 1, "amount": 1000}])


@override_settings(**AUTH_SETTINGS)
class EventDayWarningTests(TestCase):
    """The failure mode of this design is forgetting to register the day: every
    order then quietly becomes practice. The screens say so."""

    def test_the_order_screen_warns_when_today_is_not_registered(self):
        login_client(self.client, "ORDER")
        response = self.client.get(reverse("orders:order"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["is_event_day"])
        self.assertContains(response, "연습")

    def test_the_warning_is_gone_on_a_registered_day(self):
        from django.utils import timezone

        EventDay.objects.create(date=timezone.localdate())
        login_client(self.client, "ORDER")
        response = self.client.get(reverse("orders:order"))
        self.assertTrue(response.context["is_event_day"])

    def test_the_counter_screen_carries_the_same_flag(self):
        login_client(self.client, "B1_COUNTER")
        response = self.client.get(reverse("orders:b1-counter"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["is_event_day"])


class EventDayAdminTests(TestCase):
    def test_event_days_are_editable_in_the_admin(self):
        """The registry is the operator's control; it has to be reachable."""
        from django.contrib import admin

        self.assertIn(EventDay, admin.site._registry)

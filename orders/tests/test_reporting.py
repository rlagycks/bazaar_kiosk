"""8C: the sales figures agree with arithmetic done by hand.

Cancelled orders and rehearsals are not revenue (D-047/D-048). Cash is what
was handed over; the till keeps cash minus change (7A stores it). Menu lines
are grouped by menu id, so two different items that happen to share a name
are two rows (BK-R034). Rows from before the split payment fields are read
the way the order detail already reads them, and counted so the operator
knows how many the report had to interpret (D-012 stays open).
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.urls import reverse

from orders.models import MenuItem, NumberSeries, Order, OrderItem, Table
from orders.tests.auth_support import AUTH_SETTINGS, login_client

SEOUL = ZoneInfo("Asia/Seoul")
DAY = date(2026, 9, 19)


@override_settings(**AUTH_SETTINGS)
class DashboardArithmeticTests(TestCase):
    def setUp(self):
        login_client(self.client, "STATS")
        self.table = Table.objects.create(number=7)
        self.meal = MenuItem.objects.create(name="Meal", price=5000)
        self.soup = MenuItem.objects.create(name="Soup", price=2000)

    def order(self, lines, *, status="PREPARING", method="CASH", cash=None, ticket=None,
              change=None, received=None, at=time(12, 30), series=NumberSeries.REAL):
        total = sum(qty * price for _, qty, price in lines)
        # A row from before the split fields passes `received` alone and keeps
        # cash/ticket NULL; every other row gets the split filled in.
        if received is None and cash is None and ticket is None:
            cash, ticket = (total, 0) if method == "CASH" else (0, total)
        order = Order.objects.create(
            table=self.table, floor="B1", order_type="DINE_IN", order_date=DAY, status=status,
            number_series=series, total_price=total, payment_method=method,
            received_amount=received if received is not None else (cash or 0) + (ticket or 0),
            received_cash_amount=cash, received_ticket_amount=ticket, change_amount=change,
        )
        Order.objects.filter(pk=order.pk).update(created_at=datetime.combine(DAY, at, SEOUL))
        for menu, qty, price in lines:
            OrderItem.objects.create(order=order, menu_item=menu, qty=qty, unit_price=price)
        return order

    def dashboard(self, **params):
        params.setdefault("start_date", DAY.isoformat())
        response = self.client.get(reverse("orders:stats-dashboard"), params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_totals_are_the_sum_of_the_lines_and_the_stored_money(self):
        self.order([(self.meal, 2, 5000), (self.soup, 1, 2000)], cash=15000, change=3000)
        self.order([(self.soup, 3, 2000)], method="TICKET", ticket=6000, change=0)
        data = self.dashboard()
        self.assertEqual(data["summary"], {"orders": 2, "items": 6, "revenue": 18000,
                                           "cancelled_orders": 0, "legacy_unsplit_orders": 0})
        self.assertEqual(data["payment"], {
            "cash": 15000, "ticket": 6000, "change": 3000, "net_cash": 12000,
            "cash_ratio": 15000 / 21000, "ticket_ratio": 6000 / 21000,
        })

    def test_cancelled_orders_leave_every_figure_and_are_counted_aside(self):
        self.order([(self.meal, 1, 5000)])
        self.order([(self.meal, 4, 5000)], status="CANCELLED")
        data = self.dashboard()
        self.assertEqual(data["summary"], {"orders": 1, "items": 1, "revenue": 5000,
                                           "cancelled_orders": 1, "legacy_unsplit_orders": 0})
        self.assertEqual(data["payment"]["cash"], 5000)
        self.assertEqual(data["menu"], [{"menu_item_id": self.meal.id, "name": "Meal", "qty": 1, "amount": 5000}])
        self.assertEqual(data["hourly"], [{"hour": "12:00", "orders": 1, "revenue": 5000}])

    def test_menu_rows_are_by_id_not_by_name(self):
        other_meal = MenuItem.objects.create(name="Meal", price=7000)
        self.order([(self.meal, 1, 5000), (other_meal, 2, 7000)])
        data = self.dashboard()
        self.assertEqual(data["menu"], [
            {"menu_item_id": other_meal.id, "name": "Meal", "qty": 2, "amount": 14000},
            {"menu_item_id": self.meal.id, "name": "Meal", "qty": 1, "amount": 5000},
        ])

    def test_a_renamed_menu_keeps_its_row_and_shows_the_current_name(self):
        """The line keeps the price it was sold at; the name is the menu's
        current one because no name snapshot exists yet (D-008 open)."""
        self.order([(self.meal, 1, 5000)])
        MenuItem.objects.filter(pk=self.meal.pk).update(name="Big Meal", price=9000)
        data = self.dashboard()
        self.assertEqual(data["menu"], [{"menu_item_id": self.meal.id, "name": "Big Meal", "qty": 1, "amount": 5000}])
        self.assertEqual(data["summary"]["revenue"], 5000)

    def test_rows_without_split_payment_fields_are_read_like_the_order_detail(self):
        """Before the split fields, one `received_amount` carried the payment.
        Cash for a CASH order, ticket for a TICKET order, and change derived
        the same way the detail view derives it."""
        self.order([(self.meal, 1, 5000)], cash=None, ticket=None, received=10000, change=None)
        self.order([(self.soup, 1, 2000)], method="TICKET", cash=None, ticket=None, received=2000, change=None)
        self.order([(self.soup, 1, 2000)], cash=3000, ticket=0, change=1000)
        data = self.dashboard()
        self.assertEqual(data["summary"]["legacy_unsplit_orders"], 2)
        self.assertEqual(data["payment"], {
            "cash": 13000, "ticket": 2000, "change": 6000, "net_cash": 7000,
            "cash_ratio": 13000 / 15000, "ticket_ratio": 2000 / 15000,
        })

    def test_an_empty_period_is_all_zeros(self):
        data = self.dashboard()
        self.assertEqual(data["summary"], {"orders": 0, "items": 0, "revenue": 0,
                                           "cancelled_orders": 0, "legacy_unsplit_orders": 0})
        self.assertEqual(data["payment"], {"cash": 0, "ticket": 0, "change": 0, "net_cash": 0,
                                           "cash_ratio": 0.0, "ticket_ratio": 0.0})
        self.assertEqual((data["menu"], data["hourly"]), ([], []))

    def test_floor_filter_is_validated(self):
        self.assertEqual(self.client.get(reverse("orders:stats-dashboard"), {"floor": "F9"}).status_code, 400)
        self.assertEqual(self.dashboard(floor="B1")["period"]["floor"], "B1")

    def test_only_stats_may_read_the_report(self):
        login_client(self.client, "BOTH_MONITORS")
        response = self.client.get(reverse("orders:stats-dashboard"), {"start_date": DAY.isoformat()})
        self.assertEqual(response.status_code, 403)

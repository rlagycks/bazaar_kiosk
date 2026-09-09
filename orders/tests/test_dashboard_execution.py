"""BK-R016: restore dashboard execution without deciding reporting policy.

The fixed period and grouping by current menu name are existing behavior, not
newly approved contracts. D-012/013 and BK-R034 remain separate work.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.urls import reverse

from orders.models import MenuItem, Order, OrderItem, Table


class DashboardExecutionTests(TestCase):
    period = date(2025, 10, 18)

    def setUp(self):
        # Use the existing counter role without locking anonymous API access in
        # as a supported contract; endpoint authorization belongs to phase 3.
        session = self.client.session
        session["role"] = "B1_COUNTER"
        session.save()
        self.table = Table.objects.create(number=7)

    def make_order(self, lines, *, status="PREPARING", order_date=None):
        total = sum(qty * price for _, qty, price in lines)
        order = Order.objects.create(
            table=self.table, floor="B1", order_type="DINE_IN",
            order_date=order_date or self.period, status=status,
            total_price=total, payment_method="CASH",
            received_amount=total, received_cash_amount=total,
            received_ticket_amount=0,
        )
        Order.objects.filter(pk=order.pk).update(
            created_at=datetime(2025, 10, 18, 12, 30, tzinfo=ZoneInfo("Asia/Seoul"))
        )
        for menu, qty, price in lines:
            OrderItem.objects.create(
                order=order, menu_item=menu, qty=qty, unit_price=price,
            )
        return order

    def dashboard(self):
        response = self.client.get(reverse("orders:stats-dashboard"), {"floor": "B1"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(set(data), {"period", "summary", "payment", "menu", "hourly"})
        self.assertEqual(data["period"], {
            "start_date": "2025-10-18", "end_date": "2025-10-18", "floor": "B1",
        })
        return data

    def test_empty_dashboard_returns_zero_totals_and_empty_groups(self):
        data = self.dashboard()
        self.assertEqual(data["summary"], {"orders": 0, "items": 0, "revenue": 0})
        self.assertEqual(data["payment"], {
            "cash": 0, "ticket": 0, "cash_ratio": 0.0, "ticket_ratio": 0.0,
        })
        self.assertEqual(data["menu"], [])
        self.assertEqual(data["hourly"], [])

    def test_single_line_uses_order_item_price_snapshot(self):
        menu = MenuItem.objects.create(name="Meal", price=9900)
        self.make_order([(menu, 3, 1700)])
        data = self.dashboard()
        self.assertEqual(data["summary"], {"orders": 1, "items": 3, "revenue": 5100})
        self.assertEqual(data["menu"], [{"name": "Meal", "qty": 3, "amount": 5100}])
        self.assertEqual(data["payment"], {
            "cash": 5100, "ticket": 0, "cash_ratio": 1.0, "ticket_ratio": 0.0,
        })
        self.assertEqual(data["hourly"], [{"hour": "12:00", "orders": 1, "revenue": 5100}])

    def test_multiple_rows_sum_each_line_before_grouping_and_preserve_qty_key(self):
        meal = MenuItem.objects.create(name="Meal", price=4300)
        side = MenuItem.objects.create(name="Side", price=1700)
        self.make_order([(meal, 2, 4300), (side, 4, 1700)])
        self.make_order([(meal, 1, 5000)], status="READY")
        data = self.dashboard()
        self.assertEqual(data["summary"], {"orders": 2, "items": 7, "revenue": 20400})
        self.assertEqual(data["menu"], [
            {"name": "Side", "qty": 4, "amount": 6800},
            {"name": "Meal", "qty": 3, "amount": 13600},
        ])
        self.assertEqual(data["hourly"], [{"hour": "12:00", "orders": 2, "revenue": 20400}])

    def test_cancelled_and_outside_current_period_rows_do_not_enter_totals(self):
        menu = MenuItem.objects.create(name="Meal", price=1000)
        self.make_order([(menu, 2, 1000)])
        self.make_order([(menu, 50, 1000)], status="CANCELLED")
        self.make_order([(menu, 70, 1000)], order_date=date(2025, 10, 19))
        data = self.dashboard()
        self.assertEqual(data["summary"], {"orders": 1, "items": 2, "revenue": 2000})
        self.assertEqual(data["menu"], [{"name": "Meal", "qty": 2, "amount": 2000}])
        self.assertEqual(data["payment"]["cash"], 2000)
        self.assertEqual(data["hourly"], [{"hour": "12:00", "orders": 1, "revenue": 2000}])

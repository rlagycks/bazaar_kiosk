"""BK-R016: restore dashboard execution without deciding reporting policy.

The fixed period and grouping by current menu name are existing behavior, not
newly approved contracts. D-012/013 and BK-R034 remain separate work.
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.urls import reverse

from orders.models import MenuItem, Order, OrderItem, Table


class DashboardExecutionTests(TestCase):
    period = date(2025, 10, 18)

    def setUp(self):
        # Use the existing counter role without locking anonymous API access in
        # as a supported contract. This setup does not prove authorization;
        # the endpoint does not check the session yet (phase 3).
        session = self.client.session
        session["role"] = "B1_COUNTER"
        session.save()
        self.table = Table.objects.create(number=7)

    def make_order(self, lines, *, status="PREPARING", order_date=None):
        order_date = order_date or self.period
        total = sum(qty * price for _, qty, price in lines)
        order = Order.objects.create(
            table=self.table, floor="B1", order_type="DINE_IN",
            order_date=order_date, status=status,
            total_price=total, payment_method="CASH",
            received_amount=total, received_cash_amount=total,
            received_ticket_amount=0,
        )
        Order.objects.filter(pk=order.pk).update(
            created_at=datetime.combine(order_date, time(12, 30), ZoneInfo("Asia/Seoul"))
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
        # Temporary characterization: update with the approved reporting policy
        # in phase 8C, rather than treating the hardcoded date as a target rule.
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

    def test_menu_orders_by_total_qty_then_name_for_ties(self):
        # Insertion, name ASC/DESC, and quantity order must all differ.
        # Several tied groups also exercise a larger result sort: a tiny set
        # can accidentally retain name order even with no SQL tie-breaker.
        quantities = {"Zulu": 3, "Omega": 1, "Alpha": 3, "Mike": 5}
        quantities.update({f"Menu{i:02}": 1 + i % 3 for i in range(24)})
        lines = []
        for name, qty in quantities.items():
            menu = MenuItem.objects.create(name=name, price=1000)
            lines.append((menu, qty, 1000))
        self.make_order(lines)
        expected = [
            {"name": name, "qty": qty, "amount": qty * 1000}
            for name, qty in sorted(quantities.items(), key=lambda row: (-row[1], row[0]))
        ]
        self.assertEqual(self.dashboard()["menu"], expected)

    def test_invalid_floor_returns_bad_request(self):
        for floor in ("F1", "BOOTH", "unknown"):
            with self.subTest(floor=floor):
                response = self.client.get(reverse("orders:stats-dashboard"), {"floor": floor})
                self.assertEqual(response.status_code, 400)

    def test_legacy_null_prices_count_qty_but_only_known_amounts(self):
        unknown = MenuItem.objects.create(name="Unknown", price=9000)
        mixed = MenuItem.objects.create(name="Mixed", price=9000)
        legacy = self.make_order([(unknown, 4, 1000), (mixed, 5, 1000)])
        # Model save fills in a missing price. Use UPDATE to represent existing
        # nullable legacy rows without changing the creation/payment policy.
        legacy.items.update(unit_price=None)
        self.make_order([(mixed, 2, 1000)])
        data = self.dashboard()
        self.assertEqual(data["summary"]["items"], 11)
        self.assertEqual(data["menu"], [
            {"name": "Mixed", "qty": 7, "amount": 2000},
            {"name": "Unknown", "qty": 4, "amount": 0},
        ])

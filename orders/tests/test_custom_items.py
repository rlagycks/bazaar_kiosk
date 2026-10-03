"""D-073: custom ("기타") lines entered on the serving screen.

The serving screen can sell what the menu does not list, or a menu dish at a
price agreed on the spot: a name, a quantity and the amount for the whole
line ("삼계탕 3개 2만원"). A name that is a menu's name ties the line to that
menu when it is taken, so the sales report shows it inside the menu's row.
The monitor sees it like any other line. The admin cannot edit one, only
delete it or enter a new one.
"""

import uuid
from datetime import date

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from orders.models import MenuItem, NumberSeries, Order, OrderItem, OrderRequest, Table
from orders.services import custom_items
from orders.tests.auth_support import AUTH_SETTINGS, login_client


def custom(name="삼계탕", qty=3, amount=20000, **extra):
    return {"custom_name": name, "qty": qty, "line_amount": amount, **extra}


@override_settings(**AUTH_SETTINGS)
class CustomLineCreationTests(TestCase):
    def setUp(self):
        Table.objects.create(number=7)
        self.soup = MenuItem.objects.create(name="삼계탕", price=10000)
        login_client(self.client, "ORDER")

    def post(self, items, *, cash=50000, request_id=None, **extra):
        payload = {
            "request_id": request_id or str(uuid.uuid4()),
            "floor": "B1", "order_type": "DINE_IN", "table_number": "7",
            "payment_method": "CASH", "received_cash_amount": cash,
            "items": items, **extra,
        }
        return self.client.post(reverse("orders:orders-collection"), payload,
                                content_type="application/json")

    def assertNothingSaved(self):
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertEqual(OrderRequest.objects.count(), 0)

    def test_a_custom_line_costs_its_line_total_and_ties_to_the_menu_by_name(self):
        response = self.post([{"menu_item_id": self.soup.id, "qty": 1}, custom(" 삼계 탕 ")], cash=30000)
        self.assertEqual(response.status_code, 201, response.content)
        order = Order.objects.get()
        self.assertEqual((order.total_price, order.change_amount), (30000, 0))
        line = order.items.get(line_amount__isnull=False)
        self.assertEqual((line.menu_item, line.custom_name, line.qty, line.line_amount, line.unit_price),
                         (self.soup, "삼계 탕", 3, 20000, None))
        body = response.json()["items"][1]
        self.assertEqual((body["menu_item_name"], body["is_custom"], body["line_total"], body["menu_item"]["id"]),
                         ("삼계 탕", True, 20000, self.soup.id))
        self.assertFalse(response.json()["items"][0]["is_custom"])

    def test_an_unknown_name_is_kept_without_a_menu(self):
        response = self.post([custom("떡꼬치", 2, 5000)])
        self.assertEqual(response.status_code, 201, response.content)
        line = OrderItem.objects.get()
        self.assertIsNone(line.menu_item)
        self.assertEqual(response.json()["items"][0]["menu_item"]["id"], None)
        self.assertEqual(response.json()["items"][0]["menu_item_name"], "떡꼬치")

    def test_a_name_two_active_menus_share_ties_to_neither(self):
        MenuItem.objects.create(name="삼계탕", price=12000)
        self.assertEqual(self.post([custom()]).status_code, 201)
        self.assertIsNone(OrderItem.objects.get().menu_item)

    def test_an_active_menu_wins_over_a_retired_one_of_the_same_name(self):
        self.soup.is_active = False
        self.soup.save()
        current = MenuItem.objects.create(name="삼계탕", price=12000)
        self.assertEqual(self.post([custom()]).status_code, 201)
        self.assertEqual(OrderItem.objects.get().menu_item, current)

    def test_a_free_custom_line_is_allowed(self):
        response = self.post([custom("서비스 김치", 1, 0)], cash=0)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Order.objects.get().total_price, 0)

    def test_the_payment_must_cover_the_custom_total(self):
        response = self.post([custom()], cash=19999)
        self.assertEqual(response.status_code, 400)
        self.assertIn("합계보다 적습니다", response.content.decode())
        self.assertNothingSaved()

    def test_malformed_custom_lines_are_refused_and_nothing_is_saved(self):
        cases = (
            (custom(name="   "), "품목명"),
            (custom(name=5), "품목명"),
            (custom(name="가" * 101), "100자"),
            ({"custom_name": "떡", "qty": 1}, "금액"),
            (custom(amount=-1), "0 이상"),
            (custom(amount=1.5), "올바르지 않습니다"),
            (custom(qty=0), "수량"),
            (custom(menu_item_id=1), "함께"),
        )
        for row, message in cases:
            with self.subTest(row=row):
                response = self.post([row])
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn(message, response.content.decode())
                self.assertNothingSaved()

    def test_a_retry_replays_and_a_changed_amount_is_a_different_attempt(self):
        key = str(uuid.uuid4())
        first = self.post([custom()], request_id=key)
        again = self.post([custom()], request_id=key)
        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(first.json()["id"], again.json()["id"])
        changed = self.post([custom(amount=25000)], request_id=key)
        self.assertEqual(changed.status_code, 409, changed.content)
        self.assertEqual(Order.objects.count(), 1)

    def test_the_monitor_sees_and_prepares_a_custom_line(self):
        order_id = self.post([custom("떡꼬치", 2, 5000)]).json()["id"]
        monitor = self.client_class()
        login_client(monitor, "HALL_MONITOR")
        queue = monitor.get(reverse("orders:orders-collection"), {"status": "PREPARING"}).json()
        line = queue["results"][0]["items"][0]
        self.assertEqual((line["menu_item_name"], line["qty"], line["remaining_qty"]), ("떡꼬치", 2, 2))
        response = monitor.patch(
            reverse("orders:monitor-order-action", args=[order_id]),
            {"action": "progress", "expected_version": queue["results"][0]["monitor_version"],
             "items": [{"id": line["id"], "prepared_qty": 2}]},
            content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(OrderItem.objects.get().prepared_qty, 2)


class CustomLineConstraintTests(TestCase):
    def setUp(self):
        table = Table.objects.create(number=7)
        self.order = Order.objects.create(table=table, floor="B1", order_type="DINE_IN")

    def test_a_line_is_either_a_menu_line_or_a_custom_line(self):
        menu = MenuItem.objects.create(name="Meal", price=5000)
        refused = (
            {"qty": 1},                                                  # nothing
            {"qty": 1, "custom_name": "떡"},                             # no amount
            {"qty": 1, "line_amount": 1000},                             # no name
            {"qty": 1, "menu_item": menu, "custom_name": "떡"},          # half custom
        )
        for fields in refused:
            with self.subTest(fields=fields):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    OrderItem.objects.create(order=self.order, **fields)
        OrderItem.objects.create(order=self.order, qty=1, custom_name="떡", line_amount=0)
        OrderItem.objects.create(order=self.order, qty=1, menu_item=menu, custom_name="Meal", line_amount=0)


class NameMatchingTests(TestCase):
    def test_only_kitchen_menus_are_matched(self):
        MenuItem.objects.create(name="음료", price=2000, visible_kitchen=False)
        self.assertEqual(custom_items.match_menus(["음료"]), {})

    def test_names_compare_without_blanks_or_case(self):
        menu = MenuItem.objects.create(name="Iced Tea", price=2000)
        self.assertEqual(custom_items.match_menus(["iced  tea"]), {"iced  tea": menu})
        self.assertEqual(custom_items.match_menus(["icedtea"]), {"icedtea": menu})
        self.assertEqual(custom_items.match_menus(["tea"]), {})

    def test_the_stored_name_keeps_single_spaces(self):
        self.assertEqual(custom_items.clean_name("  삼계   탕 "), "삼계 탕")


@override_settings(**AUTH_SETTINGS)
class CustomLineReportTests(TestCase):
    """"삼계탕 30개 팔았고 그 아래 3개 2만원" -- one row, the custom part shown."""

    DAY = date(2026, 9, 19)

    def setUp(self):
        login_client(self.client, "STATS")
        self.table = Table.objects.create(number=7)
        self.soup = MenuItem.objects.create(name="삼계탕", price=10000)
        self.meal = MenuItem.objects.create(name="Meal", price=5000)

    def order(self, *lines):
        total = sum(line.get("line_amount") if line.get("line_amount") is not None
                    else line["qty"] * line["unit_price"] for line in lines)
        order = Order.objects.create(
            table=self.table, floor="B1", order_type="DINE_IN", order_date=self.DAY,
            number_series=NumberSeries.REAL, total_price=total, payment_method="CASH",
            received_amount=total, received_cash_amount=total, received_ticket_amount=0, change_amount=0)
        for line in lines:
            OrderItem.objects.create(order=order, **line)
        return order

    def dashboard(self):
        response = self.client.get(reverse("orders:stats-dashboard"), {"start_date": self.DAY.isoformat()})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_a_matched_custom_line_counts_inside_its_menu_row(self):
        self.order({"menu_item": self.soup, "qty": 30, "unit_price": 10000})
        self.order({"menu_item": self.soup, "qty": 3, "custom_name": "삼계탕", "line_amount": 20000},
                   {"menu_item": self.meal, "qty": 1, "unit_price": 5000})
        self.order({"qty": 2, "custom_name": "떡꼬치", "line_amount": 5000},
                   {"qty": 1, "custom_name": "떡 꼬치", "line_amount": 3000})
        data = self.dashboard()
        self.assertEqual(data["menu"], [
            {"menu_item_id": self.soup.id, "name": "삼계탕", "qty": 33, "amount": 320000,
             "custom_qty": 3, "custom_amount": 20000},
            # "떡꼬치" and "떡 꼬치" are one row; the first spelling in sort order is shown.
            {"menu_item_id": None, "name": "떡 꼬치", "qty": 3, "amount": 8000,
             "custom_qty": 3, "custom_amount": 8000},
            {"menu_item_id": self.meal.id, "name": "Meal", "qty": 1, "amount": 5000,
             "custom_qty": 0, "custom_amount": 0},
        ])
        self.assertEqual(data["summary"]["items"], 37)
        self.assertEqual(data["summary"]["revenue"], 333000)
        self.assertEqual(sum(row["amount"] for row in data["menu"]), data["summary"]["revenue"])


@override_settings(**AUTH_SETTINGS)
class AdminCustomLineTests(TestCase):
    """"삭제 후 재입력": a custom line is deleted and entered again, not edited."""

    def setUp(self):
        Table.objects.create(number=7)
        self.soup = MenuItem.objects.create(name="삼계탕", price=10000)
        serving = self.client_class()
        login_client(serving, "ORDER")
        response = serving.post(
            reverse("orders:orders-collection"),
            {"request_id": str(uuid.uuid4()), "floor": "B1", "order_type": "DINE_IN",
             "table_number": "7", "payment_method": "CASH", "received_cash_amount": 50000,
             "items": [{"menu_item_id": self.soup.id, "qty": 1}, custom()]},
            content_type="application/json")
        assert response.status_code == 201, response.content
        self.order = Order.objects.get(pk=response.json()["id"])
        self.menu_line = self.order.items.get(line_amount__isnull=True)
        self.custom_line = self.order.items.get(line_amount__isnull=False)
        operator = get_user_model().objects.create_superuser("op", "op@example.invalid", "x")
        self.client.force_login(operator)

    def post(self, *rows):
        data = {
            "status": self.order.status, "note": "",
            "items-TOTAL_FORMS": str(len(rows)),
            "items-INITIAL_FORMS": str(sum(1 for row in rows if row.get("id"))),
            "items-MIN_NUM_FORMS": "0", "items-MAX_NUM_FORMS": "1000", "_save": "Save",
        }
        for index, row in enumerate(rows):
            data[f"items-{index}-order"] = str(self.order.pk)
            for key, value in row.items():
                data[f"items-{index}-{key}"] = "on" if value is True else str(value)
        return self.client.post(reverse("admin:orders_order_change", args=[self.order.pk]), data)

    def menu_row(self):
        return {"id": self.menu_line.pk, "menu_item": self.soup.pk, "qty": 1, "service_mode": "DINE_IN"}

    def custom_row(self, **changes):
        row = {"id": self.custom_line.pk, "menu_item": self.soup.pk, "custom_name": "삼계탕",
               "line_amount": 20000, "qty": 3, "service_mode": "DINE_IN"}
        row.update(changes)
        return row

    def test_a_custom_line_cannot_be_edited(self):
        for change in ({"qty": 4}, {"line_amount": 15000}, {"custom_name": "닭죽"}):
            with self.subTest(change=change):
                response = self.post(self.menu_row(), self.custom_row(**change))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "지우고 다시 입력")
                self.custom_line.refresh_from_db()
                self.assertEqual((self.custom_line.qty, self.custom_line.line_amount), (3, 20000))

    def test_a_menu_line_cannot_turn_into_a_custom_one(self):
        response = self.post({**self.menu_row(), "line_amount": 1}, self.custom_row())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "메뉴 품목이거나")
        self.menu_line.refresh_from_db()
        self.assertIsNone(self.menu_line.line_amount)

    def test_delete_and_enter_again_recomputes_the_total(self):
        response = self.post(
            self.menu_row(), self.custom_row(DELETE=True),
            {"custom_name": " 삼계탕 ", "line_amount": 25000, "qty": 3, "service_mode": "DINE_IN"})
        self.assertEqual(response.status_code, 302, response.content[:800])
        self.assertFalse(OrderItem.objects.filter(pk=self.custom_line.pk).exists())
        added = self.order.items.get(line_amount__isnull=False)
        self.assertEqual((added.menu_item, added.custom_name, added.line_amount, added.unit_price),
                         (self.soup, "삼계탕", 25000, None))
        self.order.refresh_from_db()
        self.assertEqual((self.order.total_price, self.order.change_amount), (35000, 15000))

    def test_a_new_line_needs_a_menu_or_a_custom_name_and_amount(self):
        for row in ({"qty": 1, "service_mode": "DINE_IN"},
                    {"custom_name": "떡", "qty": 1, "service_mode": "DINE_IN"}):
            with self.subTest(row=row):
                response = self.post(self.menu_row(), self.custom_row(), row)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.order.items.count(), 2)

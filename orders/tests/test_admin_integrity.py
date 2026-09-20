"""7B: the Django admin is a writer too, and it keeps the same promises (D-052).

Before this, an operator changing a quantity in the admin left the stored
total where it was, so an order could say 5000 while its lines added up to
15000 (BK-R008). The admin could also rewrite the price snapshot, the number
and the money, and could move a cancelled order back to PREPARING.

The user chose to keep item editing in the admin, routed through the same
services the screens use. Every test here is a real admin form POST.
"""

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from orders.models import (
    MenuItem, Order, OrderEvent, OrderEventKind, OrderItem, OrderStatus, Table,
)
from orders.services import audit
from orders.tests.auth_support import AUTH_SETTINGS, login_client
from orders.views import api


@override_settings(**AUTH_SETTINGS)
class AdminOrderEditTests(TestCase):
    def setUp(self):
        Table.objects.create(number=7)
        self.meal = MenuItem.objects.create(name="Meal", price=5000)
        self.soup = MenuItem.objects.create(name="Soup", price=2000)
        self.operator = get_user_model().objects.create_superuser("op", "op@example.invalid", "x")
        self.client.force_login(self.operator)
        self.order = self.create_order(received=20000)
        self.item = self.order.items.get()

    def create_order(self, *, received):
        """A real order from the serving screen, so numbering, payment and
        audit are what they would be in the field."""
        serving = self.client_class()
        login_client(serving, "ORDER")
        response = serving.post(
            reverse("orders:orders-collection"),
            {"request_id": str(uuid.uuid4()), "floor": "B1", "order_type": "DINE_IN",
             "table_number": "7", "payment_method": "CASH", "received_cash_amount": received,
             "items": [{"menu_item_id": self.meal.id, "qty": 1}]},
            content_type="application/json",
        )
        assert response.status_code == 201, response.content
        return Order.objects.get(pk=response.json()["id"])

    def change_url(self):
        return reverse("admin:orders_order_change", args=[self.order.pk])

    def form(self, *rows, status=None, note="", **extra):
        """The admin change form with the item inline, as the browser posts it.

        Each row is a dict; an existing row carries its `id`. Fields the
        admin shows read-only are not posted -- the browser does not send
        them either -- unless a test wants to prove they are ignored.
        """
        data = {
            "status": status or self.order.status,
            "note": note,
            "items-TOTAL_FORMS": str(len(rows)),
            "items-INITIAL_FORMS": str(sum(1 for row in rows if row.get("id"))),
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "_save": "Save",
        }
        for index, row in enumerate(rows):
            prefix = f"items-{index}-"
            data[prefix + "order"] = str(self.order.pk)
            for key, value in row.items():
                data[prefix + key] = "on" if value is True else str(value)
        data.update(extra)
        return data

    def existing(self, **changes):
        row = {"id": self.item.pk, "menu_item": self.meal.pk, "qty": self.item.qty,
               "service_mode": self.item.service_mode}
        row.update(changes)
        return row

    def reload(self):
        return Order.objects.get(pk=self.order.pk)

    # --- quantity, total, change ------------------------------------------

    def test_changing_a_quantity_recomputes_the_total_and_the_change(self):
        response = self.client.post(self.change_url(), self.form(self.existing(qty=3)))
        self.assertEqual(response.status_code, 302, response.content[:500])
        order = self.reload()
        self.assertEqual(order.items.get().qty, 3)
        self.assertEqual(order.total_price, 15000)
        self.assertEqual(order.change_amount, 5000)
        self.assertEqual(order.received_cash_amount, 20000)  # the money is history
        event = OrderEvent.objects.filter(order=order, kind=OrderEventKind.ITEMS).get()
        self.assertIsNone(event.actor)  # an admin user is not an Account

    def test_adding_an_item_takes_the_current_menu_price_not_the_posted_one(self):
        response = self.client.post(self.change_url(), self.form(
            self.existing(),
            {"menu_item": self.soup.pk, "qty": 2, "service_mode": "DINE_IN", "unit_price": 1},
        ))
        self.assertEqual(response.status_code, 302, response.content[:500])
        order = self.reload()
        added = order.items.get(menu_item=self.soup)
        self.assertEqual((added.unit_price, added.qty), (2000, 2))
        self.assertEqual(order.total_price, 9000)
        self.assertEqual(order.change_amount, 11000)

    def test_deleting_an_item_recomputes_and_refuses_to_lose_cooking_history(self):
        OrderItem.objects.create(order=self.order, menu_item=self.soup, qty=1, unit_price=2000)
        extra = self.order.items.get(menu_item=self.soup)
        response = self.client.post(self.change_url(), self.form(
            self.existing(),
            {"id": extra.pk, "menu_item": self.soup.pk, "qty": 1, "service_mode": "DINE_IN", "DELETE": True},
        ))
        self.assertEqual(response.status_code, 302, response.content[:500])
        self.assertEqual(self.reload().total_price, 5000)
        self.assertFalse(OrderItem.objects.filter(pk=extra.pk).exists())
        # The remaining item has been cooked: the kitchen's record points at it.
        self.item.prepared_qty = 1
        self.item.save(update_fields=["prepared_qty"])
        audit.record_progress(self.order, self.item, None)
        response = self.client.post(self.change_url(), self.form(self.existing(DELETE=True)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "조리 이력")
        self.assertTrue(OrderItem.objects.filter(pk=self.item.pk).exists())
        self.assertEqual(self.reload().total_price, 5000)

    def test_a_quantity_below_what_the_kitchen_already_made_is_refused(self):
        self.item.qty = 3
        self.item.prepared_qty = 2
        self.item.save(update_fields=["qty", "prepared_qty"])
        response = self.client.post(self.change_url(), self.form(self.existing(qty=1)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "이미 조리")
        self.assertEqual(self.reload().items.get().qty, 3)

    def test_an_edit_the_money_no_longer_covers_is_refused_whole(self):
        """D-048 holds in the admin too: received < total is not saved."""
        response = self.client.post(self.change_url(), self.form(self.existing(qty=5)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "합계보다 적습니다")
        order = self.reload()
        self.assertEqual((order.items.get().qty, order.total_price, order.change_amount), (1, 5000, 15000))
        self.assertFalse(OrderEvent.objects.filter(order=order, kind=OrderEventKind.ITEMS).exists())

    def test_the_admin_keeps_the_screens_quantity_bound(self):
        """The API caps a line at 99; a cheap or free menu item must not let
        the admin store what the screens never could (PR #70 review)."""
        MenuItem.objects.filter(pk=self.meal.pk).update(price=0)
        self.item.unit_price = 0
        self.item.save(update_fields=["unit_price"])
        response = self.client.post(self.change_url(), self.form(self.existing(qty=100)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "99 이하")
        self.assertEqual(self.reload().items.get().qty, 1)
        response = self.client.post(self.change_url(), self.form(self.existing(qty=99)))
        self.assertEqual(response.status_code, 302, response.content[:500])

    def test_only_sellable_kitchen_menu_items_can_be_added(self):
        retired = MenuItem.objects.create(name="Retired", price=1000, is_active=False)
        counter_only = MenuItem.objects.create(name="Sticker", price=1000, visible_kitchen=False)
        for menu in (retired, counter_only):
            with self.subTest(menu=menu.name):
                response = self.client.post(self.change_url(), self.form(
                    self.existing(), {"menu_item": menu.pk, "qty": 1, "service_mode": "DINE_IN"},
                ))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "판매 중인 주방 메뉴")
                self.assertEqual(self.reload().items.count(), 1)

    def test_the_snapshot_number_and_money_cannot_be_posted_over(self):
        before = self.reload()
        response = self.client.post(self.change_url(), self.form(
            self.existing(unit_price=1),
            total_price="1", order_no="999", received_cash_amount="1", change_amount="1",
            number_series="EVENT", order_type="TAKEOUT",
        ))
        self.assertEqual(response.status_code, 302, response.content[:500])
        after = self.reload()
        self.assertEqual(after.items.get().unit_price, 5000)
        self.assertEqual(
            (after.total_price, after.order_no, after.received_cash_amount, after.change_amount,
             after.number_series, after.order_type),
            (before.total_price, before.order_no, before.received_cash_amount,
             before.change_amount, before.number_series, before.order_type),
        )

    def test_saving_without_touching_items_writes_no_event(self):
        response = self.client.post(self.change_url(), self.form(self.existing(), note="창가 자리"))
        self.assertEqual(response.status_code, 302, response.content[:500])
        self.assertEqual(self.reload().note, "창가 자리")
        self.assertFalse(OrderEvent.objects.filter(order=self.order, kind=OrderEventKind.ITEMS).exists())

    # --- status ------------------------------------------------------------

    def test_a_status_change_follows_the_kitchen_transition_table(self):
        response = self.client.post(self.change_url(), self.form(self.existing(), status="CANCELLED"))
        self.assertEqual(response.status_code, 302, response.content[:500])
        self.assertEqual(self.reload().status, OrderStatus.CANCELLED)
        event = OrderEvent.objects.filter(order=self.order, kind=OrderEventKind.STATUS).latest("id")
        self.assertEqual((event.from_status, event.to_status, event.actor), ("PREPARING", "CANCELLED", None))
        # Cancelled is final (D-050), in the admin as on the board.
        response = self.client.post(self.change_url(), self.form(self.existing(), status="PREPARING"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "취소된 주문")
        self.assertEqual(self.reload().status, OrderStatus.CANCELLED)

    def test_adding_an_item_to_a_ready_order_sends_it_back_to_preparing(self):
        self.item.prepared_qty = 1
        self.item.save(update_fields=["prepared_qty"])
        Order.objects.filter(pk=self.order.pk).update(status=OrderStatus.READY)
        self.order.refresh_from_db()
        response = self.client.post(self.change_url(), self.form(
            self.existing(),
            {"menu_item": self.soup.pk, "qty": 1, "service_mode": "DINE_IN"},
        ))
        self.assertEqual(response.status_code, 302, response.content[:500])
        self.assertEqual(self.reload().status, OrderStatus.PREPARING)
        self.assertTrue(OrderEvent.objects.filter(
            order=self.order, kind=OrderEventKind.STATUS, from_status="READY", to_status="PREPARING",
        ).exists())

    def test_items_of_a_cancelled_order_cannot_be_edited(self):
        Order.objects.filter(pk=self.order.pk).update(status=OrderStatus.CANCELLED)
        self.order.refresh_from_db()
        response = self.client.post(self.change_url(), self.form(self.existing(qty=2)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "취소된 주문")
        self.assertEqual(self.reload().items.get().qty, 1)

    def test_the_items_event_carries_the_status_the_edit_left(self):
        self.item.prepared_qty = 1
        self.item.save(update_fields=["prepared_qty"])
        Order.objects.filter(pk=self.order.pk).update(status=OrderStatus.READY)
        self.client.post(self.change_url(), self.form(
            self.existing(), {"menu_item": self.soup.pk, "qty": 1, "service_mode": "DINE_IN"},
        ))
        items_event = OrderEvent.objects.get(order=self.order, kind=OrderEventKind.ITEMS)
        self.assertEqual(items_event.to_status, OrderStatus.PREPARING)

    # --- the shape of the guard -----------------------------------------------

    def test_only_status_and_note_are_editable_on_the_order(self):
        """Django builds the form from `fields` minus `readonly_fields`; the
        narrower Meta on OrderAdminForm is not what protects the money. Keep
        the two tuples complementary (PR #70 review)."""
        from orders.admin import OrderAdmin
        self.assertEqual(set(OrderAdmin.fields) - set(OrderAdmin.readonly_fields), {"status", "note"})
        from orders.admin import OrderItemInline
        self.assertEqual(set(OrderItemInline.fields) - set(OrderItemInline.readonly_fields),
                         {"menu_item", "qty", "service_mode"})

    def test_a_change_form_post_holds_the_order_row_from_the_first_read(self):
        """The validation and the write have to see one order: the kitchen
        locks the order before touching its items, so an admin POST that holds
        the row from its first read cannot be raced into a 500 (PR #70 review)."""
        from django.contrib.admin.sites import site
        from django.test import RequestFactory
        from django.urls import resolve
        from orders.admin import OrderAdmin
        model_admin = OrderAdmin(Order, site)
        post = RequestFactory().post(self.change_url())
        post.user = self.operator
        post.resolver_match = resolve(self.change_url())
        self.assertTrue(model_admin.get_queryset(post).query.select_for_update)
        get = RequestFactory().get(self.change_url())
        get.user = self.operator
        get.resolver_match = resolve(self.change_url())
        self.assertFalse(model_admin.get_queryset(get).query.select_for_update)
        listing = RequestFactory().post(reverse("admin:orders_order_changelist"))
        listing.user = self.operator
        listing.resolver_match = resolve(reverse("admin:orders_order_changelist"))
        self.assertFalse(model_admin.get_queryset(listing).query.select_for_update)

    # --- who may ------------------------------------------------------------

    def test_orders_are_not_created_in_the_admin(self):
        """Numbering, payment and the audit trail belong to the serving
        screen; the admin has no path that could reproduce them."""
        response = self.client.get(reverse("admin:orders_order_add"))
        self.assertEqual(response.status_code, 403)

    def test_a_staff_user_without_change_permission_is_refused(self):
        clerk = get_user_model().objects.create_user("clerk", "c@example.invalid", "x", is_staff=True)
        self.client.force_login(clerk)
        response = self.client.post(self.change_url(), self.form(self.existing(qty=3)))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.reload().items.get().qty, 1)

    def test_an_anonymous_post_is_sent_to_the_admin_login(self):
        self.client.logout()
        response = self.client.post(self.change_url(), self.form(self.existing(qty=3)))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response["Location"])
        self.assertEqual(self.reload().items.get().qty, 1)

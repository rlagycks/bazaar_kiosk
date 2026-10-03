"""8B: an admin's change is true for every worker at once (BK-R010).

Two caches stood between an admin and the floor. `_get_table_by_number` held
`Table` rows in a process-level `lru_cache`, and that cache was the thing
validating the table on order creation -- so a worker that had already served
one order to table 7 kept accepting orders for it after the table was
switched off, until that worker happened to restart. Workers that had never
seen table 7 refused correctly, so the same POST succeeded or failed
depending on which process answered it.

The menu and table pickers were behind `cache_page(60)`. Django's default
cache backend is per-process memory, so the window was not one shared 60
seconds: each worker had its own, and two kitchen screens could show
different menus at the same moment.

Neither cache bought anything worth this. Both lookups are a handful of
indexed rows on page load.
"""

import uuid

from django.test import TestCase, override_settings
from django.urls import reverse

from orders.models import MenuItem, Table
from orders.tests.auth_support import AUTH_SETTINGS, login_client
from orders.views import api


@override_settings(**AUTH_SETTINGS)
class DeactivationTakesEffectAtOnceTests(TestCase):
    def setUp(self):
        self.table = Table.objects.create(number=7)
        self.menu = MenuItem.objects.create(name="Meal", price=5000)
        login_client(self.client, "ORDER")

    def create(self, table_number=7):
        return self.client.post(
            reverse("orders:orders-collection"),
            {"request_id": str(uuid.uuid4()), "floor": "B1", "order_type": "DINE_IN",
             "table_number": str(table_number),
             "items": [{"menu_item_id": self.menu.id, "qty": 1}],
             "payment_method": "CASH", "received_cash_amount": 5000},
            content_type="application/json",
        )

    def test_a_table_switched_off_after_one_order_refuses_the_next(self):
        """The first order is what used to warm the cache. Everything after
        it was answered from that copy."""
        self.assertEqual(self.create().status_code, 201)
        Table.objects.filter(pk=self.table.pk).update(is_active=False)
        response = self.create()
        self.assertEqual(response.status_code, 400)
        self.assertIn("테이블", response.content.decode())

    def test_a_table_switched_back_on_is_usable_again(self):
        Table.objects.filter(pk=self.table.pk).update(is_active=False)
        self.assertEqual(self.create().status_code, 400)
        Table.objects.filter(pk=self.table.pk).update(is_active=True)
        self.assertEqual(self.create().status_code, 201)

    def test_the_table_lookup_keeps_nothing_between_requests(self):
        """The property that makes the worker count irrelevant: there is no
        per-process copy to go stale, so every process answers from the row."""
        self.assertFalse(hasattr(api._get_table_by_number, "cache_info"))
        self.assertFalse(hasattr(api._get_table_by_number, "cache_clear"))


@override_settings(**AUTH_SETTINGS)
class PickersShowTheCurrentRowsTests(TestCase):
    def setUp(self):
        self.table = Table.objects.create(number=7)
        self.menu = MenuItem.objects.create(name="Meal", price=5000, visible_counter=True)
        login_client(self.client, "ORDER")

    def tables(self):
        response = self.client.get(reverse("orders:tables"))
        self.assertEqual(response.status_code, 200, response.content)
        return [t["number"] for t in response.json()["items"]]

    def menus(self):
        response = self.client.get(reverse("orders:menus"))
        self.assertEqual(response.status_code, 200, response.content)
        return [m["id"] for m in response.json()["items"]]

    def test_a_deactivated_table_leaves_the_picker_on_the_next_request(self):
        self.assertEqual(self.tables(), [7])
        Table.objects.filter(pk=self.table.pk).update(is_active=False)
        self.assertEqual(self.tables(), [])

    def test_a_deactivated_menu_leaves_the_picker_on_the_next_request(self):
        self.assertEqual(self.menus(), [self.menu.id])
        MenuItem.objects.filter(pk=self.menu.pk).update(is_active=False)
        self.assertEqual(self.menus(), [])

    def test_a_new_table_appears_on_the_next_request(self):
        self.assertEqual(self.tables(), [7])
        Table.objects.create(number=8)
        self.assertEqual(self.tables(), [7, 8])

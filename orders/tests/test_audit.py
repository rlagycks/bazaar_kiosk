"""D-051: every order and every change to it carries who did it."""
import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from orders.models import Account, MenuItem, Order, OrderEvent, Table
from orders.tests.auth_support import AUTH_SETTINGS, login_client
from orders.views import api


@override_settings(**AUTH_SETTINGS)
class AuditTrailTests(TestCase):
    def setUp(self):
        api._get_table_by_number.cache_clear()
        self.addCleanup(api._get_table_by_number.cache_clear)
        Table.objects.create(number=7)
        self.menu = MenuItem.objects.create(name="Meal", price=1000)
        self.server = Client()
        login_client(self.server, "SERVING")
        self.kitchen = Client()
        login_client(self.kitchen, "BOTH_MONITORS")

    def create(self):
        response = self.server.post(
            reverse("orders:orders-collection"),
            {"request_id": str(uuid.uuid4()), "floor": "B1", "order_type": "DINE_IN",
             "table_number": "7", "payment_method": "CASH", "received_cash_amount": 2000,
             "items": [{"menu_item_id": self.menu.id, "qty": 2}]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        return Order.objects.get(pk=response.json()["id"])

    def test_the_order_records_its_author_and_a_created_event(self):
        order = self.create()
        self.assertEqual(order.created_by, Account.objects.get(name="serving"))
        event = order.events.get()
        self.assertEqual((event.kind, event.actor.name, event.to_status), ("CREATED", "serving", "PREPARING"))

    def test_status_and_progress_changes_record_who_and_what(self):
        order = self.create()
        item = order.items.get()
        self.kitchen.patch(reverse("orders:order-item-progress", args=[item.id]),
                           data={"prepared_qty": 1}, content_type="application/json")
        self.kitchen.patch(reverse("orders:order-item-progress", args=[item.id]),
                           data={"done": True}, content_type="application/json")
        self.kitchen.patch(reverse("orders:order-status", args=[order.id]),
                           data={"status": "CANCELLED"}, content_type="application/json")
        trail = [(e.kind, e.actor.name, e.from_status, e.to_status, e.prepared_qty)
                 for e in order.events.order_by("id")]
        self.assertEqual(trail, [
            ("CREATED", "serving", "", "PREPARING", None),
            ("PROGRESS", "both-monitors", "", "", 1),
            ("PROGRESS", "both-monitors", "", "", 2),
            ("STATUS", "both-monitors", "PREPARING", "READY", None),
            ("STATUS", "both-monitors", "READY", "CANCELLED", None),
        ])

    def test_a_no_op_change_leaves_no_event(self):
        order = self.create()
        self.kitchen.patch(reverse("orders:order-status", args=[order.id]),
                           data={"status": "PREPARING"}, content_type="application/json")
        item = order.items.get()
        self.kitchen.patch(reverse("orders:order-item-progress", args=[item.id]),
                           data={"prepared_qty": 0}, content_type="application/json")
        self.assertEqual(order.events.count(), 1)

    def test_a_refused_change_leaves_no_event(self):
        order = self.create()
        outsider = Client()
        login_client(outsider, "TAKEOUT_MONITOR")
        response = outsider.patch(reverse("orders:order-status", args=[order.id]),
                                  data={"status": "READY"}, content_type="application/json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(order.events.count(), 1)
        self.assertEqual(OrderEvent.objects.count(), 1)

    def test_events_survive_the_actor_being_switched_off(self):
        order = self.create()
        Account.objects.filter(name="serving").update(is_active=False)
        self.assertEqual(order.events.get().actor.name, "serving")

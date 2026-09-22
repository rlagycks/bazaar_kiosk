"""D-051: the hall/takeout boundary is the server's.

A takeout monitor sees and changes takeout orders only; a hall monitor sees
and changes orders with any dine-in item (so a mixed order is a hall order);
an account holding both sees everything; STATS reads everything and changes
nothing. Every assertion here is on a real response.
"""
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from orders.models import MenuItem, Order, OrderItem, Table
from orders.roles import HALL_MONITOR, STATS, TAKEOUT_MONITOR
from orders.services import scope
from orders.tests.auth_support import AUTH_SETTINGS, login_client


@override_settings(**AUTH_SETTINGS)
class ScopeTests(TestCase):
    def setUp(self):
        self.hall_table = Table.objects.create(number=7)
        self.tag = Table.objects.create(number=105)
        self.menu = MenuItem.objects.create(name="Meal", price=1000)
        self.hall = self.order("DINE_IN", self.hall_table, ["DINE_IN"])
        self.takeout = self.order("TAKEOUT", self.tag, ["TAKEOUT"])
        self.mixed = self.order("DINE_IN", self.hall_table, ["DINE_IN", "TAKEOUT"])

    def order(self, order_type, table, modes):
        order = Order.objects.create(
            floor="B1", order_type=order_type, table=table, status="PREPARING",
            total_price=1000 * len(modes), payment_method="CASH",
            received_amount=1000 * len(modes), received_cash_amount=1000 * len(modes),
            received_ticket_amount=0, is_takeout=order_type == "TAKEOUT",
        )
        for mode in modes:
            OrderItem.objects.create(order=order, menu_item=self.menu, qty=1,
                                     unit_price=1000, service_mode=mode)
        return order

    def client_as(self, alias):
        client = Client()
        login_client(client, alias)
        return client

    def listed(self, client):
        response = client.get(reverse("orders:orders-collection"))
        self.assertEqual(response.status_code, 200)
        return {row["id"] for row in response.json()["results"]}

    # --- the rule --------------------------------------------------------

    def test_classification_follows_the_items_not_the_order_type(self):
        self.assertEqual(scope.classify(self.hall), scope.HALL)
        self.assertEqual(scope.classify(self.takeout), scope.TAKEOUT)
        self.assertEqual(scope.classify(self.mixed), scope.HALL)

    def test_visible_partitions_the_orders_exactly(self):
        every = set(Order.objects.values_list("id", flat=True))
        hall = set(scope.visible(Order.objects.all(), {HALL_MONITOR}).values_list("id", flat=True))
        takeout = set(scope.visible(Order.objects.all(), {TAKEOUT_MONITOR}).values_list("id", flat=True))
        self.assertEqual(hall & takeout, set())
        self.assertEqual(hall | takeout, every)
        self.assertEqual(hall, {self.hall.id, self.mixed.id})
        self.assertEqual(set(scope.visible(Order.objects.all(), {STATS}).values_list("id", flat=True)), every)
        self.assertEqual(set(scope.visible(Order.objects.all(), {HALL_MONITOR, TAKEOUT_MONITOR}).values_list("id", flat=True)), every)
        self.assertEqual(scope.visible(Order.objects.all(), set()).count(), 0)

    # --- reads -----------------------------------------------------------

    def test_the_listing_is_filtered_per_monitor(self):
        self.assertEqual(self.listed(self.client_as("HALL_MONITOR")), {self.hall.id, self.mixed.id})
        self.assertEqual(self.listed(self.client_as("TAKEOUT_MONITOR")), {self.takeout.id})
        self.assertEqual(self.listed(self.client_as("BOTH_MONITORS")),
                         {self.hall.id, self.mixed.id, self.takeout.id})
        self.assertEqual(self.listed(self.client_as("STATS")),
                         {self.hall.id, self.mixed.id, self.takeout.id})

    def test_asking_for_the_other_type_by_query_does_not_widen_the_view(self):
        takeout = self.client_as("TAKEOUT_MONITOR")
        response = takeout.get(reverse("orders:orders-collection"), {"types": "DINE_IN,TAKEOUT"})
        self.assertEqual({row["id"] for row in response.json()["results"]}, {self.takeout.id})

    def test_detail_of_an_order_outside_the_scope_is_403(self):
        takeout = self.client_as("TAKEOUT_MONITOR")
        self.assertEqual(takeout.get(reverse("orders:order-detail", args=[self.takeout.id])).status_code, 200)
        for other in (self.hall, self.mixed):
            with self.subTest(order=other.id):
                response = takeout.get(reverse("orders:order-detail", args=[other.id]))
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json(), {"detail": "권한이 없습니다."})
        hall = self.client_as("HALL_MONITOR")
        self.assertEqual(hall.get(reverse("orders:order-detail", args=[self.mixed.id])).status_code, 200)
        self.assertEqual(hall.get(reverse("orders:order-detail", args=[self.takeout.id])).status_code, 403)
        stats = self.client_as("STATS")
        for order in (self.hall, self.takeout, self.mixed):
            self.assertEqual(stats.get(reverse("orders:order-detail", args=[order.id])).status_code, 200)

    # --- writes ----------------------------------------------------------

    def status_change(self, client, order, status="READY"):
        return client.patch(reverse("orders:order-status", args=[order.id]),
                            data={"status": status}, content_type="application/json")

    def progress(self, client, order):
        item = order.items.first()
        return client.patch(reverse("orders:order-item-progress", args=[item.id]),
                            data={"done": True}, content_type="application/json")

    def test_a_monitor_changes_only_its_own_orders(self):
        takeout = self.client_as("TAKEOUT_MONITOR")
        hall = self.client_as("HALL_MONITOR")
        sides = (
            (takeout, [self.takeout], [self.hall, self.mixed]),
            (hall, [self.hall, self.mixed], [self.takeout]),
        )
        # Every refusal first, while nothing has been changed yet, so "still
        # PREPARING" really means the refused request wrote nothing.
        for client, _, refused in sides:
            for order in refused:
                with self.subTest(order=order.id, action="status"):
                    response = self.status_change(client, order)
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response.json(), {"detail": "권한이 없습니다."})
                    order.refresh_from_db()
                    self.assertEqual(order.status, "PREPARING")
                with self.subTest(order=order.id, action="progress"):
                    self.assertEqual(self.progress(client, order).status_code, 403)
                    self.assertEqual(order.items.first().prepared_qty, 0)
        for client, allowed, _ in sides:
            for order in allowed:
                with self.subTest(order=order.id, action="status"):
                    self.assertEqual(self.status_change(client, order).status_code, 200)
                with self.subTest(order=order.id, action="progress"):
                    self.assertEqual(self.progress(client, order).status_code, 200)

    def test_stats_reads_but_never_changes(self):
        stats = self.client_as("STATS")
        for order in (self.hall, self.takeout, self.mixed):
            self.assertEqual(self.status_change(stats, order).status_code, 403)
            self.assertEqual(self.progress(stats, order).status_code, 403)

    def test_both_monitors_change_everything(self):
        both = self.client_as("BOTH_MONITORS")
        for order in (self.hall, self.takeout, self.mixed):
            self.assertEqual(self.status_change(both, order).status_code, 200)

    def test_the_kitchen_pages_open_only_for_their_permission(self):
        pages = {"kitchen": ("BOTH_MONITORS",), "kitchen-hall": ("HALL_MONITOR", "BOTH_MONITORS"),
                 "kitchen-takeout": ("TAKEOUT_MONITOR", "BOTH_MONITORS")}
        for alias in ("HALL_MONITOR", "TAKEOUT_MONITOR", "BOTH_MONITORS", "STATS", "SERVING"):
            client = self.client_as(alias)
            for page, allowed in pages.items():
                with self.subTest(alias=alias, page=page):
                    response = client.get(reverse(f"orders:{page}"))
                    if alias in allowed:
                        self.assertEqual(response.status_code, 200)
                    else:
                        self.assertRedirects(response, reverse("orders:login"),
                                             fetch_redirect_response=False)

    def test_the_kitchen_nav_links_only_to_pages_the_account_may_open(self):
        hall = self.client_as("HALL_MONITOR").get(reverse("orders:kitchen-hall"))
        self.assertContains(hall, reverse("orders:kitchen-hall"))
        self.assertNotContains(hall, f'href="{reverse("orders:kitchen")}"')
        self.assertNotContains(hall, f'href="{reverse("orders:kitchen-takeout")}"')
        both = self.client_as("BOTH_MONITORS").get(reverse("orders:kitchen"))
        for page in ("kitchen", "kitchen-hall", "kitchen-takeout"):
            self.assertContains(both, f'href="{reverse(f"orders:{page}")}"')

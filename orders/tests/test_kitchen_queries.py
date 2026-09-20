"""8B: the kitchen sees every order that is still waiting (BK-R009).

The list was newest-first and cut at the caller's `limit`, which the kitchen
screen pinned to 80. Past that, the orders that dropped off were the ones
that had waited longest -- the only ones that matter in a queue. A busy
evening, or a straggler from the previous day, disappeared from the board
with nothing on screen to say so.

The contract here: orders still being prepared are a work queue, so they come
oldest first and complete. Everything else is a look back at what happened,
so it stays newest first and paged. Either way the response says how many
there really are.
"""

from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from orders.models import MenuItem, NumberSeries, Order, OrderItem, OrderStatus, OrderType, Table
from orders.services import queues
from orders.tests.auth_support import AUTH_SETTINGS, login_client


@override_settings(**AUTH_SETTINGS)
class WaitingQueueTests(TestCase):
    """What the kitchen board asks for: floor B1, still preparing."""

    def setUp(self):
        self.table = Table.objects.create(number=7)
        self.menu = MenuItem.objects.create(name="Meal", price=5000)
        self.now = timezone.now()
        self.next_slot = 101

    def takeout_slot(self) -> Table:
        """D-050 keeps one active takeout order per tag, so each waiting
        takeout order in these fixtures needs a tag of its own."""
        slot = Table.objects.create(number=self.next_slot)
        self.next_slot += 1
        return slot

    def make(self, *, minutes_ago, status=OrderStatus.PREPARING, mode=OrderType.DINE_IN):
        table = self.takeout_slot() if mode == OrderType.TAKEOUT else self.table
        order = Order.objects.create(
            table=table, floor="B1", order_type=mode, status=status,
            number_series=NumberSeries.REAL, total_price=5000, payment_method="CASH",
            received_amount=5000, received_cash_amount=5000, received_ticket_amount=0,
            change_amount=0,
        )
        OrderItem.objects.create(order=order, menu_item=self.menu, qty=1,
                                 unit_price=5000, service_mode=mode)
        Order.objects.filter(pk=order.pk).update(
            created_at=self.now - timedelta(minutes=minutes_ago))
        return order

    def board(self, alias="KITCHEN", **params):
        login_client(self.client, alias)
        response = self.client.get(
            reverse("orders:orders-collection"),
            {"floor": "B1", "status": "PREPARING", "types": "DINE_IN,TAKEOUT", **params},
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_eighty_one_waiting_orders_all_reach_the_board(self):
        """81 was the exact edge: the screen asked for 80."""
        for minutes in range(81):
            self.make(minutes_ago=minutes)
        body = self.board()
        self.assertEqual(body["total"], 81)
        self.assertEqual(body["count"], 81)
        self.assertFalse(body["has_more"])

    def test_two_hundred_and_one_waiting_orders_all_reach_the_board(self):
        """201 was the other edge: the server clamped `limit` at 200."""
        for minutes in range(201):
            self.make(minutes_ago=minutes)
        body = self.board()
        self.assertEqual((body["total"], body["count"]), (201, 201))
        self.assertFalse(body["has_more"])

    def test_a_limit_from_the_caller_cannot_shorten_the_queue(self):
        """The old screen pinned limit=80. A queue is not a page; asking for
        fewer must not hide work that is still waiting."""
        for minutes in range(90):
            self.make(minutes_ago=minutes)
        self.assertEqual(self.board(limit="80")["count"], 90)
        self.assertEqual(self.board(limit="1")["count"], 90)

    def test_the_longest_wait_is_first(self):
        newest = self.make(minutes_ago=1)
        oldest = self.make(minutes_ago=300)
        middle = self.make(minutes_ago=60)
        ids = [row["id"] for row in self.board()["results"]]
        self.assertEqual(ids, [oldest.id, middle.id, newest.id])

    def test_an_order_left_from_the_previous_day_leads_the_queue(self):
        """It is the oldest thing waiting, so it is the first thing to cook.
        Under the old order it was the first thing to vanish."""
        yesterday = self.make(minutes_ago=26 * 60)
        for minutes in range(100):
            self.make(minutes_ago=minutes)
        body = self.board()
        self.assertEqual(body["results"][0]["id"], yesterday.id)
        self.assertEqual(body["count"], 101)

    def test_finished_and_cancelled_orders_are_not_waiting(self):
        waiting = self.make(minutes_ago=10)
        self.make(minutes_ago=11, status=OrderStatus.READY)
        self.make(minutes_ago=12, status=OrderStatus.CANCELLED)
        body = self.board()
        self.assertEqual([row["id"] for row in body["results"]], [waiting.id])
        self.assertEqual(body["total"], 1)

    def test_past_the_safety_cap_the_remainder_is_named_not_dropped(self):
        """The queue is bounded so one query cannot grow without limit. When
        the bound bites, the response says so instead of going quiet."""
        over = queues.MAX_QUEUE + 5
        Order.objects.bulk_create([
            Order(table=self.table, floor="B1", order_type=OrderType.DINE_IN,
                  status=OrderStatus.PREPARING, number_series=NumberSeries.REAL,
                  total_price=5000, payment_method="CASH", received_amount=5000,
                  received_cash_amount=5000, received_ticket_amount=0, change_amount=0)
            for _ in range(over)
        ])
        OrderItem.objects.bulk_create([
            OrderItem(order=o, menu_item=self.menu, qty=1, unit_price=5000,
                      service_mode=OrderType.DINE_IN)
            for o in Order.objects.all()
        ])
        body = self.board()
        self.assertEqual(body["total"], over)
        self.assertEqual(body["count"], queues.MAX_QUEUE)
        self.assertTrue(body["has_more"])


@override_settings(**AUTH_SETTINGS)
class ScopeSurvivesTheQueueTests(WaitingQueueTests):
    """A monitor's own classification is applied before any cut, so a long
    queue cannot push another monitor's orders into its place (D-051)."""

    def test_a_hall_monitor_sees_every_waiting_hall_order(self):
        hall = [self.make(minutes_ago=m, mode=OrderType.DINE_IN) for m in range(100, 190)]
        for minutes in range(90):
            self.make(minutes_ago=minutes, mode=OrderType.TAKEOUT)
        body = self.board("HALL_MONITOR")
        self.assertEqual(body["total"], 90)
        self.assertEqual({row["id"] for row in body["results"]}, {o.id for o in hall})

    def test_a_takeout_monitor_sees_every_waiting_takeout_order(self):
        for minutes in range(100, 190):
            self.make(minutes_ago=minutes, mode=OrderType.DINE_IN)
        takeout = [self.make(minutes_ago=m, mode=OrderType.TAKEOUT) for m in range(90)]
        body = self.board("TAKEOUT_MONITOR")
        self.assertEqual(body["total"], 90)
        self.assertEqual({row["id"] for row in body["results"]}, {o.id for o in takeout})

    def test_a_mixed_order_stays_with_the_hall_however_long_the_queue(self):
        mixed = self.make(minutes_ago=500, mode=OrderType.DINE_IN)
        OrderItem.objects.create(order=mixed, menu_item=self.menu, qty=1,
                                 unit_price=5000, service_mode=OrderType.TAKEOUT)
        for minutes in range(120):
            self.make(minutes_ago=minutes, mode=OrderType.TAKEOUT)
        self.assertEqual(self.board("HALL_MONITOR")["results"][0]["id"], mixed.id)
        self.assertNotIn(mixed.id, {r["id"] for r in self.board("TAKEOUT_MONITOR")["results"]})


@override_settings(**AUTH_SETTINGS)
class LookingBackTests(WaitingQueueTests):
    """Not a queue: what already happened, most recent first, paged."""

    def history(self, **params):
        login_client(self.client, "KITCHEN")
        response = self.client.get(reverse("orders:orders-collection"), params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_history_is_newest_first_and_honours_the_limit(self):
        for minutes in range(10):
            self.make(minutes_ago=minutes, status=OrderStatus.READY)
        body = self.history(status="READY", limit="3")
        self.assertEqual(body["count"], 3)
        first = Order.objects.filter(status=OrderStatus.READY).order_by("-created_at").first()
        self.assertEqual(body["results"][0]["id"], first.id)

    def test_history_says_how_many_there_are_beyond_the_page(self):
        for minutes in range(10):
            self.make(minutes_ago=minutes, status=OrderStatus.READY)
        body = self.history(status="READY", limit="3")
        self.assertEqual(body["total"], 10)
        self.assertTrue(body["has_more"])
        self.assertFalse(self.history(status="READY", limit="10")["has_more"])

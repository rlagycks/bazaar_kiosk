"""10D2: the kitchen board is attached to its stream (BK-R020, BK-R033).

The board reads order data from exactly one place -- 10C's snapshot -- and
decides *when* to read in exactly one place, `kitchen_live.js`. The stream
carries no payload (D-058), so every event, every write and every timer
resolves to the same question: "read the snapshot, then apply the answer if
it is not late". `scripts/test_kitchen_live.cjs` drives that scheduler with
a scripted stream and clock; what is pinned here is the server side of the
same loop -- a write on this connection reaches an open stream and the
snapshot afterwards answers the new state -- and that the page really wires
the two together.
"""

from __future__ import annotations

import asyncio
import json
import re

from asgiref.sync import sync_to_async
from django.conf import settings
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from orders.tests.auth_support import AUTH_SETTINGS, login_client
from orders.tests.test_sse_server import FAST_HUB, StreamFixture

TEMPLATE = settings.BASE_DIR / "orders/templates/orders/kitchen_supervisor.html"
SCHEDULER = settings.BASE_DIR / "orders/static/orders/ui/kitchen_live.js"
CI = settings.BASE_DIR / ".github/workflows/ci.yml"


def template():
    return TEMPLATE.read_text(encoding="utf-8")


def scheduler():
    return SCHEDULER.read_text(encoding="utf-8")


class TheBoardReadsFromOnePlaceTests(TestCase):
    """Order data: the snapshot. Timing: the scheduler. Nothing else."""

    def test_the_page_loads_the_scheduler_and_points_it_at_this_server(self):
        source = template()
        self.assertIn("orders/ui/kitchen_live.js", source)
        self.assertIn("{% url 'orders:snapshot-waiting' %}", source)
        self.assertIn("{% url 'orders:kitchen-stream' %}", source)
        self.assertIn("BazaarLive.create(", source)

    def test_the_board_no_longer_reads_the_list_or_single_orders_itself(self):
        """The two reads that could race (BK-R033) are gone, not guarded."""
        source = template()
        self.assertNotIn("orders:orders-collection", source)
        self.assertNotIn("orders:order-detail", source)
        for name in ("refreshOrder", "queueOrderRefresh", "ORDER_REFRESH_QUEUE"):
            with self.subTest(symbol=name):
                self.assertNotIn(name, source)

    def test_a_write_never_applies_its_own_response(self):
        """A PATCH answers with an order; drawing that answer is how a late
        list could then undo it. The write asks the scheduler for a read."""
        source = template()
        self.assertNotIn("upsertOrder(result", source)
        for function in ("cancelOrder", "setPreparedQty"):
            body = source.split("async function " + function, 1)[1].split("\n    }\n", 1)[0]
            with self.subTest(function=function):
                self.assertIn("LIVE.refetch(", body)
                self.assertNotIn("upsertOrder", body)
                self.assertNotIn("renderFromStore", body)

    def test_the_template_opens_no_stream_of_its_own(self):
        """One `EventSource`, in the scheduler, refused unless same-origin."""
        self.assertNotIn("new EventSource", template())
        self.assertIn("new EventSourceImpl(streamUrl)", scheduler())
        self.assertIn("origin !== win.location.origin", scheduler())

    def test_the_status_line_says_which_way_the_board_is_being_kept_current(self):
        """A board polling because its hub is broken must not read as live."""
        source = template()
        for phrase in ("실시간", "다시 읽음", "읽기 실패", "연결 중", "감지 지연"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, source)
        self.assertNotIn("자동 갱신 안 함", source)

    def test_the_scheduler_tests_run_in_ci(self):
        self.assertIn("scripts/test_kitchen_live.cjs", CI.read_text(encoding="utf-8"))

    def test_the_scheduler_arms_only_one_shot_timers(self):
        """Its timers stop when the stream is healthy (node test); a
        `setInterval` could not."""
        self.assertNotIn("setInterval", scheduler())


@override_settings(**AUTH_SETTINGS)
class TheRenderedPageIsWiredTests(TestCase):
    def test_every_kitchen_page_carries_the_stream_and_snapshot_paths(self):
        login_client(self.client, "BOTH_MONITORS")
        for name in ("orders:kitchen", "orders:kitchen-hall", "orders:kitchen-takeout"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                body = response.content.decode()
                self.assertIn(reverse("orders:kitchen-stream"), body)
                self.assertIn(reverse("orders:snapshot-waiting"), body)
                self.assertIn("kitchen_live.js", body)
                self.assertIsNone(re.search(r"""["'](?:https?:)?//""", body),
                                  "the page addresses only this server")


@override_settings(**AUTH_SETTINGS, **FAST_HUB)
class AWriteOnThisConnectionRoundTripsTests(StreamFixture, TransactionTestCase):
    """The loop the board runs: write, be woken, read, see the write."""

    def progress_url(self, order):
        """Resolved on a thread: the item lookup is a query."""
        item = order.items.first()
        return reverse("orders:order-item-progress", args=[item.id])

    def snapshot(self, client, since):
        response = client.get(reverse("orders:snapshot-waiting"), {"since": since})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def order_of_two(self):
        """Finishing 1 of 1 would move the order to READY and out of the
        waiting list -- correct, but not the case this test is about."""
        order = self.make_order()
        order.items.update(qty=2)
        return order

    async def test_a_progress_write_wakes_the_stream_and_the_snapshot_shows_it(self):
        order = await sync_to_async(self.order_of_two)()
        client = await sync_to_async(self.watcher)("BOTH_MONITORS")

        url = await sync_to_async(self.progress_url)(order)

        async def write_after_the_stream_opens():
            await asyncio.sleep(0.15)
            response = await sync_to_async(client.patch, thread_sensitive=True)(
                url, data=json.dumps({"prepared_qty": 1}),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200, response.content)

        task = asyncio.ensure_future(write_after_the_stream_opens())
        events = await self.listen(client, want=2)
        await task
        self.assertEqual(events[0][0], "ready")
        self.assertTrue(self.named(events, "change"), f"the write did not wake the stream: {events}")

        # What the board does on `change`: read with the version it holds.
        after = await sync_to_async(self.snapshot)(client, events[0][1]["version"])
        self.assertFalse(after["unchanged"])
        self.assertEqual(after["cursor"], "accepted")
        self.assertEqual([o["items"][0]["prepared_qty"] for o in after["orders"]], [1])

    async def test_a_cancel_wakes_the_stream_and_the_snapshot_drops_the_order(self):
        order = await sync_to_async(self.make_order)()
        client = await sync_to_async(self.watcher)("BOTH_MONITORS")

        async def cancel_after_the_stream_opens():
            await asyncio.sleep(0.15)
            response = await sync_to_async(client.patch, thread_sensitive=True)(
                reverse("orders:order-status", args=[order.id]),
                data=json.dumps({"status": "CANCELLED"}), content_type="application/json",
            )
            self.assertEqual(response.status_code, 200, response.content)

        task = asyncio.ensure_future(cancel_after_the_stream_opens())
        events = await self.listen(client, want=2)
        await task
        self.assertTrue(self.named(events, "change"))
        after = await sync_to_async(self.snapshot)(client, events[0][1]["version"])
        self.assertFalse(after["unchanged"])
        self.assertEqual(after["orders"], [], "a cancelled order is not waiting")

    async def test_the_version_the_stream_opens_with_is_a_cursor_the_snapshot_accepts(self):
        """`ready` and the snapshot mint versions the same way, so a board
        that opened quietly can confirm it is current for one row read."""
        await sync_to_async(self.make_order)()
        client = await sync_to_async(self.watcher)("BOTH_MONITORS")
        events = await self.listen(client, want=1)
        again = await sync_to_async(self.snapshot)(client, events[0][1]["version"])
        self.assertTrue(again["unchanged"])
        self.assertEqual(again["cursor"], "accepted")

"""10D1: what an open stream is allowed to carry, and for how long (D-019).

10C made an answer a screen can trust. This phase delivers it without the
screen asking, which introduces the thing that makes long connections
different from requests: **a request is authorized once and is over, a stream
is authorized once and then stays open all evening.** Every guarantee the rest
of the system gets from re-reading the database per request has to be
re-established here on purpose, or a volunteer who has been logged out keeps
watching the kitchen until they close the tab (BK-R038).

So the properties pinned here are mostly about *ending* a stream rather than
about feeding one:

* a change committed on another connection reaches it (the point of the hub);
* logout, expiry, PIN rotation and a role change end it, and the user chose
  the strongest form of this -- **revalidation before every event**, not on a
  timer;
* the authentication store failing emits nothing at all and ends the stream
  within a bound, rather than falling open;
* a screen is never told about changes it cannot see. The 10D1 card asks for
  this ("발생 빈도 정보 노출 거부") and D-059 accepted the opposite for the
  *version*, so the two are reconciled on the read side: the hub compares what
  each scope can actually see, which needs no lock and so does not reopen the
  deadlock D-059 refused;
* a screen that stops reading is reset, not buffered without limit.

The hub's own health is reported separately from the heartbeat, because
D-019 settles that a client stops polling on hub health plus a complete
snapshot -- never on "a heartbeat arrived".
"""

from __future__ import annotations

import asyncio
import json
from unittest import mock

from asgiref.sync import sync_to_async
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from orders.authentication import AuthError  # noqa: F401
from orders.models import (
    MenuItem, Order, OrderItem, OrderStatus, OrderType, Table,
)
from orders.roles import STATS
from orders.services import hub, revisions
from orders.tests.auth_support import AUTH_SETTINGS, login_client

# Short enough that a test does not wait on a kitchen's schedule, long enough
# that the loop is still doing the real thing rather than spinning.
# Fast enough that a test does not wait on a kitchen's schedule, and with the
# heartbeat well clear of the change so that "two events" means "ready and the
# change" rather than "ready and a beat that happened to be first".
FAST_HUB = {"HUB_POLL_SECONDS": 0.02, "HUB_HEARTBEAT_SECONDS": 0.6,
            "HUB_REVALIDATE_SECONDS": 0.2}
BEATING_HUB = {"HUB_POLL_SECONDS": 0.02, "HUB_HEARTBEAT_SECONDS": 0.05,
               "HUB_REVALIDATE_SECONDS": 30}


class StreamFixture:
    """A kitchen with orders of both classifications, and a way to watch it."""

    def setUp(self):
        super().setUp()
        self.table = Table.objects.create(number=7)
        self.menu = MenuItem.objects.create(name="Soup", price=6000)
        from django.db import transaction
        with transaction.atomic():
            revisions.mark()

    def make_order(self, *, mode=OrderType.DINE_IN, status=OrderStatus.PREPARING):
        from django.db import transaction
        with transaction.atomic():
            order = Order.objects.create(
                table=self.table, floor="B1", order_type="DINE_IN", status=status,
                total_price=6000, payment_method="CASH", received_cash_amount=6000,
            )
            OrderItem.objects.create(
                order=order, menu_item=self.menu, qty=1, unit_price=6000,
                service_mode=mode,
            )
            revisions.mark()
        return order

    def watcher(self, alias):
        """A signed-in client holding the refresh cookie the stream reads."""
        client = self.client_class()
        login_client(client, alias)
        return client

    def url(self):
        return reverse("orders:kitchen-stream")

    async def listen(self, client, *, want, timeout=5.0):
        """Open the stream and collect events until `want` of them arrive.

        Returns as soon as the stream ends, so a test asserting that something
        *closes* a stream does not wait for the timeout to prove it.
        """
        from django.test import AsyncClient

        async_client = AsyncClient()
        async_client.cookies = client.cookies
        response = await async_client.get(self.url())
        collected = []
        buffer = ""

        async def read():
            nonlocal buffer
            async for chunk in response:
                buffer += chunk.decode("utf-8")
                while "\n\n" in buffer:
                    block, buffer = buffer.split("\n\n", 1)
                    if not block.strip():
                        continue
                    lines = block.splitlines()
                    name = lines[0].removeprefix("event: ")
                    payload = json.loads(lines[1].removeprefix("data: "))
                    collected.append((name, payload))
                    if len(collected) >= want:
                        return

        try:
            await asyncio.wait_for(read(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        finally:
            await sync_to_async(response.close, thread_sensitive=True)()
        return collected

    def named(self, events, name):
        return [payload for event, payload in events if event == name]


@override_settings(**AUTH_SETTINGS, **FAST_HUB)
class TheStreamRefusesStrangersTests(StreamFixture, TransactionTestCase):
    """A stream is an API, so a refusal is JSON and not a login page."""

    async def test_an_anonymous_caller_is_refused_in_json(self):
        from django.test import AsyncClient

        response = await AsyncClient().get(self.url())
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["Content-Type"], "application/json")

    async def test_a_caller_without_a_reading_permission_is_refused(self):
        client = await sync_to_async(self.watcher)("SERVING")
        from django.test import AsyncClient

        async_client = AsyncClient()
        async_client.cookies = client.cookies
        response = await async_client.get(self.url())
        self.assertEqual(response.status_code, 403)

    async def test_the_stream_is_never_cached(self):
        client = await sync_to_async(self.watcher)("HALL_MONITOR")
        events = await self.listen(client, want=1)
        self.assertTrue(events, "the stream said nothing at all")


@override_settings(**AUTH_SETTINGS, **FAST_HUB)
class AChangeFromAnotherConnectionReachesTheStreamTests(
    StreamFixture, TransactionTestCase
):
    """The hub's whole reason: this worker did not make the change."""

    async def test_the_first_frame_says_where_the_screen_is(self):
        client = await sync_to_async(self.watcher)("STATS")
        events = await self.listen(client, want=1)
        self.assertEqual(events[0][0], "ready")
        self.assertIn("version", events[0][1])

    async def test_a_commit_elsewhere_arrives_as_a_version(self):
        client = await sync_to_async(self.watcher)("STATS")

        async def change_after_the_stream_opens():
            await asyncio.sleep(0.15)
            await sync_to_async(self.make_order, thread_sensitive=True)()

        task = asyncio.ensure_future(change_after_the_stream_opens())
        events = await self.listen(client, want=2)
        await task
        changes = self.named(events, "change")
        self.assertTrue(changes, f"no change event arrived: {events}")
        self.assertEqual(
            changes[0], {},
            "the frame carries no payload (D-058): the screen refetches, and "
            "anything put here would be data the hub decided not to filter",
        )


@override_settings(**AUTH_SETTINGS, **FAST_HUB)
class RevocationEndsAnOpenStreamTests(StreamFixture, TransactionTestCase):
    """The user chose revalidation before every event, not on a timer."""

    def revoke(self, client):
        from orders.authentication import revoke_refresh
        from django.conf import settings

        revoke_refresh(client.cookies[settings.JWT_REFRESH_COOKIE_NAME].value)

    async def test_a_revoked_device_stops_receiving(self):
        client = await sync_to_async(self.watcher)("STATS")

        async def revoke_then_change():
            await asyncio.sleep(0.15)
            await sync_to_async(self.revoke, thread_sensitive=True)(client)
            await sync_to_async(self.make_order, thread_sensitive=True)()

        task = asyncio.ensure_future(revoke_then_change())
        events = await self.listen(client, want=50, timeout=2.0)
        await task
        self.assertEqual(
            self.named(events, "change"), [],
            "a revoked device was told about a change",
        )
        self.assertTrue(
            self.named(events, "closed"),
            f"the stream neither ended nor said why: {[e for e, _ in events]}",
        )

    async def test_a_deactivated_account_stops_receiving(self):
        client = await sync_to_async(self.watcher)("STATS")

        def deactivate():
            from orders.models import Account
            Account.objects.filter(name="stats").update(is_active=False)

        async def deactivate_then_change():
            await asyncio.sleep(0.15)
            await sync_to_async(deactivate, thread_sensitive=True)()
            await sync_to_async(self.make_order, thread_sensitive=True)()

        task = asyncio.ensure_future(deactivate_then_change())
        events = await self.listen(client, want=50, timeout=2.0)
        await task
        self.assertEqual(self.named(events, "change"), [])
        self.assertTrue(self.named(events, "closed"))

    async def test_a_role_change_ends_the_stream_instead_of_narrowing_it(self):
        """The queue was filled for a scope the caller no longer has.

        Ending is what discards it. Narrowing in place would mean deciding,
        for every event already queued, whether the *new* permissions may see
        it -- and the events carry no payload to decide with.
        """
        client = await sync_to_async(self.watcher)("STATS")

        def take_stats_away():
            from orders.models import Account
            Account.objects.filter(name="stats").update(can_view_stats=True, can_monitor_hall=True)

        async def change_the_role_then_the_board():
            await asyncio.sleep(0.15)
            await sync_to_async(take_stats_away, thread_sensitive=True)()
            await sync_to_async(self.make_order, thread_sensitive=True)()

        task = asyncio.ensure_future(change_the_role_then_the_board())
        events = await self.listen(client, want=50, timeout=2.0)
        await task
        closed = self.named(events, "closed")
        self.assertTrue(closed, f"the role change did not end it: {events}")
        self.assertEqual(closed[-1].get("reason"), "reauthenticate")


    async def test_rotating_the_event_password_cuts_every_stream_off(self):
        """D-045's "rotate the password, log every device out", on a stream.

        There is no sweep that sets `revoked_at`: the fingerprint comparison
        *is* the revocation. The first version of the hub re-listed the
        conditions by hand and left that one out, so a rotation stopped every
        request and none of the open streams -- a device that should have been
        cut off kept learning that the kitchen was busy. A security review
        found it; this is what would have.
        """
        client = await sync_to_async(self.watcher)("STATS")

        async def rotate_then_change():
            await asyncio.sleep(0.15)
            with override_settings(EVENT_PASSWORD_HASH="a-different-hash"):
                await sync_to_async(self.make_order, thread_sensitive=True)()
                await asyncio.sleep(0.4)

        task = asyncio.ensure_future(rotate_then_change())
        events = await self.listen(client, want=50, timeout=2.0)
        await task
        self.assertEqual(
            self.named(events, "change"), [],
            "a device whose credential was rotated was told about a change",
        )
        self.assertTrue(self.named(events, "closed"))

    async def test_a_revoked_screen_is_dropped_even_when_nothing_is_cooking(self):
        """"Before every event" is no bound at all on a quiet board.

        The change-triggered pass is still the first one to run; this is the
        floor underneath it, so a logged-out screen does not sit there
        receiving heartbeats until somebody happens to cook something.
        """
        client = await sync_to_async(self.watcher)("STATS")

        async def revoke_and_change_nothing():
            await asyncio.sleep(0.15)
            from orders.authentication import revoke_refresh
            from django.conf import settings as live

            await sync_to_async(revoke_refresh, thread_sensitive=True)(
                client.cookies[live.JWT_REFRESH_COOKIE_NAME].value
            )

        task = asyncio.ensure_future(revoke_and_change_nothing())
        events = await self.listen(client, want=50, timeout=3.0)
        await task
        closed = self.named(events, "closed")
        self.assertTrue(closed, f"a revoked screen stayed attached: {events}")
        self.assertEqual(closed[-1]["reason"], "revoked")


@override_settings(**AUTH_SETTINGS, **FAST_HUB)
class TheAuthenticationStoreFailingFailsClosedTests(
    StreamFixture, TransactionTestCase
):
    """"인증저장소 오류 상한" -- the bound is zero events, then the stream ends."""

    async def test_no_event_is_sent_while_the_store_cannot_be_read(self):
        client = await sync_to_async(self.watcher)("STATS")

        async def break_the_store_then_change():
            await asyncio.sleep(0.15)
            await sync_to_async(self.make_order, thread_sensitive=True)()

        with mock.patch.object(hub, "_still_allowed", side_effect=AuthError()):
            task = asyncio.ensure_future(break_the_store_then_change())
            events = await self.listen(client, want=50, timeout=2.0)
            await task
        self.assertEqual(
            self.named(events, "change"), [],
            "an event was emitted without a fresh authorization check",
        )
        self.assertTrue(self.named(events, "closed"))


@override_settings(**AUTH_SETTINGS, **FAST_HUB)
class AScreenIsNotToldAboutWhatItCannotSeeTests(
    StreamFixture, TransactionTestCase
):
    """The card's "발생 빈도 정보 노출 거부", reconciled with D-059.

    D-059 kept one global marker and accepted that the *version* moves for
    everyone; splitting the marker would have meant splitting a write lock.
    The hub does not need that: it compares what each scope can see, on the
    read side, where there is no lock to order.
    """

    async def test_a_hall_change_does_not_wake_a_takeout_screen(self):
        client = await sync_to_async(self.watcher)("TAKEOUT_MONITOR")

        async def change_only_the_hall():
            await asyncio.sleep(0.15)
            await sync_to_async(self.make_order, thread_sensitive=True)(
                mode=OrderType.DINE_IN
            )

        task = asyncio.ensure_future(change_only_the_hall())
        events = await self.listen(client, want=50, timeout=1.2)
        await task
        self.assertEqual(
            self.named(events, "change"), [],
            "a takeout screen learned that the hall is busy",
        )

    async def test_a_takeout_change_does_wake_a_takeout_screen(self):
        """The other half: the filter must not be silence."""
        client = await sync_to_async(self.watcher)("TAKEOUT_MONITOR")

        async def change_the_takeout():
            await asyncio.sleep(0.15)
            await sync_to_async(self.make_order, thread_sensitive=True)(
                mode=OrderType.TAKEOUT
            )

        task = asyncio.ensure_future(change_the_takeout())
        events = await self.listen(client, want=2, timeout=2.0)
        await task
        self.assertTrue(
            self.named(events, "change"),
            f"a takeout screen was not told about its own order: {events}",
        )


@override_settings(**AUTH_SETTINGS, **FAST_HUB)
class WhatTheChangeFrameIsAllowedToCarryTests(StreamFixture, TransactionTestCase):
    """The scope filter's saving must not be handed back in the payload.

    The counter is global. An earlier version put the snapshot version in the
    frame, so a takeout screen correctly not woken by twenty hall changes saw
    its next version jump by twenty -- and the gap is the count of what it was
    not told about. The card's "발생 빈도 정보 노출 거부" was claimed while that
    was true.
    """

    async def test_a_change_frame_carries_nothing_that_counts_other_scopes(self):
        client = await sync_to_async(self.watcher)("TAKEOUT_MONITOR")

        async def hall_churn_then_a_takeout_order():
            await asyncio.sleep(0.15)
            for _ in range(3):
                await sync_to_async(self.make_order, thread_sensitive=True)(
                    mode=OrderType.DINE_IN
                )
            await sync_to_async(self.make_order, thread_sensitive=True)(
                mode=OrderType.TAKEOUT
            )

        task = asyncio.ensure_future(hall_churn_then_a_takeout_order())
        events = await self.listen(client, want=2, timeout=3.0)
        await task
        changes = self.named(events, "change")
        self.assertTrue(changes, f"the takeout order never arrived: {events}")
        self.assertNotIn(
            "version", changes[0],
            "the frame carries a global counter the screen was not meant to see",
        )


@override_settings(**AUTH_SETTINGS, **BEATING_HUB)
class AStoppedHubDoesNotReportItselfHealthyTests(
    StreamFixture, TransactionTestCase
):
    """`failures` only moves when a read *fails*.

    Every other way the poller can stop -- cancelled, an exception escaping
    the loop, a hub that never started -- leaves `failures` at 0 and
    `last_ok` set. Without a staleness term the frame would say `hub_ok: true`
    forever while nothing polled, and 10D2 stops polling on that word.
    """

    async def test_health_goes_stale_when_the_poller_stops(self):
        """Subscribed directly: a stream would take its hub with it on close."""
        await sync_to_async(self.make_order, thread_sensitive=True)()
        subscription = hub.subscribe("watching", (STATS,))
        try:
            await asyncio.sleep(0.2)
            running = hub._hubs.get(asyncio.get_running_loop())
            self.assertIsNotNone(running, "no hub was ever started")
            self.assertTrue(running.health().ok, "it was healthy a moment ago")
            self.assertTrue(hub.health().ok)

            self.assertIsNotNone(running.task)
            running.task.cancel()
            await asyncio.sleep(0.9)  # past three ticks and the floor
            self.assertEqual(
                running.failures, 0,
                "nothing failed -- which is exactly why `failures` cannot be "
                "the only term in `ok`",
            )
            self.assertFalse(
                running.health().ok,
                "the poller was cancelled and the hub still called itself "
                "healthy; every screen would stop polling and go dark",
            )
        finally:
            hub.unsubscribe(subscription)


@override_settings(**AUTH_SETTINGS, **BEATING_HUB)
class TheHubSaysWhetherItIsHealthyTests(StreamFixture, TransactionTestCase):
    """D-019: a client stops polling on hub health, never on a heartbeat.

    So "a frame arrived" and "the hub last reached the database successfully"
    have to be two different facts in the frame, or the client cannot tell
    them apart -- which is precisely the failure the decision names.
    """

    async def test_a_heartbeat_carries_the_hubs_last_success(self):
        client = await sync_to_async(self.watcher)("STATS")
        events = await self.listen(client, want=2, timeout=2.0)
        beats = self.named(events, "heartbeat")
        self.assertTrue(beats, f"no heartbeat in {[e for e, _ in events]}")
        self.assertIn("hub_ok", beats[0])
        self.assertIn("stale_ms", beats[0])

    async def test_a_heartbeat_still_arrives_when_the_hub_cannot_reach_the_db(self):
        """The distinction, forced: beats continue and say the hub is down."""
        client = await sync_to_async(self.watcher)("STATS")
        with mock.patch.object(hub, "_read_state", side_effect=OSError("down")):
            events = await self.listen(client, want=4, timeout=2.0)
        beats = self.named(events, "heartbeat")
        self.assertTrue(beats, "the heartbeat stopped when the hub did")
        self.assertFalse(
            beats[-1]["hub_ok"],
            "the hub could not read the database but said it was healthy",
        )


@override_settings(**AUTH_SETTINGS, **FAST_HUB)
class ASlowScreenIsResetNotBufferedTests(StreamFixture, TransactionTestCase):
    """BK-R040: an unbounded queue per slow consumer is how a worker dies."""

    def test_the_queue_has_a_ceiling(self):
        self.assertLess(hub.MAX_QUEUED_EVENTS, 100)

    async def test_a_backed_up_screen_is_told_to_start_over(self):
        """Dropping events is safe here and dropping them silently is not.

        Under a convergence contract the screen only needs to know *that* it
        is behind, so a full queue collapses to one "reset" rather than
        growing -- but it must still be told, or it waits for a change that
        already happened.
        """
        subscription = hub.Subscription(session_id="s", permissions=(STATS,))
        for _ in range(hub.MAX_QUEUED_EVENTS + 5):
            subscription.offer({"version": "v"})
        self.assertLessEqual(subscription.pending(), hub.MAX_QUEUED_EVENTS)
        self.assertTrue(
            subscription.overflowed,
            "the screen fell behind and nothing recorded it",
        )


class GivingASlotBackTwiceDoesNotLowerTheCeilingTests(TransactionTestCase):
    """Two paths end a stream and both must be safe to take.

    The generator's `finally` runs on the ordinary path; the response's
    resource closer runs when the response is closed without ever being
    iterated. An earlier version registered `lambda: None` as that closer, so
    the net was inert and a dropped connection leaked a slot for the life of
    the worker. Making the closer real then makes double release possible, and
    a slot returned twice lowers the ceiling permanently -- the same failure,
    just slower to notice. So the test is for both halves at once.
    """

    def test_releasing_twice_counts_once(self):
        from orders.views import stream

        before = stream._open_streams
        self.assertTrue(stream._claim())
        give_back = stream._releaser(
            hub.Subscription(session_id="never-subscribed", permissions=())
        )
        give_back()
        give_back()
        self.assertEqual(stream._open_streams, before)

    def test_giving_back_works_outside_an_event_loop(self):
        """Where the inert closer would have been replaced by a raising one.

        A response's resource closer can run outside the loop that opened the
        stream. Looking the hub up by the *running* loop would raise there and
        leave the slot claimed -- swapping a silent leak for a noisy one.
        """
        from orders.views import stream

        before = stream._open_streams
        self.assertTrue(stream._claim())
        stream._releaser(
            hub.Subscription(session_id="never-subscribed", permissions=())
        )()
        self.assertEqual(stream._open_streams, before)

"""10F: a change is an event before it is a poll (D-068).

10E measured the hub's `HUB_POLL_SECONDS` wait as nearly all of the p95
display lag. So `revisions.mark()` now announces itself with a PostgreSQL
NOTIFY in the marking transaction, and each worker's hub holds one LISTEN
connection that wakes the reader at once. What is pinned here:

* the announcement is delivered on commit and never for a rollback;
* an open stream learns of a change well inside the poll interval;
* with the LISTEN path unavailable, the poll still carries the change and
  the hub's health -- which only ever counted the poll -- is unchanged.
"""

from __future__ import annotations

import asyncio
import time
from unittest import mock

import psycopg
from asgiref.sync import sync_to_async
from django.db import transaction
from django.test import TransactionTestCase, override_settings

from orders.services import hub, revisions
from orders.tests.auth_support import AUTH_SETTINGS
from orders.tests.test_sse_server import StreamFixture

def _capture_hub(holder: dict):
    """Keep hold of the hub a stream registers: `unsubscribe` drops it from the
    registry with the last screen, which is before a test can look at it."""
    original = hub._for_this_loop

    def spy():
        holder["hub"] = original()
        return holder["hub"]

    return mock.patch.object(hub, "_for_this_loop", spy)


SLOW_POLL = {"HUB_POLL_SECONDS": 5.0, "HUB_HEARTBEAT_SECONDS": 10.0,
             "HUB_REVALIDATE_SECONDS": 30.0}
FAST_POLL = {"HUB_POLL_SECONDS": 0.05, "HUB_HEARTBEAT_SECONDS": 10.0,
             "HUB_REVALIDATE_SECONDS": 30.0}


class MarkAnnouncesItselfOnCommitTests(StreamFixture, TransactionTestCase):
    def _ear(self):
        conn = psycopg.connect(hub._listen_conninfo(), autocommit=True)
        conn.execute(f"LISTEN {revisions.NOTIFY_CHANNEL}")
        self.addCleanup(conn.close)
        return conn

    def test_a_committed_mark_is_announced_with_its_value(self):
        ear = self._ear()
        self.make_order()
        heard = list(ear.notifies(timeout=2.0, stop_after=1))
        self.assertEqual(len(heard), 1, "no notification arrived for a committed mark")
        self.assertEqual(heard[0].channel, revisions.NOTIFY_CHANNEL)
        self.assertEqual(heard[0].payload, str(revisions.current()))

    def test_a_rolled_back_mark_is_not_announced(self):
        ear = self._ear()
        try:
            with transaction.atomic():
                revisions.mark()
                raise RuntimeError("abandon this write")
        except RuntimeError:
            pass
        self.assertEqual(list(ear.notifies(timeout=0.5)), [],
                         "a rollback must not wake any screen")


@override_settings(**AUTH_SETTINGS, **SLOW_POLL)
class TheEventPathBeatsThePollTests(StreamFixture, TransactionTestCase):
    """With a 5 s poll, only the LISTEN path can deliver a change in under 2 s."""

    async def test_a_change_arrives_without_waiting_for_the_poll(self):
        client = await sync_to_async(self.watcher)("STATS")
        marks = {}

        async def change_after_the_stream_opens():
            await asyncio.sleep(0.3)
            marks["written"] = time.monotonic()
            await sync_to_async(self.make_order, thread_sensitive=True)()

        held: dict = {}
        with _capture_hub(held):
            task = asyncio.ensure_future(change_after_the_stream_opens())
            events = await self.listen(client, want=2, timeout=4.0)
            marks["seen"] = time.monotonic()
            await task
        self.assertEqual([name for name, _ in events], ["ready", "change"], events)
        self.assertLess(marks["seen"] - marks["written"], 2.0,
                        "the change waited for the poll instead of the notification")
        self.assertGreaterEqual(held["hub"].notifications, 1)
        self.assertEqual(held["hub"].listen_failures, 0)


@override_settings(**AUTH_SETTINGS, **FAST_POLL)
class ThePollStillCarriesTheBoardWhenListeningFailsTests(StreamFixture, TransactionTestCase):
    async def test_a_change_arrives_by_polling_and_health_is_unchanged(self):
        client = await sync_to_async(self.watcher)("STATS")

        async def change_after_the_stream_opens():
            await asyncio.sleep(0.3)
            await sync_to_async(self.make_order, thread_sensitive=True)()

        def refuse(*args, **kwargs):
            raise psycopg.OperationalError("listen refused for the test")

        held: dict = {}
        with mock.patch.object(psycopg.AsyncConnection, "connect", side_effect=refuse), \
                _capture_hub(held):
            task = asyncio.ensure_future(change_after_the_stream_opens())
            events = await self.listen(client, want=2, timeout=4.0)
            await task
        running = held["hub"]
        self.assertEqual([name for name, _ in events], ["ready", "change"], events)
        self.assertFalse(running.listening)
        self.assertGreaterEqual(running.listen_failures, 1)
        self.assertEqual(running.notifications, 0)
        self.assertTrue(running.health().ok, "a listener outage is not a hub failure")
        self.assertEqual(running.failures, 0)


class TheListenerLeavesWithTheLastScreenTests(TransactionTestCase):
    @override_settings(**AUTH_SETTINGS, **FAST_POLL)
    async def test_no_subscriptions_means_no_listen_connection(self):
        from orders.roles import STATS

        # A direct subscription has no device row, so revalidation would
        # revoke it at once; the identity check is answered for it here.
        allowed = {"watching": tuple(sorted(str(code) for code in (STATS,)))}
        with mock.patch.object(hub, "_still_allowed", lambda ids: allowed):
            subscription = hub.subscribe("watching", (STATS,))
            await asyncio.sleep(0.4)
            running = hub._hubs.get(asyncio.get_running_loop())
            self.assertIsNotNone(running)
            self.assertTrue(running.listening, "the listener never connected")
            hub.unsubscribe(subscription)
            await asyncio.sleep(0.2)
        self.assertFalse(running.listening)
        self.assertIsNone(running.listener)

    @override_settings(**AUTH_SETTINGS, **FAST_POLL)
    async def test_a_screen_reconnecting_at_once_gets_a_fresh_listener(self):
        """Cancel only asks; `add()` on the next turn must not trust `done()`."""
        from orders.roles import STATS

        allowed = {"watching": tuple(sorted(str(code) for code in (STATS,)))}
        with mock.patch.object(hub, "_still_allowed", lambda ids: allowed):
            first = hub.subscribe("watching", (STATS,))
            await asyncio.sleep(0.4)
            running = hub._hubs.get(asyncio.get_running_loop())
            old_task = running.listener
            hub.unsubscribe(first)          # drops the hub from the registry too
            running.add(hub.Subscription(session_id="watching", permissions=(STATS,)))
            self.assertIsNot(running.listener, old_task, "no fresh listener was started")
            await asyncio.sleep(0.4)
            self.assertTrue(running.listening, "the replacement listener never connected")
            self.assertTrue(old_task.done())
            running.remove(running.subscriptions[0])
            await asyncio.sleep(0.2)
        self.assertFalse(running.listening)

"""10A: what has to be true before SSE can stream at all (BK-R035).

`asgi.py` existing proves nothing. Three separate things have to hold, and
none of them is visible from reading the file:

1. **No synchronous middleware.** Django adapts a sync-only middleware by
   wrapping everything inside it in `async_to_sync`, so one such entry
   anywhere in the list puts every request through two thread hops. Measured
   at 32-way concurrency that is a consistently worse tail (p90 36-39ms to
   44-50ms). It is *not* a second event loop, which is what this module
   claimed until a test disproved it -- see the loop tests below.
2. **The request path stays async end to end**, with authentication and CSRF
   still in it. Removing them would make any handler pass.
3. **A stream releases its database connection.** Holding one open for the
   life of a stream turns the connection limit into a headcount of screens.

These tests fix the contract. They are not the acceptance evidence: the card
refuses a pass that comes from walking the iterator in-process, so the timing,
the concurrent ordinary request and the cleanup are measured against a real
uvicorn process behind nginx. See docs/modernization/ASGI_RUNTIME.md.
"""

import json
from unittest import mock

from asgiref.sync import sync_to_async
from django.core.handlers.asgi import ASGIHandler
from django.core.handlers.base import BaseHandler
from django.core.signals import request_finished
from django.db import close_old_connections
from django.test import (
    AsyncClient, TestCase, TransactionTestCase, override_settings,
)
from django.urls import reverse
from django.utils.module_loading import import_string

from orders.checks import STREAM_ASYNC_MIDDLEWARE, middleware_is_async_capable
from orders.tests.auth_support import AUTH_SETTINGS, login_client
from orders.views import stream_probe as stream

PROBE_ON = {**AUTH_SETTINGS, "STREAM_PROBE_ENABLED": True}


class MiddlewareStaysAsyncTests(TestCase):
    """The middleware list is the thing that decides whether ASGI is real."""

    def test_no_middleware_forces_the_request_into_a_thread(self):
        offenders = [
            path
            for path in self.settings_middleware()
            if not getattr(import_string(path), "async_capable", False)
        ]
        self.assertEqual(
            offenders, [],
            "These middleware are sync-only. Django wraps everything inside "
            "them in async_to_sync, so every request crosses two thread hops.",
        )

    def test_building_the_asgi_chain_inserts_no_sync_bridge(self):
        """The same fact, observed where it actually happens.

        A middleware could be marked async_capable and still be adapted if a
        sync-only one sits further out, so this watches Django build the chain
        rather than trusting the attributes alone.
        """
        bridges = []
        original = BaseHandler.adapt_method_mode

        def record(handler, is_async, method, method_is_async=None, **kwargs):
            from asgiref.sync import iscoroutinefunction

            resolved = (
                iscoroutinefunction(method) if method_is_async is None else method_is_async
            )
            # process_view and process_exception hooks are sync by definition
            # and are adapted one call at a time; only the request chain
            # itself decides whether the view is reached through a thread.
            if resolved and not is_async and kwargs.get("name"):
                bridges.append(kwargs["name"])
            return original(handler, is_async, method, method_is_async, **kwargs)

        BaseHandler.adapt_method_mode = record
        try:
            ASGIHandler()
        finally:
            BaseHandler.adapt_method_mode = original

        self.assertEqual(bridges, [], "async_to_sync was inserted around these.")

    def test_authentication_and_csrf_are_still_in_the_chain(self):
        """A pass that came from deleting these would mean nothing."""
        middleware = self.settings_middleware()
        self.assertIn("django.middleware.csrf.CsrfViewMiddleware", middleware)
        self.assertIn(
            "django.contrib.auth.middleware.AuthenticationMiddleware", middleware
        )
        self.assertIn("django.middleware.security.SecurityMiddleware", middleware)

    def settings_middleware(self):
        from django.conf import settings

        return list(settings.MIDDLEWARE)


class MiddlewareCheckTests(TestCase):
    """The startup check that keeps the list that way.

    Without it, adding a sync-only middleware fails nothing and shows
    nothing: the request path quietly stops being async and the only trace is
    a slower tail under load, months later, attributed to something else.
    """

    def test_the_real_middleware_list_passes(self):
        self.assertEqual(middleware_is_async_capable(None), [])

    def test_a_sync_only_middleware_is_refused_by_name(self):
        offender = "orders.tests.test_asgi_stream.SyncOnlyMiddleware"
        with self.settings(MIDDLEWARE=[offender]):
            errors = middleware_is_async_capable(None)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].id, STREAM_ASYNC_MIDDLEWARE)
        self.assertIn(offender, errors[0].msg)

    def test_an_unimportable_middleware_is_left_to_django(self):
        """Django's own check says it better; saying it twice would make the
        real message harder to find."""
        with self.settings(MIDDLEWARE=["orders.nothing.here.Middleware"]):
            self.assertEqual(middleware_is_async_capable(None), [])


class SyncOnlyMiddleware:
    """Stands in for a third-party middleware with no async path."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)


@override_settings(**AUTH_SETTINGS)
class StreamProbeIsOffByDefaultTests(TestCase):
    """The new path does not exist until someone turns it on."""

    def test_the_probe_is_absent_without_the_setting(self):
        login_client(self.client, "ORDER")
        response = self.client.get(reverse("orders:stream-probe"))
        self.assertEqual(response.status_code, 404)

    def test_being_absent_is_decided_before_credentials_are_read(self):
        """A disabled route answers the same to everyone.

        Refusing with 401 first would tell an unauthenticated caller that the
        route exists and is merely switched off.
        """
        response = self.client.get(reverse("orders:stream-probe"))
        self.assertEqual(response.status_code, 404)


@override_settings(**PROBE_ON)
class StreamProbeAuthenticationTests(TestCase):
    """Enabled, it is still an authenticated endpoint."""

    def test_no_credentials_are_refused_in_json(self):
        response = self.client.get(reverse("orders:stream-probe"))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["Content-Type"], "application/json")

    def test_a_signed_in_account_gets_an_event_stream(self):
        login_client(self.client, "ORDER")
        response = self.client.get(reverse("orders:stream-probe"), {"frames": 2})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.streaming)
        self.assertEqual(response.headers["Content-Type"], "text/event-stream")
        # nginx buffers a proxied response by default, which would hold every
        # frame until the stream ended. The location block turns buffering off;
        # this header says so again for any proxy the location does not cover.
        self.assertEqual(response.headers["X-Accel-Buffering"], "no")
        self.assertIn("no-store", response.headers["Cache-Control"])
        # Nothing read this stream, so nothing has given its slot back yet.
        # A server always closes the response; a test has to say so.
        close_like_a_server(response)


def close_like_a_server(response):
    """Close a response the way Django's own test client closes one.

    `HttpResponseBase.close()` fires `request_finished`, and in a `TestCase`
    that closes the connection the wrapping transaction is running on -- every
    later query in the class then fails with "the connection is closed".
    Django's test client guards its own `close()` calls exactly this way
    (django/test/client.py); calling it raw is what a test gets wrong, not
    what a server does.
    """
    request_finished.disconnect(close_old_connections)
    try:
        response.close()
    finally:
        request_finished.connect(close_old_connections)


class StreamReader:
    """Reads the probe over the async request path and splits it into events."""

    async def events(self, **params):
        client = AsyncClient()
        response = await client.get(
            reverse("orders:stream-probe"), params,
            headers={"authorization": self.token},
        )
        body = b""
        async for chunk in response:
            body += chunk
        parsed = []
        for block in body.decode("utf-8").split("\n\n"):
            if not block.strip():
                continue
            name = block.splitlines()[0].removeprefix("event: ")
            payload = json.loads(block.splitlines()[1].removeprefix("data: "))
            parsed.append((name, payload))
        return parsed

    def probes(self, events):
        return [payload for name, payload in events if name == "probe"]


@override_settings(**PROBE_ON)
class StreamProbeContentTests(StreamReader, TestCase):
    """What the frames say. The timing between them is measured elsewhere."""

    def setUp(self):
        login_client(self.client, "ORDER")
        self.token = self.client.defaults["HTTP_AUTHORIZATION"]

    async def test_frames_arrive_numbered_and_in_order(self):
        events = await self.events(frames=4, interval_ms=10)
        self.assertEqual([p["seq"] for p in self.probes(events)], [0, 1, 2, 3])

    async def test_the_stream_says_when_it_is_finished(self):
        events = await self.events(frames=2, interval_ms=10)
        self.assertEqual(events[-1][0], "done")
        self.assertEqual(events[-1][1], {"frames": 2})

    async def test_a_caller_cannot_ask_for_an_unbounded_stream(self):
        """The probe is an instrument, not a way to pin a worker."""
        events = await self.events(frames=100000, interval_ms=0)
        self.assertEqual(len(self.probes(events)), 200)

    async def test_nonsense_parameters_fall_back_instead_of_failing(self):
        """A measuring tool that refuses a typo wastes the run it was set up
        for. Out-of-range numbers are clamped and unreadable ones default."""
        events = await self.events(frames="많이", interval_ms="빨리")
        self.assertEqual(len(self.probes(events)), 5)
        self.assertEqual(events[-1][0], "done")

    async def test_the_generator_is_closed_when_the_stream_ends(self):
        before = stream.closed_streams
        await self.events(frames=2, interval_ms=0)
        self.assertEqual(stream.closed_streams, before + 1)


@override_settings(**PROBE_ON)
class OneLoopEitherWayTests(StreamReader, TestCase):
    """The hazard this repository claimed, and what running it showed.

    `orders/checks.py` was first written against the worry that a sync-only
    middleware makes Django run the view in a *second* event loop, so that
    anything loop-bound the view hands to its generator -- 10D1's hub queue --
    would be stranded. These two tests were written to demonstrate that, and
    the second one failed: asgiref hands the inner coroutine back to the
    original loop (`AsyncToSync.__call__` reuses `main_event_loop` when it is
    called from inside a `SyncToAsync` thread), so the loop is the same either
    way.

    They are kept, inverted, because the belief is the kind that comes back.
    What a sync-only middleware really costs is thread hops, and that is
    measured in the check's own docstring.
    """

    def setUp(self):
        login_client(self.client, "ORDER")
        self.token = self.client.defaults["HTTP_AUTHORIZATION"]

    async def test_the_view_and_its_generator_share_one_loop(self):
        events = await self.events(frames=2, interval_ms=0)
        self.assertTrue(all(p["same_loop"] for p in self.probes(events)))

    async def test_a_sync_middleware_does_not_take_that_away(self):
        """If this ever fails, the stranded-queue hazard became real and
        10D1 has to hold its queue somewhere other than the view."""
        from django.conf import settings

        broken = ["orders.tests.test_asgi_stream.SyncOnlyMiddleware", *settings.MIDDLEWARE]
        with override_settings(MIDDLEWARE=broken):
            events = await self.events(frames=2, interval_ms=0)
        self.assertTrue(all(p["same_loop"] for p in self.probes(events)))


@override_settings(**PROBE_ON)
class StreamAdmissionTests(StreamReader, TestCase):
    """How many streams one worker will hold (PR #76 security review).

    The frame bounds limit how long one stream lasts, not how many a caller
    may start, and the measurement showed each open stream occupies a worker
    thread. Without a ceiling, any signed-in device -- this endpoint uses the
    "any authenticated account" sentinel -- can grow a worker's thread count
    for as long as the switch is on.
    """

    def setUp(self):
        login_client(self.client, "ORDER")
        self.token = self.client.defaults["HTTP_AUTHORIZATION"]
        self.url = reverse("orders:stream-probe")

    def only_room_for(self, count):
        """Admission limited to `count`, on an empty worker.

        The counter is process-wide, and an earlier test that never read its
        response legitimately leaves a slot held. Starting from a known zero
        is what makes this about admission rather than about the order the
        suite happens to run in.
        """
        return mock.patch.multiple(
            "orders.views.stream_probe", MAX_OPEN_STREAMS=count, _open_streams=0
        )

    async def open_one(self):
        return await AsyncClient().get(
            self.url, {"frames": 3, "interval_ms": 0},
            headers={"authorization": self.token},
        )

    async def test_a_worker_refuses_more_streams_than_it_will_hold(self):
        with self.only_room_for(1):
            held = await self.open_one()
            self.assertEqual(held.status_code, 200)
            refused = await self.open_one()
            self.assertEqual(refused.status_code, 503)
            self.assertEqual(refused.headers["Retry-After"], "5")
            async for _ in held:  # draining it closes the response
                pass
            self.assertEqual((await self.open_one()).status_code, 200)

    async def test_a_stream_nobody_reads_still_gives_its_slot_back(self):
        """The leak this is written against: a response created and then
        closed without ever being iterated never runs the generator's
        `finally`, so a claim released only there would be lost for the life
        of the process and the ceiling would fall by one each time."""
        with self.only_room_for(1):
            abandoned = await self.open_one()
            self.assertEqual(abandoned.status_code, 200)
            await sync_to_async(close_like_a_server)(abandoned)
            self.assertEqual((await self.open_one()).status_code, 200)

    async def test_a_finished_stream_gives_its_slot_back(self):
        """A delta, not an absolute: the counter is process-wide and a test
        that never reads its response legitimately leaves a slot held until
        something closes it, which is the behaviour above."""
        before = stream._open_streams
        events = await self.events(frames=2, interval_ms=0)
        self.assertEqual(events[-1][0], "done")
        self.assertEqual(stream._open_streams, before)


@override_settings(**PROBE_ON)
class StreamReleasesItsConnectionTests(StreamReader, TransactionTestCase):
    """Authentication reads the database. The stream must not keep it.

    A `TransactionTestCase` on purpose: `TestCase` wraps every request in a
    transaction, and a connection inside one cannot be released at all -- so
    the test that matters most here is the one `TestCase` cannot run.

    For a streaming response, Django ends the request when the last frame is
    sent. Left to that, one kitchen display would hold a connection for as
    long as someone is looking at it.
    """

    def setUp(self):
        login_client(self.client, "ORDER")
        self.token = self.client.defaults["HTTP_AUTHORIZATION"]

    async def test_no_connection_is_held_once_the_frames_start(self):
        events = await self.events(frames=3, interval_ms=0)
        self.assertEqual([p["db_open"] for p in self.probes(events)],
                         [False, False, False])

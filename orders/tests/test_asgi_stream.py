"""10A: what has to be true before SSE can stream at all (BK-R035).

`asgi.py` existing proves nothing. Three separate things have to hold, and
none of them is visible from reading the file:

1. **No synchronous middleware.** Django adapts a sync-only middleware by
   wrapping everything inside it in `async_to_sync`. One such entry anywhere in
   the list moves the view -- and the async generator it returns -- into a
   second event loop on a borrowed thread. The stream may still work by luck;
   a hub queue created in that loop (10D1) will not.
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

from django.core.handlers.asgi import ASGIHandler
from django.core.handlers.base import BaseHandler
from django.test import (
    AsyncClient, TestCase, TransactionTestCase, override_settings,
)
from django.urls import reverse
from django.utils.module_loading import import_string

from orders.checks import STREAM_ASYNC_MIDDLEWARE, middleware_is_async_capable
from orders.tests.auth_support import AUTH_SETTINGS, login_client
from orders.views import stream

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
            "them in async_to_sync, so the view runs in another event loop.",
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
            # and are adapted one call at a time; only the request chain itself
            # can move the view into another loop.
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

    Without it, adding a sync-only middleware fails nothing: the request path
    quietly stops being async and the next thing to notice is a hub queue
    bound to the wrong event loop, months later.
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

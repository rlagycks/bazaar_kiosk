"""4B2: the browser talks to this server and nowhere else (BK-R018, BK-R029).

The kitchen board loaded a third-party Realtime SDK from a CDN, was handed a
project URL and an anonymous key in its own HTML, and subscribed directly to
table changes. That put a second trust boundary next to Django's: the key
reached every screen, and whether the subscription could read more than the
board displayed depended on external Row Level Security nobody here could
verify. Removing the SDK does not retire the external grants -- that cleanup
is a separate, approved task -- but it does end the browser's part in it.

The user's instruction (2026-09-20) was to drop the polling fallback with it,
because this is not in service yet and D-018's own SSE transport is the
destination (10D). So the board is deliberately not self-updating until then,
and has to say so: a board that looks live but is frozen is the same failure
8B just removed.
"""

import re

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from orders.tests.auth_support import AUTH_SETTINGS, login_client
from django.test import override_settings

TEMPLATES = "orders/templates/orders/"
LIVE_TEMPLATES = ("order.html", "b1_counter.html", "kitchen_supervisor.html")

EXTERNAL_SCRIPT = re.compile(r"""<script[^>]*\ssrc\s*=\s*["'](?!\{%\s*static)[^"']*//""", re.I)
FOREIGN = re.compile(r"supabase|createClient|postgres_changes|realtime|cdn\.|jsdelivr|unpkg", re.I)
# Naming one vendor only closes one door. These two pin the property itself:
# nothing in a live screen addresses another origin, by any API (PR #74
# security review). `//` catches protocol-relative URLs too.
ABSOLUTE_URL = re.compile(r"""["'`](?:https?:)?//[^"'`\s]+""", re.I)
REMOTE_API = re.compile(r"new\s+(?:EventSource|WebSocket|SharedWorker|Worker)\s*\(|importScripts\s*\(", re.I)


def read(name):
    return (settings.BASE_DIR / TEMPLATES / name).read_text(encoding="utf-8")


class NoExternalCodeOrKeysTests(TestCase):
    def test_no_live_template_loads_a_script_from_another_origin(self):
        for name in LIVE_TEMPLATES:
            with self.subTest(template=name):
                self.assertIsNone(EXTERNAL_SCRIPT.search(read(name)),
                                  f"{name} still loads a script from off this server")

    def test_no_live_template_mentions_the_external_service_at_all(self):
        for name in LIVE_TEMPLATES:
            with self.subTest(template=name):
                found = FOREIGN.findall(read(name))
                self.assertEqual(found, [], f"{name} still refers to {set(found)}")

    def test_no_live_template_writes_an_absolute_url_anywhere(self):
        """Not just in a script tag. An inline `fetch("https://...")` or a
        protocol-relative URL in any attribute would leave this server."""
        for name in LIVE_TEMPLATES:
            with self.subTest(template=name):
                found = ABSOLUTE_URL.findall(read(name))
                self.assertEqual(found, [], f"{name} addresses another origin: {found}")

    def test_no_live_template_opens_a_stream_or_a_worker(self):
        """The transports a URL check alone would not make obvious. When
        10D adds SSE it will be to this server, and this test is where that
        change has to be stated rather than slipped in."""
        for name in LIVE_TEMPLATES:
            with self.subTest(template=name):
                found = REMOTE_API.findall(read(name))
                self.assertEqual(found, [], f"{name} opens {found}")

    def test_the_view_layer_hands_no_external_configuration_to_a_page(self):
        source = (settings.BASE_DIR / "orders/views/pages.py").read_text(encoding="utf-8")
        self.assertNotIn("supabase", source.lower())

    def test_the_settings_no_longer_carry_realtime_credentials(self):
        for name in ("SUPABASE_URL", "SUPABASE_ANON_KEY"):
            with self.subTest(setting=name):
                self.assertFalse(hasattr(settings, name),
                                 f"{name} is still a setting; a value in the environment would still be read")

    def test_the_environment_example_no_longer_offers_them(self):
        example = (settings.BASE_DIR / ".env.example").read_text(encoding="utf-8")
        self.assertNotIn("SUPABASE", example)


@override_settings(**AUTH_SETTINGS)
class RenderedPagesAreCleanTests(TestCase):
    """Source tests can miss a value injected at render time."""

    PAGES = (("orders:kitchen", "BOTH_MONITORS"), ("orders:order", "SERVING"),
             ("orders:b1-counter", "STATS"))

    def test_no_rendered_page_carries_an_external_origin_or_key(self):
        for name, alias in self.PAGES:
            with self.subTest(page=name):
                login_client(self.client, alias)
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200, response.content)
                body = response.content.decode()
                self.assertIsNone(FOREIGN.search(body), f"{name} still carries external references")
                self.assertIsNone(EXTERNAL_SCRIPT.search(body), f"{name} still loads external code")


SHARED_JS = "orders/static/orders/ui/"
# 10D2 will add a single EventSource/polling scheduler, and this fence is
# meant to expire then. Loosening it is how that change gets stated out loud
# instead of slipping in (PR #74 architecture review).
RESCHEDULING_TIMEOUT = re.compile(r"setTimeout\s*\(\s*(?:loadOrders|tick|poll|schedule)", re.I)


def read_js(name):
    return (settings.BASE_DIR / SHARED_JS / name).read_text(encoding="utf-8")


class TheBoardDoesNotPretendToBeLiveTests(TestCase):
    """No timer, and the screen says as much."""

    def test_nothing_schedules_a_repeating_reload(self):
        source = read("kitchen_supervisor.html")
        for pattern in ("setInterval", "AUTO_MS", "startPolling", "stopPolling"):
            with self.subTest(pattern=pattern):
                self.assertNotIn(pattern, source)

    def test_no_shared_script_schedules_a_reload_either(self):
        """The fence has to cover the files the page also loads, or a timer
        moved one directory over would pass."""
        import os

        for name in sorted(os.listdir(settings.BASE_DIR / SHARED_JS)):
            if not name.endswith(".js"):
                continue
            with self.subTest(script=name):
                source = read_js(name)
                self.assertNotIn("setInterval", source)
                self.assertIsNone(RESCHEDULING_TIMEOUT.search(source))

    def test_a_timeout_does_not_reschedule_the_list_read(self):
        """A `setTimeout` that re-arms itself is a timer under another name."""
        self.assertIsNone(RESCHEDULING_TIMEOUT.search(read("kitchen_supervisor.html")))

    def test_the_read_time_shown_is_the_list_read_not_the_redraw(self):
        """A single-card refresh redraws without reading the list. Stamping
        that moment made this notice claim a freshness it did not have
        (PR #74 architecture review)."""
        source = read("kitchen_supervisor.html")
        self.assertIn("LAST_LIST_READ_AT", source)
        render = source.split("function renderFromStore", 1)[1].split("function ", 1)[0]
        self.assertIn("LAST_LIST_READ_AT", render)
        self.assertNotIn("new Date()", render)

    def test_a_failed_read_keeps_the_cards_and_says_so(self):
        """Nothing retries now, so wiping the board on one dropped request
        would leave the kitchen with an empty screen."""
        source = read("kitchen_supervisor.html")
        failure = source.split("console.error('주문 불러오기 실패'", 1)[1][:600]
        self.assertNotIn("BOARD.innerHTML", failure)
        self.assertIn("STATUS.textContent", failure)

    def test_the_only_refresh_control_shows_that_it_heard_the_press(self):
        source = read("kitchen_supervisor.html")
        self.assertIn("RELOAD_BUTTON.disabled = true", source)
        self.assertIn("RELOAD_BUTTON.disabled = false", source)

    def test_the_screen_says_it_does_not_refresh_itself(self):
        """A stale board must not read as a quiet kitchen."""
        source = read("kitchen_supervisor.html")
        self.assertIn("자동 갱신", source)

    def test_returning_to_the_tab_reads_once_rather_than_starting_a_timer(self):
        source = read("kitchen_supervisor.html")
        self.assertIn("visibilitychange", source)
        handler = source.split("visibilitychange", 1)[1][:400]
        self.assertIn("loadOrders", handler)
        self.assertNotIn("setInterval", handler)

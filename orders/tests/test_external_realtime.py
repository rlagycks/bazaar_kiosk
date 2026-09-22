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
        """The transports a URL check alone would not make obvious. 10D2
        added the one SSE connection this project has, to this server, and
        it lives in `kitchen_live.js` behind a same-origin check -- see
        `test_realtime.py` and `scripts/test_kitchen_live.cjs`. No template
        opens one, and no other shared script does either."""
        for name in LIVE_TEMPLATES:
            with self.subTest(template=name):
                found = REMOTE_API.findall(read(name))
                self.assertEqual(found, [], f"{name} opens {found}")
        for name in shared_scripts():
            if name == "kitchen_live.js":
                continue
            with self.subTest(script=name):
                self.assertIsNone(REMOTE_API.search(read_js(name)), f"{name} opens a stream")

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
# 4B2 fenced off every timer until 10D2 brought the one scheduler that may
# arm them. The fence now says where a timer is allowed to live -- in
# `kitchen_live.js`, one-shot, and stopped while the stream is healthy (the
# node tests drive that) -- and that nothing else re-arms a read.
RESCHEDULING_TIMEOUT = re.compile(r"setTimeout\s*\(\s*(?:loadOrders|tick|poll|schedule)", re.I)
THE_SCHEDULER = "kitchen_live.js"


def read_js(name):
    return (settings.BASE_DIR / SHARED_JS / name).read_text(encoding="utf-8")


def shared_scripts():
    import os

    return sorted(n for n in os.listdir(settings.BASE_DIR / SHARED_JS) if n.endswith(".js"))


class TheBoardSaysHowLiveItIsTests(TestCase):
    """One scheduler, and the screen says which way it is being kept current."""

    def test_nothing_in_the_template_schedules_a_repeating_reload(self):
        source = read("kitchen_supervisor.html")
        for pattern in ("setInterval", "AUTO_MS", "startPolling", "stopPolling", "setTimeout"):
            with self.subTest(pattern=pattern):
                self.assertNotIn(pattern, source)

    def test_only_the_scheduler_arms_timers_and_never_a_repeating_one(self):
        """The fence has to cover the files the page also loads, or a timer
        moved one directory over would pass."""
        for name in shared_scripts():
            with self.subTest(script=name):
                source = read_js(name)
                self.assertNotIn("setInterval", source)
                if name != THE_SCHEDULER:
                    # The one exception outside the scheduler: auth.js waits
                    # a bounded, one-shot backoff between attempts of a
                    # refresh that lost a race (409). It re-reads nothing and
                    # never reschedules itself; the pattern below is what
                    # would catch it if it started to.
                    self.assertNotIn("setTimeout(", source.replace("window.setTimeout(resolve", ""))
                    self.assertIsNone(RESCHEDULING_TIMEOUT.search(source))

    def controller(self):
        self.assertIn("ui/monitor.js", read("kitchen_supervisor.html"))
        return (settings.BASE_DIR / "orders/static/orders/ui/monitor.js").read_text()

    def test_the_read_time_shown_is_the_list_read_not_the_redraw(self):
        handler = self.controller().split("function onLiveStatus", 1)[1].split("const live =", 1)[0]
        self.assertIn("clock(state.applied.at)", handler)
        self.assertNotIn("new Date()", handler)

    def test_a_status_report_redraws_the_line_and_not_the_cards(self):
        source = self.controller()
        handler = source.split("function onLiveStatus", 1)[1].split("const live =", 1)[0]
        self.assertIn("byId('live-status').textContent", handler)
        self.assertNotIn("DOM.render", handler)
        self.assertNotIn("drawSnapshot(", handler)
        apply = source.split("function drawSnapshot", 1)[1].split("function onLiveStatus", 1)[0]
        self.assertIn("DOM.render(byId('waiting-orders')", apply)

    def test_a_failed_read_keeps_the_cards_and_says_so(self):
        handler = self.controller().split("function onLiveStatus", 1)[1].split("const live =", 1)[0]
        self.assertNotIn("DOM.render", handler)
        self.assertNotIn("orders.clear", handler)
        self.assertIn("읽기 실패", handler)
        self.assertIn("목록 유지", handler)

    def test_the_only_refresh_control_shows_that_it_heard_the_press(self):
        source = self.controller()
        self.assertIn("byId('reload-orders').disabled = state.inFlight", source)
        self.assertIn("읽는 중…", source)

    def test_the_screen_distinguishes_live_from_polling(self):
        source = self.controller()
        self.assertIn("실시간", source)
        self.assertIn("다시 읽음", source)
        self.assertNotIn("자동 갱신 안 함", source)

    def test_tab_visibility_is_the_schedulers_business_not_the_templates(self):
        """Hiding the tab closes the stream and stops the poll; showing it
        opens a fresh stream and reads once. One place decides that."""
        self.assertNotIn("visibilitychange", read("kitchen_supervisor.html"))
        scheduler = read_js(THE_SCHEDULER)
        for event in ("visibilitychange", "pagehide", "pageshow"):
            with self.subTest(event=event):
                self.assertIn(event, scheduler)

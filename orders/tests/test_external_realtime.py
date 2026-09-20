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


class TheBoardDoesNotPretendToBeLiveTests(TestCase):
    """No timer, and the screen says as much."""

    def test_nothing_schedules_a_repeating_reload(self):
        source = read("kitchen_supervisor.html")
        for pattern in ("setInterval", "AUTO_MS", "startPolling", "stopPolling"):
            with self.subTest(pattern=pattern):
                self.assertNotIn(pattern, source)

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

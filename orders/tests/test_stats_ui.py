"""UI-05C: the real stats page keeps its access and presentation contracts.

The shared account-menu tests own the complete 16-permission matrix. These
cases check its wiring through the stats view with real authentication.
"""

from django.templatetags.static import static
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.html import escape

from orders.models import Account
from orders.tests.auth_support import AUTH_SETTINGS, login_client
from orders.tests.test_account_menu_templates import Elements


@override_settings(**AUTH_SETTINGS)
class StatsPageTests(TestCase):
    def setUp(self):
        login_client(self.client, "STATS")
        self.url = reverse("orders:b1-counter")

    def page(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response, Elements(response.content.decode())

    def test_stats_only_account_can_open_the_page_and_its_own_menu_link(self):
        response, elements = self.page()
        self.assertTemplateUsed(response, "orders/b1_counter.html")
        self.assertTemplateUsed(response, "orders/_account_menu.html")
        self.assertRegex(response.content.decode(), r"<h[12]\b[^>]*>\s*누적·통계\s*</h[12]>")
        self.assertEqual({a["href"] for a in elements.find("a")}, {self.url})
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])

    def test_anonymous_page_access_redirects_to_login(self):
        response = Client().get(self.url)
        self.assertRedirects(response, reverse("orders:login"), fetch_redirect_response=False)

    def test_accounts_without_stats_permission_cannot_open_the_page(self):
        for alias in ("SERVING", "HALL_MONITOR", "TAKEOUT_MONITOR", "BOTH_MONITORS"):
            with self.subTest(alias=alias):
                client = Client()
                login_client(client, alias)
                self.assertRedirects(client.get(self.url), reverse("orders:login"),
                                     fetch_redirect_response=False)

    def test_revoking_stats_permission_blocks_an_existing_session(self):
        Account.objects.filter(name="stats").update(can_view_stats=False, can_serve=True)
        self.assertRedirects(self.client.get(self.url), reverse("orders:login"),
                             fetch_redirect_response=False)

    def test_named_identity_is_escaped_and_logout_has_a_csrf_token(self):
        name = '김바자 <img src=x onerror="alert(1)"> & 통계'
        Account.objects.filter(name="stats").update(name=name)
        response, elements = self.page()
        self.assertContains(response, str(escape(name)))
        self.assertEqual(elements.find("img"), [])
        self.assertTrue(any(d.get("id") == "account-menu" for d in elements.find("dialog")))
        logout, = [f for f in elements.find("form") if f.get("action") == reverse("orders:logout")]
        self.assertEqual(logout["method"].lower(), "post")
        csrf, = [i for i in elements.find("input") if i.get("name") == "csrfmiddlewaretoken"]
        self.assertTrue(csrf["value"])

    def test_page_context_limits_monitor_links_and_requires_both_for_overview(self):
        for takeout in (False, True):
            with self.subTest(takeout=takeout):
                Account.objects.filter(name="stats").update(
                    can_monitor_hall=True, can_monitor_takeout=takeout,
                )
                _, elements = self.page()
                expected = {self.url, reverse("orders:kitchen-hall")}
                if takeout:
                    expected |= {reverse("orders:kitchen-takeout"), reverse("orders:kitchen")}
                self.assertEqual({a["href"] for a in elements.find("a")}, expected)

    def test_dashboard_url_period_and_accessible_feedback_are_wired(self):
        _, elements = self.page()
        by_id = {attrs["id"]: attrs for _, attrs in elements.tags if "id" in attrs}
        self.assertEqual(by_id["stats-page"]["data-dashboard-url"], reverse("orders:stats-dashboard"))
        self.assertEqual(by_id["stats-error"]["role"], "alert")
        self.assertEqual(by_id["stats-status"]["role"], "status")
        self.assertIn("periodLabel", by_id)

    def test_shared_assets_load_before_the_extracted_stats_controller(self):
        _, elements = self.page()
        styles = {link.get("href") for link in elements.find("link") if link.get("rel") == "stylesheet"}
        self.assertIn(static("orders/ui/ui05.css"), styles)
        scripts = [script["src"] for script in elements.find("script") if "src" in script]
        controller = static("orders/ui/stats.js")
        self.assertEqual(scripts.count(controller), 1)
        self.assertEqual(scripts.count(static("orders/ui/account_menu.js")), 1)
        for name in ("dom.js", "auth.js", "stats_state.js"):
            dependency = static("orders/ui/" + name)
            with self.subTest(asset=name):
                self.assertEqual(scripts.count(dependency), 1)
                self.assertLess(scripts.index(dependency), scripts.index(controller))

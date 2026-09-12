"""Phase 3 preparation for BK-R001: measure the authorization surface, decide nothing.

BK-R001 is the only Critical risk and stays Open. D-003 (the role/route matrix) is
undecided, so this module deliberately does NOT assert a target policy. It pins what
the server does today, endpoint by endpoint, so D-003 can be chosen from measured
behavior instead of from the page decorators — which do not guard the API at all.

Read the assertions as a defect report, not as a contract worth keeping: most of them
record that an unauthenticated client succeeds. A green run here is NOT evidence that
authorization exists. When phase 3 lands, these expectations must be replaced with the
approved matrix, and every expectation that currently reads OPEN must fail first.

Run with bazaar_kiosk.settings_test_pg and the dedicated Compose test database.
"""

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from orders.models import MenuItem, Order, OrderItem, Table
from orders.views import api

ROLE_PINS = {
    "ORDER": "test-order-pin",
    "B1_COUNTER": "test-counter-pin",
    "KITCHEN": "test-kitchen-pin",
    "KITCHEN_HALL": "test-hall-pin",
    "KITCHEN_TAKEOUT": "test-takeout-pin",
}

# Every actor a request can arrive as. "GHOST" is a session carrying a role string
# the application does not define: it separates "has any session" from "has a role
# the server recognises", which the page guard and the API treat differently.
ROLES = tuple(ROLE_PINS)
ACTORS = ("anonymous", *ROLES, "GHOST")

# What the measurement means, kept out of the status codes so the table stays readable.
OPEN = "OPEN"  # reached the handler; no authorization was applied
DENY = "DENY"  # redirected to login or refused before the handler


@override_settings(ROLE_PINS=ROLE_PINS)
class AuthorizationSurfaceTests(TestCase):
    """One row per (endpoint, actor). The matrix is the deliverable for D-003."""

    def setUp(self):
        cache.clear()
        api._get_table_by_number.cache_clear()
        self.addCleanup(cache.clear)
        self.addCleanup(api._get_table_by_number.cache_clear)
        self.table = Table.objects.create(number=7)
        self.menu = MenuItem.objects.create(name="Meal", price=1000)
        self.order = self._make_order()
        self.item = self.order.items.first()

    def _make_order(self):
        order = Order.objects.create(
            table=self.table, floor="B1", order_type="DINE_IN",
            status="PREPARING", total_price=1000, payment_method="CASH",
            received_amount=1000, received_cash_amount=1000, received_ticket_amount=0,
        )
        OrderItem.objects.create(order=order, menu_item=self.menu, qty=1, unit_price=1000)
        return order

    def client_as(self, actor):
        """A client carrying the given actor's session. No PIN is used for GHOST:
        the point is to hold a session whose role the server never issued."""
        client = Client()
        if actor == "anonymous":
            return client
        if actor == "GHOST":
            session = client.session
            session["role"] = "GHOST"
            session.save()
            return client
        response = client.post(
            reverse("orders:login"), {"role": actor, "pin": ROLE_PINS[actor]}
        )
        self.assertEqual(response.status_code, 302, f"{actor} could not log in")
        self.assertEqual(client.session["role"], actor)
        return client

    # --- request builders -------------------------------------------------
    # Each returns (method, url, kwargs) for a request that is *valid* apart from
    # who is sending it, so a refusal can only come from authorization.

    def read_requests(self):
        return {
            "tables": ("get", reverse("orders:tables"), {}),
            "menus": ("get", reverse("orders:menus"), {}),
            "orders-collection": ("get", reverse("orders:orders-collection"), {}),
            "order-detail": (
                "get", reverse("orders:order-detail", args=[self.order.id]), {},
            ),
            "kitchen-menu-summary": (
                "get", reverse("orders:kitchen-menu-summary"), {},
            ),
            "stats-menu-counts": ("get", reverse("orders:stats-menu-counts"), {}),
            "stats-dashboard": (
                "get", reverse("orders:stats-dashboard"), {"data": {"floor": "B1"}},
            ),
        }

    def write_requests(self):
        return {
            "orders-collection": ("post", reverse("orders:orders-collection"), {
                "data": {
                    "floor": "B1", "order_type": "DINE_IN", "table_number": "7",
                    "payment_method": "CASH", "received_cash_amount": 1000,
                    "items": [{"menu_item_id": self.menu.id, "qty": 1}],
                },
                "content_type": "application/json",
            }),
            "order-status": (
                "patch", reverse("orders:order-status", args=[self.order.id]), {
                    "data": {"status": "READY"}, "content_type": "application/json",
                },
            ),
            "order-item-progress": (
                "patch",
                reverse("orders:order-item-progress", args=[self.item.id]), {
                    "data": {"done": True}, "content_type": "application/json",
                },
            ),
        }

    def send(self, client, spec):
        method, url, kwargs = spec
        return getattr(client, method)(url, **kwargs)

    @staticmethod
    def classify(response):
        """DENY only for the shapes this app uses to refuse: a login redirect or a
        403/401. Anything that reaches the handler — including a 400 for business
        reasons — is OPEN, because the request was never stopped on identity."""
        if response.status_code in (401, 403):
            return DENY
        if response.status_code in (301, 302) and "/login" in response.get("Location", ""):
            return DENY
        return OPEN

    # --- positive control -------------------------------------------------

    def test_page_guard_is_detected_so_an_open_api_result_is_not_a_harness_bug(self):
        """Without this, every OPEN below could just mean the client never
        authenticated. The pages use the same sessions and DO refuse."""
        page_expectations = {
            "order": {"ORDER"},
            "b1-counter": {"B1_COUNTER"},
            "kitchen": {"KITCHEN", "KITCHEN_HALL", "KITCHEN_TAKEOUT"},
            "kitchen-hall": {"KITCHEN_HALL"},
            "kitchen-takeout": {"KITCHEN_TAKEOUT"},
        }
        for page, allowed in page_expectations.items():
            for actor in ACTORS:
                with self.subTest(page=page, actor=actor):
                    response = self.client_as(actor).get(reverse(f"orders:{page}"))
                    expected = OPEN if actor in allowed else DENY
                    self.assertEqual(
                        self.classify(response), expected,
                        f"page {page} for {actor} was {response.status_code}",
                    )

    # --- the measurement --------------------------------------------------

    def test_every_read_api_is_open_to_every_actor_including_anonymous(self):
        # Revenue and order data (stats-dashboard, stats-menu-counts, orders-collection)
        # are in here. This is BK-R001's 매출 기밀성 limb.
        for name, spec in self.read_requests().items():
            for actor in ACTORS:
                with self.subTest(endpoint=name, actor=actor):
                    response = self.send(self.client_as(actor), spec)
                    self.assertEqual(
                        self.classify(response), OPEN,
                        f"{name} unexpectedly refused {actor}; the matrix changed",
                    )
                    self.assertEqual(response.status_code, 200)

    def test_every_write_api_is_open_to_every_actor_including_anonymous(self):
        for name, spec in self.write_requests().items():
            for actor in ACTORS:
                with self.subTest(endpoint=name, actor=actor):
                    self.setUp_state_for_write()
                    response = self.send(self.client_as(actor), spec)
                    self.assertEqual(
                        self.classify(response), OPEN,
                        f"{name} unexpectedly refused {actor}; the matrix changed",
                    )
                    self.assertIn(response.status_code, (200, 201))

    def setUp_state_for_write(self):
        """Writes mutate the fixture, so restore a clean target between actors."""
        self.order.status = "PREPARING"
        self.order.save(update_fields=["status"])
        self.item.refresh_from_db()

    def test_order_role_can_drive_kitchen_progress_and_cancel_orders(self):
        """The specific cross-role case BK-R001 names: a serving-only role reaching
        kitchen and counter commands. Recorded separately because the approved
        matrix (D-003) is most likely to differ from today exactly here."""
        client = self.client_as("ORDER")
        progress = client.patch(
            reverse("orders:order-item-progress", args=[self.item.id]),
            data={"done": True}, content_type="application/json",
        )
        self.assertEqual(progress.status_code, 200)
        cancel = client.patch(
            reverse("orders:order-status", args=[self.order.id]),
            data={"status": "CANCELLED"}, content_type="application/json",
        )
        self.assertEqual(cancel.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "CANCELLED")

    def test_write_apis_accept_requests_with_no_csrf_token(self):
        """csrf_exempt on the three write endpoints, measured with a client that
        does enforce CSRF. The control is the login POST: same client, and it is
        refused, so a 200 here is the exemption and not a disabled check."""
        enforcing = Client(enforce_csrf_checks=True)
        refused = enforcing.post(
            reverse("orders:login"), {"role": "ORDER", "pin": ROLE_PINS["ORDER"]}
        )
        self.assertEqual(refused.status_code, 403, "CSRF enforcement is not active")

        for name, spec in self.write_requests().items():
            with self.subTest(endpoint=name):
                self.setUp_state_for_write()
                response = self.send(enforcing, spec)
                self.assertIn(
                    response.status_code, (200, 201),
                    f"{name} began rejecting tokenless writes; the matrix changed",
                )

    def test_method_boundaries_are_the_only_enforced_gate_on_the_api(self):
        """require_http_methods is the sole guard present. Pinning it keeps a later
        phase from mistaking a 405 for authorization."""
        cases = (
            ("orders:tables", [], "post", 405),
            ("orders:menus", [], "post", 405),
            ("orders:orders-collection", [], "patch", 405),
            ("orders:order-status", [self.order.id], "get", 405),
            ("orders:order-item-progress", [self.item.id], "get", 405),
            ("orders:stats-dashboard", [], "post", 405),
        )
        for name, args, method, expected in cases:
            with self.subTest(endpoint=name, method=method):
                client = self.client_as("anonymous")
                response = getattr(client, method)(reverse(name, args=args))
                self.assertEqual(response.status_code, expected)

    def test_logout_changes_nothing_about_api_access(self):
        """Session teardown is the app's only revocation. It does not reach the API,
        so 'expired session' and 'no session' are the same row in the matrix."""
        client = self.client_as("B1_COUNTER")
        before = client.get(reverse("orders:stats-dashboard"), {"floor": "B1"})
        self.assertEqual(before.status_code, 200)
        client.get(reverse("orders:logout"))
        self.assertNotIn("role", client.session)
        after = client.get(reverse("orders:stats-dashboard"), {"floor": "B1"})
        self.assertEqual(after.status_code, 200)

"""Phase 3: the approved authorization matrix for BK-R001.

These were characterization tests pinning that every API was open to everyone.
D-036 (block anonymous) and D-040 (per-account subjects) replaced that, so the
expectations below are now a contract, not a defect report. The previous OPEN
expectations were confirmed to fail against this implementation before being
rewritten — without that step a passing suite would prove nothing.

Approved matrix, D-040 as revised 2026-09-13:

    order-status, order-item-progress     주방        (KITCHEN_ROLES)
    stats-dashboard, stats-menu-counts    주방 카운터  (COUNTER_ROLES)
    everything else                       인증된 계정 전체

"Everything else" is authenticated-only on purpose. D-040 left those subjects
undecided, and guessing a role restriction would invent an approval. Anonymous
is refused everywhere, which is the part D-036 did decide.

Rejections are 403 for both "no session" and "wrong role" while identification
is session-based; the 401/403 split waits for D-035's refresh flow (4A2).

Run with bazaar_kiosk.settings_test_pg and the dedicated Compose test database.
"""

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from orders.models import MenuItem, Order, OrderItem, Table
from orders.views import api
from orders.views.auth import COUNTER_ROLES, KITCHEN_ROLES

ROLE_PINS = {
    "ORDER": "test-order-pin",
    "B1_COUNTER": "test-counter-pin",
    "KITCHEN": "test-kitchen-pin",
    "KITCHEN_HALL": "test-hall-pin",
    "KITCHEN_TAKEOUT": "test-takeout-pin",
}

ROLES = tuple(ROLE_PINS)
# "GHOST" holds a session whose role the server never issued. It separates
# "has a session" from "has a role the server recognises"; without it, a guard
# that only checked for session presence would still pass every case here.
ACTORS = ("anonymous", *ROLES, "GHOST")
UNAUTHENTICATED = ("anonymous", "GHOST")

ALLOWED = "ALLOWED"
REFUSED = "REFUSED"


@override_settings(ROLE_PINS=ROLE_PINS)
class AuthorizationMatrixTests(TestCase):
    def setUp(self):
        cache.clear()
        api._get_table_by_number.cache_clear()
        self.addCleanup(cache.clear)
        self.addCleanup(api._get_table_by_number.cache_clear)
        self.table = Table.objects.create(number=7)
        self.menu = MenuItem.objects.create(name="Meal", price=1000)
        self.order = self.make_order()
        self.item = self.order.items.first()

    def make_order(self):
        order = Order.objects.create(
            table=self.table, floor="B1", order_type="DINE_IN",
            status="PREPARING", total_price=1000, payment_method="CASH",
            received_amount=1000, received_cash_amount=1000, received_ticket_amount=0,
        )
        OrderItem.objects.create(order=order, menu_item=self.menu, qty=1, unit_price=1000)
        return order

    def reset_order(self):
        self.order.status = "PREPARING"
        self.order.save(update_fields=["status"])

    def client_as(self, actor):
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
        return client

    # --- the matrix ------------------------------------------------------
    # Each entry is (method, url builder, request kwargs, allowed roles).
    # An empty allowed set means "any authenticated account".

    def endpoints(self):
        return {
            "tables": ("get", reverse("orders:tables"), {}, ()),
            "menus": ("get", reverse("orders:menus"), {}, ()),
            "orders-collection-read": (
                "get", reverse("orders:orders-collection"), {}, (),
            ),
            "order-detail": (
                "get", reverse("orders:order-detail", args=[self.order.id]), {}, (),
            ),
            "kitchen-menu-summary": (
                "get", reverse("orders:kitchen-menu-summary"), {}, (),
            ),
            "orders-collection-create": ("post", reverse("orders:orders-collection"), {
                "data": {
                    "floor": "B1", "order_type": "DINE_IN", "table_number": "7",
                    "payment_method": "CASH", "received_cash_amount": 1000,
                    "items": [{"menu_item_id": self.menu.id, "qty": 1}],
                },
                "content_type": "application/json",
            }, ()),
            "order-status": (
                "patch", reverse("orders:order-status", args=[self.order.id]),
                {"data": {"status": "READY"}, "content_type": "application/json"},
                KITCHEN_ROLES,
            ),
            "order-item-progress": (
                "patch", reverse("orders:order-item-progress", args=[self.item.id]),
                {"data": {"done": True}, "content_type": "application/json"},
                KITCHEN_ROLES,
            ),
            "stats-menu-counts": (
                "get", reverse("orders:stats-menu-counts"), {}, COUNTER_ROLES,
            ),
            "stats-dashboard": (
                "get", reverse("orders:stats-dashboard"), {"data": {"floor": "B1"}},
                COUNTER_ROLES,
            ),
        }

    def send(self, client, spec):
        method, url, kwargs, _ = spec
        return getattr(client, method)(url, **kwargs)

    def test_every_endpoint_answers_the_approved_matrix_for_every_actor(self):
        for name, spec in self.endpoints().items():
            allowed = spec[3]
            for actor in ACTORS:
                with self.subTest(endpoint=name, actor=actor):
                    self.reset_order()
                    response = self.send(self.client_as(actor), spec)
                    permitted = (
                        actor not in UNAUTHENTICATED
                        and (not allowed or actor in allowed)
                    )
                    if permitted:
                        # Assert success, not merely "not 403": a guard that
                        # broke the handler would otherwise look like a pass.
                        self.assertIn(
                            response.status_code, (200, 201),
                            f"{name} refused {actor}, which the matrix allows",
                        )
                    else:
                        self.assertEqual(
                            response.status_code, 403,
                            f"{name} did not refuse {actor} with 403",
                        )

    def test_refusals_are_json_and_never_an_html_login_redirect(self):
        """A redirect would reach the caller as an HTML page and surface as a
        JSON parse error rather than a permission problem."""
        for name, spec in self.endpoints().items():
            with self.subTest(endpoint=name):
                response = self.send(self.client_as("anonymous"), spec)
                self.assertEqual(response.status_code, 403)
                self.assertTrue(response["Content-Type"].startswith("application/json"))
                self.assertIn("detail", response.json())
                self.assertFalse(response.has_header("Location"))

    def test_refusal_body_does_not_disclose_the_role_or_the_allowed_set(self):
        client = self.client_as("ORDER")
        response = client.get(reverse("orders:stats-dashboard"), {"floor": "B1"})
        self.assertEqual(response.status_code, 403)
        body = response.content.decode()
        for leak in ("ORDER", "B1_COUNTER", "KITCHEN"):
            self.assertNotIn(leak, body)

    # --- ordering guarantees --------------------------------------------

    def test_authorization_runs_before_the_cached_response_is_served(self):
        """`tables` and `menus` are cache_page views. If the guard sat inside
        the cache, a body warmed by an authorised caller would then be handed
        to anyone. Warm it first, then check an anonymous caller."""
        for name in ("orders:tables", "orders:menus"):
            with self.subTest(endpoint=name):
                cache.clear()
                warm = self.client_as("ORDER").get(reverse(name))
                self.assertEqual(warm.status_code, 200)
                cached = self.client_as("ORDER").get(reverse(name))
                self.assertEqual(cached.status_code, 200)
                refused = self.client_as("anonymous").get(reverse(name))
                self.assertEqual(refused.status_code, 403)
                self.assertTrue(
                    refused["Content-Type"].startswith("application/json")
                )

    def test_authorization_runs_before_the_method_check(self):
        """An unauthenticated caller must not learn which methods a route
        accepts. Authorization is the outer decorator, so it answers first."""
        anonymous = self.client_as("anonymous")
        self.assertEqual(anonymous.post(reverse("orders:tables")).status_code, 403)
        self.assertEqual(
            anonymous.get(reverse("orders:order-status", args=[self.order.id])).status_code,
            403,
        )
        # The method boundary still exists for an authorised caller.
        self.assertEqual(
            self.client_as("ORDER").post(reverse("orders:tables")).status_code, 405,
        )
        self.assertEqual(
            self.client_as("KITCHEN").get(
                reverse("orders:order-status", args=[self.order.id])
            ).status_code,
            405,
        )

    def test_logout_revokes_api_access(self):
        """Previously session teardown did not reach the API, so "expired
        session" and "no session" were the same row. Now it revokes."""
        client = self.client_as("B1_COUNTER")
        before = client.get(reverse("orders:stats-dashboard"), {"floor": "B1"})
        self.assertEqual(before.status_code, 200)
        client.get(reverse("orders:logout"))
        self.assertNotIn("role", client.session)
        after = client.get(reverse("orders:stats-dashboard"), {"floor": "B1"})
        self.assertEqual(after.status_code, 403)

    # --- CSRF ------------------------------------------------------------

    def write_specs(self):
        return {
            name: spec for name, spec in self.endpoints().items()
            if spec[0] in ("post", "patch")
        }

    def role_for(self, spec):
        allowed = spec[3]
        return allowed[0] if allowed else "ORDER"

    def test_writes_are_rejected_without_a_csrf_token(self):
        """`@csrf_exempt` was removed from all three write endpoints. The
        control is the status code: 403 from CSRF, while the same client with
        a token succeeds in the next test — so this is the check firing, not
        the authorization guard refusing a valid session."""
        for name, spec in self.write_specs().items():
            with self.subTest(endpoint=name):
                self.reset_order()
                enforcing = Client(enforce_csrf_checks=True)
                role = self.role_for(spec)
                login = enforcing.post(
                    reverse("orders:login"),
                    {"role": role, "pin": ROLE_PINS[role]},
                    HTTP_X_CSRFTOKEN=enforcing.get(reverse("orders:login")).cookies[
                        "csrftoken"
                    ].value,
                )
                self.assertEqual(login.status_code, 302, "login itself failed")
                response = self.send(enforcing, spec)
                self.assertEqual(
                    response.status_code, 403,
                    f"{name} accepted a tokenless write",
                )

    def test_writes_succeed_with_a_csrf_token_from_the_page(self):
        """The positive half: the same enforcing client, same role, plus the
        token the screen would read from the cookie."""
        for name, spec in self.write_specs().items():
            with self.subTest(endpoint=name):
                self.reset_order()
                enforcing = Client(enforce_csrf_checks=True)
                role = self.role_for(spec)
                token = enforcing.get(reverse("orders:login")).cookies["csrftoken"].value
                self.assertEqual(
                    enforcing.post(
                        reverse("orders:login"),
                        {"role": role, "pin": ROLE_PINS[role]},
                        HTTP_X_CSRFTOKEN=token,
                    ).status_code,
                    302,
                )
                # Django rotates the token on login, so re-read the cookie.
                token = enforcing.cookies["csrftoken"].value
                method, url, kwargs, _ = spec
                response = getattr(enforcing, method)(
                    url, **kwargs, HTTP_X_CSRFTOKEN=token
                )
                self.assertIn(
                    response.status_code, (200, 201),
                    f"{name} rejected a properly tokened write",
                )

    def test_write_capable_pages_set_the_csrf_cookie(self):
        """Without the cookie the screens cannot send a token at all, so the
        guard above would make every write fail in the browser."""
        for role, page in (
            ("ORDER", "order"),
            ("KITCHEN", "kitchen"),
            ("KITCHEN_HALL", "kitchen-hall"),
            ("KITCHEN_TAKEOUT", "kitchen-takeout"),
        ):
            with self.subTest(page=page):
                client = self.client_as(role)
                response = client.get(reverse(f"orders:{page}"))
                self.assertEqual(response.status_code, 200)
                # response.cookies holds only what THIS response set, so the
                # page itself is issuing the token, not the earlier login.
                self.assertIn("csrftoken", response.cookies)
                self.assertTrue(response.cookies["csrftoken"].value)

    # --- existing journeys ----------------------------------------------

    def test_the_existing_kitchen_and_counter_journeys_still_work(self):
        """Phase 3's acceptance criterion is that normal journeys survive.
        These are the exact calls the two screens make today."""
        kitchen = self.client_as("KITCHEN")
        progress = kitchen.patch(
            reverse("orders:order-item-progress", args=[self.item.id]),
            data={"prepared_qty": 1}, content_type="application/json",
        )
        self.assertEqual(progress.status_code, 200)
        cancel = kitchen.patch(
            reverse("orders:order-status", args=[self.order.id]),
            data={"status": "CANCELLED"}, content_type="application/json",
        )
        self.assertEqual(cancel.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "CANCELLED")

        counter = self.client_as("B1_COUNTER")
        dashboard = counter.get(reverse("orders:stats-dashboard"), {"floor": "B1"})
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("summary", dashboard.json())

    def test_pages_still_refuse_the_wrong_role_by_redirecting(self):
        """The page guard is unchanged: screens redirect, APIs answer JSON.
        This keeps the two rejection styles from drifting into each other."""
        response = self.client_as("ORDER").get(reverse("orders:kitchen"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response["Location"])

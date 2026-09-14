"""Phase 3: the approved authorization matrix for BK-R001.

These were characterization tests pinning that every API was open to everyone.
D-036 (block anonymous) and D-040 (per-account subjects) replaced that, so the
expectations below are now a contract, not a defect report. The previous OPEN
expectations were confirmed to fail against this implementation before being
rewritten — without that step a passing suite would prove nothing.

Approved matrix, D-040 as revised 2026-09-13:

    order-status, order-item-progress     주방        (KITCHEN_ROLES)
    stats-dashboard, stats-menu-counts    주방 카운터  (COUNTER_ROLES)
    orders-collection GET, order-detail   주방+카운터  (ORDER_READ_ROLES)
    everything else                       인증된 계정 전체  (tables, menus,
                                          orders-collection POST)

Reading an order carries its money -- total_price, payment_method, the cash and
ticket split, change, per-item unit_price -- so leaving it open would undo the
counter-only restriction on the stats endpoints rather than stay neutral on it.
Creating an order stays open: the ordering screen posts and never reads back.

"Everything else" is authenticated-only on purpose. D-040 left those subjects
undecided, and guessing a role restriction would invent an approval. Anonymous
is refused everywhere, which is the part D-036 did decide.

Rejections are 403 for both "no session" and "wrong role" while identification
is session-based; the 401/403 split waits for D-035's refresh flow (4A2).

Run with bazaar_kiosk.settings_test_pg and the dedicated Compose test database.
"""

from importlib import import_module

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from orders.models import MenuItem, Order, OrderItem, Table
from orders.views import api
from orders.views.auth import (
    COUNTER_ROLES,
    KITCHEN_ROLES,
    ORDER_READ_ROLES,
    ROLE_LABELS,
)

# The approved matrix is written here as literals, NOT imported from the code
# under test. Deriving it from KITCHEN_ROLES/COUNTER_ROLES would move the
# expectation in lockstep with the implementation, so widening either tuple
# would pass unnoticed -- exactly the escalation this file exists to catch.
# test_the_role_constants_still_match_the_approved_matrix pins the constants
# themselves, so a deliberate change has to be made here too.
APPROVED_KITCHEN = ("KITCHEN", "KITCHEN_HALL", "KITCHEN_TAKEOUT")
APPROVED_COUNTER = ("B1_COUNTER",)
APPROVED_ORDER_READ = APPROVED_KITCHEN + APPROVED_COUNTER

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
                "get", reverse("orders:orders-collection"), {}, APPROVED_ORDER_READ,
            ),
            "order-detail": (
                "get", reverse("orders:order-detail", args=[self.order.id]), {},
                APPROVED_ORDER_READ,
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
                APPROVED_KITCHEN,
            ),
            "order-item-progress": (
                "patch", reverse("orders:order-item-progress", args=[self.item.id]),
                {"data": {"done": True}, "content_type": "application/json"},
                APPROVED_KITCHEN,
            ),
            "stats-menu-counts": (
                "get", reverse("orders:stats-menu-counts"), {}, APPROVED_COUNTER,
            ),
            "stats-dashboard": (
                "get", reverse("orders:stats-dashboard"), {"data": {"floor": "B1"}},
                APPROVED_COUNTER,
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
        """Both refusal branches. The English role codes alone are not enough:
        this app names roles in Korean, so a body reading "주방 카운터 전용"
        would leak the allowed set while passing an English-only check."""
        url = reverse("orders:stats-dashboard")
        leaks = (*ROLES, *ROLE_LABELS.values())
        cases = (
            ("wrong role", self.client_as("ORDER"), "권한이 없습니다."),
            ("no session", self.client_as("anonymous"), "로그인이 필요합니다."),
        )
        for label, client, expected in cases:
            with self.subTest(branch=label):
                response = client.get(url, {"floor": "B1"})
                self.assertEqual(response.status_code, 403)
                # Pin the body exactly. Asserting only on absence lets any
                # future message through, including a disclosing one.
                self.assertEqual(response.json(), {"detail": expected})
                body = response.content.decode()
                for leak in leaks:
                    self.assertNotIn(leak, body)
                for header in response.headers.values():
                    for leak in leaks:
                        self.assertNotIn(leak, header)

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

    # --- the matrix itself, not just the responses -----------------------

    def test_the_role_constants_still_match_the_approved_matrix(self):
        """The expectations above are literals on purpose, so widening a role
        tuple in the code cannot move them. That leaves one gap: the widening
        would be invisible rather than wrong. This closes it by pinning the
        constants, so changing who counts as 주방 or 카운터 has to be a
        deliberate edit here, traceable back to D-040."""
        self.assertEqual(tuple(KITCHEN_ROLES), APPROVED_KITCHEN)
        self.assertEqual(tuple(COUNTER_ROLES), APPROVED_COUNTER)
        self.assertEqual(tuple(ORDER_READ_ROLES), APPROVED_ORDER_READ)

    def test_every_api_route_appears_in_the_matrix(self):
        """The table is a hand-written dict. A duplicated key would silently
        discard the earlier entry, and a new endpoint would simply never be
        checked. Both failures are invisible without this."""
        from django.urls import resolve

        declared = set()
        for spec in self.endpoints().values():
            declared.add(resolve(spec[1]).url_name)

        routed = {
            pattern.name
            for pattern in import_module("orders.urls").urlpatterns
            if getattr(pattern, "callback", None) is not None
            and pattern.callback.__module__ == api.__name__
        }
        self.assertEqual(declared, routed)

        # orders-collection carries GET and POST, so the route count and the
        # check count differ by one. Pin both: a duplicate key would shrink
        # the table while leaving the route set intact.
        self.assertEqual(len(routed), 8)
        self.assertEqual(len(self.endpoints()), 9)
        self.assertEqual(len(self.write_specs()), 3)

    def test_reading_an_order_is_refused_to_the_ordering_account(self):
        """The stats endpoints are counter-only, but the same figures ride
        along on every serialized order. If the read stayed open, restricting
        stats would accomplish nothing -- so this pins the money out of reach
        and pins that creating an order is still open."""
        money = (
            "total_price", "payment_method", "received_cash_amount",
            "received_ticket_amount", "change_amount", "unit_price",
        )
        listing = reverse("orders:orders-collection")
        detail = reverse("orders:order-detail", args=[self.order.id])

        ordering = self.client_as("ORDER")
        for url in (listing, detail):
            with self.subTest(url=url):
                self.assertEqual(ordering.get(url).status_code, 403)

        # The counter reads it, and the body really does carry the figures --
        # otherwise the refusal above would be protecting nothing.
        body = self.client_as("B1_COUNTER").get(listing).json()
        self.assertTrue(body["results"], "no orders to inspect; the test proves nothing")
        served = body["results"][0]
        for field in money:
            with self.subTest(field=field):
                self.assertTrue(
                    field in served or any(field in item for item in served["items"]),
                    f"{field} is missing, so this test no longer guards it",
                )

        # Creating is not reading: the ordering screen must still post.
        created = ordering.post(
            listing,
            data={
                "floor": "B1", "order_type": "DINE_IN", "table_number": "7",
                "payment_method": "CASH", "received_cash_amount": 1000,
                "items": [{"menu_item_id": self.menu.id, "qty": 1}],
            },
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)

    # --- session and CSRF boundaries -------------------------------------

    def test_login_starts_a_clean_session_and_rotates_the_csrf_token(self):
        """The session is now the only authorization credential the API has, so
        a key planted before login must not survive it -- and neither should the
        contents, nor the CSRF secret bound to the old key. The session key is
        only half the pair; Django's own login rotates both."""
        client = Client()
        client.get(reverse("orders:login"))
        session = client.session
        session["planted"] = "attacker"
        session.save()
        client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key
        planted_key = session.session_key
        planted_csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
        self.assertTrue(planted_key, "no pre-login session; the test proves nothing")
        self.assertTrue(planted_csrf, "no pre-login token; the test proves nothing")

        response = client.post(
            reverse("orders:login"), {"role": "KITCHEN", "pin": ROLE_PINS["KITCHEN"]}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(client.session["role"], "KITCHEN")
        self.assertNotEqual(client.session.session_key, planted_key)
        self.assertNotIn("planted", client.session)
        self.assertNotEqual(client.cookies[settings.CSRF_COOKIE_NAME].value, planted_csrf)

    def test_a_failed_login_leaves_the_session_alone(self):
        """Rotation belongs to the privilege transition. If a wrong PIN also
        cycled the key, an unauthenticated caller could churn session rows."""
        client = Client()
        client.get(reverse("orders:login"))
        before = client.session.session_key

        response = client.post(
            reverse("orders:login"), {"role": "KITCHEN", "pin": "wrong-pin"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("role", client.session)
        self.assertEqual(client.session.session_key, before)

    def test_head_is_authorized_as_the_get_it_is(self):
        """HEAD is GET without a body, so it must clear GET's bar. The guard
        has to enforce that itself: require_http_methods would also refuse HEAD
        today, but that decorator sits inside this one, so relying on it makes
        the restriction a side effect of an unrelated list."""
        from orders.views.auth import require_api_roles

        @require_api_roles(by_method={"GET": APPROVED_COUNTER})
        def view(request):
            return JsonResponse({"money": 1})

        factory = RequestFactory()
        for method in ("get", "head"):
            with self.subTest(method=method):
                request = getattr(factory, method)("/probe")
                request.session = {"role": "ORDER"}
                self.assertEqual(view(request).status_code, 403)

    def test_a_mistyped_method_key_is_refused_at_decoration(self):
        """A key that never matches would leave that method on the endpoint
        default, which for orders-collection is the open sentinel. The narrower
        mistake -- a mistyped role -- already raises; this is the one that
        actually grants access."""
        from orders.views.auth import require_api_roles

        for bad in ({"GTE": APPROVED_COUNTER}, {"GET": "B1_COUNTER"}, {"GET": ()}):
            with self.subTest(by_method=bad):
                with self.assertRaises(ValueError):
                    require_api_roles(by_method=bad)
        with self.assertRaises(ValueError):
            require_api_roles("NOT_A_ROLE")

    def test_a_csrf_rejection_on_the_api_is_json_not_html(self):
        """CsrfViewMiddleware runs outside every view decorator, so a tokenless
        write never reaches the guard. Without a JSON failure view the caller
        gets an HTML page and reports a parse error, not a permission problem."""
        client = Client(enforce_csrf_checks=True)
        client.post(
            reverse("orders:login"), {"role": "KITCHEN", "pin": ROLE_PINS["KITCHEN"]}
        )
        response = client.patch(
            reverse("orders:order-status", args=[self.order.id]),
            data={"status": "READY"}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response["Content-Type"].startswith("application/json"))
        self.assertIn("detail", response.json())
        body = response.content.decode()
        # The reason string names the check that failed; it is not the caller's.
        for leak in ("CSRF", "Referer", "origin", *ROLES):
            self.assertNotIn(leak, body)

    def test_a_csrf_rejection_on_a_page_is_still_the_html_page(self):
        """A browser navigation should see a page, not a JSON blob. This keeps
        the JSON answer scoped to the API instead of applying it everywhere."""
        response = Client(enforce_csrf_checks=True).post(
            reverse("orders:login"), {"role": "KITCHEN", "pin": ROLE_PINS["KITCHEN"]}
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response["Content-Type"].startswith("text/html"))

    def test_pages_still_refuse_the_wrong_role_by_redirecting(self):
        """The page guard is unchanged: screens redirect, APIs answer JSON.
        This keeps the two rejection styles from drifting into each other."""
        response = self.client_as("ORDER").get(reverse("orders:kitchen"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response["Location"])

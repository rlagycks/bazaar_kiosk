"""Authorization matrix regression (phase 3, rewritten for D-051 in 4A4).

The approved matrix (D-051) is written here as literals, NOT imported from
the code under test. Deriving it from the permission tuples in orders.roles
would move the expectation in lockstep with the implementation, so widening
a tuple would pass unnoticed -- exactly the escalation this file exists to
catch. test_the_permission_constants_still_match_the_approved_matrix pins the
constants themselves, so a deliberate change has to be made here too.

Actors are accounts holding exactly one permission each, plus an account
holding both monitor permissions, an anonymous caller and a "GHOST" carrying
a legacy session role the server never issued.
"""
from importlib import import_module
import uuid

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from orders.models import Account, MenuItem, Order, OrderItem, Table
from orders.roles import (
    MONITOR_PERMISSIONS,
    ORDER_READ_PERMISSIONS,
    PERMISSION_LABELS,
    STATS_PERMISSIONS,
)
from orders.tests.auth_support import ALIASES, AUTH_SETTINGS, credentials, login_client
from orders.views import api

APPROVED_MONITORS = ("HALL_MONITOR", "TAKEOUT_MONITOR")
APPROVED_STATS = ("STATS",)
APPROVED_ORDER_READ = APPROVED_MONITORS + APPROVED_STATS

# The order under test is a dine-in order, so the takeout monitor is refused
# by scope (403) where the hall monitor is allowed. Both hold the permission
# the endpoint names; the matrix below is what the server actually answers.
# An account holding no permission cannot log in at all (D-051), so it is
# covered in test_accounts rather than as an actor here.
PERMISSION_ACTORS = ("SERVING", "HALL_MONITOR", "TAKEOUT_MONITOR", "STATS", "BOTH_MONITORS")
ACTORS = ("anonymous", *PERMISSION_ACTORS, "GHOST")
UNAUTHENTICATED = ("anonymous", "GHOST")

ALLOWED = "ALLOWED"
REFUSED = "REFUSED"


@override_settings(**AUTH_SETTINGS)
class AuthorizationMatrixTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
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
            session["role"] = "KITCHEN"
            session.save()
            return client
        login_client(client, actor)
        return client

    # --- the matrix ------------------------------------------------------
    # Each entry is (method, url, request kwargs, actors the server allows).
    # An empty allowed set means "any authenticated account".

    def endpoints(self):
        hall_side = ("HALL_MONITOR", "BOTH_MONITORS")
        return {
            "tables": ("get", reverse("orders:tables"), {}, ()),
            "menus": ("get", reverse("orders:menus"), {}, ()),
            "orders-collection-read": (
                "get", reverse("orders:orders-collection"), {},
                ("HALL_MONITOR", "TAKEOUT_MONITOR", "STATS", "BOTH_MONITORS"),
            ),
            "order-detail": (
                "get", reverse("orders:order-detail", args=[self.order.id]), {},
                hall_side + ("STATS",),
            ),
            "orders-collection-create": ("post", reverse("orders:orders-collection"), {
                "data": {
                    "request_id": str(uuid.uuid4()),
                    "floor": "B1", "order_type": "DINE_IN", "table_number": "7",
                    "payment_method": "CASH", "received_cash_amount": 1000,
                    "items": [{"menu_item_id": self.menu.id, "qty": 1}],
                },
                "content_type": "application/json",
            }, ("SERVING",)),
            "order-status": (
                "patch", reverse("orders:order-status", args=[self.order.id]),
                {"data": {"status": "READY"}, "content_type": "application/json"},
                hall_side,
            ),
            "order-item-progress": (
                "patch", reverse("orders:order-item-progress", args=[self.item.id]),
                {"data": {"done": True}, "content_type": "application/json"},
                hall_side,
            ),
            "stats-menu-counts": (
                "get", reverse("orders:stats-menu-counts"), {}, ("STATS",),
            ),
            "stats-dashboard": (
                "get", reverse("orders:stats-dashboard"), {"data": {"floor": "B1"}},
                ("STATS",),
            ),
        }

    def send(self, client, spec):
        method, url, kwargs, _ = spec
        data = kwargs.get("data")
        if isinstance(data, dict) and "request_id" in data:
            # 6A: each send is a separate attempt, not a retry of the last one.
            data = dict(data, request_id=str(uuid.uuid4()))
            kwargs = dict(kwargs, data=data)
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
                            response.status_code, 401 if actor in UNAUTHENTICATED else 403,
                            f"{name} did not refuse {actor}",
                        )

    def test_the_takeout_side_of_the_matrix_mirrors_the_hall_side(self):
        """The dine-in order above refuses the takeout monitor by scope. A
        takeout order swaps the two, so the scope check is not a hardcoded
        preference for one side."""
        tag = Table.objects.create(number=105)
        takeout = Order.objects.create(
            table=tag, floor="B1", order_type="TAKEOUT", is_takeout=True,
            status="PREPARING", total_price=1000, payment_method="CASH",
            received_amount=1000, received_cash_amount=1000, received_ticket_amount=0,
        )
        item = OrderItem.objects.create(order=takeout, menu_item=self.menu, qty=1,
                                        unit_price=1000, service_mode="TAKEOUT")
        for actor, expected in (("TAKEOUT_MONITOR", 200), ("HALL_MONITOR", 403),
                                ("BOTH_MONITORS", 200), ("STATS", 403), ("SERVING", 403)):
            with self.subTest(actor=actor):
                client = self.client_as(actor)
                status = client.patch(reverse("orders:order-status", args=[takeout.id]),
                                      data={"status": "READY"}, content_type="application/json")
                self.assertEqual(status.status_code, expected)
                progress = client.patch(reverse("orders:order-item-progress", args=[item.id]),
                                        data={"done": True}, content_type="application/json")
                self.assertEqual(progress.status_code, expected)
                detail = client.get(reverse("orders:order-detail", args=[takeout.id]))
                self.assertEqual(detail.status_code, 200 if actor in ("TAKEOUT_MONITOR", "BOTH_MONITORS", "STATS") else 403)

    def test_refusals_are_json_and_never_an_html_login_redirect(self):
        """A redirect would reach the caller as an HTML page and surface as a
        JSON parse error rather than a permission problem."""
        for name, spec in self.endpoints().items():
            with self.subTest(endpoint=name):
                response = self.send(self.client_as("anonymous"), spec)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response["WWW-Authenticate"], "Bearer")
                self.assertTrue(response["Content-Type"].startswith("application/json"))
                self.assertIn("detail", response.json())
                self.assertFalse(response.has_header("Location"))

    def test_refusal_body_does_not_disclose_the_permission_or_the_allowed_set(self):
        """Both refusal branches. The English codes alone are not enough: this
        app names permissions in Korean, so a body reading "누적·통계 전용"
        would leak the allowed set while passing an English-only check."""
        url = reverse("orders:stats-dashboard")
        leaks = (*PERMISSION_LABELS, *PERMISSION_LABELS.values(), *(name for name, _ in ALIASES.values()))
        cases = (
            ("wrong permission", self.client_as("SERVING"), "권한이 없습니다."),
            ("no session", self.client_as("anonymous"), "로그인이 필요합니다."),
        )
        for label, client, expected in cases:
            with self.subTest(branch=label):
                response = client.get(url, {"floor": "B1"})
                self.assertEqual(response.status_code, 401 if label == "no session" else 403)
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
                warm = self.client_as("SERVING").get(reverse(name))
                self.assertEqual(warm.status_code, 200)
                cached = self.client_as("SERVING").get(reverse(name))
                self.assertEqual(cached.status_code, 200)
                refused = self.client_as("anonymous").get(reverse(name))
                self.assertEqual(refused.status_code, 401)
                self.assertTrue(refused["Content-Type"].startswith("application/json"))

    def test_authorization_runs_before_the_method_check(self):
        """An unauthenticated caller must not learn which methods a route
        accepts. Authorization is the outer decorator, so it answers first."""
        anonymous = self.client_as("anonymous")
        self.assertEqual(anonymous.post(reverse("orders:tables")).status_code, 401)
        self.assertEqual(
            anonymous.get(reverse("orders:order-status", args=[self.order.id])).status_code,
            401,
        )
        # The method boundary still exists for an authorised caller.
        self.assertEqual(self.client_as("SERVING").post(reverse("orders:tables")).status_code, 405)
        self.assertEqual(
            self.client_as("BOTH_MONITORS").get(
                reverse("orders:order-status", args=[self.order.id])
            ).status_code,
            405,
        )

    def test_logout_revokes_api_access(self):
        """Logout revokes the device, including an already-issued access JWT."""
        client = self.client_as("STATS")
        before = client.get(reverse("orders:stats-dashboard"), {"floor": "B1"})
        self.assertEqual(before.status_code, 200)
        self.assertEqual(client.post(reverse("orders:logout")).status_code, 302)
        self.assertNotIn("role", client.session)
        after = client.get(reverse("orders:stats-dashboard"), {"floor": "B1"})
        self.assertEqual(after.status_code, 401)

    def test_logout_is_not_reachable_by_a_safe_method(self):
        """A GET logout is triggerable cross-site (BK-R019). All three safe
        methods are checked; a guard written as "refuse GET" rather than
        "require POST" would pass GET and still revoke the device on HEAD."""
        for method in ("get", "head", "options"):
            with self.subTest(method=method):
                client = self.client_as("STATS")
                response = getattr(client, method)(reverse("orders:logout"))
                self.assertEqual(response.status_code, 405)
                self.assertTrue(client.cookies["bk_refresh"].value)
                self.assertEqual(
                    client.get(reverse("orders:stats-dashboard"), {"floor": "B1"}).status_code,
                    200,
                )

    # --- 자격증명 회수 ----------------------------------------------------

    def test_switching_an_account_off_blocks_existing_device_tokens(self):
        """Revocation has to reach devices that are already signed in, on
        both surfaces: a page redirects, an API answers JSON, so a fix applied
        to only one would leave the switched-off account still reading."""
        stats = self.client_as("STATS")
        kitchen = self.client_as("BOTH_MONITORS")
        dashboard = (reverse("orders:stats-dashboard"), {"floor": "B1"})
        self.assertEqual(stats.get(*dashboard).status_code, 200)

        Account.objects.filter(name="stats").update(is_active=False)
        self.assertEqual(stats.get(*dashboard).status_code, 401)
        page = stats.get(reverse("orders:b1-counter"))
        self.assertEqual(page.status_code, 302)
        self.assertEqual(page.headers["Location"], reverse("orders:login"))
        # Aimed at one account. Everyone else keeps working: a fix that
        # simply refused every session would also pass the assertions above.
        self.assertEqual(kitchen.get(reverse("orders:kitchen")).status_code, 200)
        self.assertEqual(
            kitchen.get(reverse("orders:order-detail", args=[self.order.id])).status_code, 200
        )

    def test_legacy_session_roles_do_not_authorize_pages_or_apis(self):
        for role in ("B1_COUNTER", "b1_counter", "KITCHEN"):
            client = Client()
            session = client.session
            session["role"] = role
            session.save()
            self.assertEqual(client.get(reverse("orders:stats-dashboard")).status_code, 401)
            self.assertEqual(client.get(reverse("orders:b1-counter")).status_code, 302)
            self.assertEqual(client.get(reverse("orders:kitchen")).status_code, 302)

    def test_event_password_rotation_revokes_previously_issued_tokens(self):
        stats = self.client_as("STATS")
        from django.contrib.auth.hashers import PBKDF2PasswordHasher
        rotated = PBKDF2PasswordHasher().encode("replacement", "synthetic-salt", iterations=1)
        with override_settings(EVENT_PASSWORD_HASH=rotated):
            self.assertEqual(stats.get(reverse("orders:stats-dashboard")).status_code, 401)
            self.assertEqual(stats.get(reverse("orders:b1-counter")).status_code, 302)

    def test_withdrawal_reaches_the_cached_endpoints_too(self):
        """tables and menus wear the guard OUTSIDE @cache_page, so the guard
        runs before the cache lookup, for the revoked-but-still-has-a-token
        case as well as the anonymous one."""
        stats = self.client_as("STATS")
        for name in ("orders:tables", "orders:menus"):
            with self.subTest(endpoint=name):
                self.assertEqual(stats.get(reverse(name)).status_code, 200)
        Account.objects.filter(name="stats").update(is_active=False)
        for name in ("orders:tables", "orders:menus"):
            with self.subTest(endpoint=name):
                response = stats.get(reverse(name))
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json(), {"detail": "로그인이 필요합니다."})

    # --- CSRF ------------------------------------------------------------

    def write_specs(self):
        return {
            name: spec for name, spec in self.endpoints().items()
            if spec[0] in ("post", "patch")
        }

    def actor_for(self, spec):
        allowed = spec[3]
        return allowed[0] if allowed else "SERVING"

    def enforcing_client(self, actor):
        """A client that enforces CSRF, logged in the way the screen does
        (login_client sends the token the login page set)."""
        enforcing = Client(enforce_csrf_checks=True)
        login_client(enforcing, actor)
        return enforcing

    def test_writes_are_rejected_without_a_csrf_token(self):
        """`@csrf_exempt` was removed from all three write endpoints. The
        control is the status code: 403 from CSRF, while the same client with
        a token succeeds in the next test."""
        for name, spec in self.write_specs().items():
            with self.subTest(endpoint=name):
                self.reset_order()
                enforcing = self.enforcing_client(self.actor_for(spec))
                response = self.send(enforcing, spec)
                self.assertEqual(response.status_code, 403, f"{name} accepted a tokenless write")

    def test_writes_succeed_with_a_csrf_token_from_the_page(self):
        for name, spec in self.write_specs().items():
            with self.subTest(endpoint=name):
                self.reset_order()
                enforcing = self.enforcing_client(self.actor_for(spec))
                token = enforcing.cookies["csrftoken"].value
                method, url, kwargs, _ = spec
                response = getattr(enforcing, method)(url, **kwargs, HTTP_X_CSRFTOKEN=token)
                self.assertIn(response.status_code, (200, 201), f"{name} rejected a properly tokened write")

    def test_write_capable_pages_set_the_csrf_cookie(self):
        """Without the cookie the screens cannot send a token at all."""
        for actor, page in (
            ("SERVING", "order"),
            ("BOTH_MONITORS", "kitchen"),
            ("HALL_MONITOR", "kitchen-hall"),
            ("TAKEOUT_MONITOR", "kitchen-takeout"),
        ):
            with self.subTest(page=page):
                client = self.client_as(actor)
                response = client.get(reverse(f"orders:{page}"))
                self.assertEqual(response.status_code, 200)
                self.assertIn("csrftoken", response.cookies)
                self.assertTrue(response.cookies["csrftoken"].value)

    # --- existing journeys ----------------------------------------------

    def test_the_existing_kitchen_and_counter_journeys_still_work(self):
        kitchen = self.client_as("BOTH_MONITORS")
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

        stats = self.client_as("STATS")
        dashboard = stats.get(reverse("orders:stats-dashboard"), {"floor": "B1"})
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("summary", dashboard.json())

    # --- the matrix itself, not just the responses -----------------------

    def test_the_permission_constants_still_match_the_approved_matrix(self):
        self.assertEqual(tuple(MONITOR_PERMISSIONS), APPROVED_MONITORS)
        self.assertEqual(tuple(STATS_PERMISSIONS), APPROVED_STATS)
        self.assertEqual(tuple(ORDER_READ_PERMISSIONS), APPROVED_ORDER_READ)

    def test_every_api_route_appears_in_the_matrix(self):
        from django.urls import resolve

        declared = {resolve(spec[1]).url_name for spec in self.endpoints().values()}
        routed = {
            pattern.name
            for pattern in import_module("orders.urls").urlpatterns
            if getattr(pattern, "callback", None) is not None
            and pattern.callback.__module__ == api.__name__
        }
        self.assertEqual(declared, routed)
        self.assertEqual(len(routed), 8)
        self.assertEqual(len(self.endpoints()), 9)
        self.assertEqual(len(self.write_specs()), 3)

    def test_reading_an_order_is_refused_to_the_serving_account(self):
        """The stats endpoints are STATS-only, but the same figures ride along
        on every serialized order. If the read stayed open, restricting stats
        would accomplish nothing."""
        money = (
            "total_price", "payment_method", "received_cash_amount",
            "received_ticket_amount", "change_amount", "unit_price",
        )
        listing = reverse("orders:orders-collection")
        detail = reverse("orders:order-detail", args=[self.order.id])

        serving = self.client_as("SERVING")
        for url in (listing, detail):
            with self.subTest(url=url):
                self.assertEqual(serving.get(url).status_code, 403)

        body = self.client_as("STATS").get(listing).json()
        self.assertTrue(body["results"], "no orders to inspect; the test proves nothing")
        served = body["results"][0]
        for field in money:
            with self.subTest(field=field):
                self.assertTrue(
                    field in served or any(field in item for item in served["items"]),
                    f"{field} is missing, so this test no longer guards it",
                )

        created = serving.post(
            listing,
            data={
                "request_id": str(uuid.uuid4()),
                "floor": "B1", "order_type": "DINE_IN", "table_number": "7",
                "payment_method": "CASH", "received_cash_amount": 1000,
                "items": [{"menu_item_id": self.menu.id, "qty": 1}],
            },
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)

    # --- session and CSRF boundaries -------------------------------------

    def test_login_starts_a_clean_session_and_rotates_the_csrf_token(self):
        login_client(Client(), "BOTH_MONITORS")  # creates the account
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

        response = client.post(reverse("orders:login"), credentials("BOTH_MONITORS"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("role", client.session)
        self.assertNotEqual(client.session.session_key, planted_key)
        self.assertNotIn("planted", client.session)
        self.assertNotEqual(client.cookies[settings.CSRF_COOKIE_NAME].value, planted_csrf)

    def test_logout_rotates_the_csrf_token_as_well_as_the_session(self):
        client = self.client_as("BOTH_MONITORS")
        before = client.cookies[settings.CSRF_COOKIE_NAME].value
        self.assertTrue(before, "no token before logout; the test proves nothing")
        self.assertEqual(client.post(reverse("orders:logout")).status_code, 302)
        self.assertNotIn("role", client.session)
        self.assertNotEqual(client.cookies[settings.CSRF_COOKIE_NAME].value, before)

    def test_the_logout_control_on_a_live_screen_is_a_post_form(self):
        page = self.client_as("BOTH_MONITORS").get(reverse("orders:kitchen"))
        self.assertEqual(page.status_code, 200)
        html = page.content.decode()
        logout_url = reverse("orders:logout")
        self.assertIn(f'<form method="post" action="{logout_url}"', html)
        self.assertIn("csrfmiddlewaretoken", html)
        self.assertNotIn(f'href="{logout_url}"', html)

    def test_a_failed_login_leaves_the_session_alone(self):
        login_client(Client(), "BOTH_MONITORS")  # creates the account
        client = Client()
        client.get(reverse("orders:login"))
        before = client.session.session_key
        response = client.post(reverse("orders:login"), {"name": "both-monitors", "password": "wrong-password"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("role", client.session)
        self.assertEqual(client.session.session_key, before)

    def test_head_is_authorized_as_the_get_it_is(self):
        from orders.authentication import issue_tokens
        from orders.tests.auth_support import ensure_account
        from orders.views.guards import require_api_permissions

        @require_api_permissions(by_method={"GET": APPROVED_STATS})
        def view(request):
            return JsonResponse({"money": 1})

        factory = RequestFactory()
        serving = ensure_account("SERVING")
        for method in ("get", "head"):
            with self.subTest(method=method):
                request = getattr(factory, method)("/probe")
                request.META["HTTP_AUTHORIZATION"] = "Bearer " + issue_tokens(serving).access_token
                self.assertEqual(view(request).status_code, 403)

    def test_a_mistyped_method_key_is_refused_at_decoration(self):
        from orders.views.guards import require_api_permissions, require_permissions

        for bad in ({"GTE": APPROVED_STATS}, {"GET": "STATS"}, {"GET": ()}):
            with self.subTest(by_method=bad):
                with self.assertRaises(ValueError):
                    require_api_permissions(by_method=bad)
        with self.assertRaises(ValueError):
            require_api_permissions("NOT_A_PERMISSION")
        with self.assertRaises(ValueError):
            require_permissions("KITCHEN")
        with self.assertRaises(ValueError):
            require_permissions(all_of=("HALL_MONITOR", "KITCHEN"))

    def test_a_csrf_rejection_on_the_api_is_json_not_html(self):
        login_client(Client(), "BOTH_MONITORS")
        client = Client(enforce_csrf_checks=True)
        client.post(reverse("orders:login"), credentials("BOTH_MONITORS"))
        response = client.patch(
            reverse("orders:order-status", args=[self.order.id]),
            data={"status": "READY"}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response["Content-Type"].startswith("application/json"))
        self.assertIn("detail", response.json())
        body = response.content.decode()
        for leak in ("CSRF", "Referer", "origin", *PERMISSION_LABELS):
            self.assertNotIn(leak, body)

    @override_settings(ROOT_URLCONF="orders.tests.urls_outside_api")
    def test_the_json_refusal_follows_the_guard_and_not_the_path(self):
        login_client(Client(), "BOTH_MONITORS")
        client = Client(enforce_csrf_checks=True)
        client.post(reverse("orders:login"), credentials("BOTH_MONITORS"))
        response = client.post(reverse("outside-api-ping"))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            response["Content-Type"].startswith("application/json"),
            f"refused as {response['Content-Type']}, so the path decided it",
        )
        self.assertIn("detail", response.json())

    def test_a_csrf_rejection_on_a_page_is_still_the_html_page(self):
        login_client(Client(), "BOTH_MONITORS")
        response = Client(enforce_csrf_checks=True).post(
            reverse("orders:login"), credentials("BOTH_MONITORS")
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response["Content-Type"].startswith("text/html"))

    def test_pages_still_refuse_the_wrong_permission_by_redirecting(self):
        response = self.client_as("SERVING").get(reverse("orders:kitchen"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("orders:login"))
        for actor in ("HALL_MONITOR", "TAKEOUT_MONITOR", "STATS"):
            with self.subTest(actor=actor):
                response = self.client_as(actor).get(reverse("orders:order"))
                self.assertEqual(response["Location"], reverse("orders:login"))

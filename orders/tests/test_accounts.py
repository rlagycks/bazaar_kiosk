"""D-051: name + event password login, permission-driven landing, and the
boundaries an unregistered or switched-off name must not cross."""
import re

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from orders.models import Account, AuthDevice, LoginAttempt
from orders.roles import HALL_MONITOR, SERVING, STATS, TAKEOUT_MONITOR, landing_urlname
from orders.tests.auth_support import (
    AUTH_SETTINGS, EVENT_PASSWORD, credentials, login_client, make_account,
)


@override_settings(**AUTH_SETTINGS)
class LoginByNameTests(TestCase):
    def login(self, name, password=EVENT_PASSWORD, client=None):
        client = client or Client()
        csrf = client.get(reverse("orders:login")).cookies["csrftoken"].value
        return client.post(reverse("orders:login"), {"name": name, "password": password},
                           HTTP_X_CSRFTOKEN=csrf), client

    def test_each_permission_lands_on_its_own_screen(self):
        cases = (
            (("서빙 담당", SERVING), "orders:order"),
            (("홀 담당", HALL_MONITOR), "orders:kitchen-hall"),
            (("포장 담당", TAKEOUT_MONITOR), "orders:kitchen-takeout"),
            (("통계 담당", STATS), "orders:b1-counter"),
            (("주방 총괄", HALL_MONITOR, TAKEOUT_MONITOR), "orders:kitchen"),
            (("만능", SERVING, HALL_MONITOR, TAKEOUT_MONITOR, STATS), "orders:order"),
        )
        for (name, *permissions), target in cases:
            with self.subTest(name=name):
                make_account(name, *permissions)
                response, client = self.login(name)
                self.assertRedirects(response, reverse(target), fetch_redirect_response=False)
                self.assertEqual(client.get(response.url).status_code, 200)
                self.assertTrue(client.cookies["bk_refresh"].value)

    def test_landing_priority_is_a_pure_function(self):
        self.assertIsNone(landing_urlname(()))
        self.assertEqual(landing_urlname((STATS, TAKEOUT_MONITOR)), "orders:kitchen-takeout")
        self.assertEqual(landing_urlname((HALL_MONITOR, TAKEOUT_MONITOR)), "orders:kitchen")

    def test_unknown_inactive_and_permissionless_names_are_refused_alike(self):
        """The screen must not say which names are registered. All three get
        the same sentence, the same status, and no device."""
        make_account("퇴직자", SERVING, is_active=False)
        make_account("권한 없음")
        bodies = set()
        for name in ("등록 안 된 이름", "퇴직자", "권한 없음"):
            with self.subTest(name=name):
                response, client = self.login(name)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("bk_refresh", response.cookies)
                self.assertContains(response, "이름 또는 비밀번호가 올바르지 않습니다.")
                # Identical apart from the per-client CSRF token.
                bodies.add(re.sub(rb'name="csrfmiddlewaretoken" value="[^"]*"', b"", response.content))
        self.assertEqual(len(bodies), 1, "the three refusals rendered differently")
        self.assertEqual(AuthDevice.objects.count(), 0)
        # Each refusal counted against the name + address budget.
        self.assertEqual(LoginAttempt.objects.count(), 3)

    def test_the_name_is_trimmed_but_not_case_folded(self):
        make_account("김바자", SERVING)
        response, _ = self.login("  김바자 ")
        self.assertEqual(response.status_code, 302)
        response, _ = self.login("김바자".upper() + "x")
        self.assertEqual(response.status_code, 200)

    def test_overlong_and_missing_names_are_refused_before_hashing(self):
        for name in ("", " ", "x" * 51):
            with self.subTest(name=repr(name)):
                response, _ = self.login(name)
                self.assertEqual(response.status_code, 200)
        self.assertEqual(LoginAttempt.objects.count(), 0)

    def test_a_wrong_event_password_is_refused_for_a_registered_name(self):
        make_account("김바자", SERVING)
        response, _ = self.login("김바자", password="wrong")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AuthDevice.objects.count(), 0)

    @override_settings(EVENT_PASSWORD_HASH="")
    def test_no_event_password_configured_is_a_503_not_a_login(self):
        make_account("김바자", SERVING)
        response, _ = self.login("김바자")
        self.assertEqual(response.status_code, 503)

    def test_the_login_form_asks_for_a_name_and_the_event_password(self):
        page = Client().get(reverse("orders:login"))
        self.assertContains(page, 'name="name"')
        self.assertContains(page, "행사 비밀번호")
        self.assertNotContains(page, 'name="account_id"')


@override_settings(**AUTH_SETTINGS)
class AccountLifecycleTests(TestCase):
    def test_deactivating_an_account_ends_its_sessions_on_the_next_request(self):
        client = Client()
        login_client(client, "STATS")
        dashboard = (reverse("orders:stats-dashboard"), {"floor": "B1"})
        self.assertEqual(client.get(*dashboard).status_code, 200)
        Account.objects.filter(name="stats").update(is_active=False)
        self.assertEqual(client.get(*dashboard).status_code, 401)
        page = client.get(reverse("orders:b1-counter"))
        self.assertRedirects(page, reverse("orders:login"), fetch_redirect_response=False)
        # Re-activation restores nothing: the device is checked, not re-issued,
        # and the token is still valid -- which is the point of checking live.
        Account.objects.filter(name="stats").update(is_active=True)
        self.assertEqual(client.get(*dashboard).status_code, 200)

    def test_a_permission_change_applies_without_a_new_login(self):
        client = Client()
        login_client(client, "SERVING")
        dashboard = (reverse("orders:stats-dashboard"), {"floor": "B1"})
        self.assertEqual(client.get(*dashboard).status_code, 403)
        Account.objects.filter(name="serving").update(can_view_stats=True)
        self.assertEqual(client.get(*dashboard).status_code, 200)
        Account.objects.filter(name="serving").update(can_view_stats=False, can_serve=False)
        self.assertEqual(client.get(*dashboard).status_code, 403)
        self.assertRedirects(client.get(reverse("orders:order")), reverse("orders:login"),
                             fetch_redirect_response=False)

    def test_changing_the_event_password_logs_every_device_out(self):
        first, second = Client(), Client()
        login_client(first, "SERVING")
        login_client(second, "STATS")
        with override_settings(EVENT_PASSWORD_HASH="pbkdf2_sha256$1$other$" + "A" * 43 + "="):
            self.assertEqual(first.get(reverse("orders:menus")).status_code, 401)
            self.assertEqual(second.get(reverse("orders:menus")).status_code, 401)

    def test_an_account_with_history_cannot_be_deleted(self):
        from django.db.models import ProtectedError

        client = Client()
        login_client(client, "SERVING")
        with self.assertRaises(ProtectedError):
            Account.objects.get(name="serving").delete()

    def test_two_people_keep_separate_devices_and_throttle_buckets(self):
        make_account("갑", SERVING)
        make_account("을", SERVING)
        for _ in range(10):
            Client().post(reverse("orders:login"), {"name": "갑", "password": "wrong"})
        blocked = Client().post(reverse("orders:login"), {"name": "갑", "password": EVENT_PASSWORD})
        self.assertEqual(blocked.status_code, 429)
        fine = Client().post(reverse("orders:login"), credentials("SERVING") | {"name": "을"})
        self.assertEqual(fine.status_code, 302)
        self.assertEqual(AuthDevice.objects.filter(account__name="을").count(), 1)
        self.assertEqual(AuthDevice.objects.filter(account__name="갑").count(), 0)

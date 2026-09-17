"""Browser/API token boundary regressions using a real local PostgreSQL DB."""
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from django.test import Client, TestCase, override_settings
from django.urls import reverse, path
from orders.views.guards import require_api_roles

from orders.authentication import issue_tokens, AuthError, validate_access
from orders.models import AuthDevice, LoginAttempt


@require_api_roles()
def failing_api(request):
    raise RuntimeError("synthetic downstream failure")


urlpatterns = [path("failure/", failing_api)]


class JWTHTTPTests(TestCase):
    def login(self, client, account='order', password='test-order-password'):
        response = client.get(reverse('orders:login'))
        return client.post(reverse('orders:login'), {
            'account_id': account, 'password': password,
        }, HTTP_X_CSRFTOKEN=response.cookies['csrftoken'].value)

    def refresh(self, client):
        return client.post(reverse('orders:refresh'),
                           HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)

    def test_real_login_refresh_api_flow_and_cookie_attributes(self):
        client = Client(enforce_csrf_checks=True)
        response = self.login(client)
        self.assertEqual(response.status_code, 302)
        cookie = response.cookies['bk_refresh']
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'], 'Strict')
        self.assertEqual(cookie['path'], '/orders/')
        self.assertNotIn('role', client.session)
        self.assertIn('no-store', response['Cache-Control'])
        response = self.refresh(client)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('refresh_token', response.json())
        access = response.json()['access_token']
        menus = client.get(reverse('orders:menus'), HTTP_AUTHORIZATION='Bearer ' + access)
        self.assertEqual(menus.status_code, 200)
        self.assertIn('private', menus['Cache-Control'])
        self.assertIn('no-store', menus['Cache-Control'])
        self.assertEqual(client.get(reverse('orders:menus')).status_code, 401)
        self.assertIn('no-store', response['Cache-Control'])

    @override_settings(ROOT_URLCONF=__name__, DEBUG=True)
    def test_unhandled_api_failure_redacts_bearer_from_guard_locals(self):
        pair = issue_tokens('ORDER')
        client = Client(raise_request_exception=False)
        with self.assertLogs('django.request', level='ERROR'):
            response = client.get('/failure/', HTTP_AUTHORIZATION='Bearer ' + pair.access_token)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(pair.access_token, response.content.decode())

    def test_csrf_and_method_boundaries(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse('orders:login'), {}).status_code, 403)
        self.login(client)
        for name in ('refresh', 'logout'):
            self.assertEqual(client.get(reverse('orders:' + name)).status_code, 405)
            self.assertEqual(client.post(reverse('orders:' + name)).status_code, 403)

    def test_legacy_session_and_refresh_bearer_cannot_authorize_api(self):
        session = self.client.session
        session['role'] = 'KITCHEN'
        session.save()
        pair = issue_tokens('KITCHEN')
        for auth in ('', 'Bearer ' + pair.refresh_token, 'Basic ignored'):
            response = self.client.get(reverse('orders:menus'), HTTP_AUTHORIZATION=auth)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response['WWW-Authenticate'], 'Bearer')

    def test_role_refusal_is_403(self):
        pair = issue_tokens('ORDER')
        response = self.client.get(reverse('orders:stats-dashboard'),
                                   HTTP_AUTHORIZATION='Bearer ' + pair.access_token)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('WWW-Authenticate', response)

    def test_refresh_conflict_does_not_overwrite_cookie(self):
        self.login(self.client)
        original = self.client.cookies['bk_refresh'].value
        self.assertEqual(self.refresh(self.client).status_code, 200)
        self.client.cookies['bk_refresh'] = original
        response = self.refresh(self.client)
        self.assertEqual(response.status_code, 409)
        self.assertNotIn('bk_refresh', response.cookies)
        self.assertEqual(AuthDevice.objects.filter(revoked_at__isnull=False).count(), 0)

    def test_coalesced_refresh_does_not_set_a_cookie(self):
        self.login(self.client)
        self.refresh(self.client)
        response = self.refresh(self.client)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('bk_refresh', response.cookies)
        self.assertTrue(response.json()['session_id'])

    def test_logout_revokes_only_its_device(self):
        self.login(self.client)
        access = self.refresh(self.client).json()['access_token']
        other = issue_tokens('ORDER')
        self.client.post(reverse('orders:logout'))
        with self.assertRaises(AuthError):
            validate_access(access)
        self.assertEqual(validate_access(other.access_token), 'ORDER')
        self.assertEqual(self.client.get(reverse('orders:order')).status_code, 302)

    def test_failed_login_limit_is_shared_and_scoped_by_id_and_direct_ip(self):
        # D-045: the tenth failure within the window blocks, the ninth does not.
        for _ in range(9):
            response = self.login(Client(), password='wrong')
        self.assertEqual(response.status_code, 200)
        response = self.login(Client(), password='wrong')
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response['Retry-After'], '300')
        blocked = self.login(Client())
        self.assertEqual(blocked.status_code, 429)
        self.assertIn('Retry-After', blocked)
        other_ip = Client(REMOTE_ADDR='127.0.0.2')
        self.assertEqual(self.login(other_ip).status_code, 302)
        spoofed = Client(HTTP_X_FORWARDED_FOR='127.0.0.3')
        self.assertEqual(self.login(spoofed).status_code, 429)
        self.assertEqual(AuthDevice.objects.count(), 1)
        self.assertNotIn('order', LoginAttempt.objects.first().key)

    @override_settings(LOGIN_MAX_FAILURES=2)
    def test_login_failure_budget_expires_and_success_resets_it(self):
        start = timezone.now()
        with patch('orders.login_security.timezone.now', return_value=start):
            self.assertEqual(self.login(self.client, password='wrong').status_code, 200)
            self.assertEqual(self.login(self.client).status_code, 302)
            self.assertEqual(self.login(self.client, password='wrong').status_code, 200)
            self.assertEqual(self.login(self.client, password='wrong').status_code, 429)
        with patch('orders.login_security.timezone.now', return_value=start + timedelta(seconds=301)):
            self.assertEqual(self.login(self.client).status_code, 302)

    @override_settings(JWT_COOKIE_SECURE=True)
    def test_refresh_cookie_is_secure_in_deployment(self):
        self.assertTrue(self.login(self.client).cookies['bk_refresh']['secure'])

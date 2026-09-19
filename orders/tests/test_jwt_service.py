"""JWT validation, revocation boundaries, and serialized refresh rotation."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

import jwt
from django.contrib.auth.hashers import make_password
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from orders.authentication import (
    AUDIENCE, ISSUER, AuthError, RefreshInProgress, authenticate_credentials,
    issue_tokens, revoke_refresh, rotate_refresh, validate_access, validate_refresh,
)
from orders.models import Account, AuthDevice
from orders.roles import SERVING
from orders.tests.auth_support import make_account

KEY = "test-jwt-signing-key-with-at-least-48-bytes-for-all-test-algorithms"
PASSWORD = "service-password"
HASH = make_password(PASSWORD)


@override_settings(EVENT_PASSWORD_HASH=HASH, JWT_SIGNING_KEY=KEY)
class JWTServiceTests(TestCase):
    def setUp(self):
        self.account = make_account("order", SERVING)

    def assert_identity(self, identity):
        self.assertEqual(identity.account, self.account)
        self.assertEqual(identity.permissions, frozenset({SERVING}))

    def claims(self, token):
        return jwt.decode(token, KEY, algorithms=["HS256"], issuer=ISSUER, audience=AUDIENCE)

    def signed(self, claims):
        return jwt.api_jws.encode(json.dumps(claims).encode(), KEY, algorithm="HS256")

    def test_credentials_unknown_names_and_inactive_accounts(self):
        self.assertEqual(authenticate_credentials("order", PASSWORD), self.account)
        self.assertEqual(authenticate_credentials("  order ", PASSWORD), self.account)
        self.assertIsNone(authenticate_credentials("order", "wrong"))
        self.assertIsNone(authenticate_credentials("missing", PASSWORD))
        self.assertIsNone(authenticate_credentials("", PASSWORD))
        self.assertIsNone(authenticate_credentials("x" * 51, PASSWORD))
        self.assertIsNone(authenticate_credentials(None, PASSWORD))
        retired = make_account("retired", SERVING, is_active=False)
        self.assertIsNone(authenticate_credentials("retired", PASSWORD))
        with self.assertRaises(AuthError):
            issue_tokens(retired)
        with self.assertRaises(AuthError):
            issue_tokens("KITCHEN_HALL")
        with override_settings(EVENT_PASSWORD_HASH=""):
            self.assertIsNone(authenticate_credentials("order", PASSWORD))
            with self.assertRaises(AuthError):
                issue_tokens(self.account)

    def test_pair_lifetimes_and_no_raw_refresh_storage(self):
        pair = issue_tokens(self.account)
        access, refresh = self.claims(pair.access_token), self.claims(pair.refresh_token)
        self.assertEqual(access["exp"] - access["iat"], 900)
        self.assertEqual(refresh["exp"] - refresh["iat"], 43200)
        device = AuthDevice.objects.get()
        self.assertNotEqual(device.refresh_jti_hash, refresh["jti"])
        self.assertEqual(len(device.refresh_jti_hash), 64)
        self.assert_identity(validate_access(pair.access_token))
        self.assert_identity(validate_refresh(pair.refresh_token))

    def test_claim_types_missing_claims_and_wrong_token_types(self):
        pair = issue_tokens(self.account)
        claims = self.claims(pair.access_token)
        for name in claims:
            changed = claims.copy()
            changed.pop(name)
            with self.subTest(missing=name), self.assertRaises(AuthError):
                validate_access(self.signed(changed))
        for name in ("iss", "aud", "iat", "exp", "sub", "device", "jti", "type"):
            for value in (None, [], {}, True, float("inf"), float("nan")):
                with self.subTest(name=name, value=value), self.assertRaises(AuthError):
                    validate_access(self.signed({**claims, name: value}))
        for validator, token in ((validate_access, pair.refresh_token),
                                 (validate_refresh, pair.access_token),
                                 (rotate_refresh, pair.access_token)):
            with self.assertRaises(AuthError):
                validator(token)
        self.assertIsNone(AuthDevice.objects.get().revoked_at)

    def test_wrong_signature_algorithm_issuer_audience_and_expiry(self):
        pair = issue_tokens(self.account)
        claims = self.claims(pair.access_token)
        bad = [jwt.encode(claims, "different-key-with-at-least-32-bytes", algorithm="HS256"),
               jwt.encode(claims, KEY, algorithm="HS384"),
               self.signed({**claims, "iss": "other"}),
               self.signed({**claims, "aud": "other"}),
               self.signed({**claims, "exp": int(timezone.now().timestamp()) - 1}),
               self.signed({**claims, "device": "invalid"}),
               "malformed"]
        for token in bad:
            with self.subTest(token=token[:12]), self.assertRaises(AuthError):
                validate_access(token)
        self.assertIsNone(AuthDevice.objects.get().revoked_at)

    def test_rotation_grace_then_replay_revokes_only_one_device(self):
        first, second = issue_tokens(self.account), issue_tokens(self.account)
        rotated = rotate_refresh(first.refresh_token)
        with self.assertRaises(RefreshInProgress):
            rotate_refresh(first.refresh_token)
        self.assert_identity(validate_access(rotated.access_token))
        self.assert_identity(validate_refresh(rotated.refresh_token))
        AuthDevice.objects.filter(pk=self.claims(first.refresh_token)["device"]).update(
            rotated_at=timezone.now() - timedelta(seconds=6))
        with self.assertRaises(AuthError):
            rotate_refresh(first.refresh_token)
        with self.assertRaises(AuthError):
            validate_access(rotated.access_token)
        with self.assertRaises(AuthError):
            validate_refresh(rotated.refresh_token)
        self.assert_identity(validate_access(second.access_token))
        self.assert_identity(validate_refresh(second.refresh_token))

    def test_three_tabs_coalesce_current_generation_without_cookie_write(self):
        first = issue_tokens(self.account)
        rotated = rotate_refresh(first.refresh_token)
        for _ in range(3):
            coalesced = rotate_refresh(rotated.refresh_token)
            self.assertIsNone(coalesced.refresh_token)
            self.assertEqual(coalesced.session_id, rotated.session_id)
            self.assert_identity(validate_access(coalesced.access_token))
        with self.assertRaises(RefreshInProgress):
            rotate_refresh(first.refresh_token)
        self.assertIsNone(AuthDevice.objects.get().revoked_at)
        self.assert_identity(validate_refresh(rotated.refresh_token))

    def test_navigation_validation_does_not_rotate_or_revoke(self):
        first = issue_tokens(self.account)
        device = AuthDevice.objects.get()
        for _ in range(3):
            self.assert_identity(validate_refresh(first.refresh_token))
        self.assertEqual(AuthDevice.objects.get().refresh_jti_hash, device.refresh_jti_hash)
        rotated = rotate_refresh(first.refresh_token)
        with self.assertRaises(AuthError):
            validate_refresh(first.refresh_token)
        self.assert_identity(validate_refresh(rotated.refresh_token))

    def test_stale_refresh_logout_revokes_device(self):
        first = issue_tokens(self.account)
        rotated = rotate_refresh(first.refresh_token)
        revoke_refresh(first.refresh_token)
        revoke_refresh(first.refresh_token)
        with self.assertRaises(AuthError):
            validate_access(rotated.access_token)

    def test_replaced_event_password_and_deactivated_account_invalidate_tokens(self):
        pair = issue_tokens(self.account)
        validators = ((validate_access, pair.access_token),
                      (validate_refresh, pair.refresh_token),
                      (rotate_refresh, pair.refresh_token))
        for encoded in ("", make_password("new-password")):
            with override_settings(EVENT_PASSWORD_HASH=encoded):
                for validator, token in validators:
                    with self.subTest(hash=bool(encoded), validator=validator.__name__):
                        with self.assertRaises(AuthError):
                            validator(token)
        # The account is switched off: same tokens, same password, refused.
        Account.objects.filter(pk=self.account.pk).update(is_active=False)
        for validator, token in validators:
            with self.assertRaises(AuthError):
                validator(token)
        Account.objects.filter(pk=self.account.pk).update(is_active=True)
        self.assert_identity(validate_access(pair.access_token))

    def test_permission_changes_apply_on_the_next_check(self):
        pair = issue_tokens(self.account)
        self.assert_identity(validate_access(pair.access_token))
        Account.objects.filter(pk=self.account.pk).update(can_serve=False, can_view_stats=True)
        self.assertEqual(validate_access(pair.access_token).permissions, frozenset({"STATS"}))

    def test_absolute_device_expiry_and_access_cap(self):
        pair = issue_tokens(self.account)
        device = AuthDevice.objects.get()
        deadline = timezone.now() + timedelta(minutes=2)
        AuthDevice.objects.filter(pk=device.pk).update(expires_at=deadline)
        rotated = rotate_refresh(pair.refresh_token)
        self.assertEqual(self.claims(rotated.access_token)["exp"], int(deadline.timestamp()))
        with patch("orders.authentication.timezone.now", return_value=deadline + timedelta(seconds=1)):
            with self.assertRaises(AuthError):
                validate_access(rotated.access_token)
            with self.assertRaises(AuthError):
                rotate_refresh(rotated.refresh_token)

    def test_oversized_token_rejected_before_decode(self):
        with patch("orders.authentication.jwt.decode") as decode:
            for token in ("x" * 8193, b"token", None, ""):
                with self.subTest(token_type=type(token)), self.assertRaises(AuthError):
                    validate_access(token)
            decode.assert_not_called()

    def test_bad_signature_cannot_revoke_a_device(self):
        pair = issue_tokens(self.account)
        claims = self.claims(pair.refresh_token)
        forged = jwt.encode(claims, "different-key-with-at-least-32-bytes", algorithm="HS256")
        for action in (rotate_refresh, revoke_refresh):
            with self.assertRaises(AuthError):
                action(forged)
        self.assert_identity(validate_refresh(pair.refresh_token))


@override_settings(EVENT_PASSWORD_HASH=HASH, JWT_SIGNING_KEY=KEY)
@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class JWTRefreshRaceTests(TransactionTestCase):
    def test_parallel_refresh_mints_once_and_preserves_device(self):
        account = make_account("order", SERVING)
        pair = issue_tokens(account)
        barrier = Barrier(2)

        def refresh():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    return rotate_refresh(pair.refresh_token)
                except RefreshInProgress:
                    return None
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: refresh(), range(2)))
        winners = [result for result in results if result is not None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(validate_refresh(winners[0].refresh_token).account, account)
        self.assertIsNone(AuthDevice.objects.get().revoked_at)

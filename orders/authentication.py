"""Signed credentials backed by an individually revocable browser device.

Only hashes of refresh identifiers are stored. A refresh rotation locks its
row; replay revocation commits before an authentication error is raised.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
import hashlib
import hmac
import uuid

import jwt
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from orders.models import AuthDevice
from orders.roles import ROLE_TO_URLNAME

ISSUER = "bazaar-kiosk"
AUDIENCE = "bazaar-kiosk-browser"
_DUMMY_PASSWORD = make_password("unusable-account-timing-padding")


class AuthError(Exception):
    """The credential cannot authenticate this request."""


class RefreshInProgress(AuthError):
    """Another tab just rotated this credential; retry with shared cookies."""


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str | None
    role: str
    expires_at: datetime
    session_id: str


@sensitive_variables()
def _account(role):
    account = getattr(settings, "ROLE_ACCOUNTS", {}).get(role)
    if role not in ROLE_TO_URLNAME or not isinstance(account, dict):
        return None
    if not isinstance(account.get("id"), str) or not account["id"]:
        return None
    if not isinstance(account.get("password_hash"), str) or not account["password_hash"]:
        return None
    return account


@sensitive_variables()
def authenticate_credentials(account_id, password):
    if not isinstance(account_id, str) or not isinstance(password, str):
        return None
    for role in ROLE_TO_URLNAME:
        account = _account(role)
        if account and hmac.compare_digest(account["id"].encode(), account_id.encode()):
            return role if check_password(password, account["password_hash"]) else None
    check_password(password, _DUMMY_PASSWORD)
    return None


def _digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


@sensitive_variables()
def _fingerprint(account):
    return _digest(account["id"] + "\0" + account["password_hash"])


@sensitive_variables()
def _decode(raw, token_type):
    if not isinstance(raw, str) or not raw or len(raw) > 8192:
        raise AuthError()
    try:
        claims = jwt.decode(
            raw, settings.JWT_SIGNING_KEY, algorithms=["HS256"],
            issuer=ISSUER, audience=AUDIENCE,
            options={"require": ["iss", "aud", "iat", "exp", "sub", "role", "device", "jti", "type"]},
        )
        for name in ("iss", "aud", "sub", "role", "device", "jti", "type"):
            if not isinstance(claims[name], str) or not claims[name]:
                raise AuthError()
        for name in ("iat", "exp"):
            if type(claims[name]) is not int:
                raise AuthError()
        if claims["type"] != token_type or claims["exp"] <= claims["iat"]:
            raise AuthError()
        uuid.UUID(claims["device"])
        uuid.UUID(claims["jti"])
        return claims
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError, OverflowError) as exc:
        raise AuthError() from exc


def _check_device(device, claims, now):
    account = _account(device.role)
    if (device.revoked_at is not None or device.expires_at <= now or not account
            or device.role != claims["role"] or device.account_id != claims["sub"]
            or account["id"] != device.account_id
            or not hmac.compare_digest(device.credential_fingerprint, _fingerprint(account))):
        raise AuthError()


@sensitive_variables()
def _pair(device, refresh_jti, now):
    common = {"iss": ISSUER, "aud": AUDIENCE, "iat": int(now.timestamp()),
              "sub": device.account_id, "role": device.role, "device": str(device.id)}
    access_expiry = min(now + timedelta(minutes=getattr(settings, "JWT_ACCESS_MINUTES", 15)), device.expires_at)
    access = jwt.encode({**common, "type": "access", "jti": str(uuid.uuid4()),
                         "exp": int(access_expiry.timestamp())}, settings.JWT_SIGNING_KEY, algorithm="HS256")
    refresh = jwt.encode({**common, "type": "refresh", "jti": refresh_jti,
                          "exp": int(device.expires_at.timestamp())}, settings.JWT_SIGNING_KEY, algorithm="HS256")
    return TokenPair(access, refresh, device.role, device.expires_at, str(device.id))


@sensitive_variables()
def issue_tokens(role):
    account = _account(role)
    if not account:
        raise AuthError()
    now = timezone.now()
    jti = str(uuid.uuid4())
    device = AuthDevice(
        role=role, account_id=account["id"], credential_fingerprint=_fingerprint(account),
        refresh_jti_hash=_digest(jti),
        expires_at=datetime.fromtimestamp(int((now + timedelta(hours=getattr(settings, "JWT_REFRESH_HOURS", 12))).timestamp()), dt_timezone.utc),
    )
    pair = _pair(device, jti, now)
    device.save(force_insert=True)
    return pair


def _device(claims, lock=False):
    query = AuthDevice.objects.select_for_update() if lock else AuthDevice.objects
    try:
        return query.get(pk=claims["device"])
    except AuthDevice.DoesNotExist as exc:
        raise AuthError() from exc


@sensitive_variables()
def validate_access(raw):
    claims = _decode(raw, "access")
    device = _device(claims)
    _check_device(device, claims, timezone.now())
    return device.role


@sensitive_variables()
def refresh_identity(raw):
    claims = _decode(raw, "refresh")
    device = _device(claims)
    _check_device(device, claims, timezone.now())
    if not hmac.compare_digest(device.refresh_jti_hash, _digest(claims["jti"])):
        raise AuthError()
    return device.role, str(device.id)


@sensitive_variables()
def validate_refresh(raw):
    return refresh_identity(raw)[0]


@sensitive_variables()
def rotate_refresh(raw):
    claims = _decode(raw, "refresh")
    replay = False
    with transaction.atomic():
        device = _device(claims, lock=True)
        now = timezone.now()
        _check_device(device, claims, now)
        presented = _digest(claims["jti"])
        if not hmac.compare_digest(device.refresh_jti_hash, presented):
            if (device.rotated_at and now - device.rotated_at < timedelta(seconds=5)
                    and hmac.compare_digest(device.previous_jti_hash, presented)):
                raise RefreshInProgress()
            device.revoked_at = now
            device.save(update_fields=["revoked_at"])
            replay = True
        else:
            if device.rotated_at and now - device.rotated_at < timedelta(seconds=5):
                # Coalesce current-token requests while older requests may still
                # be in flight. Do not advance generation or overwrite cookies.
                pair = _pair(device, claims["jti"], now)
                return TokenPair(pair.access_token, None, pair.role, pair.expires_at, pair.session_id)
            jti = str(uuid.uuid4())
            pair = _pair(device, jti, now)
            device.previous_jti_hash = device.refresh_jti_hash
            device.refresh_jti_hash = _digest(jti)
            device.rotated_at = now
            device.save(update_fields=["previous_jti_hash", "refresh_jti_hash", "rotated_at"])
    if replay:
        raise AuthError()
    return pair


@sensitive_variables()
def revoke_refresh(raw):
    claims = _decode(raw, "refresh")
    with transaction.atomic():
        device = _device(claims, lock=True)
        # A signed stale refresh still identifies the browser being logged out.
        if device.role != claims["role"] or device.account_id != claims["sub"]:
            raise AuthError()
        if device.revoked_at is None:
            device.revoked_at = timezone.now()
            device.save(update_fields=["revoked_at"])

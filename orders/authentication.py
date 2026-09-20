"""Signed credentials backed by an individually revocable browser device.

D-051: the subject is a personal `Account`, identified at login by name plus
the shared event password. Only hashes of refresh identifiers are stored. A
refresh rotation locks its row; replay revocation commits before an
authentication error is raised. Permissions are read from the account row on
every check, so an administrator's change applies on the next request.
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

from orders.models import Account, AuthDevice

ISSUER = "bazaar-kiosk"
AUDIENCE = "bazaar-kiosk-browser"
NAME_MAX_LENGTH = 50
_DUMMY_PASSWORD = make_password("unusable-account-timing-padding")


class AuthError(Exception):
    """The credential cannot authenticate this request."""


class RefreshInProgress(AuthError):
    """Another tab just rotated this credential; retry with shared cookies."""


@dataclass(frozen=True)
class Identity:
    """Who a validated credential belongs to, as of this request."""
    account: Account
    permissions: frozenset[str]
    session_id: str

    @property
    def account_id(self) -> str:
        return str(self.account.id)


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str | None
    account: Account
    expires_at: datetime
    session_id: str

    @property
    def permissions(self) -> frozenset[str]:
        return self.account.permissions


def _event_password_hash() -> str:
    encoded = getattr(settings, "EVENT_PASSWORD_HASH", "")
    return encoded if isinstance(encoded, str) else ""


def clean_name(raw) -> str | None:
    """The name as an account row would store it, or None if unusable."""
    if not isinstance(raw, str):
        return None
    name = raw.strip()
    if not name or len(name) > NAME_MAX_LENGTH:
        return None
    return name


@sensitive_variables()
def authenticate_credentials(name, password):
    """The active account for this name if the event password matches, else None.

    An unknown or inactive name is refused exactly like a wrong password, and
    costs the same hashing work, so the response does not say which names
    are registered.
    """
    cleaned = clean_name(name)
    encoded = _event_password_hash()
    if cleaned is None or not isinstance(password, str) or not encoded:
        return None
    account = Account.objects.filter(name=cleaned, is_active=True).first()
    if account is None:
        check_password(password, _DUMMY_PASSWORD)
        return None
    return account if check_password(password, encoded) else None


def _digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


@sensitive_variables()
def _fingerprint():
    return _digest(_event_password_hash())


@sensitive_variables()
def _decode(raw, token_type):
    if not isinstance(raw, str) or not raw or len(raw) > 8192:
        raise AuthError()
    try:
        claims = jwt.decode(
            raw, settings.JWT_SIGNING_KEY, algorithms=["HS256"],
            issuer=ISSUER, audience=AUDIENCE,
            options={"require": ["iss", "aud", "iat", "exp", "sub", "device", "jti", "type"]},
        )
        for name in ("iss", "aud", "sub", "device", "jti", "type"):
            if not isinstance(claims[name], str) or not claims[name]:
                raise AuthError()
        for name in ("iat", "exp"):
            if type(claims[name]) is not int:
                raise AuthError()
        if claims["type"] != token_type or claims["exp"] <= claims["iat"]:
            raise AuthError()
        uuid.UUID(claims["sub"])
        uuid.UUID(claims["device"])
        uuid.UUID(claims["jti"])
        return claims
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError, OverflowError) as exc:
        raise AuthError() from exc


def device_is_current(device, now=None) -> bool:
    """Whether this device may still act, independent of any one token.

    Everything that revokes a session lives here: the device row itself, the
    account behind it, and the credential fingerprint -- which is the *only*
    mechanism by which rotating the shared event password logs every device
    out (D-045). There is no separate sweep that sets `revoked_at`.

    It is a function rather than a few lines inside `_check_device` because
    10D1 needs the same question answered for an open stream, in bulk, with
    no token in hand. The first version of the hub asked it by re-listing the
    conditions and left the fingerprint out, so a rotated password stopped
    every request and none of the streams. Asking it in one place is what
    makes that kind of divergence impossible rather than merely unlikely.
    """
    if now is None:
        now = timezone.now()
    account = device.account
    fingerprint = _event_password_hash()
    return not (device.revoked_at is not None or device.expires_at <= now
                or account is None or not account.is_active
                or not fingerprint
                or not hmac.compare_digest(device.credential_fingerprint,
                                           _fingerprint()))


def _check_device(device, claims, now):
    if not device_is_current(device, now) or str(device.account_id) != claims["sub"]:
        raise AuthError()


@sensitive_variables()
def _pair(device, refresh_jti, now):
    common = {"iss": ISSUER, "aud": AUDIENCE, "iat": int(now.timestamp()),
              "sub": str(device.account_id), "device": str(device.id)}
    access_expiry = min(now + timedelta(minutes=getattr(settings, "JWT_ACCESS_MINUTES", 15)), device.expires_at)
    access = jwt.encode({**common, "type": "access", "jti": str(uuid.uuid4()),
                         "exp": int(access_expiry.timestamp())}, settings.JWT_SIGNING_KEY, algorithm="HS256")
    refresh = jwt.encode({**common, "type": "refresh", "jti": refresh_jti,
                          "exp": int(device.expires_at.timestamp())}, settings.JWT_SIGNING_KEY, algorithm="HS256")
    return TokenPair(access, refresh, device.account, device.expires_at, str(device.id))


@sensitive_variables()
def issue_tokens(account):
    if not isinstance(account, Account) or not account.is_active or not _event_password_hash():
        raise AuthError()
    now = timezone.now()
    jti = str(uuid.uuid4())
    device = AuthDevice(
        account=account, credential_fingerprint=_fingerprint(),
        refresh_jti_hash=_digest(jti),
        expires_at=datetime.fromtimestamp(int((now + timedelta(hours=getattr(settings, "JWT_REFRESH_HOURS", 12))).timestamp()), dt_timezone.utc),
    )
    pair = _pair(device, jti, now)
    device.save(force_insert=True)
    return pair


def _device(claims, lock=False):
    query = AuthDevice.objects.select_related("account")
    if lock:
        # Lock the device row only; the account row is read, not changed.
        query = query.select_for_update(of=("self",))
    try:
        return query.get(pk=claims["device"])
    except AuthDevice.DoesNotExist as exc:
        raise AuthError() from exc


def _identity(device) -> Identity:
    return Identity(device.account, device.account.permissions, str(device.id))


@sensitive_variables()
def validate_access(raw) -> Identity:
    claims = _decode(raw, "access")
    device = _device(claims)
    _check_device(device, claims, timezone.now())
    return _identity(device)


@sensitive_variables()
def refresh_identity(raw) -> Identity:
    claims = _decode(raw, "refresh")
    device = _device(claims)
    _check_device(device, claims, timezone.now())
    if not hmac.compare_digest(device.refresh_jti_hash, _digest(claims["jti"])):
        raise AuthError()
    return _identity(device)


@sensitive_variables()
def validate_refresh(raw) -> Identity:
    return refresh_identity(raw)


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
                return TokenPair(pair.access_token, None, pair.account, pair.expires_at, pair.session_id)
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
        if str(device.account_id) != claims["sub"]:
            raise AuthError()
        if device.revoked_at is None:
            device.revoked_at = timezone.now()
            device.save(update_fields=["revoked_at"])

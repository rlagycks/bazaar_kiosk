"""Validate the configured event password hash without ever echoing it."""
import base64
import binascii

from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.core.exceptions import ImproperlyConfigured


def parse_password_hash(raw):
    """A Django PBKDF2 encoded hash, or "" when none is configured.

    D-051: one shared event password, supplied as a hash. Anything that is
    not a usable PBKDF2 encoding is refused at startup; a plaintext value
    would otherwise sit in the environment and never match anyone.
    """
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise ImproperlyConfigured("EVENT_PASSWORD_HASH must be a PBKDF2 encoded hash.")
    encoded = raw.strip()
    if not encoded:
        return ""
    try:
        if not encoded.startswith("pbkdf2_sha256$"):
            raise ValueError
        decoded = PBKDF2PasswordHasher().decode(encoded)
        if (decoded["iterations"] < 1 or not decoded["salt"]
                or len(base64.b64decode(decoded["hash"], validate=True)) != 32):
            raise ValueError
    except (ValueError, TypeError, KeyError, AssertionError, binascii.Error):
        raise ImproperlyConfigured("EVENT_PASSWORD_HASH must be a PBKDF2 encoded hash.") from None
    return encoded

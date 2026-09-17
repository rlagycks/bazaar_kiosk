"""Validate configured shared accounts without ever echoing credential values."""
import json
import base64
import binascii

from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.core.exceptions import ImproperlyConfigured

from orders.roles import ROLE_TO_URLNAME


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def parse_role_accounts(raw):
    try:
        accounts = json.loads(raw, object_pairs_hook=_unique_object)
        if not isinstance(accounts, dict) or set(accounts) - set(ROLE_TO_URLNAME):
            raise ValueError
        identifiers = set()
        for account in accounts.values():
            if not isinstance(account, dict) or set(account) != {"id", "password_hash"}:
                raise ValueError
            account_id = account["id"]
            encoded = account["password_hash"]
            if (not isinstance(account_id, str) or not account_id.strip()
                    or account_id != account_id.strip() or len(account_id) > 128
                    or account_id in identifiers):
                raise ValueError
            identifiers.add(account_id)
            if not isinstance(encoded, str) or not encoded.startswith("pbkdf2_sha256$"):
                raise ValueError
            decoded = PBKDF2PasswordHasher().decode(encoded)
            if (decoded["iterations"] < 1 or not decoded["salt"]
                    or len(base64.b64decode(decoded["hash"], validate=True)) != 32):
                raise ValueError
        return accounts
    except (ValueError, TypeError, KeyError, AssertionError, binascii.Error):
        raise ImproperlyConfigured("ROLE_ACCOUNTS must contain unique IDs and PBKDF2 password hashes for known roles.") from None

"""Explicit local PostgreSQL fixture profile; never uses DATABASE_URL."""

import os
import re
import uuid
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

from unittest.mock import patch


def test_database_config(raw):
    error = "BK_TEST_DATABASE_URL must target the dedicated local fixture database"
    # libpq's PGHOSTADDR/PGSERVICE can override routing despite a literal HOST.
    if any(key.startswith("PG") and value for key, value in os.environ.items()):
        raise ImproperlyConfigured("Unset libpq PG* environment variables for fixture tests")
    try:
        url = urlsplit(raw)
        valid = (
            url.scheme in {"postgres", "postgresql"}
            and url.hostname == "127.0.0.1"
            and url.port is not None
            and 1024 <= url.port <= 65535
            and url.username == "bk_test_runner"
            and url.password == "synthetic-local-runner-only"
            and url.path == "/bk_test_control"
            and not url.query
            and not url.fragment
        )
    except ValueError:
        raise ImproperlyConfigured(error) from None
    if not valid:
        raise ImproperlyConfigured(error)
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "bk_test_control",
        "USER": "bk_test_runner",
        "PASSWORD": "synthetic-local-runner-only",
        "HOST": "127.0.0.1",
        "PORT": str(url.port),
        "OPTIONS": {
            "hostaddr": "127.0.0.1",
            "sslmode": "disable",  # Only this loopback disposable test profile.
            "connect_timeout": 3,
            "application_name": "bazaar-phase-1a-test",
        },
        "CONN_MAX_AGE": 0,
    }


# Validate the caller's explicit fixture target before importing base settings.
_test_config = test_database_config(os.environ.get("BK_TEST_DATABASE_URL", ""))
with patch.dict(os.environ, {
    "DATABASE_URL": "postgresql://bk_test_runner:synthetic-local-runner-only@127.0.0.1:"
                    + _test_config["PORT"] + "/bk_test_control?sslmode=disable",
}, clear=True):
    from .settings import *  # noqa: F403

_app_database_name = os.environ.get("BK_TEST_APP_DATABASE", "bk_test_app_" + uuid.uuid4().hex)
if not re.fullmatch(r"bk_test_app_[0-9a-f]{32}", _app_database_name):
    raise ImproperlyConfigured("Invalid disposable application test database name")
_test_config["TEST"] = {"NAME": _app_database_name}
DATABASES = {"default": _test_config}


SECRET_KEY = "synthetic-local-tests-only-not-a-deployment-secret-key"
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
CSRF_TRUSTED_ORIGINS = []
SECURE_PROXY_SSL_HEADER = None
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "bazaar-characterization-tests",
    }
}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
SUPABASE_URL = ""
SUPABASE_ANON_KEY = ""
ROLE_PINS = {
    "ORDER": "test-order",
    "B1_COUNTER": "test-counter",
    "KITCHEN": "test-kitchen",
    "KITCHEN_HALL": "test-hall",
    "KITCHEN_TAKEOUT": "test-takeout",
}

# Template tests need static URLs, not a deployment's collectstatic manifest.
STATIC_ROOT = None
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

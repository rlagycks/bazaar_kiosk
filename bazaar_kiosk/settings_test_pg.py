"""Explicit local PostgreSQL fixture profile; never uses DATABASE_URL."""

import os
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

from .settings_test import *  # noqa: F403


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


DATABASES = {"default": test_database_config(os.environ.get("BK_TEST_DATABASE_URL", ""))}

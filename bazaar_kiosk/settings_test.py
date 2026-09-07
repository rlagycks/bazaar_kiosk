"""Local characterization only: synthetic credentials and in-memory SQLite.

Keep the application's apps, middleware, templates and migrations. Import their
defaults without reading deployment environment values (including malformed DB
URLs), then explicitly isolate every external or persistent test backend.
Never use this module to serve the application.
"""

import os
from unittest.mock import patch

with patch.dict(os.environ, {}, clear=True):
    from .settings import *  # noqa: F403

SECRET_KEY = "synthetic-local-tests-only-not-a-deployment-secret-key"
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
CSRF_TRUSTED_ORIGINS = []
SECURE_PROXY_SSL_HEADER = None
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "TEST": {"NAME": ":memory:"},
    }
}
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

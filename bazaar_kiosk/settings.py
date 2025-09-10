from pathlib import Path
import os
from urllib.parse import urlparse, parse_qs, unquote

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-not-for-prod")
DEBUG = os.environ.get("DEBUG", "1") == "1"

ALLOWED_HOSTS = (
    [] if DEBUG else [h for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h]
)

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "orders",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "bazaar_kiosk.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "bazaar_kiosk.wsgi.application"

def _parse_database_url(db_url: str):
    """
    간단한 Postgres URL 파서. 예: postgresql://user:pass@host:5432/dbname?sslmode=require
    """
    u = urlparse(db_url)
    if u.scheme not in ("postgres", "postgresql"):
        raise ValueError("DATABASE_URL must use postgres/postgresql scheme")

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(u.path[1:]),
        "USER": unquote(u.username) if u.username else "",
        "PASSWORD": unquote(u.password) if u.password else "",
        "HOST": u.hostname or "",
        "PORT": str(u.port or ""),
        "OPTIONS": {
            "sslmode": parse_qs(u.query).get("sslmode", ["require"])[0]
        },
    }

_db_url = os.environ.get("DATABASE_URL")
if _db_url:
    DATABASES = {"default": _parse_database_url(_db_url)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "/static/"  # ★ 권장: 절대 경로
STATIC_ROOT = BASE_DIR / "staticfiles"

_static_dir = BASE_DIR / "static"
if _static_dir.is_dir():
    STATICFILES_DIRS = [_static_dir]

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    }
}

# 운영 보안/프록시 설정(★)
if not DEBUG:
    # CSRF_TRUSTED_ORIGINS: https 포함, 콤마 1개만 받는다면 아래처럼
    _csrf_origin = os.environ.get("CSRF_TRUSTED_ORIGINS", "")
    CSRF_TRUSTED_ORIGINS = [o for o in [_csrf_origin] if o]

    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
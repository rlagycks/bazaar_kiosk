#BAZAAR_KIOSK/bazaar_kiosk/setting.py
from pathlib import Path
import os
from django.core.exceptions import ImproperlyConfigured
from urllib.parse import urlparse, parse_qs, unquote

from .auth_config import parse_role_accounts

# --- 기본 경로/디버그 ---
BASE_DIR = Path(__file__).resolve().parent.parent

# Every SECRET_KEY this repository publishes. A deployment must not wear any of
# them. The second one is what .env.example ships, so it is the value most
# likely to be carried to a server by someone who copied that file.
_DEV_SECRET_KEY = "dev-only-not-for-prod"
_PUBLISHED_SECRET_KEYS = frozenset({
    _DEV_SECRET_KEY,
    "replace-with-a-long-random-development-secret",
})
# Django's own check --deploy (W009) uses 50. Matching it keeps one threshold.
_MIN_SECRET_KEY_LENGTH = 50


def _require_explicit_debug() -> bool:
    """DEBUG has to be stated, not defaulted.

    A default of "on" would mean a deployment that sets nothing runs with the
    development secret, ALLOWED_HOSTS=['*'] and the published PINs -- and never
    reaches the deployment checks below, because those only run when DEBUG is
    off. The refusal would be decorative. Stating it is one line in .env.
    """
    raw = os.environ.get("DEBUG")
    if raw not in ("0", "1"):
        raise ImproperlyConfigured(
            "DEBUG must be set to 0 (deployment) or 1 (development). "
            "It has no default: see .env.example."
        )
    return raw == "1"


SECRET_KEY = os.environ.get("SECRET_KEY", _DEV_SECRET_KEY)
DEBUG = _require_explicit_debug()
DEFAULT_EXCEPTION_REPORTER_FILTER = "bazaar_kiosk.error_reporting.CredentialExceptionReporterFilter"

# 공백 안전 콤마 파서
def _split_csv(env_key: str):
    raw = os.environ.get(env_key, "")
    return [s.strip() for s in raw.split(",") if s.strip()]

ALLOWED_HOSTS = ["*"] if DEBUG else _split_csv("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = [] if DEBUG else _split_csv("CSRF_TRUSTED_ORIGINS")


ROLE_ACCOUNTS = parse_role_accounts(os.environ.get("ROLE_ACCOUNTS", "{}"))
JWT_SIGNING_KEY = os.environ.get("JWT_SIGNING_KEY", "")
JWT_ACCESS_MINUTES = 15
JWT_REFRESH_HOURS = 12
JWT_COOKIE_SECURE = True
JWT_REFRESH_COOKIE_NAME = "bk_refresh"
JWT_REFRESH_COOKIE_PATH = "/orders/"
# D-045: 10 failures per account ID + direct peer IP within 5 minutes block for
# 5 minutes. Approved policy, fixed in code like the token lifetimes.
LOGIN_MAX_FAILURES = 10
LOGIN_WINDOW_SECONDS = 300
LOGIN_BLOCK_SECONDS = 300


def _bad_secret_key() -> bool:
    key = SECRET_KEY.strip()
    if key.lower() in {k.lower() for k in _PUBLISHED_SECRET_KEYS}:
        return True
    return len(key) < _MIN_SECRET_KEY_LENGTH


def _refuse_deployment_defaults() -> None:
    """Refuse to start a deployment that is still wearing development values.

    Silently falling back to a default is how the published PINs and the
    development secret reach a public host. Every check names the environment
    variable and never the value it found. Nothing renders a Django error report
    at this point -- the module has not finished importing, so the credential
    filter is not active either -- but the message travels wherever a boot
    failure travels, and the values are what must not travel with it.

    Development is untouched. This runs only when DEBUG is off.
    """
    missing = []
    if _bad_secret_key():
        missing.append("SECRET_KEY")
    # A wildcard is not a configured host. The whole reason DEBUG has no default
    # is to keep ALLOWED_HOSTS=['*'] off a public host; accepting a literal "*"
    # here would permit by hand exactly what that refuses by accident.
    if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
        missing.append("ALLOWED_HOSTS")
    # Django only reports a schemeless origin through a system check, and
    # gunicorn does not run system checks at boot. Without this the app starts
    # and silently rejects the origins it was configured to trust.
    if not CSRF_TRUSTED_ORIGINS or not all("://" in o for o in CSRF_TRUSTED_ORIGINS):
        missing.append("CSRF_TRUSTED_ORIGINS")
    if not ROLE_ACCOUNTS:
        missing.append("ROLE_ACCOUNTS")
    if (len(JWT_SIGNING_KEY.strip()) < 50 or JWT_SIGNING_KEY == SECRET_KEY
            or JWT_SIGNING_KEY.lower() in {k.lower() for k in _PUBLISHED_SECRET_KEYS}):
        missing.append("JWT_SIGNING_KEY")
    # DATABASE_URL is required in every mode, but it is parsed further down.
    # Naming it here means one refusal lists everything instead of a deployment
    # discovering the requirements one restart at a time.
    if not os.environ.get("DATABASE_URL", "").strip():
        missing.append("DATABASE_URL")
    if missing:
        raise ImproperlyConfigured(
            "Deployment (DEBUG=0) requires these environment variables to be set "
            "to non-default values: " + ", ".join(sorted(missing)) + ". "
            "See .env.example. Values are never logged."
        )


if not DEBUG:
    _refuse_deployment_defaults()
elif ROLE_ACCOUNTS and (len(JWT_SIGNING_KEY.strip()) < 50 or JWT_SIGNING_KEY == SECRET_KEY):
    raise ImproperlyConfigured("JWT_SIGNING_KEY must be configured separately before enabling ROLE_ACCOUNTS.")

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

# --- 앱 ---
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "orders",
]

# --- 미들웨어 ---
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

# CSRF middleware sits outside every view decorator, so a tokenless write to the
# JSON API is rejected before the API guard can answer. Django's default answers
# HTML, which a JSON client reports as a parse error rather than a permission
# problem. This view returns JSON for API paths and keeps the HTML page for
# browser navigations.
CSRF_FAILURE_VIEW = "orders.views.guards.csrf_failure"

# --- 템플릿 ---
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

# --- 데이터베이스 ---
def _parse_database_url(db_url: str):
    error = "DATABASE_URL must be a complete PostgreSQL URL (host, database and user required)"
    try:
        u = urlparse(db_url.strip())
        if (u.scheme not in ("postgres", "postgresql") or not u.hostname
                or not u.username or not u.path.strip("/") or u.fragment):
            raise ValueError
        port = u.port
    except (ValueError, AttributeError):
        raise ImproperlyConfigured(error) from None
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(u.path[1:]),
        "USER": unquote(u.username),
        "PASSWORD": unquote(u.password) if u.password else "",
        "HOST": u.hostname,
        "PORT": str(port or ""),
        "OPTIONS": {"sslmode": parse_qs(u.query).get("sslmode", ["require"])[0]},
    }


# Missing or invalid configuration must never select a local file database.
DATABASES = {"default": _parse_database_url(os.environ.get("DATABASE_URL", ""))}

# --- Supabase realtime ---
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

# --- 정적 파일(WhiteNoise) ---
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
_static_dir = BASE_DIR / "static"
if _static_dir.is_dir():
    STATICFILES_DIRS = [_static_dir]

STORAGES = {
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}
}

# --- 운영 보안 설정 ---
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- S2: Role PIN 설정(로그인용) ---
# 파서와 값은 위의 운영 필수 설정 검증 블록에서 정의한다.

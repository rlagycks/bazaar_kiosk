#BAZAAR_KIOSK/bazaar_kiosk/setting.py
from pathlib import Path
import os
from django.core.exceptions import ImproperlyConfigured
from urllib.parse import urlparse, parse_qs, unquote

# --- 기본 경로/디버그 ---
BASE_DIR = Path(__file__).resolve().parent.parent

# The published default PINs. Named here so the startup check can refuse them
# without the check itself becoming the place they are written down twice.
LEGACY_DEMO_ROLE_PINS = "ORDER:1001,B1_COUNTER:2001,KITCHEN:3001,KITCHEN_HALL:4001,KITCHEN_TAKEOUT:5001"
_DEV_SECRET_KEY = "dev-only-not-for-prod"


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
CSRF_FAILURE_VIEW = "orders.views.auth.csrf_failure"

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
def parse_role_pins(raw: str) -> dict[str, str]:
    result: dict[str, str] = {}
    if not raw:
        return result
    for pair in raw.split(","):
        pair = pair.strip()
        if ":" in pair:
            role, pin = pair.split(":", 1)
            result[role.strip().upper()] = pin.strip()
    return result

_ROLE_PINS_RAW = os.environ.get("ROLE_PINS", LEGACY_DEMO_ROLE_PINS)
ROLE_PINS = parse_role_pins(_ROLE_PINS_RAW)


# --- 운영 필수 설정 검증 (D-039) ---
def _refuse_deployment_defaults() -> None:
    """Refuse to start a deployment that is still wearing development values.

    Silently falling back to a default is how the published PINs and the
    development secret reach a public host. Every check below names the
    environment variable and never the value it found: this exception can reach
    an error report, and the values are exactly what must not appear there.

    Development is untouched. This runs only when DEBUG is off.
    """
    missing = []
    if not os.environ.get("SECRET_KEY") or SECRET_KEY == _DEV_SECRET_KEY:
        missing.append("SECRET_KEY")
    if not ALLOWED_HOSTS:
        missing.append("ALLOWED_HOSTS")
    if not CSRF_TRUSTED_ORIGINS:
        missing.append("CSRF_TRUSTED_ORIGINS")
    # The PINs are a credential, so "unset" and "still the published demo set"
    # are the same failure. D-035 replaces this mechanism in 4A2; until then it
    # is the only thing standing between the internet and the kitchen screens.
    if "ROLE_PINS" not in os.environ or _ROLE_PINS_RAW.strip() == LEGACY_DEMO_ROLE_PINS:
        missing.append("ROLE_PINS")
    elif not ROLE_PINS:
        missing.append("ROLE_PINS")
    if missing:
        raise ImproperlyConfigured(
            "Deployment (DEBUG=0) requires these environment variables to be set "
            "to non-default values: " + ", ".join(sorted(missing)) + ". "
            "See .env.example. Values are never logged."
        )


if not DEBUG:
    _refuse_deployment_defaults()

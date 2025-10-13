#BAZAAR_KIOSK/bazaar_kiosk/setting.py
from pathlib import Path
import os
from urllib.parse import urlparse, parse_qs, unquote

# --- 기본 경로/디버그 ---
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-not-for-prod")
DEBUG = os.environ.get("DEBUG", "1") == "1"

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
        "OPTIONS": {"sslmode": parse_qs(u.query).get("sslmode", ["require"])[0]},
    }

_db_url = os.environ.get("DATABASE_URL")
if _db_url:
    DATABASES = {"default": _parse_database_url(_db_url)}
else:
    DATABASES = {
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}
    }

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

ROLE_PINS = parse_role_pins(os.environ.get(
    "ROLE_PINS",
    "ORDER:1001,B1_COUNTER:2001,KITCHEN:3001,KITCHEN_HALL:4001,KITCHEN_TAKEOUT:5001"
))
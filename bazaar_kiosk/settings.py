from pathlib import Path
import os
from urllib.parse import urlparse, parse_qs, unquote

BASE_DIR = Path(__file__).resolve().parent.parent

# ── 보안/디버그: 환경변수만 사용
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-not-for-prod")
DEBUG = os.environ.get("DEBUG", "1") == "1"

# DEBUG True면 ALLOWED_HOSTS 비워도 check 경고 없음
ALLOWED_HOSTS = (
    [] if DEBUG else [h for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h]
)

# ── 지역/언어
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
    # biz apps
    "orders",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
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
        # 프로젝트 루트의 templates/ 폴더 사용
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

# ── DATABASE: DATABASE_URL(Supabase) 우선, 없으면 SQLite 로컬 개발용 폴백
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
            # Supabase는 보통 sslmode=require 필요
            "sslmode": parse_qs(u.query).get("sslmode", ["require"])[0]
        },
    }

_db_url = os.environ.get("DATABASE_URL")
if _db_url:
    DATABASES = {"default": _parse_database_url(_db_url)}
else:
    # 로컬 개발 편의를 위한 폴백(환경변수 미설정 시)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ── Static
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]  # 개발용
STATIC_ROOT = BASE_DIR / "staticfiles"    # collectstatic 용

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
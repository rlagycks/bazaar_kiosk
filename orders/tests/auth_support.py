"""Synthetic accounts and real HTTP authentication for regression tests (D-051).

Every test account logs in with the same synthetic event password. The alias
names below keep the old three-role vocabulary usable in tests that only need
"someone who can serve / monitor the kitchen / see the stats"; the matrix
tests build their own accounts per permission.
"""
from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.urls import reverse

from orders.models import Account
from orders.roles import HALL_MONITOR, SERVING, STATS, TAKEOUT_MONITOR

EVENT_PASSWORD = "test-event-password"
EVENT_PASSWORD_HASH = PBKDF2PasswordHasher().encode(EVENT_PASSWORD, "synthetic-regression-salt", iterations=1)
AUTH_SETTINGS = {"EVENT_PASSWORD_HASH": EVENT_PASSWORD_HASH, "JWT_COOKIE_SECURE": False}

# alias -> (account name, permissions). The first three mirror the retired
# shared accounts so existing journeys read the same.
ALIASES = {
    "ORDER": ("order", (SERVING,)),
    "KITCHEN": ("kitchen", (HALL_MONITOR, TAKEOUT_MONITOR)),
    "B1_COUNTER": ("counter", (STATS,)),
    "SERVING": ("serving", (SERVING,)),
    "HALL_MONITOR": ("hall", (HALL_MONITOR,)),
    "TAKEOUT_MONITOR": ("takeout", (TAKEOUT_MONITOR,)),
    "STATS": ("stats", (STATS,)),
    "BOTH_MONITORS": ("both-monitors", (HALL_MONITOR, TAKEOUT_MONITOR)),
    "NONE": ("no-permissions", ()),
}

_FLAGS = {
    SERVING: "can_serve",
    HALL_MONITOR: "can_monitor_hall",
    TAKEOUT_MONITOR: "can_monitor_takeout",
    STATS: "can_view_stats",
}


def make_account(name, *permissions, is_active=True):
    """Create or update a synthetic account holding exactly these permissions."""
    flags = {flag: code in permissions for code, flag in _FLAGS.items()}
    account, _ = Account.objects.update_or_create(
        name=name, defaults={**flags, "is_active": is_active},
    )
    return account


def ensure_account(alias):
    name, permissions = ALIASES[alias]
    return make_account(name, *permissions)


def credentials(alias):
    return {"name": ALIASES[alias][0], "password": EVENT_PASSWORD}


def login_client(client, alias):
    """Log a test client in as the alias, creating the account if needed, and
    arm it with a Bearer access token for API calls."""
    ensure_account(alias)
    csrf = client.get(reverse("orders:login")).cookies["csrftoken"].value
    response = client.post(reverse("orders:login"), credentials(alias), HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 302, response.status_code
    refreshed = client.post("/orders/auth/refresh/", HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
    assert refreshed.status_code == 200, refreshed.content
    client.defaults["HTTP_AUTHORIZATION"] = "Bearer " + refreshed.json()["access_token"]
    return response

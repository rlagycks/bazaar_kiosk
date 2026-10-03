# FILE: orders/roles.py
"""The permission vocabulary the rest of the app agrees on (D-051).

This lives outside `views/` because it is data, not a view: the guards, the
login screen, the API endpoints, the admin and the tests all need the same
names, and importing them from whichever view module happened to define them
made that module the door for everything.

D-051 replaced the three shared role accounts with personal accounts. An
account holds a *set* of these permissions, so "who may do what" is answered
by set membership, never by a single role string. The retired role names are
deliberately not aliases: a device issued under them must log in again.
"""
from __future__ import annotations

SERVING = "SERVING"
HALL_MONITOR = "HALL_MONITOR"
TAKEOUT_MONITOR = "TAKEOUT_MONITOR"
STATS = "STATS"

# (code, label, hint, landing url name). The order is the landing priority
# for an account that holds several: a serving phone lands on the order
# screen even if it can also monitor.
PERMISSION_DEFINITIONS = [
    (SERVING,         "서빙",        "테이블·포장 주문 입력",       "orders:order"),
    (HALL_MONITOR,    "식당 모니터링", "매장 주문 조리 현황",         "orders:kitchen-hall"),
    (TAKEOUT_MONITOR, "포장 모니터링", "포장 주문 조리 현황",         "orders:kitchen-takeout"),
    (STATS,           "누적·통계",    "누적 주문과 매출 통계",       "orders:b1-counter"),
]

PERMISSION_CODES = tuple(code for code, *_ in PERMISSION_DEFINITIONS)
PERMISSION_LABELS = {code: label for code, label, *_ in PERMISSION_DEFINITIONS}
PERMISSION_TO_URLNAME = {code: urlname for code, _, _, urlname in PERMISSION_DEFINITIONS}

MONITOR_PERMISSIONS = (HALL_MONITOR, TAKEOUT_MONITOR)
STATS_PERMISSIONS = (STATS,)
SERVING_PERMISSIONS = (SERVING,)

# Reading an order exposes its money: total_price, payment_method, the cash and
# ticket split, change, and per-item unit_price. Those are the same figures the
# stats endpoints are restricted to, so leaving the read open would undo that
# restriction rather than stay neutral on it. Monitors read only the orders of
# their own classification (orders/services/scope.py); STATS reads all of them.
# Creating an order stays open to every account -- the ordering screen posts,
# it never reads back (D-051 agent judgement 5, to be confirmed).
ORDER_READ_PERMISSIONS = MONITOR_PERMISSIONS + STATS_PERMISSIONS


def landing_urlname(permissions) -> str | None:
    """Where a freshly logged-in account goes. None when it holds nothing."""
    held = frozenset(permissions)
    if SERVING in held:
        return PERMISSION_TO_URLNAME[SERVING]
    if HALL_MONITOR in held and TAKEOUT_MONITOR in held:
        return "orders:kitchen"
    for code in (HALL_MONITOR, TAKEOUT_MONITOR, STATS):
        if code in held:
            return PERMISSION_TO_URLNAME[code]
    return None

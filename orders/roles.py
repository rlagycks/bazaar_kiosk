# FILE: orders/roles.py
"""The role vocabulary the rest of the app agrees on.

This lives outside `views/` because it is data, not a view: the guards, the
login screen, the API endpoints and the tests all need the same names, and
importing them from whichever view module happened to define them made that
module the door for everything.

D-034 uses one shared KITCHEN account. Hall and takeout are display filters,
not separate identities. Retired role names are deliberately not aliases: old
sessions must log in again with the shared kitchen credential.
"""
from __future__ import annotations

ROLE_DEFINITIONS = [
    ("ORDER",           "주문(서빙)",   "테이블 주문 · 서빙 전용 화면", "orders:order"),
    ("B1_COUNTER",      "주방 카운터",  "결제 · 주문 현황 모니터링",    "orders:b1-counter"),
    ("KITCHEN",         "주방",        "모든 주문을 한 화면에서 확인",  "orders:kitchen"),
]

ROLE_TO_URLNAME = {code: urlname for code, _, _, urlname in ROLE_DEFINITIONS}
ROLE_LABELS = {code: label for code, label, *_ in ROLE_DEFINITIONS}

KITCHEN_ROLES = ("KITCHEN",)
COUNTER_ROLES = ("B1_COUNTER",)

# Reading an order exposes its money: total_price, payment_method, the cash and
# ticket split, change, and per-item unit_price. Those are the same figures the
# stats endpoints are restricted to, so leaving the read open would undo that
# restriction rather than stay neutral on it. Creating an order stays open to
# every account -- the ordering screen posts, it never reads back.
ORDER_READ_ROLES = KITCHEN_ROLES + COUNTER_ROLES


def provisioned_roles() -> frozenset[str]:
    """Current configured roles; configuration changes require worker restart."""
    from django.conf import settings

    return frozenset(set(getattr(settings, "ROLE_ACCOUNTS", {})) & set(ROLE_TO_URLNAME))

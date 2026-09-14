# FILE: orders/roles.py
"""The role vocabulary the rest of the app agrees on.

This lives outside `views/` because it is data, not a view: the guards, the
login screen, the API endpoints and the tests all need the same names, and
importing them from whichever view module happened to define them made that
module the door for everything.

D-034 decided the three kitchen roles collapse into one shared account, but
that is not implemented yet. Until it is, "the kitchen" means all three: they
share the same screen and the same capabilities today.
"""
from __future__ import annotations

ROLE_DEFINITIONS = [
    ("ORDER",           "주문(서빙)",   "테이블 주문 · 서빙 전용 화면", "orders:order"),
    ("B1_COUNTER",      "주방 카운터",  "결제 · 주문 현황 모니터링",    "orders:b1-counter"),
    ("KITCHEN",         "주방",        "모든 주문을 한 화면에서 확인",  "orders:kitchen"),
    ("KITCHEN_HALL",    "홀 총괄",      "홀 주문 · 혼합 주문 집중 관리", "orders:kitchen-hall"),
    ("KITCHEN_TAKEOUT", "포장 총괄",    "포장 주문만 모아서 확인",      "orders:kitchen-takeout"),
]

ROLE_TO_URLNAME = {code: urlname for code, _, _, urlname in ROLE_DEFINITIONS}
ROLE_LABELS = {code: label for code, label, *_ in ROLE_DEFINITIONS}

KITCHEN_ROLES = ("KITCHEN", "KITCHEN_HALL", "KITCHEN_TAKEOUT")
COUNTER_ROLES = ("B1_COUNTER",)

# Reading an order exposes its money: total_price, payment_method, the cash and
# ticket split, change, and per-item unit_price. Those are the same figures the
# stats endpoints are restricted to, so leaving the read open would undo that
# restriction rather than stay neutral on it. Creating an order stays open to
# every account -- the ordering screen posts, it never reads back.
ORDER_READ_ROLES = KITCHEN_ROLES + COUNTER_ROLES


def provisioned_roles() -> frozenset[str]:
    """The roles that currently have a credential configured.

    The guards consult this on every request instead of the static table above,
    so that withdrawing a role's credential ends the sessions already holding
    it. Without it, revocation only stops new logins: every device already
    signed in keeps its access until someone logs it out, and the only way to
    reach those devices is to restart with a new SECRET_KEY, which signs out
    every role at once (BK-R019).

    Names not in ROLE_DEFINITIONS are dropped rather than honoured: a typo in
    the deployment's credential list must not mint a role.

    Today the credential store is `settings.ROLE_PINS`. When D-035's
    id/password store replaces it, this is the one place that has to change.

    **This covers withdrawal, not rotation.** Changing a role's PIN to a new
    value leaves the role provisioned, so sessions opened with the old PIN
    survive. Making rotation end them too needs the session to carry something
    derived from the credential, and that mechanism is part of the revocation
    procedure that is still undecided. Do not assume rotation logs anyone out.
    """
    from django.conf import settings

    configured = {
        str(role).upper()
        for role, secret in getattr(settings, "ROLE_PINS", {}).items()
        if secret
    }
    return frozenset(configured & set(ROLE_TO_URLNAME))

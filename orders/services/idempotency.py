"""Naming an order attempt so a retry cannot become a second order (6A).

The client mints an id for one press of 저장 and reuses it while retrying that
same order. The server stores the id with the order it created, so the second
arrival of the id is answered with the first order.

Two things this deliberately does not do:

* it does not guess. An id that comes back with a different order is refused,
  not merged and not overwritten -- the likely cause is a volunteer who edited
  the cart after a failure, and silently returning the old order would tell
  them their edit was saved.
* it does not expire ids. An expiry only changes when a duplicate happens; it
  does not prevent one.
"""

from __future__ import annotations

import hashlib
import json
import re

from orders.models import OrderRequest

# A client-generated id: UUIDs in practice, but any opaque token of a sane
# shape is accepted. Bounded and restricted because it is stored, logged and
# compared; the point is to reject nonsense early, not to prove randomness.
KEY_PATTERN = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{7,63}\Z")


class RequestIdError(ValueError):
    """The caller's request id is missing or unusable."""


def clean_key(raw) -> str:
    if raw is None or not isinstance(raw, str):
        raise RequestIdError(
            "request_id가 필요합니다. 화면을 새로고침한 뒤 다시 시도해 주세요."
        )
    key = raw.strip()
    if not KEY_PATTERN.match(key):
        raise RequestIdError(
            "request_id 형식이 올바르지 않습니다. 화면을 새로고침한 뒤 다시 시도해 주세요."
        )
    return key


def fingerprint(payload: dict) -> str:
    """A stable digest of what the order actually is.

    Only the fields that decide the order take part, so a retry that differs
    only in transport detail still counts as the same attempt, while a changed
    cart, table, payment or note does not.
    """
    items = sorted(
        (
            str(item.get("menu_item_id")),
            str(item.get("qty")),
            str(item.get("mode") or item.get("service_mode") or "").upper(),
        )
        for item in (payload.get("items") or [])
        if isinstance(item, dict)
    )
    subject = {
        "floor": str(payload.get("floor") or "").upper(),
        "order_type": str(payload.get("order_type") or "").upper(),
        "is_takeout": bool(payload.get("is_takeout")),
        "payment_method": str(payload.get("payment_method") or "").upper(),
        "table_number": str(payload.get("table_number") or "").strip(),
        "note": str(payload.get("note") or "").strip(),
        # Amounts as text, like every other field: a retry sending 8000 where
        # the first attempt sent "8000" is the same order. `None` is kept
        # distinct from 0 -- "nothing received" and "zero received" are
        # different claims -- which is why this is not str() of everything.
        "received_cash_amount": _amount(payload.get("received_cash_amount")),
        "received_ticket_amount": _amount(payload.get("received_ticket_amount")),
        "received_amount": _amount(payload.get("received_amount")),
        "items": items,
    }
    encoded = json.dumps(subject, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _amount(value):
    return None if value is None else str(value)


def find(key: str) -> OrderRequest | None:
    return (
        OrderRequest.objects.select_related("order")
        .filter(key=key)
        .first()
    )


def matches(record: OrderRequest, *, role: str, digest: str) -> bool:
    """Whether this arrival is a replay of the attempt that made the record.

    The role is part of it: two screens colliding on one id is a conflict, and
    answering with the other screen's order would hand it data it never took.
    """
    # `role` keeps the 6A parameter name; since D-051 it carries the account id.
    return record.actor == (role or "") and record.fingerprint == digest


def remember(key: str, *, role: str, digest: str, order) -> OrderRequest:
    """Record the attempt. Called inside the order's own transaction, so a
    conflict here must roll that transaction back rather than be swallowed."""
    return OrderRequest.objects.create(
        key=key, actor=role or "", fingerprint=digest, order=order
    )


def is_key_conflict(exc: Exception) -> bool:
    cause = getattr(exc, "__cause__", None)
    diag = getattr(cause, "diag", None)
    name = getattr(diag, "constraint_name", None) if diag else None
    return "orders_orderrequest_key" in (name or str(exc))

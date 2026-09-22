"""UI-05B monitoring actions: lock, compare source state, validate, then write."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from orders.models import Order, OrderStatus
from orders.services import audit, revisions, scope
from orders.services import status as status_service


class InvalidAction(ValueError):
    """Malformed input; no part of the action has been saved."""


class ActionConflict(ValueError):
    """The displayed version or requested state is no longer applicable."""


class ActionForbidden(PermissionError):
    """The locked order is outside this monitor's scope."""


@dataclass(frozen=True)
class Action:
    name: str
    expected_version: str
    items: tuple[tuple[int, int], ...]


def monitor_version(order: Order, *, items=None) -> str:
    """Opaque equality token from persisted source fields, never display labels.

    Snapshot readers pass their already-prefetched items; writers pass the rows
    locked after the order. Quantity writers also advance updated_at under
    that lock, so restoring earlier quantities cannot restore an old token.
    Including line prices/modes/quantities detects changes to their source data.
    """
    if items is None:
        items = order.items.all()
    source = {
        "order": {field.attname: getattr(order, field.attname)
                  for field in Order._meta.concrete_fields},
        "items": [[item.pk, item.menu_item_id, item.qty, item.prepared_qty,
                   item.unit_price, item.service_mode]
                  for item in sorted(items, key=lambda item: item.pk)],
    }
    encoded = json.dumps(source, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def parse(payload: dict) -> Action:
    if not isinstance(payload, dict) or set(payload) - {"action", "expected_version", "items"}:
        raise InvalidAction("action, expected_version, items만 허용됩니다.")
    name = payload.get("action")
    if not isinstance(name, str) or name not in {"progress", "depart", "reopen", "cancel"}:
        raise InvalidAction("action은 progress/depart/reopen/cancel이어야 합니다.")
    version = payload.get("expected_version")
    if not isinstance(version, str) or not version or len(version) > 128:
        raise InvalidAction("expected_version 문자열이 필요합니다.")
    rows = payload.get("items", [])
    if not isinstance(rows, list):
        raise InvalidAction("items는 배열이어야 합니다.")
    if name != "progress":
        if rows:
            raise InvalidAction("준비 수량은 progress에서만 지정할 수 있습니다.")
        return Action(name, version, ())
    if not rows:
        raise InvalidAction("주문의 모든 품목 준비 수량이 필요합니다.")
    parsed, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"id", "prepared_qty"}:
            raise InvalidAction("각 품목은 id와 prepared_qty가 필요합니다.")
        item_id, quantity = row["id"], row["prepared_qty"]
        if type(item_id) is not int or item_id < 1 or type(quantity) is not int or quantity < 0:
            raise InvalidAction("품목 id와 준비 수량은 유효한 정수여야 합니다.")
        if item_id in seen:
            raise InvalidAction("중복 품목은 허용되지 않습니다.")
        seen.add(item_id)
        parsed.append((item_id, quantity))
    return Action(name, version, tuple(parsed))


@transaction.atomic
def apply(order_id: int, payload: dict, *, actor, permissions) -> Order:
    action = parse(payload)
    order = status_service.locked(order_id)
    # Scope is decided only after taking the same lock every order writer uses.
    if not scope.may_change(order, permissions):
        raise ActionForbidden("권한이 없습니다.")
    items = list(order.items.select_for_update().order_by("id"))
    if monitor_version(order, items=items) != action.expected_version:
        raise ActionConflict("다른 기기에서 주문을 변경했습니다. 새로고침 후 다시 시도해 주세요.")

    quantities = dict(action.items)
    if action.name == "progress":
        if set(quantities) != {item.pk for item in items}:
            raise InvalidAction("주문의 모든 품목을 빠짐없이 한 번씩 지정해 주세요.")
        if any(quantities[item.pk] > item.qty for item in items):
            raise InvalidAction("준비 수량이 주문 수량을 초과합니다.")
    if order.status == OrderStatus.CANCELLED and action.name != "cancel":
        raise ActionConflict("취소된 주문은 변경할 수 없습니다.")
    if action.name == "depart":
        if order.status == OrderStatus.READY:
            if order.departed_at is None:
                raise ActionConflict("기존 완료 이력에는 출발 기록이 없습니다. 재개 후 출발해 주세요.")
            return order  # A fresh-version retry of an already recorded departure.
        if order.status != OrderStatus.PREPARING or not items:
            raise ActionConflict("준비 중인 주문만 출발할 수 있습니다.")
        quantities = {item.pk: item.qty for item in items}

    changed = False
    previous = order.status
    for item in items:
        quantity = quantities.get(item.pk, item.prepared_qty)
        if quantity != item.prepared_qty:
            item.prepared_qty = quantity
            item.save(update_fields=["prepared_qty"])
            audit.record_progress(order, item, actor)
            changed = True

    if action.name == "progress":
        status_service.sync_from_items(order)
        if changed and order.status == previous:
            # Status changes already touch the order. Quantity-only writes
            # must do so too, or 0 -> 1 -> 0 revives an earlier version.
            order.save(update_fields=["updated_at"])
    elif action.name == "depart":
        status_service.change(order, OrderStatus.READY)
        order.departed_at = timezone.now()
        order.save(update_fields=["departed_at", "updated_at"])
    elif action.name == "reopen":
        status_service.change(order, OrderStatus.PREPARING)
    elif action.name == "cancel":
        status_service.change(order, OrderStatus.CANCELLED)
    if order.status != previous:
        audit.record_status(order, actor, previous=previous)
        changed = True
    if changed:
        revisions.mark()
    return order

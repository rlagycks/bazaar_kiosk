"""D-075: takeout work by menu, allocated oldest first under order locks.

The read owns one REPEATABLE READ transaction. Completion locks orders in ID
order, then their items, and takes the shared revision lock last. The
completion token covers only what a batch can collide with: how much takeout
work has been marked done, per menu (user decision 2026-10-03). A new order,
hall progress on a mixed order or a status change elsewhere does not refuse a
batch; another device completing the same takeout work does. Mixed orders
contribute only TAKEOUT lines; hall departure remains explicit.
"""
from __future__ import annotations

import hashlib
import json

from django.db import IntegrityError, connection, transaction
from django.db.models import Exists, OuterRef, Prefetch, Sum
from django.utils import timezone

from orders.models import FloorChoices, MenuItem, NumberSeries, Order, OrderItem, OrderStatus, OrderType, TakeoutCompletionRequest
from orders.roles import TAKEOUT_MONITOR
from orders.services import audit, custom_items, idempotency, revisions, snapshots
from orders.services import status as status_service
from orders.services.monitoring_actions import ActionConflict, InvalidAction
from orders.services.monitoring_snapshot import HISTORY_PAGE_SIZE, MAX_PAGE_NUMBER


def visible():
    return Order.objects.filter(floor=FloorChoices.B1).filter(Exists(
        OrderItem.objects.filter(order_id=OuterRef("pk"), service_mode=OrderType.TAKEOUT)))


def item_key(item):
    if item.menu_item_id is not None:
        return f"menu:{item.menu_item_id}"
    return "custom:" + hashlib.sha256(custom_items.match_key(item.custom_name).encode()).hexdigest()


def completion_version(generation):
    """Takeout quantity marked done, per menu key, over every takeout line.

    Completing only ever raises these sums, and the sums do not move when an
    order arrives (it brings no done quantity) or when hall lines change. Two
    devices that read the same sums cannot both apply a batch: the first one
    changes them. Allocation itself is re-checked against the locked rows."""
    done = {}
    lines = (OrderItem.objects.filter(order__in=visible(), service_mode=OrderType.TAKEOUT)
             .values_list("menu_item_id", "custom_name").annotate(done=Sum("prepared_qty")).order_by())
    for menu_id, name, total in lines:
        key = f"menu:{menu_id}" if menu_id is not None else \
            "custom:" + hashlib.sha256(custom_items.match_key(name).encode()).hexdigest()
        done[key] = done.get(key, 0) + int(total or 0)
    source = [generation, sorted(done.items())]
    return hashlib.sha256(json.dumps(source, separators=(",", ":")).encode()).hexdigest()


def menus_for(orders):
    rows = {f"menu:{menu.pk}": {"key": f"menu:{menu.pk}", "name": menu.name,
            "remaining_qty": 0, "is_custom": False}
            for menu in MenuItem.objects.filter(is_active=True, visible_kitchen=True).order_by("sort_index", "name", "id")}
    for order in sorted(orders, key=lambda o: (o.created_at, o.pk)):
        for item in order.items.all():
            if item.service_mode != OrderType.TAKEOUT or not item.remaining_qty:
                continue
            key = item_key(item)
            row = rows.setdefault(key, {"key": key,
                "name": item.menu_item.name if item.menu_item_id else item.custom_name,
                "remaining_qty": 0, "is_custom": item.menu_item_id is None})
            row["remaining_qty"] += item.remaining_qty
    return list(rows.values())


def history_order(order):
    items = [item for item in order.items.all() if item.service_mode == OrderType.TAKEOUT]
    return {"id": order.pk, "order_no": order.order_no,
            "created_at": timezone.localtime(order.created_at).isoformat(),
            "order_date": order.order_date.isoformat() if order.order_date else None,
            "is_practice": order.number_series == NumberSeries.PRACTICE,
            "items": [{"id": item.pk, "menu_item_name": item.display_name,
                       "qty": item.qty, "is_custom": item.is_custom} for item in items],
            "total_qty": sum(item.qty for item in items)}


def _prefetched(query):
    return query.prefetch_related(Prefetch("items", queryset=OrderItem.objects.select_related("menu_item").order_by("id")))


def read(permissions, *, page=1, since=None):
    if TAKEOUT_MONITOR not in permissions:
        raise PermissionError("포장 모니터링 권한이 필요합니다.")
    if type(page) is not int or not 1 <= page <= MAX_PAGE_NUMBER:
        raise ValueError("잘못된 page")
    if connection.in_atomic_block or not connection.get_autocommit():
        raise RuntimeError("takeout snapshot must own its REPEATABLE READ transaction")
    with transaction.atomic():
        snapshots._isolate(True)
        generation, revision = revisions.state()
        version = snapshots.version_from(revision, (*permissions, "representation=takeout-v1", f"page={page}"), generation=generation)
        cursor = snapshots.CURSOR_ABSENT if not since else (
            snapshots.CURSOR_ACCEPTED if snapshots._same_lineage_and_scope(since, version) else snapshots.CURSOR_REJECTED)
        unchanged = since == version
        pending = list(_prefetched(visible().filter(status=OrderStatus.PREPARING)).order_by("id"))
        menus = menus_for(pending)
        history_total = visible().count()
        pages = (history_total + HISTORY_PAGE_SIZE - 1) // HISTORY_PAGE_SIZE
        orders = []
        if not unchanged and page <= pages:
            offset = (page - 1) * HISTORY_PAGE_SIZE
            orders = [history_order(o) for o in _prefetched(visible()).order_by("-created_at", "-id")[offset:offset + HISTORY_PAGE_SIZE]]
        return {"version": version, "unchanged": unchanged, "cursor": cursor,
                "orders": [], "count": 0, "total": len(pending), "has_more": False, "complete": True,
                "menus": [] if unchanged else menus,
                "remaining_total": sum(row["remaining_qty"] for row in menus),
                "completion_version": completion_version(generation),
                "history": {"orders": orders, "total": history_total, "page": page, "pages": pages,
                            "has_previous": page > 1 and pages > 0, "has_next": page < pages}}


def stream_digest():
    """Include catalog zeroes and every history page in SSE invalidation.

The old waiting-only digest misses edits to finished orders and empty menus.
Use the same menu/history projections as the screen, without a queue cutoff.
"""
    isolated = not connection.in_atomic_block and connection.get_autocommit()
    with transaction.atomic():
        snapshots._isolate(isolated)
        orders = list(_prefetched(visible()).order_by("id"))
        pending = [o for o in orders if o.status == OrderStatus.PREPARING]
        body = {"menus": menus_for(pending), "history": [history_order(o) for o in orders],
                "completion_version": completion_version(revisions.state()[0])}
        return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def parse(payload):
    if not isinstance(payload, dict) or set(payload) != {"request_id", "expected_version", "items"}:
        raise InvalidAction("request_id, expected_version과 items가 필요합니다.")
    try:
        request_key = idempotency.clean_key(payload["request_id"])
    except idempotency.RequestIdError as exc:
        raise InvalidAction(str(exc)) from exc
    version = payload["expected_version"]
    if not isinstance(version, str) or len(version) != 64 or any(c not in "0123456789abcdef" for c in version):
        raise InvalidAction("올바른 완료 버전이 필요합니다.")
    rows = payload["items"]
    if not isinstance(rows, list) or not rows:
        raise InvalidAction("완료할 메뉴와 수량을 선택해 주세요.")
    quantities = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"key", "quantity"}:
            raise InvalidAction("각 메뉴는 key와 quantity가 필요합니다.")
        menu_key, qty = row["key"], row["quantity"]
        if not isinstance(menu_key, str) or not 1 <= len(menu_key) <= 80 or menu_key in quantities:
            raise InvalidAction("메뉴 키가 올바르지 않거나 중복되었습니다.")
        if type(qty) is not int or not 1 <= qty <= 2**53 - 1:
            raise InvalidAction("완료 수량은 양의 정수여야 합니다.")
        quantities[menu_key] = qty
    return request_key, version, quantities


@transaction.atomic
def complete(payload, *, actor, permissions):
    if TAKEOUT_MONITOR not in permissions:
        raise PermissionError("포장 모니터링 권한이 필요합니다.")
    request_key, expected, quantities = parse(payload)
    digest = hashlib.sha256(json.dumps([expected, sorted(quantities.items())], separators=(",", ":")).encode()).hexdigest()
    # Reserve the attempt before taking order locks. A concurrent identical
    # insert waits for the first transaction's commit/rollback. A savepoint
    # keeps the losing insert from poisoning the surrounding transaction.
    try:
        with transaction.atomic():
            receipt = TakeoutCompletionRequest.objects.create(key=request_key, actor=str(actor.pk), fingerprint=digest)
    except IntegrityError as exc:
        receipt = TakeoutCompletionRequest.objects.filter(key=request_key).first()
        if receipt is None:
            raise exc
        if receipt.actor != str(actor.pk) or receipt.fingerprint != digest:
            raise ActionConflict("같은 요청 ID로 다른 완료 요청을 보낼 수 없습니다.")
        return receipt.result
    # Lock the order before examining its lines, as every other order writer does.
    orders = list(visible().filter(status=OrderStatus.PREPARING).select_for_update().order_by("id"))
    items = list(OrderItem.objects.filter(order_id__in=[o.pk for o in orders]).select_for_update().order_by("order_id", "id"))
    grouped = {o.pk: [] for o in orders}
    for item in items:
        grouped[item.order_id].append(item)
    for order in orders:
        order._prefetched_objects_cache = {"items": grouped[order.pk]}
    # A concurrent edit can remove the last TAKEOUT line while we wait for its lock.
    orders = [o for o in orders if any(i.service_mode == OrderType.TAKEOUT for i in grouped[o.pk])]
    if completion_version(revisions.state()[0]) != expected:
        raise ActionConflict("다른 기기에서 주문을 변경했습니다. 최신 수량을 확인해 주세요.")
    available = {}
    for order in orders:
        for item in grouped[order.pk]:
            if item.service_mode == OrderType.TAKEOUT:
                key = item_key(item)
                available[key] = available.get(key, 0) + item.remaining_qty
    if any(qty > available.get(key, 0) for key, qty in quantities.items()):
        raise ActionConflict("선택한 수량이 남은 포장 수량을 초과합니다. 최신 수량을 확인해 주세요.")
    completed = []
    remaining = quantities.copy()
    for order in sorted(orders, key=lambda o: (o.created_at, o.pk)):
        changed = False
        for item in grouped[order.pk]:
            if item.service_mode != OrderType.TAKEOUT:
                continue
            key = item_key(item)
            count = min(remaining.get(key, 0), item.remaining_qty)
            if count:
                item.prepared_qty += count
                item.save(update_fields=["prepared_qty"])
                audit.record_progress(order, item, actor)
                remaining[key] -= count
                changed = True
        if not changed:
            continue
        all_done = all(i.remaining_qty == 0 for i in grouped[order.pk])
        hall = any(i.service_mode == OrderType.DINE_IN for i in grouped[order.pk])
        if all_done and (not hall or order.departed_at is not None):
            previous = order.status
            status_service.change(order, OrderStatus.READY)
            audit.record_status(order, actor, previous=previous)
            completed.append(order.pk)
        else:
            order.save(update_fields=["updated_at"])
    result = {"completed_qty": sum(quantities.values()), "completed_orders": completed}
    receipt.result = result
    receipt.save(update_fields=["result"])
    revisions.mark()
    return result

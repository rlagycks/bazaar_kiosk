from __future__ import annotations
import logging
from typing import List

from django.http import JsonResponse, HttpRequest, HttpResponseBadRequest, Http404
from django.views.decorators.http import require_http_methods
from django.db import IntegrityError, transaction
from django.db.models import Sum, F, IntegerField
from django.utils import timezone

from orders.models import (
    FloorChoices, OrderType, OrderStatus, OrderSource,
    Table, MenuItem, Order, OrderItem,
)
from orders.services import allocate_floor_order_no, series_for, idempotency
from orders.services import status as status_service
from orders.roles import MONITOR_PERMISSIONS, ORDER_READ_PERMISSIONS, SERVING_PERMISSIONS, STATS_PERMISSIONS
from orders.services import audit, payments, queues, reporting, revisions, scope, snapshots
from orders.views import selectors, serializers, validators
from orders.views.guards import require_api_permissions

# The repository's first logger. There is no `LOGGING` configuration yet, so
# this reaches stderr through the root handler, which under uvicorn is the
# same stream everything else uses. Wiring logging properly is 12A1's
# observability item; one warning that nobody has to configure is worth more
# here than a signal that waits for it.
logger = logging.getLogger(__name__)




def _get_table_by_number(number: int) -> Table:
    """The table as it stands right now (8B, BK-R010).

    This lookup is order creation's only check that the table is still in
    service, so it cannot be memoised. A process-level cache made the answer
    depend on which worker took the POST and on whether that worker had seen
    the table before it was switched off. It is one indexed row.
    """
    return Table.objects.get(number=number, is_active=True)


# ---------- 메뉴/테이블 ----------
# 8B: no response cache here. Django's default backend is per-process
# memory, so `cache_page` gave each worker its own stale window and two
# screens could show different rows at the same moment. This is a handful of
# indexed rows on page load (BK-R010).
@require_api_permissions()
@require_http_methods(["GET"])
def tables_list(request: HttpRequest):
    qs = Table.objects.filter(is_active=True).order_by("sort_index", "number")
    items = [{"id": t.id, "number": t.number, "name": t.name} for t in qs]
    return JsonResponse({"items": items})


@require_api_permissions()
@require_http_methods(["GET"])
def menus_list(request: HttpRequest):
    scope = (request.GET.get("scope") or "").upper()
    channel = (request.GET.get("channel") or "").upper()  # 선택

    qs = MenuItem.objects.filter(is_active=True)

    # 스코프/채널 필터
    if scope in ("KITCHEN", "B1"):
        qs = qs.filter(visible_kitchen=True)
    else:
        qs = qs.filter(visible_counter=True)

    qs = qs.order_by("sort_index", "name")

    items = [
        {"id": m.id, "name": m.name, "price": m.price, "sort_index": m.sort_index}
        for m in qs
    ]
    return JsonResponse({"items": items})


# ---------- 주문 목록/생성 ----------
# D-051 judgement 5 (settled 2026-09-20): creating an order is the serving
# screen's job, so POST is SERVING only. Reading exposes money: monitors and STATS.
@require_api_permissions(by_method={"GET": ORDER_READ_PERMISSIONS, "POST": SERVING_PERMISSIONS})
@require_http_methods(["GET", "POST"])
def orders_collection(request: HttpRequest):
    if request.method == "GET":
        floor = (request.GET.get("floor") or "").upper()
        status = (request.GET.get("status") or "").upper()
        types_raw = request.GET.get("types") or ""
        types = [t.strip().upper() for t in types_raw.split(",") if t.strip()]

        if floor and floor != FloorChoices.B1:
            return HttpResponseBadRequest("floor 파라미터는 B1만 허용됩니다.")
        # D-051: the scope narrowing happens inside, before any filter and
        # before any cut, so a long queue in one classification can never
        # displace another monitor's orders.
        qs = selectors.visible_orders(
            request.auth_permissions, floor=floor, status=status, types=types)

        # 8B (D-055): work still to do is a queue, everything else is a page.
        # `mode` says which contract answered, so a caller whose `limit` was
        # ignored can see that from the response (PR #73 code review).
        if status == OrderStatus.PREPARING:
            page, mode = queues.waiting(qs), queues.QUEUE
        else:
            page, mode = queues.looking_back(qs, request.GET.get("limit")), queues.PAGE
        data = [serializers.order(o) for o in page.orders]
        return JsonResponse({
            "results": data,
            "count": len(data),
            "total": page.total,
            "has_more": page.has_more,
            "mode": mode,
        })

    # POST
    try:
        p = validators.body(request)
    except validators.InvalidInput as exc:
        return HttpResponseBadRequest(str(exc))

    # 6A: identify the attempt before anything else. A replay is answered with
    # the order that attempt already created, even if the menu has changed
    # since -- the caller is asking what happened, not asking again.
    try:
        request_key = idempotency.clean_key(p.get("request_id"))
    except idempotency.RequestIdError as exc:
        return HttpResponseBadRequest(str(exc))
    request_digest = idempotency.fingerprint(p)
    actor = request.auth_account
    acting_role = str(actor.id)
    replayed = _replay_if_known(request_key, acting_role, request_digest)
    if replayed is not None:
        return replayed

    # 9 (BK-R015): a field of the wrong type is the caller's mistake, and
    # used to end the request on `.upper()` with a 500.
    try:
        floor = validators.upper(p, "floor", default=FloorChoices.B1)
        order_type = validators.upper(p, "order_type")
        note = validators.text(p, "note")
    except validators.InvalidInput as exc:
        return HttpResponseBadRequest(str(exc))
    items = p.get("items") or []                      # [{menu_item_id, qty}, ...]

    if floor != FloorChoices.B1:
        return HttpResponseBadRequest("floor 파라미터는 B1만 허용됩니다.")
    if order_type not in (OrderType.DINE_IN, OrderType.TAKEOUT):
        return HttpResponseBadRequest("order_type이 유효하지 않습니다.")

    # 지하 주문서 확장 필드
    is_takeout = bool(p.get("is_takeout", order_type == OrderType.TAKEOUT))
    # 7A: every figure is checked by the payment service; nothing is int()-ed here.
    try:
        payment = payments.read_payment(p)
    except payments.AmountError as exc:
        return HttpResponseBadRequest(str(exc))
    payment_method = payment.method

    # 테이블 (지하 매장 전용 규칙)
    table = None
    try:
        table_number_raw = validators.text(p, "table_number")
    except validators.InvalidInput as exc:
        return HttpResponseBadRequest(str(exc))
    if order_type == OrderType.DINE_IN and not is_takeout:
        if not table_number_raw:
            return HttpResponseBadRequest("매장 주문은 테이블 번호가 필요합니다(포장 제외).")
        try:
            table = _get_table_by_number(int(table_number_raw))
        except Exception:
            return HttpResponseBadRequest("유효한 테이블 번호가 아닙니다.")
    elif order_type == OrderType.TAKEOUT:
        if not table_number_raw:
            return HttpResponseBadRequest("포장 주문은 101~120 번호를 입력해야 합니다.")
        try:
            table_no = int(table_number_raw)
        except ValueError:
            return HttpResponseBadRequest("포장 주문 번호는 숫자여야 합니다.")
        if not (101 <= table_no <= 120):
            return HttpResponseBadRequest("포장 주문 번호는 101~120 범위여야 합니다.")
        try:
            table = _get_table_by_number(table_no)
        except Table.DoesNotExist:
            return HttpResponseBadRequest("등록되지 않은 포장 번호입니다.")
        # D-050: one waiting customer per tag. The unique constraint is the
        # real boundary; this check exists to answer with a sentence rather
        # than an integrity error, and to say which number is taken.
        if _takeout_slot_in_use(table):
            return JsonResponse(
                {"detail": f"{table_no}번 포장 번호는 아직 사용 중입니다. "
                           "다른 번호를 사용해 주세요."},
                status=409,
            )

    cash_value, ticket_value = payment.cash, payment.ticket

    # 아이템 파싱/검증
    if not isinstance(items, list) or not items:
        return HttpResponseBadRequest("items 배열이 필요합니다.")
    parsed: List[tuple[int, int, str]] = []
    id_list: List[int] = []
    for row in items:
        if not isinstance(row, dict):
            return HttpResponseBadRequest("menu_item_id/qty 형식 오류")
        try:
            mid = payments.parse_amount(row.get("menu_item_id"), "메뉴")
            qty = payments.parse_qty(row.get("qty"))
        except payments.AmountError as exc:
            return HttpResponseBadRequest(str(exc))
        if mid is None:
            return HttpResponseBadRequest("menu_item_id/qty 형식 오류")
        # 9 (PR #75 code review): these two reached `.upper()` unguarded, so
        # `"mode": 5` in one item ended the whole request in a 500.
        try:
            mode = (validators.text(row, "mode", strip=False)
                    or validators.text(row, "service_mode", strip=False)
                    or order_type).upper()
        except validators.InvalidInput as exc:
            return HttpResponseBadRequest(str(exc))
        if mode not in (OrderType.DINE_IN, OrderType.TAKEOUT):
            return HttpResponseBadRequest("mode/service_mode 값이 유효하지 않습니다.")
        parsed.append((mid, qty, mode))
        id_list.append(mid)

    mi_map = {m.id: m for m in MenuItem.objects.filter(id__in=id_list, is_active=True)}
    if len(mi_map) != len(set(id_list)):
        return HttpResponseBadRequest("비활성 또는 존재하지 않는 메뉴가 포함되어 있습니다.")

    # 스코프별 허용 메뉴
    for mid, _, mode in parsed:
        m = mi_map[mid]
        if not m.visible_kitchen:
            return HttpResponseBadRequest("주방 메뉴만 선택 가능합니다.")

    try:
        source_raw = validators.upper(p, "source", default=OrderSource.COUNTER)
    except validators.InvalidInput as exc:
        return HttpResponseBadRequest(str(exc))
    if source_raw not in OrderSource.values:
        source_raw = OrderSource.COUNTER

    # 7A (D-048): the total is the server's price snapshot; a short payment
    # is refused before anything is written, and the change is decided here.
    try:
        total_price = payments.order_total((mi_map[mid].price, qty) for mid, qty, _ in parsed)
        settlement = payments.settle(payment, total_price)
    except (payments.AmountError, payments.PaymentRefused) as exc:
        return HttpResponseBadRequest(str(exc))

    try:
        with transaction.atomic():
            order = Order.objects.create(
                floor=floor,
                order_type=order_type,
                status=OrderStatus.PREPARING,
                source=source_raw,
                table=table,
                is_takeout=is_takeout,
                payment_method=payment_method,
                # 7C (D-054): a number in every money field, zero included.
                # A NULL here used to mean "unknown", which is what made old
                # rows need interpreting; a new order knows what it took.
                received_amount=settlement.received,
                received_cash_amount=cash_value,
                received_ticket_amount=ticket_value,
                change_amount=settlement.change,
                total_price=total_price,
                note=note[:200],
                created_by=actor,
            )
            item_objects = [
                OrderItem(
                    order=order,
                    menu_item=mi_map[mid],
                    qty=qty,
                    unit_price=mi_map[mid].price,
                    service_mode=mode,
                )
                for mid, qty, mode in parsed
            ]
            OrderItem.objects.bulk_create(item_objects, batch_size=len(item_objects) or 1)

            allocate_floor_order_no(order)  # 계열·연도별 번호 부여 (D-047)
            audit.record_created(order, actor)

            created_items = list(
                OrderItem.objects.select_related("menu_item")
                .filter(order=order)
                .order_by("id")
            )

            # Last, and inside the same transaction: if another request already
            # claimed this id, the unique index refuses here and everything above
            # -- order, items, the allocated number -- rolls back with it.
            idempotency.remember(
                request_key, role=acting_role, digest=request_digest, order=order
            )

            # 10B: last, so the board's marker is taken after every lock this
            # transaction needs and released the moment it commits. A screen
            # comparing markers now learns there is a new order without being
            # told what it is (D-019).
            revisions.mark()
    except IntegrityError as exc:
        slot_conflict = _is_takeout_slot_conflict(exc)
        if not slot_conflict and not idempotency.is_key_conflict(exc):
            raise
        # Whichever index refused us, the winner committed while we waited on
        # its insert, so its record is readable now. This request created
        # nothing. Look the attempt up again before deciding what the refusal
        # means: when the tag is held by *this same attempt* -- a retry that
        # raced its own first arrival -- the right answer is that order, not
        # "use another number", which would send the volunteer off to create
        # a second order for the same customer (2026-09-20 code review).
        replayed = _replay_if_known(request_key, acting_role, request_digest)
        if replayed is not None:
            return replayed
        if slot_conflict:
            # Two different attempts claimed the tag at once; the constraint let
            # one through. Same answer as the check above, from the other side.
            return JsonResponse(
                {"detail": f"{table.number}번 포장 번호는 아직 사용 중입니다. "
                           "다른 번호를 사용해 주세요."},
                status=409,
            )
        raise  # pragma: no cover - a key conflict whose row is gone

    order._prefetched_objects_cache = {"items": created_items}
    return JsonResponse(serializers.order(order), status=201)


def _is_takeout_slot_conflict(exc: Exception) -> bool:
    cause = getattr(exc, "__cause__", None)
    diag = getattr(cause, "diag", None)
    name = getattr(diag, "constraint_name", None) if diag else None
    return "uq_active_takeout_slot" in (name or str(exc))


def _takeout_slot_in_use(table) -> bool:
    return Order.objects.filter(
        table=table,
        order_type=OrderType.TAKEOUT,
        status__in=[OrderStatus.PREPARING, OrderStatus.READY],
    ).exists()


def _replay_if_known(key: str, role: str, digest: str):
    """The answer for an id that has been seen, or None if it has not."""
    record = idempotency.find(key)
    if record is None:
        return None
    if not idempotency.matches(record, role=role, digest=digest):
        # Deliberately says nothing about the stored order: the caller either
        # changed the order under a used id, or collided with another screen.
        return JsonResponse(
            {
                "detail": "같은 request_id로 다른 주문이 이미 저장돼 있습니다. "
                "새 주문이라면 화면을 새로고침한 뒤 다시 저장해 주세요."
            },
            status=409,
        )
    order = (
        Order.objects.select_related("table")
        .prefetch_related("items__menu_item")
        .get(pk=record.order_id)
    )
    return JsonResponse(serializers.order(order), status=200)


# ---------- 상태 변경 ----------
@require_api_permissions(*MONITOR_PERMISSIONS)
@require_http_methods(["PATCH"])
def order_status(request: HttpRequest, order_id: int):
    try:
        payload = validators.body(request)
    except validators.InvalidInput as exc:
        return HttpResponseBadRequest(str(exc))
    raw_status = payload.get("status")
    new_status = raw_status.upper() if isinstance(raw_status, str) else ""
    if new_status not in (OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.CANCELLED):
        # A value that is not a status at all is malformed input. A status the
        # order may not take is a conflict, answered below with 409.
        return HttpResponseBadRequest("status는 PREPARING/READY/CANCELLED만 허용됩니다.")

    try:
        # 6B: lock, decide and write as one step (D-050). Reading first and
        # saving afterwards is how a cancel used to be overwritten.
        with transaction.atomic():
            order = status_service.locked(order_id)
            # D-051: the lock is taken first so the classification read here
            # cannot change under the decision.
            if not scope.may_change(order, request.auth_permissions):
                return JsonResponse({"detail": "권한이 없습니다."}, status=403)
            previous = order.status
            if status_service.change(order, new_status):
                audit.record_status(order, request.auth_account, previous=previous)
                # Asking for the status the order already has wrote nothing,
                # so nothing on a screen is stale and the marker stays put.
                revisions.mark()
    except Order.DoesNotExist:
        raise Http404("주문이 존재하지 않습니다.")
    except status_service.TransitionRefused as refused:
        return JsonResponse(
            {"detail": refused.detail, "id": order_id, "status": refused.current},
            status=409,
        )

    return JsonResponse({"id": order.id, "status": order.status}, status=200)


@require_api_permissions(*MONITOR_PERMISSIONS)
@require_http_methods(["PATCH"])
def order_item_progress(request: HttpRequest, item_id: int):
    try:
        payload = validators.body(request)
    except validators.InvalidInput as exc:
        return HttpResponseBadRequest(str(exc))

    prepared_qty = payload.get("prepared_qty", None)
    done_flag = payload.get("done", None)

    try:
        with transaction.atomic():
            # Always the order first, then the item. Both rows are locked --
            # the status decision below belongs to the order, and a cancel
            # arriving in parallel must not slip between this check and the
            # write -- and taking them in one fixed order everywhere is what
            # keeps two requests on the same order from deadlocking each other
            # (2026-09-18 security review).
            order_id = (
                OrderItem.objects.filter(id=item_id)
                .values_list("order_id", flat=True)
                .first()
            )
            if order_id is None:
                raise OrderItem.DoesNotExist
            order = status_service.locked(order_id)
            if not scope.may_change(order, request.auth_permissions):
                return JsonResponse({"detail": "권한이 없습니다."}, status=403)
            item = (
                OrderItem.objects.select_related("order", "menu_item")
                .select_for_update()
                .get(id=item_id)
            )
            if status_service.is_closed(order):
                # 409, like every other refusal that is about the order's
                # state rather than the request's shape (D-050).
                return JsonResponse(
                    {"detail": "취소된 주문은 조리 상태를 바꿀 수 없습니다.",
                     "id": order.id, "status": order.status},
                    status=409,
                )

            if prepared_qty is None:
                if done_flag is None:
                    return HttpResponseBadRequest("prepared_qty 또는 done 값이 필요합니다.")
                prepared_qty = item.qty if bool(done_flag) else 0

            try:
                prepared_qty = int(prepared_qty)
            except (TypeError, ValueError):
                return HttpResponseBadRequest("prepared_qty는 정수여야 합니다.")

            if prepared_qty < 0 or prepared_qty > item.qty:
                return HttpResponseBadRequest("prepared_qty 범위 오류")

            changed = prepared_qty != item.prepared_qty
            if changed:
                item.prepared_qty = prepared_qty
                item.save(update_fields=["prepared_qty"])
                audit.record_progress(order, item, request.auth_account)

            # 상태 동기화: 수량이 말하는 상태가 이긴다 (D-050)
            previous = order.status
            status_service.sync_from_items(order)
            if order.status != previous:
                audit.record_status(order, request.auth_account, previous=previous)
            # 10B: the write most easily missed, in both directions. It is
            # saved here rather than in a service, and *either* half can move
            # without the other.
            #
            # An earlier version asked only `if changed`, and that was wrong.
            # `sync_from_items` writes the order row whenever the quantities
            # imply a different status, including when this request changed no
            # quantity at all: an order manually set READY while an item is
            # still outstanding drops back to PREPARING the moment anyone
            # re-taps a finished item. The order row committed and no screen
            # was told -- with polling gone (4B2), permanently (PR #77 review,
            # reproduced against PostgreSQL).
            if changed or order.status != previous:
                revisions.mark()
            order.refresh_from_db()
    except OrderItem.DoesNotExist:
        raise Http404("주문 품목이 존재하지 않습니다.")

    return JsonResponse({"id": order.id}, status=200)


# ---------- 10C: the kitchen board's snapshot ----------
@require_api_permissions(*ORDER_READ_PERMISSIONS)
@require_http_methods(["GET"])
def snapshot_waiting(request: HttpRequest):
    """Everything still to cook, and the version it belongs to.

    The answer to "has anything changed since the version I am showing?".
    A caller that sends the version it holds and gets `unchanged` back has
    cost the server one row read -- four round trips with BEGIN, the
    isolation level and COMMIT around it, plus a connection, since
    `CONN_MAX_AGE` is 0. A caller whose version has moved on -- or whose
    permissions have -- gets the whole list and a new version.

    Deliberately not paginated by the caller. The queue is a work list, not a
    page (8B, D-055): a screen asking for one screenful must not thereby stop
    being told what is outstanding. When the server's own bound cuts it,
    `complete` says so, and a version on an incomplete list is not a claim
    that the screen holds everything.
    """
    taken = snapshots.waiting(
        request.auth_permissions, since=request.GET.get("since") or None
    )
    if not taken.isolated:
        # Unreachable today: no deployment setting wraps a request in a
        # transaction, and `test_required_settings.py` pins that against the
        # real settings module. If it ever becomes reachable the answer is
        # still safe -- the read order means at most one extra refetch -- but
        # it is no longer the one-instant contract this endpoint documents,
        # and that should not be something only a code reader can discover.
        logger.warning(
            "snapshot served without its own isolation level: the version and "
            "the orders beside it are not guaranteed to be one instant"
        )
    return JsonResponse({
        "version": taken.version,
        "unchanged": taken.unchanged,
        # "absent" | "accepted" | "rejected" -- a screen that sent a version
        # and sees "rejected" learns its version was minted under a different
        # database lineage or different permissions, and that the list beside
        # this is the whole answer rather than a difference.
        "cursor": taken.cursor,
        "orders": [serializers.order(o) for o in taken.orders],
        "count": len(taken.orders),
        "total": taken.total,
        "has_more": taken.has_more,
        "complete": taken.complete,
    }, status=200)


# ---------- 간이 통계(카운터용) ----------
@require_api_permissions(*STATS_PERMISSIONS)
@require_http_methods(["GET"])
def stats_menu_counts(request: HttpRequest):
    floor = (request.GET.get("floor") or FloorChoices.B1).upper()
    if floor != FloorChoices.B1:
        return HttpResponseBadRequest("floor 파라미터는 B1만 허용됩니다.")

    today = timezone.localdate()
    # D-047: this is the counter's running tally for today, not a sales report,
    # so it follows today's own series. On an event day it counts event orders;
    # during a rehearsal it counts the rehearsal. It never mixes the two, and
    # the sales figures (stats_dashboard) stay event-only either way.
    qs = (
        OrderItem.objects.filter(
            order__floor=floor,
            order__status__in=[OrderStatus.PREPARING, OrderStatus.READY],
            order__order_date=today,
            order__number_series=series_for(today),
        )
        .values("menu_item__name")
        .annotate(
            qty_sum=Sum("qty"),
            amount=Sum(F("qty") * F("unit_price"), output_field=IntegerField()),
        )
        .order_by("-qty_sum", "menu_item__name")
    )

    data = [
        {"name": r["menu_item__name"], "qty": r["qty_sum"], "amount": r["amount"] or 0}
        for r in qs
    ]
    return JsonResponse({"items": data}, status=200)


@require_api_permissions(*ORDER_READ_PERMISSIONS)
@require_http_methods(["GET"])
def order_detail(request: HttpRequest, order_id: int):
    try:
        order = selectors.base().get(id=order_id)
    except Order.DoesNotExist:
        raise Http404("주문이 존재하지 않습니다.")
    if not scope.may_read(order, request.auth_permissions):
        return JsonResponse({"detail": "권한이 없습니다."}, status=403)
    return JsonResponse(serializers.order(order), status=200)


@require_api_permissions(*STATS_PERMISSIONS)
@require_http_methods(["GET"])
def stats_dashboard(request: HttpRequest):
    """The sales report (8C, D-053). The period contract and every figure's
    meaning live in services/reporting.py; this only answers HTTP."""
    try:
        period = reporting.resolve_period(request.GET)
        floor = reporting.clean_floor(request.GET.get("floor"))
    except reporting.PeriodError as exc:
        return HttpResponseBadRequest(str(exc))
    return JsonResponse(reporting.dashboard(period, floor), status=200)

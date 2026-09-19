from __future__ import annotations
import json
from typing import Any, Dict, List

from django.http import JsonResponse, HttpRequest, HttpResponseBadRequest, Http404
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import cache_page
from django.db import IntegrityError, transaction
from django.db.models import Sum, F, IntegerField, Count, Max
from django.db.models.functions import TruncHour
from django.utils import timezone
from functools import lru_cache
from datetime import datetime

from orders.models import (
    FloorChoices, PaymentMethod, OrderType, OrderStatus, OrderSource, NumberSeries,
    Table, MenuItem, Order, OrderItem,
)
from orders.services import allocate_floor_order_no, series_for, idempotency
from orders.services import status as status_service
from orders.roles import MONITOR_PERMISSIONS, ORDER_READ_PERMISSIONS, STATS_PERMISSIONS
from orders.services import audit, scope
from orders.views.guards import require_api_permissions


# ---------- 공용 ----------
def _parse_json(request: HttpRequest) -> Dict[str, Any]:
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise ValueError("JSON 파싱 실패")


def _serialize_order(o: Order) -> Dict[str, Any]:
    cash_amount = o.received_cash_amount
    ticket_amount = o.received_ticket_amount
    if cash_amount is None:
        cash_amount = o.received_amount if o.payment_method == PaymentMethod.CASH else 0
    if ticket_amount is None:
        ticket_amount = o.received_amount if o.payment_method == PaymentMethod.TICKET else 0
    total_received = (cash_amount or 0) + (ticket_amount or 0)
    due_after_ticket = max(0, (o.total_price or 0) - (ticket_amount or 0))
    change_amount = max(0, (cash_amount or 0) - due_after_ticket)
    return {
        "id": o.id,
        "floor": o.floor,
        "order_type": o.order_type,
        "status": o.status,
        "order_no": o.order_no,
        "order_date": o.order_date.isoformat() if o.order_date else None,
        # D-047: the kitchen shows practice orders, marked; sales leave them out.
        "number_series": o.number_series,
        "is_practice": o.number_series == NumberSeries.PRACTICE,
        "table": ({"id": o.table_id, "number": o.table.number, "name": o.table.name} if o.table_id else None),
        "is_takeout": o.is_takeout,
        "payment_method": o.payment_method,
        "received_amount": o.received_amount,
        "received_cash_amount": cash_amount or 0,
        "received_ticket_amount": ticket_amount or 0,
        "total_price": o.total_price,
        "note": o.note,
        "change_amount": change_amount,
        "created_at": timezone.localtime(o.created_at).isoformat(),
        "items": [
            {
                "id": i.id,
                "menu_item": {"id": i.menu_item_id, "name": i.menu_item.name, "price": i.unit_price},
                "menu_item_name": i.menu_item.name,
                "qty": i.qty,
                "unit_price": i.unit_price,
                "line_total": i.qty * (i.unit_price or 0),
                "service_mode": i.service_mode,
                "prepared_qty": i.prepared_qty,
                "remaining_qty": i.remaining_qty,
                "is_prepared": i.is_prepared,
            }
            for i in o.items.all()
        ],
    }


def _order_base_queryset():
    return (
        Order.objects.select_related("table")
        .prefetch_related("items", "items__menu_item")
    )


def _parse_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None


def _date_limits(request: HttpRequest):
    start = _parse_date(request.GET.get("start_date"))
    end = _parse_date(request.GET.get("end_date"))
    start_date = start.date() if start else None
    end_date = end.date() if end else None
    return start_date, end_date


def _filtered_orders(request: HttpRequest):
    qs = Order.objects.filter(
        status__in=[OrderStatus.PREPARING, OrderStatus.READY],
        number_series=NumberSeries.REAL,
        order_date=datetime(2025, 10, 18).date(),
    )
    return qs, datetime(2025, 10, 18).date(), datetime(2025, 10, 18).date()


@lru_cache(maxsize=128)
def _get_table_by_number(number: int) -> Table:
    return Table.objects.get(number=number, is_active=True)


# ---------- 메뉴/테이블 ----------
@require_api_permissions()
@cache_page(60)
@require_http_methods(["GET"])
def tables_list(request: HttpRequest):
    qs = Table.objects.filter(is_active=True).order_by("sort_index", "number")
    items = [{"id": t.id, "number": t.number, "name": t.name} for t in qs]
    return JsonResponse({"items": items})


@require_api_permissions()
@cache_page(60)
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
@require_api_permissions(by_method={"GET": ORDER_READ_PERMISSIONS})
@require_http_methods(["GET", "POST"])
def orders_collection(request: HttpRequest):
    if request.method == "GET":
        floor = (request.GET.get("floor") or "").upper()
        status = (request.GET.get("status") or "").upper()
        types_raw = request.GET.get("types") or ""
        types = [t.strip().upper() for t in types_raw.split(",") if t.strip()]
        try:
            limit = int(request.GET.get("limit") or 50)
        except ValueError:
            limit = 50
        limit = max(1, min(limit, 200))

        # D-051: a monitor sees only the orders of its own classification.
        qs = scope.visible(_order_base_queryset(), request.auth_permissions).order_by("-created_at", "-id")
        if floor and floor != FloorChoices.B1:
            return HttpResponseBadRequest("floor 파라미터는 B1만 허용됩니다.")
        if floor == FloorChoices.B1:
            qs = qs.filter(floor=floor)
        if status in (OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.CANCELLED):
            qs = qs.filter(status=status)
        if types:
            qs = qs.filter(order_type__in=types)

        data = [_serialize_order(o) for o in qs[:limit]]
        return JsonResponse({"results": data, "count": len(data)})

    # POST
    try:
        p = _parse_json(request)
    except ValueError as e:
        return HttpResponseBadRequest(str(e))

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

    floor = (p.get("floor") or FloorChoices.B1).upper()
    order_type = (p.get("order_type") or "").upper()
    items = p.get("items") or []                      # [{menu_item_id, qty}, ...]
    note = (p.get("note") or "").strip()

    if floor != FloorChoices.B1:
        return HttpResponseBadRequest("floor 파라미터는 B1만 허용됩니다.")
    if order_type not in (OrderType.DINE_IN, OrderType.TAKEOUT):
        return HttpResponseBadRequest("order_type이 유효하지 않습니다.")

    # 지하 주문서 확장 필드
    is_takeout = bool(p.get("is_takeout", order_type == OrderType.TAKEOUT))
    payment_method = (p.get("payment_method") or PaymentMethod.CASH).upper()
    received_amount = p.get("received_amount", None)
    received_cash_amount = p.get("received_cash_amount", None)
    received_ticket_amount = p.get("received_ticket_amount", None)
    if payment_method not in (PaymentMethod.CASH, PaymentMethod.TICKET, PaymentMethod.CASH_TICKET):
        return HttpResponseBadRequest("payment_method 값이 유효하지 않습니다.")

    # 테이블 (지하 매장 전용 규칙)
    table = None
    table_number_raw = (p.get("table_number") or "").strip()
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

    def _to_int(value):
        if value in (None, ""):
            return None
        if isinstance(value, str):
            value = value.strip().replace(",", "")
            if value == "":
                return None
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValueError

    try:
        if payment_method == PaymentMethod.CASH:
            cash_value = _to_int(received_amount) or 0
            ticket_value = 0
        elif payment_method == PaymentMethod.TICKET:
            cash_value = 0
            ticket_value = _to_int(received_amount) or 0
        else:
            cash_value = _to_int(received_cash_amount)
            ticket_value = _to_int(received_ticket_amount)
            if cash_value is None or ticket_value is None:
                cash_value = None
                ticket_value = None
                if isinstance(received_amount, str) and "+" in received_amount:
                    parts = [part.strip() for part in received_amount.split("+") if part.strip()]
                    if len(parts) == 2:
                        try:
                            cash_value = _to_int(parts[0])
                            ticket_value = _to_int(parts[1])
                        except ValueError:
                            cash_value = None
                            ticket_value = None
                if cash_value is None or ticket_value is None:
                    raise ValueError
    except ValueError:
        return HttpResponseBadRequest("금액 입력이 올바르지 않습니다.")

    cash_value = int(cash_value or 0)
    ticket_value = int(ticket_value or 0)
    if payment_method == PaymentMethod.CASH_TICKET and (cash_value <= 0 or ticket_value <= 0):
        return HttpResponseBadRequest("현금과 티켓 금액을 모두 입력하세요.")

    total_received = cash_value + ticket_value

    # 아이템 파싱/검증
    if not isinstance(items, list) or not items:
        return HttpResponseBadRequest("items 배열이 필요합니다.")
    parsed: List[tuple[int, int, str]] = []
    id_list: List[int] = []
    for row in items:
        try:
            mid = int(row.get("menu_item_id"))
            qty = int(row.get("qty"))
        except Exception:
            return HttpResponseBadRequest("menu_item_id/qty 형식 오류")
        if qty < 1:
            return HttpResponseBadRequest("qty는 1 이상")
        mode = (row.get("mode") or row.get("service_mode") or order_type).upper()
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

    source_raw = (p.get("source") or OrderSource.COUNTER).upper()
    if source_raw not in OrderSource.values:
        source_raw = OrderSource.COUNTER

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
                received_amount=total_received or None,
                received_cash_amount=cash_value or None,
                received_ticket_amount=ticket_value or None,
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

            total_price = sum(
                (mi_map[mid].price or 0) * qty for mid, qty, _ in parsed
            )
            Order.objects.filter(pk=order.pk).update(total_price=total_price)
            order.total_price = total_price

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
    return JsonResponse(_serialize_order(order), status=201)


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
    return JsonResponse(_serialize_order(order), status=200)


# ---------- 상태 변경 ----------
@require_api_permissions(*MONITOR_PERMISSIONS)
@require_http_methods(["PATCH"])
def order_status(request: HttpRequest, order_id: int):
    try:
        payload = _parse_json(request)
    except ValueError as e:
        return HttpResponseBadRequest(str(e))
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
        payload = _parse_json(request)
    except ValueError as e:
        return HttpResponseBadRequest(str(e))

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

            if prepared_qty != item.prepared_qty:
                item.prepared_qty = prepared_qty
                item.save(update_fields=["prepared_qty"])
                audit.record_progress(order, item, request.auth_account)

            # 상태 동기화: 수량이 말하는 상태가 이긴다 (D-050)
            previous = order.status
            status_service.sync_from_items(order)
            if order.status != previous:
                audit.record_status(order, request.auth_account, previous=previous)
            order.refresh_from_db()
    except OrderItem.DoesNotExist:
        raise Http404("주문 품목이 존재하지 않습니다.")

    return JsonResponse({"id": order.id}, status=200)


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
        order = _order_base_queryset().get(id=order_id)
    except Order.DoesNotExist:
        raise Http404("주문이 존재하지 않습니다.")
    if not scope.may_read(order, request.auth_permissions):
        return JsonResponse({"detail": "권한이 없습니다."}, status=403)
    return JsonResponse(_serialize_order(order), status=200)


@require_api_permissions(*STATS_PERMISSIONS)
@require_http_methods(["GET"])
def stats_dashboard(request: HttpRequest):
    orders_qs, start_date, end_date = _filtered_orders(request)
    floor = (request.GET.get("floor") or "").upper()
    if floor:
        if floor not in FloorChoices.values:
            return HttpResponseBadRequest("유효하지 않은 floor 값입니다.")
        orders_qs = orders_qs.filter(floor=floor)

    items_filters = {
        "order__status__in": [OrderStatus.PREPARING, OrderStatus.READY],
        # D-047/D-048: rehearsals and cancelled orders are not revenue. The
        # status filter above is the cancellation half.
        "order__number_series": NumberSeries.REAL,
    }
    if start_date:
        items_filters["order__order_date__gte"] = start_date
    if end_date:
        items_filters["order__order_date__lte"] = end_date
    if floor:
        items_filters["order__floor"] = floor

    totals = orders_qs.aggregate(
        total_revenue=Sum("total_price"),
        cash_total=Sum("received_cash_amount"),
        ticket_total=Sum("received_ticket_amount"),
        order_count=Count("id"),
    )
    total_orders = totals.get("order_count") or 0
    total_revenue = totals.get("total_revenue") or 0
    cash_total = totals.get("cash_total") or 0
    ticket_total = totals.get("ticket_total") or 0

    items_qs = OrderItem.objects.filter(**items_filters)
    item_totals = items_qs.aggregate(
        item_count=Sum("qty"),
        item_revenue=Sum(F("qty") * F("unit_price"), output_field=IntegerField()),
    )
    total_items = item_totals.get("item_count") or 0

    menu_breakdown = list(
        items_qs.values("menu_item__name")
        .annotate(
            qty_sum=Sum("qty"),
            amount=Sum(F("qty") * F("unit_price"), output_field=IntegerField()),
        )
        .order_by("-qty_sum", "menu_item__name")
    )

    hourly = list(
        orders_qs.annotate(hour=TruncHour("created_at"))
        .values("hour")
        .annotate(
            orders=Count("id"),
            revenue=Sum("total_price"),
        )
        .order_by("hour")
    )
    current_tz = timezone.get_current_timezone()
    for row in hourly:
        hour = row["hour"]
        if hour:
            if timezone.is_naive(hour):
                hour = timezone.make_aware(hour, timezone.utc)
            hour_local = hour.astimezone(current_tz)
            row["hour_label"] = hour_local.strftime("%H:%M")
        else:
            row["hour_label"] = ""
        row["orders"] = row["orders"] or 0
        row["revenue"] = row["revenue"] or 0

    total_payment = cash_total + ticket_total
    payment_breakdown = {
        "cash": cash_total,
        "ticket": ticket_total,
        "cash_ratio": float(cash_total) / total_payment if total_payment else 0.0,
        "ticket_ratio": float(ticket_total) / total_payment if total_payment else 0.0,
    }

    response = {
        "period": {
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "floor": floor or None,
        },
        "summary": {
            "orders": total_orders,
            "items": total_items,
            "revenue": total_revenue,
        },
        "payment": payment_breakdown,
        "menu": [
            {
                "name": row["menu_item__name"],
                "qty": row["qty_sum"],
                "amount": row["amount"] or 0,
            }
            for row in menu_breakdown
        ],
        "hourly": [
            {
                "hour": row["hour_label"],
                "orders": row["orders"],
                "revenue": row["revenue"],
            }
            for row in hourly
        ],
    }
    return JsonResponse(response, status=200)

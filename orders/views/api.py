from __future__ import annotations
import json
from typing import Any, Dict, List

from django.http import JsonResponse, HttpRequest, HttpResponseBadRequest, Http404
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt  # 개발 편의. 운영 전 제거 권장.
from django.db import transaction
from django.db.models import Sum, F, IntegerField
from django.utils import timezone

from orders.models import (
    FloorChoices, PaymentMethod, OrderType, OrderStatus, OrderSource,
    Table, MenuItem, Order, OrderItem,
)
from orders.services import allocate_floor_order_no, recalc_totals


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


# ---------- 메뉴/테이블 ----------
@require_http_methods(["GET"])
def tables_list(request: HttpRequest):
    qs = Table.objects.filter(is_active=True).order_by("sort_index", "number")
    items = [{"id": t.id, "number": t.number, "name": t.name} for t in qs]
    return JsonResponse({"items": items})


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
@csrf_exempt
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

        qs = (
            Order.objects.all()
            .select_related("table")
            .prefetch_related("items", "items__menu_item")
            .order_by("-created_at", "-id")
        )
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
            table = Table.objects.get(number=int(table_number_raw), is_active=True)
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
            table = Table.objects.get(number=table_no, is_active=True)
        except Table.DoesNotExist:
            return HttpResponseBadRequest("등록되지 않은 포장 번호입니다.")

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
        )
        for mid, qty, mode in parsed:
            m = mi_map[mid]
            OrderItem.objects.create(
                order=order,
                menu_item=m,
                qty=qty,
                unit_price=m.price,
                service_mode=mode,
            )

        allocate_floor_order_no(order)  # 층별 일자 카운터 부여
        recalc_totals(order)            # 합계 계산
        order.refresh_from_db()

    order = (
        Order.objects.filter(id=order.id)
        .select_related("table")
        .prefetch_related("items", "items__menu_item")
        .get()
    )
    return JsonResponse(_serialize_order(order), status=201)


# ---------- 상태 변경 ----------
@csrf_exempt
@require_http_methods(["PATCH"])
def order_status(request: HttpRequest, order_id: int):
    try:
        payload = _parse_json(request)
    except ValueError as e:
        return HttpResponseBadRequest(str(e))
    new_status = (payload.get("status") or "").upper()
    if new_status not in (OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.CANCELLED):
        return HttpResponseBadRequest("status는 PREPARING/READY/CANCELLED만 허용됩니다.")

    try:
        order = (
            Order.objects.select_related("table")
            .prefetch_related("items", "items__menu_item")
            .get(id=order_id)
        )
    except Order.DoesNotExist:
        raise Http404("주문이 존재하지 않습니다.")

    order.status = new_status

    order.save(update_fields=["status", "updated_at"])

    return JsonResponse(_serialize_order(order), status=200)


def _sync_order_status_from_items(order: Order) -> None:
    if order.status == OrderStatus.CANCELLED:
        return
    remaining_exists = order.items.filter(prepared_qty__lt=F("qty")).exists()
    desired = OrderStatus.PREPARING if remaining_exists else OrderStatus.READY
    if order.status != desired:
        order.status = desired
        order.save(update_fields=["status", "updated_at"])


@csrf_exempt
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
            item = (
                OrderItem.objects.select_related("order", "menu_item")
                .select_for_update()
                .get(id=item_id)
            )
            order = item.order
            if order.status == OrderStatus.CANCELLED:
                return HttpResponseBadRequest("취소된 주문입니다.")

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

            # 상태 동기화
            _sync_order_status_from_items(order)
            order.refresh_from_db()
    except OrderItem.DoesNotExist:
        raise Http404("주문 품목이 존재하지 않습니다.")

    order = (
        Order.objects.filter(id=order.id)
        .select_related("table")
        .prefetch_related("items", "items__menu_item")
        .get()
    )
    return JsonResponse(_serialize_order(order), status=200)


# ---------- 간이 통계(카운터용) ----------
@require_http_methods(["GET"])
def stats_menu_counts(request: HttpRequest):
    floor = (request.GET.get("floor") or FloorChoices.B1).upper()
    if floor != FloorChoices.B1:
        return HttpResponseBadRequest("floor 파라미터는 B1만 허용됩니다.")

    today = timezone.localdate()
    qs = (
        OrderItem.objects.filter(
            order__floor=floor,
            order__status__in=[OrderStatus.PREPARING, OrderStatus.READY],
            order__created_at__date=today,
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


@require_http_methods(["GET"])
def kitchen_menu_summary(request: HttpRequest):
    floor = (request.GET.get("floor") or FloorChoices.B1).upper()
    if floor != FloorChoices.B1:
        return HttpResponseBadRequest("floor 파라미터는 B1만 허용됩니다.")

    qs = OrderItem.objects.filter(
        order__status=OrderStatus.PREPARING,
        order__floor=floor,
    ).values("menu_item_id", "menu_item__name")

    qs = qs.annotate(
        pending=Sum(F("qty") - F("prepared_qty"), output_field=IntegerField()),
    ).filter(pending__gt=0).order_by("-pending", "menu_item__name")

    data = [
        {"menu_item_id": r["menu_item_id"], "name": r["menu_item__name"], "pending": r["pending"]}
        for r in qs
    ]
    return JsonResponse({"items": data}, status=200)

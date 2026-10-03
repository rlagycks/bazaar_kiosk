"""Changing an order's lines after it was taken (7B, D-052).

The serving screen creates orders; nothing in the field edits them. The
Django admin can, and until 7B it did so straight into the tables: a
quantity changed there left the stored total, the change and the status
where they were (BK-R008). The user chose to keep that editing and route it
through here, so an admin save keeps the same promises the screens keep:

* the total is the price snapshot times quantity, recomputed from the lines;
* the money received is history and is not touched; the change is derived
  from it again, and a total the money no longer covers is refused (D-048);
* incomplete items reopen READY; preparation alone never completes it (UI-05B);
* every change leaves an event (D-051).

Callers validate first with `check_lines` -- inside a form, where a refusal
can become a message -- and apply with `apply_line_changes` inside the
transaction that saved the lines.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from orders.models import Account, Order, OrderStatus, PaymentMethod
from orders.services import audit, payments
from orders.services import status as status_service


class EditRefused(ValueError):
    """The lines as proposed cannot be saved. The message is for the form."""


@dataclass(frozen=True)
class Line:
    """One proposed line: what it would cost and what the kitchen already did."""
    unit_price: int
    qty: int
    prepared_qty: int = 0
    deleting: bool = False
    has_history: bool = False
    # A menu item the serving screen could not sell (inactive, or not a
    # kitchen item). The admin must not add what the API refuses (PR #70).
    sellable: bool = True


def payment_of(order: Order) -> payments.Payment:
    """The money as it was received, from the stored row. Older rows kept a
    single `received_amount`; the split fields are the authority when set."""
    cash = order.received_cash_amount
    ticket = order.received_ticket_amount
    if cash is None:
        cash = order.received_amount if order.payment_method == PaymentMethod.CASH else 0
    if ticket is None:
        ticket = order.received_amount if order.payment_method == PaymentMethod.TICKET else 0
    return payments.Payment(order.payment_method, int(cash or 0), int(ticket or 0))


def check_lines(order: Order, lines: Iterable[Line]) -> payments.Settlement:
    """Refuse what must not be saved; otherwise say what the order would settle to."""
    if order.status == OrderStatus.CANCELLED:
        raise EditRefused("취소된 주문의 품목은 바꿀 수 없습니다.")
    kept = []
    for line in lines:
        if line.deleting:
            if line.has_history:
                raise EditRefused("조리 이력이 있는 품목은 지울 수 없습니다. 수량을 조정해 주세요.")
            continue
        if not line.sellable:
            raise EditRefused("판매 중인 주방 메뉴만 담을 수 있습니다.")
        if line.qty < 1 or line.qty > payments.MAX_QTY:
            raise EditRefused(f"수량은 1 이상 {payments.MAX_QTY} 이하여야 합니다.")
        if line.qty < line.prepared_qty:
            raise EditRefused("이미 조리한 수량보다 적게 줄일 수 없습니다.")
        kept.append((line.unit_price, line.qty))
    if not kept:
        raise EditRefused("주문에는 품목이 하나 이상 있어야 합니다.")
    try:
        total = payments.order_total(kept)
        return payments.settle(payment_of(order), total)
    except (payments.AmountError, payments.PaymentRefused) as exc:
        raise EditRefused(str(exc)) from exc


def apply_line_changes(order: Order, actor: Account | None) -> None:
    """Bring the order row in line with its saved items. Call with the order
    locked, inside the transaction that wrote the items."""
    lines = [Line(int(item.unit_price or 0), item.qty, item.prepared_qty)
             for item in order.items.all()]
    settlement = check_lines(order, lines)
    order.total_price = payments.order_total((l.unit_price, l.qty) for l in lines)
    order.change_amount = settlement.change
    order.save(update_fields=["total_price", "change_amount", "updated_at"])
    previous = order.status
    status_service.sync_from_items(order)
    # The ITEMS row carries the status the edit left the order in; the STATUS
    # row after it says how it got there (PR #70 review).
    audit.record_items(order, actor)
    if order.status != previous:
        audit.record_status(order, actor, previous=previous)

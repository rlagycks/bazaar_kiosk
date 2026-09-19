"""What an order costs and whether it was paid (7A, D-048).

Money arrives from the order screen as JSON, which means it can arrive as
anything: a float, a boolean, a string with commas, a negative number. Until
7A the view answered with `int()`, so `True` was one won, `1.9` was one won,
and a 5000-won order saved happily with nothing received (BK-R014).

Every amount passes through here now, and the rules are the user's (D-048):

* amounts are whole, non-negative won, bounded so a typo cannot become a
  ten-digit sale;
* the total is the server's own price snapshot times quantity;
* received < total is refused outright, not warned about;
* the change is decided here and stored with the order. Ticket surplus is
  not change: tickets are not refunded in cash. That last rule is an agent
  reading of the existing screen, not a user decision, and is recorded as
  such in docs/modernization/PAYMENTS.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from orders.models import PaymentMethod

# One field's ceiling. A school festival sells bowls, not cars: ten million won
# in a single field is a mistyped number, not a payment. (Agent judgement.)
MAX_AMOUNT = 10_000_000
# The largest one order may come to. Same reasoning, same bound.
MAX_TOTAL = MAX_AMOUNT
# One line's quantity ceiling. Two digits is what the screen shows.
MAX_QTY = 99
# ASCII digits only. `str.isdigit()` also says yes to superscripts and other
# scripts' digits, some of which `int()` then refuses with a ValueError that is
# not ours (PR #69 review). The length bound keeps `int()` away from its own
# 4300-digit limit; MAX_AMOUNT has eight digits.
_DIGITS = re.compile(r"[0-9]{1,12}")


class AmountError(ValueError):
    """The caller's number cannot be used. The message is a sentence for the
    screen; it names the field and not the value."""


class PaymentRefused(ValueError):
    """The money does not cover the order (D-048)."""


@dataclass(frozen=True)
class Payment:
    method: str
    cash: int
    ticket: int

    @property
    def received(self) -> int:
        return self.cash + self.ticket


@dataclass(frozen=True)
class Settlement:
    received: int
    change: int


def parse_amount(raw, field: str) -> int | None:
    """A whole number of won, or None when nothing was sent.

    None and the empty string mean "not given"; the caller decides whether
    that is allowed. Everything else has to be an integer already, or a
    string of digits (commas and surrounding blanks tolerated, since that is
    how people type money). Floats are refused even when integral: a client
    that sends 5000.0 is a client that could send 5000.5, and the one figure
    we must never do is round money.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise AmountError(f"{field} 값이 올바르지 않습니다.")
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, str):
        text = raw.strip().replace(",", "")
        if text == "":
            return None
        if not _DIGITS.fullmatch(text):
            raise AmountError(f"{field} 값이 올바르지 않습니다.")
        value = int(text)
    else:
        raise AmountError(f"{field} 값이 올바르지 않습니다.")
    if value < 0:
        raise AmountError(f"{field}은(는) 0 이상이어야 합니다.")
    if value > MAX_AMOUNT:
        raise AmountError(f"{field}이(가) 너무 큽니다.")
    return value


def parse_qty(raw) -> int:
    value = parse_amount(raw, "수량")
    if value is None or value < 1:
        raise AmountError("수량은 1 이상이어야 합니다.")
    if value > MAX_QTY:
        raise AmountError(f"수량은 {MAX_QTY} 이하여야 합니다.")
    return value


def read_payment(payload: dict) -> Payment:
    """The payment as the order screen described it.

    Single methods report one figure in `received_amount`. Mixed payment
    reports cash and ticket separately, or -- for the older screen -- as one
    `"cash+ticket"` string, and both parts have to be there: a mixed payment
    with one side missing is a single payment sent under the wrong label.
    """
    method = str(payload.get("payment_method") or PaymentMethod.CASH).upper()
    if method not in (PaymentMethod.CASH, PaymentMethod.TICKET, PaymentMethod.CASH_TICKET):
        raise AmountError("payment_method 값이 유효하지 않습니다.")
    if method == PaymentMethod.CASH:
        return Payment(method, _single(payload, "received_cash_amount", "받은 현금"), 0)
    if method == PaymentMethod.TICKET:
        return Payment(method, 0, _single(payload, "received_ticket_amount", "받은 식권"))
    cash = parse_amount(payload.get("received_cash_amount"), "받은 현금")
    ticket = parse_amount(payload.get("received_ticket_amount"), "받은 식권")
    if cash is None or ticket is None:
        cash, ticket = _split_legacy_pair(payload.get("received_amount"))
    if not cash or not ticket:
        raise AmountError("현금과 식권 금액을 모두 입력하세요.")
    return Payment(method, cash, ticket)


def _single(payload: dict, specific: str, field: str) -> int:
    """One method's figure. The screen sends it twice -- as the method's own
    field and as `received_amount` -- and older callers send only the latter.
    Either is accepted; both together have to agree, because two different
    figures for one payment is a bug upstream, not a choice to make here."""
    own = parse_amount(payload.get(specific), field)
    total = parse_amount(payload.get("received_amount"), field)
    if own is not None and total is not None and own != total:
        raise AmountError(f"{field} 값이 서로 다릅니다.")
    return own if own is not None else (total or 0)


def _split_legacy_pair(raw) -> tuple[int | None, int | None]:
    if not isinstance(raw, str) or "+" not in raw:
        return None, None
    parts = [part.strip() for part in raw.split("+")]
    if len(parts) != 2 or not all(parts):
        return None, None
    return parse_amount(parts[0], "받은 현금"), parse_amount(parts[1], "받은 식권")


def order_total(lines: Iterable[tuple[int, int]]) -> int:
    """Sum of unit price times quantity, from the server's own figures."""
    total = sum(int(price or 0) * int(qty) for price, qty in lines)
    if total > MAX_TOTAL:
        raise AmountError("주문 합계가 너무 큽니다.")
    return total


def settle(payment: Payment, total: int) -> Settlement:
    """Refuse a short payment; otherwise say how much cash goes back.

    Tickets pay first, cash covers the rest, and only cash beyond that rest
    is change. A ticket worth more than the order is simply used up.
    """
    if payment.received < total:
        raise PaymentRefused("받은 금액이 합계보다 적습니다. 금액을 확인해 주세요.")
    due_after_ticket = max(0, total - payment.ticket)
    return Settlement(received=payment.received, change=max(0, payment.cash - due_after_ticket))


def change_for(*, cash: int | None, ticket: int | None, total: int | None) -> int:
    """The same rule as `settle`, for rows saved before the change was stored."""
    due_after_ticket = max(0, (total or 0) - (ticket or 0))
    return max(0, (cash or 0) - due_after_ticket)

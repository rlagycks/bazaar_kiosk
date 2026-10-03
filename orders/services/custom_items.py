"""Custom ("기타") order lines (D-073).

The serving screen can sell something the menu does not list, or a menu dish
at a price agreed on the spot: a name, a quantity and what the whole line
cost. "삼계탕 3개 2만원" is one line of 20,000 won; there is no unit price,
because 20,000 does not divide by 3 in whole won.

When the name is a menu's name the line is tied to that menu at the moment it
is taken, so the sales report can show it under that menu ("30개 정가, 3개
기타") and a later rename of the menu does not move it. Names are compared
without whitespace and case. Two menus answering to the same name are two
different items (BK-R034), so an ambiguous name ties to neither. Only kitchen
menus are candidates: the serving screen cannot sell any other (PR review L1).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from orders.models import MenuItem
from orders.services import payments

NAME_MAX = 100


class CustomLineError(ValueError):
    """The custom line cannot be taken. The message is for the serving screen."""


@dataclass(frozen=True)
class CustomLine:
    name: str
    qty: int
    amount: int


def clean_name(raw) -> str:
    """The name as it will be stored: NFC, blanks collapsed, nothing around it."""
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise CustomLineError("기타 품목명이 올바르지 않습니다.")
    return " ".join(unicodedata.normalize("NFC", raw).split())


def match_key(name: str) -> str:
    return "".join(unicodedata.normalize("NFC", name).split()).casefold()


def read_line(row: dict) -> CustomLine:
    name = clean_name(row.get("custom_name"))
    if not name:
        raise CustomLineError("기타 품목명을 입력해 주세요.")
    if len(name) > NAME_MAX:
        raise CustomLineError(f"기타 품목명은 {NAME_MAX}자 이하여야 합니다.")
    try:
        qty = payments.parse_qty(row.get("qty"))
        amount = payments.parse_amount(row.get("line_amount"), "기타 금액")
    except payments.AmountError as exc:
        raise CustomLineError(str(exc)) from exc
    if amount is None:
        raise CustomLineError("기타 품목의 금액(줄 합계)을 입력해 주세요.")
    return CustomLine(name, qty, amount)


def match_menus(names) -> dict[str, MenuItem]:
    """Each name's menu, for the names that answer to exactly one.

    Active menus are preferred: a dish taken off the menu still has its old
    row, and a new one may carry the same name. Among the preferred group the
    match must be unique, or the name stays unmatched."""
    wanted = {match_key(name) for name in names}
    if not wanted:
        return {}
    candidates: dict[str, list[MenuItem]] = {}
    for menu in MenuItem.objects.filter(visible_kitchen=True).order_by("id"):
        key = match_key(menu.name)
        if key in wanted:
            candidates.setdefault(key, []).append(menu)
    matched = {}
    for name in names:
        found = candidates.get(match_key(name), [])
        active = [menu for menu in found if menu.is_active]
        pool = active or found
        if len(pool) == 1:
            matched[name] = pool[0]
    return matched

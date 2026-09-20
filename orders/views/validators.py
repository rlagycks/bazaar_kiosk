"""What a request body is allowed to be (9, BK-R015).

Every writing endpoint read its body with one helper and then treated the
result as a mapping. `[]`, `"text"`, `5` and `null` are all valid JSON and
none of them is a mapping, so the next `.get` raised an AttributeError and
Django answered 500. One level down the same thing happened per field: a
`floor` that arrived as a number ended the request on `.upper()`.

A 500 is the server saying it broke. Malformed input is the caller's, and it
is answered here with a sentence and a 400. Nothing in this module changes
what a well-formed request does -- the coercions below are the ones the views
already performed inline, with the crash replaced by a refusal.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

from django.http import HttpRequest


class InvalidInput(ValueError):
    """Caller error. The message is shown to the caller, so it is a sentence."""


def body(request: HttpRequest) -> dict:
    """The request body as an object, or a refusal.

    An empty body stays `{}`, which is what the views have always assumed;
    the fields they need are then reported missing one at a time.
    """
    try:
        raw = request.body.decode("utf-8")
    except UnicodeDecodeError:
        raise InvalidInput("요청 본문이 UTF-8이 아닙니다.")
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise InvalidInput("JSON 파싱 실패")
    if not isinstance(parsed, dict):
        raise InvalidInput("요청 본문은 JSON 객체여야 합니다.")
    return parsed


def _present(payload: dict, field: str) -> Any:
    value = payload.get(field)
    return None if value == "" else value


def text(payload: dict, field: str, *, default: str = "", limit: int | None = None,
         strip: bool = True) -> str:
    """A string field. Absent and empty both mean the default.

    `True` is rejected although Python would accept it as a value: a boolean
    in a name field is a caller mistake, and silently stringifying it would
    store "True" as an order note.
    """
    value = _present(payload, field)
    if value is None:
        return default
    if not isinstance(value, str):
        raise InvalidInput(f"{field}은(는) 문자열이어야 합니다.")
    if strip:
        value = value.strip()
    if limit is not None:
        value = value[:limit]
    return value


def upper(payload: dict, field: str, *, default: str = "") -> str:
    """Unstripped, because the views these came from did not strip either.
    Widening what is accepted is a behaviour change like any other (9)."""
    return text(payload, field, default=default, strip=False).upper()


def flag(payload: dict, field: str, *, default: bool) -> bool:
    value = payload.get(field)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise InvalidInput(f"{field}은(는) true/false여야 합니다.")
    return value


def rows(payload: dict, field: str) -> list[dict]:
    """A list of objects. Anything else is refused by shape, not by contents."""
    value = payload.get(field) or []
    if not isinstance(value, list) or not value:
        raise InvalidInput(f"{field} 배열이 필요합니다.")
    for row in value:
        if not isinstance(row, dict):
            raise InvalidInput("menu_item_id/qty 형식 오류")
    return value


def one_of(value: str, allowed: Iterable[str], message: str) -> str:
    if value not in tuple(allowed):
        raise InvalidInput(message)
    return value

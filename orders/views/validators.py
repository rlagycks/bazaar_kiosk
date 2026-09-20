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
from typing import Any

from django.http import HttpRequest


class InvalidInput(ValueError):
    """Caller error. The message is shown to the caller, so it is a sentence.

    Catch this exact class. A broad `except ValueError` around a validator
    call would swallow it and answer with whatever that handler decided,
    which is how a precise 400 turns into a vague one (PR #75 review).
    """


def body(request: HttpRequest) -> dict:
    """The request body as an object, or a refusal.

    An empty body stays `{}`, which is what the views have always assumed;
    the fields they need are then reported missing one at a time.
    """
    try:
        raw = request.body.decode("utf-8")
    except UnicodeDecodeError:
        raise InvalidInput("요청 본문이 UTF-8이 아닙니다.")
    if raw == "":
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise InvalidInput("JSON 파싱 실패")
    except RecursionError:
        # Nesting deep enough to exhaust the interpreter's stack. Python
        # raises this instead of a decode error, so leaving it uncaught put
        # back the very 500 this module exists to remove: about 20k opening
        # brackets, well under Django's body-size limit (PR #75 security
        # review).
        raise InvalidInput("JSON 중첩이 너무 깊습니다.")
    if not isinstance(parsed, dict):
        raise InvalidInput("요청 본문은 JSON 객체여야 합니다.")
    return parsed


def _present(payload: dict[str, Any], field: str) -> Any:
    """Absent, in the sense the views used before this module existed.

    They read fields as `p.get(x) or default`, and `or` swallows every falsy
    value, not just `None` and `""`. Matching that exactly is the point: a
    body carrying `"note": 0` created an order before, and refusing it now
    would be a behaviour change smuggled in as a bug fix (PR #75 review).
    """
    value = payload.get(field)
    return None if not value else value


def text(payload: dict[str, Any], field: str, *, default: str = "", strip: bool = True) -> str:
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
    return value


def upper(payload: dict[str, Any], field: str, *, default: str = "") -> str:
    """Unstripped, because the views these came from did not strip either.
    Widening what is accepted is a behaviour change like any other (9)."""
    return text(payload, field, default=default, strip=False).upper()

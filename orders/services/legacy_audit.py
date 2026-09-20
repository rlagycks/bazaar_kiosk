"""What a database holds in the old money shapes (7C, D-054).

The split payment fields have been nullable since 0017, so a row can carry
one `received_amount` and nothing else. The report reads those rows the way
the order detail does, but nobody could say how many there were, how much
money they involved, or whether any of them disagreed with themselves
(BK-R007, BK-R031).

This answers that, and only that. **Nothing here writes.** The user's
decision (D-054) is that original values stay as they are: an estimate
written into a payment field would be indistinguishable from a real
takings record afterwards. D-037 says a fresh deployment has no such rows
at all, so on the intended path this survey reports zero.

New orders no longer produce these shapes; `orders/views/api.py` stores a
number in every money field, including zero.
"""

from __future__ import annotations

from django.db.models import Case, Count, F, IntegerField, Q, Sum, Value, When
from django.db.models.functions import Abs, Coalesce

from orders.models import Order, PaymentMethod

# The 0017 shape: one figure, no split.
UNSPLIT = Q(received_cash_amount__isnull=True) & Q(received_ticket_amount__isnull=True)
# Among those, a single-method row can be attributed (the method says which
# side the figure belongs to); a mixed one cannot be divided at all.
INTERPRETABLE = UNSPLIT & Q(payment_method__in=(PaymentMethod.CASH, PaymentMethod.TICKET))
UNATTRIBUTED = UNSPLIT & Q(payment_method=PaymentMethod.CASH_TICKET)

_SPLIT_SUM = Coalesce(F("received_cash_amount"), Value(0)) + Coalesce(F("received_ticket_amount"), Value(0))
# A row that carries a total and at least one split figure, where the two do
# not agree. A NULL on one side counts as zero, which is right because the
# only writer sets the pair together (api.py): one side NULL means that
# method took nothing, not that the figure is missing. A future writer that
# filled one side alone would land here too, and should be read as a conflict
# rather than passed over (PR #72 code review).
_HAS_SPLIT = Q(received_amount__isnull=False) & ~UNSPLIT
_MISMATCH = _HAS_SPLIT & ~Q(received_amount=_SPLIT_SUM)


def survey() -> dict:
    """Count the rows a reader has to interpret. Read-only, one query."""
    figures = Order.objects.aggregate(
        orders=Count("id"),
        unsplit=Count("id", filter=UNSPLIT),
        unsplit_amount=Coalesce(Sum("received_amount", filter=UNSPLIT), Value(0)),
        interpretable=Count("id", filter=INTERPRETABLE),
        interpretable_amount=Coalesce(Sum("received_amount", filter=INTERPRETABLE), Value(0)),
        unattributed=Count("id", filter=UNATTRIBUTED),
        unattributed_amount=Coalesce(Sum("received_amount", filter=UNATTRIBUTED), Value(0)),
        # A split with no total: the other direction of the same gap.
        missing_total=Count("id", filter=Q(received_amount__isnull=True) & ~UNSPLIT),
        mismatched=Count("id", filter=_MISMATCH),
        difference=Coalesce(
            Sum(
                Case(When(_MISMATCH, then=Abs(F("received_amount") - _SPLIT_SUM)), default=Value(0)),
                output_field=IntegerField(),
            ),
            Value(0),
        ),
        # Written before 7A stored the change; the report derives theirs.
        no_change=Count("id", filter=Q(change_amount__isnull=True)),
    )
    needs_attention = any(
        figures[key] for key in ("unsplit", "missing_total", "mismatched", "no_change")
    )
    return {
        "orders": figures["orders"],
        "unsplit": {
            "count": figures["unsplit"],
            "amount": figures["unsplit_amount"],
            "interpretable": {"count": figures["interpretable"], "amount": figures["interpretable_amount"]},
            "unattributed": {"count": figures["unattributed"], "amount": figures["unattributed_amount"]},
        },
        "missing_total": figures["missing_total"],
        "mismatched": {"count": figures["mismatched"], "difference": figures["difference"]},
        "no_change": figures["no_change"],
        "needs_attention": needs_attention,
    }


def render(figures: dict) -> str:
    """The survey as sentences, for an operator reading a terminal."""
    unsplit = figures["unsplit"]
    lines = [
        f"주문 {figures['orders']:,}건을 살펴봤습니다. 이 명령은 아무것도 고치지 않습니다.",
        "",
        f"분할 수납 기록이 없는 주문: {unsplit['count']:,}건 (합계 {unsplit['amount']:,}원)",
        f"  - 현금·식권 단일 결제라 해석할 수 있음: {unsplit['interpretable']['count']:,}건 "
        f"({unsplit['interpretable']['amount']:,}원)",
        f"  - 혼합 결제라 현금·식권으로 나눌 수 없음: {unsplit['unattributed']['count']:,}건 "
        f"({unsplit['unattributed']['amount']:,}원)",
        f"받은 금액 합계가 비어 있는 주문: {figures['missing_total']:,}건",
        f"합계와 분할이 어긋나는 주문: {figures['mismatched']['count']:,}건 "
        f"(차이 합계 {figures['mismatched']['difference']:,}원)",
        f"거스름돈이 기록되지 않은 주문: {figures['no_change']:,}건",
        "",
    ]
    if figures["needs_attention"]:
        lines.append(
            "해석이 필요한 주문이 있습니다. 통계 화면은 이 행들을 주문 상세와 같은 방식으로 읽고 "
            "건수를 함께 보여 줍니다. 값을 채우려면 별도 승인과 계획이 필요합니다(D-054)."
        )
    else:
        lines.append("해석이 필요한 주문이 없습니다.")
    return "\n".join(lines)

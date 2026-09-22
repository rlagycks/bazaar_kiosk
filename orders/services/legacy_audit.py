"""What a database holds in the old money shapes (7C, D-054).

The split payment fields have been nullable since 0017, so a row can carry
one `received_amount` and nothing else, or one side of the split and a NULL
where a zero belonged. The report reads those rows the way the order detail
does, but nobody could say how many there were, how much money they
involved, or whether any of them disagreed with themselves (BK-R007,
BK-R031).

This answers that, and only that. **Nothing here writes.** The user's
decision (D-054) is that original values stay as they are: an estimate
written into a payment field would be indistinguishable from a real
takings record afterwards. D-037 says a fresh deployment has no such rows
at all, so on the intended path this survey reports zero.

New orders no longer produce these shapes; `orders/views/api.py` stores a
number in every money field, including zero.
"""

from __future__ import annotations

from django.db.models import BigIntegerField, Case, Count, F, Q, Sum, Value, When
from django.db.models.functions import Abs, Cast, Coalesce

from orders.models import Order, PaymentMethod

# The 0017 shape: one figure, no split.
UNSPLIT = Q(received_cash_amount__isnull=True) & Q(received_ticket_amount__isnull=True)
# Among those, a single-method row can be attributed (the method says which
# side the figure belongs to); a mixed one cannot be divided at all.
INTERPRETABLE = UNSPLIT & Q(payment_method__in=(PaymentMethod.CASH, PaymentMethod.TICKET))
UNATTRIBUTED = UNSPLIT & Q(payment_method=PaymentMethod.CASH_TICKET)

# Exactly one side filled. Until this phase `api.py` wrote `value or None`,
# so every single-method order ever taken has the other side NULL rather than
# zero. Arithmetically such a row is determined -- the missing side is the
# remainder, and every reader coalesces it to zero -- so it needs no
# interpreting, but it is still the shape this phase stops producing, and an
# operator asking "does this database predate 7C?" has to be told yes
# (PR #72 DB review).
HALF_SPLIT = (
    Q(received_cash_amount__isnull=True, received_ticket_amount__isnull=False)
    | Q(received_cash_amount__isnull=False, received_ticket_amount__isnull=True)
)

_BIG = BigIntegerField()


def _big(field: str):
    """The column in bigint space.

    These are `PositiveIntegerField`s, and the schema bounds them only at
    zero from below. Two legal rows near 2^31 sum past int4 and PostgreSQL
    raises `integer out of range`, which would fail the whole audit over one
    anomalous row. The 7A ceiling (`payments.MAX_AMOUNT`) did not exist when
    these rows were written, so the tool cannot assume it (PR #72 DB review).
    """
    return Coalesce(Cast(F(field), _BIG), Value(0, output_field=_BIG))


_SPLIT_SUM = _big("received_cash_amount") + _big("received_ticket_amount")
# A row that carries a total and at least one split figure, where the two do
# not agree. A NULL on one side counts as zero: one side NULL means that
# method took nothing, so a total that does not match the other side is a
# conflict, not an absence.
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
        half_split=Count("id", filter=HALF_SPLIT),
        half_split_amount=Coalesce(Sum("received_amount", filter=HALF_SPLIT), Value(0)),
        # A split with no total: the other direction of the same gap.
        missing_total=Count("id", filter=Q(received_amount__isnull=True) & ~UNSPLIT),
        mismatched=Count("id", filter=_MISMATCH),
        difference=Coalesce(
            Sum(
                Case(
                    When(_MISMATCH, then=Abs(_big("received_amount") - _SPLIT_SUM)),
                    default=Value(0, output_field=_BIG),
                    output_field=_BIG,
                ),
                output_field=_BIG,
            ),
            Value(0, output_field=_BIG),
        ),
        # Written before 7A stored the change; the report derives theirs.
        no_change=Count("id", filter=Q(change_amount__isnull=True)),
    )
    needs_attention = any(
        figures[key]
        for key in ("unsplit", "half_split", "missing_total", "mismatched", "no_change")
    )
    return {
        "orders": figures["orders"],
        "unsplit": {
            "count": figures["unsplit"],
            "amount": figures["unsplit_amount"],
            "interpretable": {"count": figures["interpretable"], "amount": figures["interpretable_amount"]},
            "unattributed": {"count": figures["unattributed"], "amount": figures["unattributed_amount"]},
        },
        "half_split": {"count": figures["half_split"], "amount": figures["half_split_amount"]},
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
        f"한쪽 수단만 기록된 주문: {figures['half_split']['count']:,}건 "
        f"(합계 {figures['half_split']['amount']:,}원, 나머지 한쪽은 0으로 읽습니다)",
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

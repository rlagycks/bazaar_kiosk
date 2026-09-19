from __future__ import annotations
from django.db import models
from django.db.models import Q
from django.db.models.functions import ExtractYear


class FloorChoices(models.TextChoices):
    B1 = "B1", "지하"


class PaymentMethod(models.TextChoices):
    CASH   = "CASH", "현금"
    TICKET = "TICKET", "티켓"
    CASH_TICKET = "CASH_TICKET", "현금+티켓"


class OrderType(models.TextChoices):
    DINE_IN = "DINE_IN", "매장"
    TAKEOUT = "TAKEOUT", "포장"


class OrderStatus(models.TextChoices):
    PREPARING = "PREPARING", "준비중"
    READY     = "READY", "완료"
    CANCELLED = "CANCELLED", "취소"


class NumberSeries(models.TextChoices):
    # D-047: an order belongs to the event or to a rehearsal, and the two count
    # separately. PRACTICE is the default so a row that never went through
    # allocation cannot pass for an event order.
    REAL = "REAL", "행사"
    PRACTICE = "PRACTICE", "연습"


class OrderSource(models.TextChoices):
    ORDER   = "ORDER", "주문(서빙)"
    COUNTER = "B1_COUNTER", "주방 카운터"
    KITCHEN = "KITCHEN", "주방"


class Table(models.Model):
    number = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=50, blank=True, default="")
    is_active = models.BooleanField(default=True)
    sort_index = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_index", "number", "id"]
        indexes = [models.Index(fields=["is_active", "sort_index", "number"])]

    def __str__(self):
        return f"테이블 {self.number}{' · ' + self.name if self.name else ''}"


class MenuItem(models.Model):
    name = models.CharField(max_length=100)
    price = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    # 채널 가시성
    visible_counter = models.BooleanField(default=True)   # 카운터 공통
    visible_booth   = models.BooleanField(default=False)  # 부스 채널(현재 미사용)
    visible_kitchen = models.BooleanField(default=True)   # 지하 주방(=식사류)

    # 관리
    sku = models.CharField(max_length=50, blank=True, null=True)
    sort_index = models.IntegerField(default=0)

    # 이력
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        ordering = ["sort_index", "name"]
        indexes = [
            models.Index(fields=["is_active", "sort_index", "name"]),
        ]

    def __str__(self):
        return f"{self.name}({self.price:,}원)"


class Order(models.Model):
    # 핵심
    floor = models.CharField(max_length=2, choices=FloorChoices.choices,default=FloorChoices.B1)  # 단일 지하 운영
    order_type = models.CharField(max_length=10, choices=OrderType.choices)  # DINE_IN/TAKEOUT
    status = models.CharField(max_length=10, choices=OrderStatus.choices, default=OrderStatus.PREPARING)
    source = models.CharField(max_length=12, choices=OrderSource.choices, default=OrderSource.ORDER)

    # 번호: 계열(행사/연습)·연도별 증가 (D-047)
    order_no = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    order_date = models.DateField(null=True, blank=True, db_index=True)
    number_series = models.CharField(
        max_length=8, choices=NumberSeries.choices,
        default=NumberSeries.PRACTICE, db_index=True,
    )

    # 지하 매장만 테이블 사용
    table = models.ForeignKey(Table, null=True, blank=True, on_delete=models.PROTECT, related_name="orders")

    # 지하 주문서 확장
    is_takeout = models.BooleanField(default=False)  # 지하: 포장 여부
    payment_method = models.CharField(max_length=12, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    received_amount = models.PositiveIntegerField(null=True, blank=True)
    received_cash_amount = models.PositiveIntegerField(null=True, blank=True)
    received_ticket_amount = models.PositiveIntegerField(null=True, blank=True)
    # 7A (D-048): decided by the server at creation and kept. NULL on rows
    # older than 0026; the API computes those the old way.
    change_amount = models.PositiveIntegerField(null=True, blank=True, verbose_name="거스름돈")

    # 공통
    total_price = models.PositiveIntegerField(default=0)
    note = models.CharField(max_length=200, blank=True, default="")

    # D-051: who took the order. Null for orders written before accounts
    # existed; PROTECT so an author with orders is deactivated, not deleted.
    created_by = models.ForeignKey(
        "orders.Account", null=True, blank=True, on_delete=models.PROTECT,
        related_name="created_orders", verbose_name="주문자",
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # 테이블 규칙: 모든 지하 주문은 테이블(테이블 번호·포장 슬롯)을 가져야 함
            models.CheckConstraint(
                name="orders_table_rule",
                check=Q(
                    Q(order_type=OrderType.DINE_IN, floor=FloorChoices.B1, table__isnull=False)
                    | Q(order_type=OrderType.TAKEOUT, floor=FloorChoices.B1, table__isnull=False)
                ),
            ),
            # 포장 번호표는 한 번에 한 손님 것이다 (D-050). 아직 넘겨주지 않은
            # 포장 주문이 그 번호를 쥐고 있으면 같은 번호로 새 주문을 만들 수 없다.
            # 취소된 주문은 번호를 놓아준다. 뷰에서 미리 확인하지만 두 요청이
            # 동시에 확인하면 둘 다 비어 있다고 보므로, 경계는 DB에 둔다.
            models.UniqueConstraint(
                fields=["table"],
                condition=Q(
                    order_type=OrderType.TAKEOUT,
                    status__in=[OrderStatus.PREPARING, OrderStatus.READY],
                ),
                name="uq_active_takeout_slot",
            ),
            # 층+계열+연도+번호 유니크(번호가 있을 때만). D-047로 초기화 주기가
            # 날짜에서 연도로 바뀌었으므로 고유 범위도 연도다. 연도는 주문일에서
            # 끌어내 별도 컬럼과 어긋날 여지를 남기지 않는다.
            models.UniqueConstraint(
                "floor",
                "number_series",
                ExtractYear("order_date"),
                "order_no",
                condition=Q(order_no__isnull=False),
                name="uq_floor_series_year_no",
            ),
            # The uniqueness above is scoped by the year of order_date, and
            # EXTRACT(YEAR FROM NULL) is NULL, so a number without a date would
            # slip past it entirely. Allocation always writes both together;
            # this stops a manual or admin write from breaking that quietly.
            models.CheckConstraint(
                name="orders_number_needs_date",
                condition=Q(order_no__isnull=True) | Q(order_date__isnull=False),
            ),
        ]
        indexes = [
            models.Index(fields=["floor", "order_type", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]
        ordering = ["-created_at", "-id"]

    def __str__(self):
        no = f"{self.order_no}" if self.order_no else "—"
        return f"[{self.floor}/{self.order_type}] #{no} {self.status}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT, related_name="order_items")
    qty = models.PositiveIntegerField()
    unit_price = models.PositiveIntegerField(blank=True, null=True)
    service_mode = models.CharField(max_length=10, choices=OrderType.choices, default=OrderType.DINE_IN)
    prepared_qty = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["order", "menu_item"]), models.Index(fields=["order", "id"])]

    @property
    def line_total(self) -> int:
        return int(self.qty) * int(self.unit_price or 0)

    @property
    def remaining_qty(self) -> int:
        return max(0, int(self.qty) - int(self.prepared_qty or 0))

    @property
    def is_prepared(self) -> bool:
        return self.remaining_qty == 0

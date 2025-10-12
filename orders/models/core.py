from __future__ import annotations
from django.db import models
from django.db.models import Q


class FloorChoices(models.TextChoices):
    B1 = "B1", "지하"
    F1 = "F1", "1층"


class PaymentMethod(models.TextChoices):
    CASH   = "CASH", "현금"
    TICKET = "TICKET", "티켓"
    CASH_TICKET = "CASH_TICKET", "현금+티켓"


class OrderType(models.TextChoices):
    DINE_IN = "DINE_IN", "매장"
    TAKEOUT = "TAKEOUT", "포장"
    BOOTH   = "BOOTH", "부스(1층)"


class OrderStatus(models.TextChoices):
    PREPARING = "PREPARING", "준비중"
    READY     = "READY", "완료"
    CANCELLED = "CANCELLED", "취소"


class OrderSource(models.TextChoices):
    ORDER   = "ORDER", "서빙(모바일)"
    B1      = "B1_COUNTER", "지하 카운터"
    F1      = "F1_COUNTER", "1층 카운터"
    KITCHEN = "KITCHEN", "주방"
    BOOTH   = "F1_BOOTH", "1층 부스"


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
    visible_booth   = models.BooleanField(default=False)  # 1층 부스
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
    floor = models.CharField(max_length=2, choices=FloorChoices.choices,default=FloorChoices.B1)  # B1/F1
    order_type = models.CharField(max_length=10, choices=OrderType.choices)  # DINE_IN/TAKEOUT/BOOTH
    status = models.CharField(max_length=10, choices=OrderStatus.choices, default=OrderStatus.PREPARING)
    source = models.CharField(max_length=12, choices=OrderSource.choices, default=OrderSource.ORDER)

    # 번호: 층별·일자별 증가
    order_no = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    order_date = models.DateField(null=True, blank=True, db_index=True)

    # 지하 매장만 테이블 사용
    table = models.ForeignKey(Table, null=True, blank=True, on_delete=models.PROTECT, related_name="orders")

    # 지하 주문서 확장
    is_takeout = models.BooleanField(default=False)  # 지하: 포장 여부
    payment_method = models.CharField(max_length=12, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    received_amount = models.PositiveIntegerField(null=True, blank=True)
    received_cash_amount = models.PositiveIntegerField(null=True, blank=True)
    received_ticket_amount = models.PositiveIntegerField(null=True, blank=True)

    # 공통
    total_price = models.PositiveIntegerField(default=0)
    note = models.CharField(max_length=200, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # 테이블 규칙: 지하 매장/포장 외에는 테이블이 없어야 함
            models.CheckConstraint(
                name="orders_table_rule",
                check=Q(
                    Q(order_type=OrderType.DINE_IN, floor=FloorChoices.B1, table__isnull=False)
                    | Q(~Q(order_type=OrderType.DINE_IN), table__isnull=True)
                ),
            ),
            # 층+일자+번호 유니크(번호가 있을 때만)
            models.UniqueConstraint(
                fields=["floor", "order_date", "order_no"],
                condition=Q(order_no__isnull=False),
                name="uq_floor_date_no",
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

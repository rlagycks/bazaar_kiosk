from __future__ import annotations
from django.contrib import admin
from django.utils.html import format_html

from .models import Table, MenuItem, Order, OrderItem

# ---- 공용 유틸: 모델에 실제 존재하는 필드만 골라서 사용 ----
def _field_names(model):
    # auto_created(역참조 등) 제외
    return {f.name for f in model._meta.get_fields() if not f.auto_created}

def _present(model, *names):
    exist = _field_names(model)
    return [n for n in names if n in exist]

# ---- Table ----
@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = _present(Table, "number", "name", "is_active", "sort_index")
    list_filter  = _present(Table, "is_active",)
    search_fields = _present(Table, "number", "name")
    ordering = _present(Table, "sort_index", "number")

# ---- MenuItem ----
@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = _present(
        MenuItem,
        "name", "price", "is_active",
        "visible_counter", "visible_booth", "visible_kitchen",
        "sort_index", "sku",
    )
    list_filter = _present(
        MenuItem,
        "is_active", "visible_counter", "visible_booth", "visible_kitchen",
    )
    search_fields = _present(MenuItem, "name", "sku")
    ordering = _present(MenuItem, "sort_index", "name")
    list_editable = _present(
        MenuItem,
        "price", "is_active", "visible_counter", "visible_booth", "visible_kitchen", "sort_index",
    )

# ---- Order / OrderItem ----
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = _present(OrderItem, "menu_item", "qty", "unit_price")
    readonly_fields = _present(OrderItem, )
    autocomplete_fields = _present(OrderItem, "menu_item")

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    inlines = [OrderItemInline]

    # 목록 컬럼(있는 것만)
    list_display = (
        ["id"]
        + _present(Order, "order_type", "status", "table", "pickup_no", "pickup_date",
                   "total_price", "source", "is_pickup_call", "created_at")
    )
    list_filter = _present(
        Order, "order_type", "status", "source", "pickup_date", "created_at"
    )
    search_fields = _present(Order, "id", "note")
    date_hierarchy = "created_at" if "created_at" in _field_names(Order) else None
    ordering = _present(Order, "-created_at", "-id") or ["-id"]

    # 읽기전용 필드(실존하는 것만)
    def get_readonly_fields(self, request, obj=None):
        base = _present(
            Order,
            "pickup_no", "pickup_date", "total_price",
            "created_at", "updated_at", "source", "is_pickup_call",
        )
        return tuple(base)

    # 상세 화면 필드 구성(최소 필드만, 나머지는 자동으로 인라인에서 편집)
    fields = (
        _present(Order,
                 "order_type", "status", "table",
                 "pickup_no", "pickup_date",
                 "total_price", "note",
                 "source", "is_pickup_call",
                 "created_at", "updated_at")
        or ["id"]  # 안전망
    )

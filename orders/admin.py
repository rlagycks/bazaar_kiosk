from __future__ import annotations
from django.contrib import admin
from django.utils.html import format_html

from .models import Account, Table, MenuItem, Order, OrderItem, OrderEvent, EventDay

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
                   "total_price", "source", "is_pickup_call", "created_by", "created_at")
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
            "created_at", "updated_at", "source", "is_pickup_call", "created_by",
        )
        return tuple(base)

    # 상세 화면 필드 구성(최소 필드만, 나머지는 자동으로 인라인에서 편집)
    fields = (
        _present(Order,
                 "order_type", "status", "table",
                 "pickup_no", "pickup_date",
                 "total_price", "note",
                 "source", "is_pickup_call", "created_by",
                 "created_at", "updated_at")
        or ["id"]  # 안전망
    )


# ---- EventDay (D-047) ----
@admin.register(EventDay)
class EventDayAdmin(admin.ModelAdmin):
    """The operator's one control over numbering.

    A day registered here gives real order numbers; every other day is a
    rehearsal and counts in the practice series. Registering a day after the
    fact does not renumber orders already taken that day.
    """

    list_display = ("date", "label", "created_at")
    search_fields = ("label",)
    ordering = ("-date",)


# ---- Account (D-051) ----
@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    """The operator's control over who may do what.

    One row per person. The event password is shared and lives in the
    deployment configuration, not here; this screen grants permissions and
    switches people off. Deactivating, not deleting: an account with orders
    or history behind it is protected from deletion.
    """

    list_display = ("name", "can_serve", "can_monitor_hall", "can_monitor_takeout",
                    "can_view_stats", "is_active", "created_at")
    list_editable = ("can_serve", "can_monitor_hall", "can_monitor_takeout",
                     "can_view_stats", "is_active")
    list_filter = ("is_active", "can_serve", "can_monitor_hall", "can_monitor_takeout", "can_view_stats")
    search_fields = ("name",)
    ordering = ("name",)
    readonly_fields = ("id", "created_at")


# ---- OrderEvent (D-051) -- read only ----
@admin.register(OrderEvent)
class OrderEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "order", "kind", "actor", "from_status", "to_status", "item", "prepared_qty")
    list_filter = ("kind", "actor")
    search_fields = ("order__id", "actor__name")
    ordering = ("-created_at", "-id")
    readonly_fields = ("order", "actor", "kind", "from_status", "to_status", "item", "prepared_qty", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

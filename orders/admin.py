from __future__ import annotations
from django import forms
from django.contrib import admin

from orders.services import audit, order_edits
from orders.services import status as status_service

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

# ---- Order / OrderItem (7B, D-052) ----
# The admin is a writer like the screens, and it keeps the same promises: the
# total and change are recomputed by the order-edit service, the price snapshot
# and the number are not editable, a status change follows the kitchen's
# transition table, and every change leaves an event. Orders are not created
# here at all -- numbering, payment and the audit trail belong to the serving
# screen.

class OrderItemInlineFormSet(forms.BaseInlineFormSet):
    def clean(self):
        # Ours first: Django's own check also refuses deleting a line that an
        # event protects, but in database terms. This says what it means.
        if not any(self.errors) and self.has_changed():
            self._check_lines()
        super().clean()

    def _check_lines(self):
        lines = []
        for form in self.forms:
            if not form.cleaned_data or not form.is_bound:
                continue
            data = form.cleaned_data
            item = form.instance
            deleting = bool(data.get("DELETE"))
            sellable = True
            if item.pk:
                price = int(item.unit_price or 0)
                history = item.events.exists()
            else:
                if deleting or not data.get("menu_item"):
                    continue
                menu = data["menu_item"]
                price = int(menu.price or 0)
                history = False
                sellable = bool(menu.is_active and menu.visible_kitchen)
            lines.append(order_edits.Line(
                unit_price=price, qty=int(data.get("qty") or 0),
                prepared_qty=int(item.prepared_qty or 0) if item.pk else 0,
                deleting=deleting, has_history=history, sellable=sellable,
            ))
        try:
            order_edits.check_lines(self.instance, lines)
        except order_edits.EditRefused as exc:
            raise forms.ValidationError(str(exc))


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    formset = OrderItemInlineFormSet
    extra = 0
    fields = ("menu_item", "qty", "service_mode", "unit_price", "prepared_qty")
    readonly_fields = ("unit_price", "prepared_qty")
    autocomplete_fields = ("menu_item",)


class OrderAdminForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ("status", "note")

    def clean_status(self):
        target = self.cleaned_data["status"]
        current = self.instance.status
        if target != current and target not in status_service.ALLOWED_TRANSITIONS.get(current, ()):
            raise forms.ValidationError(status_service.TransitionRefused(current, target).detail)
        return target


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = OrderAdminForm
    inlines = [OrderItemInline]

    list_display = ("id", "order_no", "number_series", "order_type", "status", "table",
                    "total_price", "change_amount", "source", "created_by", "created_at")
    list_filter = ("order_type", "status", "number_series", "source", "created_at")
    search_fields = ("id", "note")
    date_hierarchy = "created_at"
    ordering = ("-created_at", "-id")

    fields = ("status", "note",
              "floor", "order_type", "is_takeout", "table",
              "order_no", "order_date", "number_series",
              "payment_method", "received_cash_amount", "received_ticket_amount", "received_amount",
              "total_price", "change_amount",
              "source", "created_by", "created_at", "updated_at")
    readonly_fields = ("floor", "order_type", "is_takeout", "table",
                       "order_no", "order_date", "number_series",
                       "payment_method", "received_cash_amount", "received_ticket_amount", "received_amount",
                       "total_price", "change_amount",
                       "source", "created_by", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        # A change-form POST runs inside one transaction. Take the row lock
        # when the object is first read, so the validation (transition table,
        # cooking history, money) and the write see the same order and the
        # kitchen -- which locks the order before its items -- waits its turn.
        # Without this a cancel or a cooked item landing between validation
        # and save surfaced as a 500 (PR #70 review).
        match = getattr(request, "resolver_match", None)
        if request.method == "POST" and match and match.url_name == "orders_order_change":
            queryset = queryset.select_for_update()
        return queryset

    def save_model(self, request, obj, form, change):
        # Already locked by get_queryset for this POST; locking again in the
        # same transaction is a no-op and keeps this method honest on its own.
        locked = status_service.locked(obj.pk)
        previous = locked.status
        if status_service.change(locked, obj.status):
            audit.record_status(locked, None, previous=previous)
        locked.note = obj.note
        locked.save(update_fields=["note", "updated_at"])
        # Hand the locked, current row to the rest of the save.
        obj.status = locked.status
        obj.total_price = locked.total_price
        obj.change_amount = locked.change_amount

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for item in instances:
            if item.pk is None or item.unit_price is None:
                item.unit_price = item.menu_item.price  # the snapshot, taken now
            item.save()
        for item in formset.deleted_objects:
            item.delete()
        formset.save_m2m()

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if any(formset.has_changed() for formset in formsets):
            order = status_service.locked(form.instance.pk)
            order_edits.apply_line_changes(order, None)


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

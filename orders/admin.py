from __future__ import annotations
from django import forms
from django.contrib import admin

from django.db import transaction

from orders.services import audit, order_edits, revisions
from orders.services import status as status_service

from .models import Account, Table, MenuItem, Order, OrderItem, OrderEvent, EventDay

class MarksTheBoard:
    """Say that a screen's contents changed, for admins that write directly.

    `TableAdmin`, `MenuItemAdmin` and `EventDayAdmin` have no `save_model` of
    their own, so Django's generic one writes the row and nothing tells the
    screens. Each of these is display state: a price, a table's name, whether
    an item is offered at all. `EventDay` is the sharpest -- registering a day
    changes the series badge on every order shown, without writing to a single
    order row, so no marker scoped to orders could ever notice it.

    Django wraps the change form, the editable change list and the single
    delete in transactions of its own, so the mark joins them. The bulk
    "delete selected" action is not wrapped, so `delete_queryset` opens one
    (PR #77 writer audit).

    Marking happens in `save_related` rather than `save_model` because the
    counter row has to be the last row this transaction locks, and Django
    calls `save_related` after `save_model` on both routes that write --
    the change form (`options.py:1895`) and the editable change list
    (`options.py:2121`). One rule for every admin, with no exception to
    remember (PR #77 security review).

    The change list needs one more thing. Django edits every changed row in a
    *single* transaction, one `save_model`/`save_related` pair per row, so
    marking per row would take the counter after row one and then go on to
    lock row two -- putting the counter in the middle of a cycle. Two
    operators bulk-editing the same rows in different sort orders would
    deadlock on it. So a change-list POST defers: it marks once, at the end,
    in a transaction wrapped around the whole thing (PR #77 architecture
    review).

    That wrapper also gives the bulk "delete selected" action a transaction,
    which Django does not provide. What it does not fix is Django's own
    pre-existing hazard -- two operators editing the same rows in opposite
    orders can still deadlock on the *rows*, with or without this mixin.
    """

    _DEFER = "_bk_defer_board_mark"

    def changelist_view(self, request, extra_context=None):
        if request.method != "POST":
            return super().changelist_view(request, extra_context)
        setattr(request, self._DEFER, True)
        with transaction.atomic():
            response = super().changelist_view(request, extra_context)
            revisions.mark()
        return response

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if not getattr(request, self._DEFER, False):
            revisions.mark()

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        revisions.mark()

    def delete_queryset(self, request, queryset):
        if getattr(request, self._DEFER, False):
            # Reached through the change list, which already holds a
            # transaction and will mark once it closes.
            super().delete_queryset(request, queryset)
            return
        with transaction.atomic():
            super().delete_queryset(request, queryset)
            revisions.mark()


# ---- 공용 유틸: 모델에 실제 존재하는 필드만 골라서 사용 ----
def _field_names(model):
    # auto_created(역참조 등) 제외
    return {f.name for f in model._meta.get_fields() if not f.auto_created}

def _present(model, *names):
    exist = _field_names(model)
    return [n for n in names if n in exist]

# ---- Table ----
@admin.register(Table)
class TableAdmin(MarksTheBoard, admin.ModelAdmin):
    list_display = _present(Table, "number", "name", "is_active", "sort_index")
    list_filter  = _present(Table, "is_active",)
    search_fields = _present(Table, "number", "name")
    ordering = _present(Table, "sort_index", "number")

# ---- MenuItem ----
@admin.register(MenuItem)
class MenuItemAdmin(MarksTheBoard, admin.ModelAdmin):
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
        # The note is on the screens, and it is written here rather than
        # through a service. The mark for it happens in `save_related`, which
        # Django calls after this and after the inline items -- see there.
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
        """The end of the admin's transaction, and where it marks.

        An earlier version marked in `save_model`, which was wrong: Django
        runs the inline item writes and the total recomputation *after*
        `save_model`, so the counter row was locked and then held for the rest
        of the form submission -- an operator editing a ten-line order would
        have serialized every order in the building behind that one page. It
        also made the lock order `Order -> ChangeRevision -> OrderItem`, the
        reverse of every other writer, which is the shape this design exists
        to forbid (PR #77 security review).

        `save_model` writes the note unconditionally, so there is always
        something to announce by the time this runs.
        """
        super().save_related(request, form, formsets, change)
        if any(formset.has_changed() for formset in formsets):
            order = status_service.locked(form.instance.pk)
            order_edits.apply_line_changes(order, None)
        revisions.mark()


# ---- EventDay (D-047) ----
@admin.register(EventDay)
class EventDayAdmin(MarksTheBoard, admin.ModelAdmin):
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
class AccountAdmin(MarksTheBoard, admin.ModelAdmin):
    """The operator's control over who may do what.

    Marks the board like the others, for a reason that is one step removed:
    no screen draws an account, but `_identity` reads these permissions from
    the database on every request and `scope.visible` narrows the orders a
    caller may see by them. Switching `can_monitor_takeout` off changes what
    that screen is allowed to hold, without writing to a single order row --
    the same shape as an event day, and missed in the first pass because the
    question asked was "does a screen draw it?" rather than "does it change
    what a screen may see?" (PR #77 architecture review).

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

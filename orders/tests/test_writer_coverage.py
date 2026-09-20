"""10B: no writer gets added without someone deciding about the marker.

D-019 chose service-layer integration over a database trigger. A trigger fires
whatever route the write took; integration only covers the call sites someone
remembered. That difference is the whole risk of this phase, and it does not
show up as a failing test on the day it is introduced -- it shows up weeks
later as a board that stopped updating for one kind of edit.

So the call sites are inventoried here, and the inventory is checked against
the code. Adding a write to `orders/` fails this test until the new entry is
classified. The classification is the point: three of the four answers below
mean "no marker needed", and each says why.

This is a structural test. It reads the source, it does not run it. Whether a
writer that claims to mark actually marks is what `test_change_tracking.py`
asserts by behaviour; the two together are what "every writer" means.
"""

from __future__ import annotations

import ast
import pathlib

from django.test import SimpleTestCase, TestCase

ORDERS = pathlib.Path(__file__).resolve().parent.parent

# Calls that write. `save`/`delete` are also plain English, so a receiver that
# is obviously not a model (a formset, a session, a file) is excluded below
# rather than left to make this list lie.
WRITE_CALLS = frozenset({
    "save", "create", "bulk_create", "bulk_update", "update", "delete",
    "get_or_create", "update_or_create",
    # async ORM writes: none today, and this is where they would appear.
    # 10D1 is an async hub, so this half of the list is the half that will
    # start mattering (PR #77 review: three of these were missing).
    "acreate", "asave", "aupdate", "adelete", "abulk_create",
    "abulk_update", "aget_or_create", "aupdate_or_create",
})

# Receivers whose `.save()`/`.update()`/`.delete()` is not a database write.
#
# Kept as short as it can be. Every name here is a name this scanner will not
# look at again, and a missed writer fails silently while a false alarm fails
# loudly and gets fixed in a minute -- so the two errors are not worth the same
# and the list only holds names that cannot plausibly be a model. An earlier
# version had `results`, `counts`, `totals`, `seen`, `errors` and `context` in
# it, which are ordinary names for an ordinary variable holding a row
# (PR #77 review). `form` and `request` came out for the same reason:
# `form.instance.save()` is the commonest way in Django to write a model.
NOT_A_MODEL = frozenset({
    "formset", "response", "session", "cache",
    "self.client", "client", "connection", "connections",
    "os", "sys", "shutil", "pathlib", "json", "settings",
})

# Directories that are not the request path. Migrations write rows too, but
# they run once under a maintenance window, not while a screen is watching;
# what revision migrated rows get is a data question, answered in the
# migration itself (10B) and not by this inventory.
SKIPPED = ("tests", "migrations", "__pycache__")


class Classification:
    """Why a writer does or does not move the marker."""

    MARKS = "marks"                     # moves the marker itself
    INSIDE_A_MARKED_WRITE = "inside"    # its caller marks, in the same transaction
    NOT_DISPLAY_STATE = "not-display"   # nothing a screen renders
    UNREACHABLE = "unreachable"         # no production caller


# module:function -> (classification, why).
#
# Sourced from the 2026-09-20 writer audit (PR #77) and re-derived by the scan
# below. An entry here is a claim someone made on purpose; a call site missing
# from it fails the test with instructions rather than passing quietly.
INVENTORY: dict[str, tuple[str, str]] = {
    # ---- the order lifecycle -------------------------------------------------
    "views.api:orders_collection": (
        Classification.MARKS,
        "Takes an order: creates the order row, bulk-creates its lines, "
        "allocates the number and remembers the idempotency key, all in one "
        "transaction that marks once at the end.",
    ),
    "views.api:order_item_progress": (
        Classification.MARKS,
        "Cooking progress. Saved inline here, not through a service, and the "
        "status often does not move with it -- the write most easily missed.",
    ),
    "services.status:change": (
        Classification.INSIDE_A_MARKED_WRITE,
        "Called by the two views above and by the admin, each inside their own "
        "transaction. Marking here too would be harmless but would hide which "
        "transaction owns the change.",
    ),
    "services.numbering:allocate_floor_order_no": (
        Classification.INSIDE_A_MARKED_WRITE,
        "Refuses to run outside a transaction; that transaction is the order "
        "creation above, which marks.",
    ),
    "services.numbering:_locked_counter": (
        Classification.INSIDE_A_MARKED_WRITE,
        "Same transaction as the allocation that called it.",
    ),
    "services.numbering:_resync": (
        Classification.INSIDE_A_MARKED_WRITE,
        "Same transaction as the allocation that called it.",
    ),
    "services.order_edits:apply_line_changes": (
        Classification.INSIDE_A_MARKED_WRITE,
        "Runs inside the admin change-form transaction, which marks.",
    ),
    "services.totals:recalc_totals": (
        Classification.MARKS,
        "No production caller (PR #77 audit, UNCERTAIN 1) and it wrote "
        "total_price outside any transaction. Given its own transaction and a "
        "mark, so that calling it can never be the thing that breaks a board.",
    ),
    # ---- history and request bookkeeping ------------------------------------
    "services.audit:record_created": (
        Classification.INSIDE_A_MARKED_WRITE,
        "Append-only history (D-051), written in the marked transaction.",
    ),
    "services.audit:record_status": (
        Classification.INSIDE_A_MARKED_WRITE,
        "History for a status change, written in the transaction that marks.",
    ),
    "services.audit:record_progress": (
        Classification.INSIDE_A_MARKED_WRITE,
        "History for cooking progress, written in the transaction that marks.",
    ),
    "services.audit:record_items": (
        Classification.INSIDE_A_MARKED_WRITE,
        "History for an admin line edit, written in the transaction that marks.",
    ),
    "services.idempotency:remember": (
        Classification.INSIDE_A_MARKED_WRITE,
        "The request tag, not the order. Written in the marked transaction.",
    ),
    # ---- the marker itself ---------------------------------------------------
    "services.revisions:mark": (
        Classification.MARKS,
        "This is the marker: it takes the counter row's lock and advances it.",
    ),
    "services.revisions:_counter": (
        Classification.MARKS,
        "Creates the counter row when migration 0028 has not run or it was "
        "removed by hand, then locks it for the caller.",
    ),
    "services.revisions:save_and_mark": (
        Classification.MARKS,
        "Writes display state outside the order tables -- a price, a table, an "
        "event day -- and marks in the same transaction.",
    ),
    "services.revisions:delete_and_mark": (
        Classification.MARKS,
        "Removes display state outside the order tables and marks with it.",
    ),
    # ---- the admin -----------------------------------------------------------
    "admin:OrderAdmin.save_model": (
        Classification.INSIDE_A_MARKED_WRITE,
        "Order note and status, written directly rather than through a "
        "service. Django calls save_related after this, in the same "
        "transaction, and that is where the mark happens -- so the counter "
        "row is not held across the inline writes (PR #77 security review).",
    ),
    "admin:OrderAdmin.save_formset": (
        Classification.INSIDE_A_MARKED_WRITE,
        "Order lines added, edited and removed -- direct instance writes, not "
        "through a service (PR #77 audit, bypasses 5 and 6). Called by "
        "save_related, which marks after it returns.",
    ),
    # `MarksTheBoard` (TableAdmin, MenuItemAdmin, EventDayAdmin) is not listed:
    # it delegates the write to Django's generic ModelAdmin through super() and
    # marks in `save_related`, so it is not itself a write call site. The scan
    # cannot see it, which is why the admin paths -- change form, editable
    # change list, single delete and bulk delete -- are exercised for real in
    # test_change_tracking.py rather than asserted here.
    # ---- authentication: not display state -----------------------------------
    "authentication:issue_tokens": (
        Classification.NOT_DISPLAY_STATE,
        "AuthDevice on login. Session bookkeeping, nothing a screen draws.",
    ),
    "authentication:rotate_refresh": (
        Classification.NOT_DISPLAY_STATE,
        "AuthDevice rotation. Session bookkeeping, nothing a screen draws.",
    ),
    "authentication:revoke_refresh": (
        Classification.NOT_DISPLAY_STATE,
        "AuthDevice revocation. Session bookkeeping, nothing a screen draws.",
    ),
    "login_security:attempt_login": (
        Classification.NOT_DISPLAY_STATE,
        "LoginAttempt, for rate limiting. Nothing a screen draws.",
    ),
}


def _receiver(node: ast.Call) -> str:
    """The dotted text left of the call, as written."""
    try:
        return ast.unparse(node.func.value)
    except Exception:  # pragma: no cover - unparse handles everything we write
        return ""


def _looks_like_a_model_write(node: ast.Call) -> bool:
    receiver = _receiver(node)
    if not receiver:
        return False
    head = receiver.split(".")[0]
    if receiver in NOT_A_MODEL or head in NOT_A_MODEL:
        return False
    # `super().save_model(...)` and friends delegate; the delegating method is
    # already the inventoried site.
    return not receiver.startswith("super(")


def _module_name(path: pathlib.Path) -> str:
    relative = path.relative_to(ORDERS).with_suffix("")
    parts = [part for part in relative.parts if part != "__init__"]
    return ".".join(parts)


def _enclosing(tree: ast.AST) -> dict[int, str]:
    """Line number -> the innermost function (or Class.method) containing it.

    Innermost, not outermost. The first version claimed each function's whole
    line range before recursing, so a write inside a closure was credited to
    the function around it -- and if that outer function was already in
    INVENTORY, the new writer passed silently. That is precisely the case this
    file exists to fail on (PR #77 review, reproduced). Recursing first and
    letting the inner name win fixes it.
    """
    owner: dict[int, str] = {}

    def walk(node, prefix=""):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                walk(child, f"{prefix}{child.name}.")
                continue
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}{child.name}"
                walk(child, f"{name}.")
                for line in range(child.lineno, (child.end_lineno or child.lineno) + 1):
                    owner.setdefault(line, name)
                continue
            walk(child, prefix)

    walk(tree)
    return owner


def find_writers() -> dict[str, set[int]]:
    """Every write call in production code, keyed `module:function`."""
    found: dict[str, set[int]] = {}
    for path in sorted(ORDERS.rglob("*.py")):
        if any(part in SKIPPED for part in path.relative_to(ORDERS).parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:  # pragma: no cover - a broken file fails earlier
            raise AssertionError(f"{path} does not parse: {exc}") from None
        owner = _enclosing(tree)
        module = _module_name(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in WRITE_CALLS:
                continue
            if not _looks_like_a_model_write(node):
                continue
            function = owner.get(node.lineno)
            if function is None:
                continue  # module level; none today, and it would be a bug
            found.setdefault(f"{module}:{function}", set()).add(node.lineno)
    return found


# Models whose rows change what a screen shows, or what a screen is allowed to
# show. Every admin registered for one of these has to mark the board.
#
# The second half of that sentence is the half the first pass got wrong. The
# question asked was "does a screen draw this?", which put `Account` in the
# "no" column -- no screen draws an account. But `_identity` reads an account's
# permissions from the database on every request and `scope.visible` narrows
# the orders a caller may see by them, so switching one off changes what a
# screen may hold without touching an order row (PR #77 architecture review).
DISPLAY_STATE_MODELS = frozenset({
    "Order", "OrderItem", "MenuItem", "Table", "EventDay", "Account",
})

# Registered admins for models that are deliberately not display state, with
# the reason. Anything else registered for a model outside DISPLAY_STATE_MODELS
# has to be named here, so "is this display state?" gets asked once per model
# rather than never.
ADMINS_THAT_NEED_NO_MARK = {
    "OrderEvent": "Read-only in the admin (D-051); history, not state.",
    "ChangeRevision": "The marker itself.",
}


class AdminCoverageTests(TestCase):
    """The scanner is blind to admins, so this asks Django instead.

    A new `@admin.register(...)` adds a writer without adding a single write
    call to `orders/` -- Django's generic `ModelAdmin` does the saving, from
    `django/contrib/admin/options.py`. The AST scan cannot see that, and
    `AccountAdmin` went in through exactly that gap. This walks the live
    registry instead of the source.
    """

    def registered(self):
        from django.contrib import admin

        return {
            model: admin_class
            for model, admin_class in admin.site._registry.items()
            if model._meta.app_label == "orders"
        }

    def test_every_admin_for_display_state_marks_the_board(self):
        from orders.admin import MarksTheBoard

        unmarked = []
        for model, admin_class in self.registered().items():
            name = model.__name__
            if name not in DISPLAY_STATE_MODELS:
                continue
            marks = isinstance(admin_class, MarksTheBoard) or any(
                name in type(admin_class).__dict__
                for name in ("save_related", "save_model", "changelist_view")
            )
            if not marks:
                unmarked.append(name)
        self.assertEqual(
            unmarked, [],
            "These admins write state a screen depends on without telling it. "
            "Add the MarksTheBoard mixin, or mark explicitly: " + ", ".join(unmarked),
        )

    def test_every_other_registered_admin_has_been_considered(self):
        unclassified = sorted(
            model.__name__ for model in self.registered()
            if model.__name__ not in DISPLAY_STATE_MODELS
            and model.__name__ not in ADMINS_THAT_NEED_NO_MARK
        )
        self.assertEqual(
            unclassified, [],
            "A model was registered in the admin and nobody said whether "
            "changing it changes what a screen shows -- or what a screen is "
            "allowed to show, which is the part that was missed once already. "
            "Add it to DISPLAY_STATE_MODELS or to ADMINS_THAT_NEED_NO_MARK "
            "with a reason: " + ", ".join(unclassified),
        )


class WriterInventoryTests(SimpleTestCase):
    """The inventory and the code have to agree, in both directions."""

    def test_every_writer_in_the_code_is_classified(self):
        found = find_writers()
        unclassified = sorted(set(found) - set(INVENTORY))
        self.assertEqual(
            unclassified, [],
            "A new writer appeared in orders/. Decide whether a screen can see "
            "what it changes, then add it to INVENTORY in this file with one of "
            "the classifications and the reason. Lines: "
            + "; ".join(f"{key} at {sorted(found[key])}" for key in unclassified),
        )

    def test_the_inventory_has_no_entries_for_code_that_is_gone(self):
        found = find_writers()
        stale = sorted(set(INVENTORY) - set(found))
        self.assertEqual(
            stale, [],
            "INVENTORY names writers that no longer exist. Remove them, or the "
            "next reader will trust a list that has stopped being true.",
        )

    def test_every_classification_carries_a_reason(self):
        known = {
            Classification.MARKS, Classification.INSIDE_A_MARKED_WRITE,
            Classification.NOT_DISPLAY_STATE, Classification.UNREACHABLE,
        }
        for key, (classification, why) in INVENTORY.items():
            with self.subTest(writer=key):
                self.assertIn(classification, known)
                self.assertGreater(len(why), 20, "a reason, not a label")

    def test_the_scan_finds_the_writers_the_audit_named(self):
        """A scanner that quietly matched nothing would pass every test above.

        These four are the call sites the 2026-09-20 audit called out as the
        ones a service-layer marker would miss. If the scan stops seeing them,
        it has broken, not the code.
        """
        found = find_writers()
        for key in (
            "views.api:orders_collection",
            "views.api:order_item_progress",
            "admin:OrderAdmin.save_formset",
            "services.numbering:allocate_floor_order_no",
        ):
            with self.subTest(writer=key):
                self.assertIn(key, found)

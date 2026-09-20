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

from django.test import SimpleTestCase

ORDERS = pathlib.Path(__file__).resolve().parent.parent

# Calls that write. `save`/`delete` are also plain English, so a receiver that
# is obviously not a model (a formset, a session, a file) is excluded below
# rather than left to make this list lie.
WRITE_CALLS = frozenset({
    "save", "create", "bulk_create", "bulk_update", "update", "delete",
    "get_or_create", "update_or_create",
    # async ORM writes: none today, and this is where they would appear
    "acreate", "asave", "aupdate", "adelete", "abulk_create",
})

# Receivers whose `.save()`/`.update()`/`.delete()` is not a database write.
NOT_A_MODEL = frozenset({
    "formset", "form", "request", "response", "session", "cache", "payload",
    "defaults", "flags", "self.client", "client", "counts", "totals", "seen",
    "results", "codes", "outcomes", "errors", "connection", "connections",
    "os", "sys", "shutil", "pathlib", "json", "settings", "context",
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
        Classification.MARKS,
        "Order note and status. Django wraps the change form in a transaction; "
        "the mark joins it.",
    ),
    "admin:OrderAdmin.save_formset": (
        Classification.MARKS,
        "Order lines added, edited and removed -- direct instance writes, not "
        "through a service (PR #77 audit, bypasses 5 and 6).",
    ),
    # `MarksTheBoard` (TableAdmin, MenuItemAdmin, EventDayAdmin) is not listed:
    # it delegates the write to Django's generic ModelAdmin through super() and
    # marks afterwards, so it is not itself a write call site. The scan cannot
    # see it, which is why the admin paths are exercised for real in
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
    """Line number -> the function (or Class.method) that contains it."""
    owner: dict[int, str] = {}

    def walk(node, prefix=""):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                walk(child, f"{prefix}{child.name}.")
                continue
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}{child.name}"
                for line in range(child.lineno, (child.end_lineno or child.lineno) + 1):
                    owner.setdefault(line, name)
                walk(child, prefix)
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
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
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

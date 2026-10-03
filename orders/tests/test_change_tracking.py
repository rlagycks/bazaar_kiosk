"""10B: every change a screen can see moves one persisted number (D-019).

The kitchen board has no way to know it is stale. Until now the only thing a
screen could do was ask for everything again on a timer, and 4B2 removed even
that. What replaces it has to answer one question cheaply and without lying:
*has anything changed since the version I am showing?*

D-019's answer is convergence, not replay: the screen is entitled to the
current truth, never to the sequence of steps that produced it. History
already exists and is not this -- `OrderEvent` is append-only and written in
the same transaction as the change it describes (D-051). So the marker here
carries no payload. It is a number that goes up.

Three properties make it usable, and each is a test below.

* **It moves for every writer.** Not just the ones that go through a service:
  the kitchen's own cooking-progress write lives in the view, a menu price and
  an event day are edited in the admin, and an event day changes what every
  order displays without touching a single order row.
* **It is handed out in commit order.** A number taken earlier cannot commit
  later. Without that a reader can move its cursor past a change it never saw
  -- the "10/11 inversion" this phase exists to rule out.
* **It only counts what committed.** A rolled back transaction leaves it where
  it was, because a screen that refetched for a change that never happened
  would be doing it forever.
"""

import threading
import uuid

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from orders.models import (
    EventDay, MenuItem, Order, OrderItem, OrderStatus, Table,
)
from orders.services import revisions
from orders.tests.auth_support import AUTH_SETTINGS, login_client


class MarkerFixture:
    """An order the screens would show, and a way to read the marker."""

    def setUp(self):
        super().setUp()
        self.table = Table.objects.create(number=31)
        self.menu = MenuItem.objects.create(name="Stew", price=9000)
        self.client_kitchen = self.client_class()
        login_client(self.client_kitchen, "KITCHEN")

    def marker(self) -> int:
        """What a screen would read: the last committed value."""
        return revisions.current()

    def make_order(self, *, status=OrderStatus.PREPARING, qty=2, prepared=0):
        order = Order.objects.create(
            table=self.table, floor="B1", order_type="DINE_IN", status=status,
            total_price=9000 * qty, payment_method="CASH",
            received_cash_amount=9000 * qty,
        )
        item = OrderItem.objects.create(
            order=order, menu_item=self.menu, qty=qty, unit_price=9000,
            prepared_qty=prepared,
        )
        return order, item


@override_settings(**AUTH_SETTINGS)
class ScreenVisibleWritesMoveTheMarkerTests(MarkerFixture, TestCase):
    """The writer inventory, turned into assertions (PR #77 audit)."""

    def order_payload(self):
        return {
            "request_id": str(uuid.uuid4()),
            "floor": "B1",
            "order_type": "DINE_IN",
            "table_number": str(self.table.number),
            "payment_method": "CASH",
            "received_cash_amount": 18000,
            "items": [{"menu_item_id": self.menu.id, "qty": 2}],
        }

    def test_taking_an_order_moves_the_marker_exactly_once(self):
        """One order, one step -- not one per row the transaction wrote.

        Order creation writes the order, its lines, the number and the audit
        row. A screen sees one new order, so the marker moves once.

        This asserts an exact value, which readers are told not to do (the
        value is opaque; only "same or different" is a contract). The
        difference is who is being pinned: a *screen* must not do arithmetic
        on it, but this suite is pinning the *implementation* -- that each
        unit of work marks once and not once per writer. That is worth
        holding, and it is how the admin's double mark was caught.
        """
        client = self.client_class()
        login_client(client, "SERVING")
        before = self.marker()
        response = client.post(
            reverse("orders:orders-collection"),
            self.order_payload(), content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.marker(), before + 1)

    def test_cooking_progress_moves_the_marker_even_when_the_status_does_not(self):
        """The write the kitchen itself makes, and the one most easily missed.

        `prepared_qty` is saved inline in the view, not through a service, and
        when a two-item order has only one item finished the order's status
        stays PREPARING. A marker wired to the status service alone would sit
        still while the board went stale -- which is the exact failure this
        phase exists to prevent (PR #77 writer audit, bypass 3).
        """
        order, item = self.make_order(qty=4)
        before = self.marker()
        response = self.client_kitchen.patch(
            reverse("orders:order-item-progress", args=[item.id]),
            {"prepared_qty": 1}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PREPARING, "status must not have moved")
        self.assertGreater(self.marker(), before)

    def test_a_status_change_moves_the_marker(self):
        order, _ = self.make_order()
        before = self.marker()
        response = self.client_kitchen.patch(
            reverse("orders:order-status", args=[order.id]),
            {"status": OrderStatus.CANCELLED}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertGreater(self.marker(), before)

    def test_asking_for_the_status_it_already_has_does_not_move_the_marker(self):
        """A retry is not a change. Nothing was written, so nothing is stale."""
        order, _ = self.make_order(status=OrderStatus.PREPARING)
        before = self.marker()
        response = self.client_kitchen.patch(
            reverse("orders:order-status", args=[order.id]),
            {"status": OrderStatus.PREPARING}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.marker(), before)

    def test_progress_that_only_moves_the_status_still_moves_the_marker(self):
        """The branch the first version of this phase got wrong (PR #77).

        The mark was wired to `changed` -- whether the item's quantity moved --
        but the order's status can move without it. Reachable in the kitchen:

        1. two items, one already cooked, one not; the order is PREPARING;
        2. a monitor marks the whole order READY, which the transition table
           allows and which never looks at the items;
        3. someone taps the already-finished item again. `done: true` sets
           `prepared_qty` to the value it already had, so `changed` is False;
        4. `sync_from_items` sees the second item outstanding and puts the
           order back to PREPARING -- a real, committed write;
        5. the mark was skipped.

        The order went READY -> PREPARING in the database and every screen kept
        showing READY, with no polling left to correct it (4B2). That is the
        exact failure this phase exists to remove.
        """
        order, cooked = self.make_order(qty=1, prepared=1)
        waiting = OrderItem.objects.create(
            order=order, menu_item=self.menu, qty=1, unit_price=9000, prepared_qty=0,
        )
        ready = self.client_kitchen.patch(
            reverse("orders:order-status", args=[order.id]),
            {"status": OrderStatus.READY}, content_type="application/json",
        )
        self.assertEqual(ready.status_code, 200, ready.content)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.READY)

        before = self.marker()
        response = self.client_kitchen.patch(
            reverse("orders:order-item-progress", args=[cooked.id]),
            {"done": True}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PREPARING, "the status did move")
        self.assertEqual(waiting.qty, 1)
        self.assertGreater(
            self.marker(), before,
            "the order row was written; every screen is now showing a stale status",
        )

    def test_progress_that_changes_nothing_does_not_move_the_marker(self):
        order, item = self.make_order(qty=2, prepared=1)
        before = self.marker()
        response = self.client_kitchen.patch(
            reverse("orders:order-item-progress", args=[item.id]),
            {"prepared_qty": 1}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.marker(), before)


class WritesOutsideTheOrderTablesMoveTheMarkerTests(MarkerFixture, TestCase):
    """What a screen renders is not only the order rows (PR #77 audit, bypass 7).

    A price, a menu item switched off, a table renamed -- each changes what the
    board draws. An event day is the sharpest: registering one flips every
    order's series badge without writing to `orders_order` at all. A marker
    scoped per order would never notice.
    """

    def test_changing_a_menu_price_moves_the_marker(self):
        before = self.marker()
        revisions.save_and_mark(self.menu, price=9500)
        self.menu.refresh_from_db()
        self.assertEqual(self.menu.price, 9500)
        self.assertGreater(self.marker(), before)

    def test_hiding_a_menu_item_moves_the_marker(self):
        before = self.marker()
        revisions.save_and_mark(self.menu, is_active=False)
        self.assertGreater(self.marker(), before)

    def test_renaming_a_table_moves_the_marker(self):
        before = self.marker()
        revisions.save_and_mark(self.table, name="창가 1번")
        self.assertGreater(self.marker(), before)

    def test_registering_an_event_day_moves_the_marker(self):
        """No order row is touched, and every order on screen changes."""
        before = self.marker()
        with transaction.atomic():
            EventDay.objects.create(date="2026-09-20", label="바자회")
            revisions.mark()
        self.assertGreater(self.marker(), before)

    def test_deleting_a_menu_item_moves_the_marker(self):
        spare = MenuItem.objects.create(name="Gone", price=1000)
        before = self.marker()
        revisions.delete_and_mark(spare)
        self.assertGreater(self.marker(), before)


@override_settings(**AUTH_SETTINGS)
class AdminWritesMoveTheMarkerTests(MarkerFixture, TestCase):
    """Real admin form posts, because the admin is where the bypasses were.

    `TableAdmin`, `MenuItemAdmin` and `EventDayAdmin` had no `save_model` of
    their own -- Django's generic one wrote the row and nothing told the
    screens. `OrderAdmin` wrote the note and the order lines directly. Calling
    the service in a test would prove the service works; these go through the
    form, which is what an operator actually does.
    """

    def setUp(self):
        super().setUp()
        self.operator = get_user_model().objects.create_superuser(
            "op", "op@example.invalid", "synthetic-admin-password-for-tests"
        )
        self.client.force_login(self.operator)

    def test_a_whole_admin_save_moves_the_marker_exactly_once(self):
        """Note, lines and recomputed total are one edit, so one step.

        This also pins where the mark happens. It used to be in `save_model`,
        which runs *before* Django writes the inline items -- so the counter
        row was locked and then held for the rest of the form submission, and
        the lock order was the reverse of every other writer's. Moving it to
        `save_related` made it one mark instead of two, which is why this
        asserts the exact value rather than just an increase.
        """
        order, item = self.make_order(qty=2)
        before = self.marker()
        response = self.client.post(
            reverse("admin:orders_order_change", args=[order.pk]),
            {
                "status": order.status,
                "note": "창가 자리",
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "1",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-id": str(item.pk),
                "items-0-order": str(order.pk),
                "items-0-menu_item": str(self.menu.pk),
                "items-0-qty": "1",
                "items-0-service_mode": item.service_mode,
                "items-0-prepared_qty": "0",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302, response.content[:600])
        order.refresh_from_db()
        self.assertEqual(order.note, "창가 자리")
        self.assertEqual(self.marker(), before + 1)

    def test_editing_a_menu_price_in_the_admin_moves_the_marker(self):
        before = self.marker()
        response = self.client.post(
            reverse("admin:orders_menuitem_change", args=[self.menu.pk]),
            {"name": "Stew", "price": "9500", "sort_index": "0", "_save": "Save"},
        )
        self.assertEqual(response.status_code, 302, response.content[:400])
        self.menu.refresh_from_db()
        self.assertEqual(self.menu.price, 9500)
        self.assertGreater(self.marker(), before)

    def test_registering_an_event_day_in_the_admin_moves_the_marker(self):
        """Not one order row is written, and every order on screen changes."""
        before = self.marker()
        response = self.client.post(
            reverse("admin:orders_eventday_add"),
            {"date": "2026-09-20", "label": "바자회", "_save": "Save"},
        )
        self.assertEqual(response.status_code, 302, response.content[:400])
        self.assertTrue(EventDay.objects.filter(date="2026-09-20").exists())
        self.assertGreater(self.marker(), before)

    def test_editing_a_price_in_the_admin_list_moves_the_marker(self):
        """The other route to the same edit, and a separate code path.

        `list_editable` puts the price straight in the change list, so an
        operator never opens the change form. Django handles that at
        `options.py:2114` with its own transaction and its own call to
        `save_model` -- which the mixin covers, but only because it overrides
        `save_model` rather than the change form's view.
        """
        before = self.marker()
        response = self.client.post(
            reverse("admin:orders_menuitem_changelist"),
            {
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "form-0-id": str(self.menu.pk),
                "form-0-price": "11000",
                "form-0-sort_index": str(self.menu.sort_index),
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302, response.content[:400])
        self.menu.refresh_from_db()
        self.assertEqual(self.menu.price, 11000)
        self.assertGreater(self.marker(), before)

    def test_deleting_a_table_in_the_admin_moves_the_marker(self):
        spare = Table.objects.create(number=99)
        before = self.marker()
        response = self.client.post(
            reverse("admin:orders_table_delete", args=[spare.pk]), {"post": "yes"}
        )
        self.assertEqual(response.status_code, 302, response.content[:400])
        self.assertFalse(Table.objects.filter(pk=spare.pk).exists())
        self.assertGreater(self.marker(), before)

    def test_the_bulk_delete_action_moves_the_marker(self):
        """Django does not wrap `delete_selected` in a transaction of its own."""
        spare = MenuItem.objects.create(name="Gone", price=1000)
        before = self.marker()
        response = self.client.post(
            reverse("admin:orders_menuitem_changelist"),
            {"action": "delete_selected", "_selected_action": [str(spare.pk)], "post": "yes"},
        )
        self.assertEqual(response.status_code, 302, response.content[:400])
        self.assertFalse(MenuItem.objects.filter(pk=spare.pk).exists())
        self.assertGreater(self.marker(), before)


class OnlyCommittedWorkCountsTests(MarkerFixture, TestCase):

    def test_a_rolled_back_change_leaves_the_marker_alone(self):
        before = self.marker()
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                revisions.mark()
                raise RuntimeError("the writer failed after marking")
        self.assertEqual(self.marker(), before)

    def test_the_marker_only_ever_goes_up(self):
        """The one property a reader depends on.

        It is not a count and nothing should read it as one: an admin save
        moves it twice, an order once. What a screen does is compare it with
        the value it holds, so the only thing that must never happen is a
        value it has already seen coming round again.
        """
        seen = [self.marker()]
        for _ in range(5):
            with transaction.atomic():
                seen.append(revisions.mark())
        self.assertEqual(seen, sorted(set(seen)), seen)


class MarkerIsHandedOutInCommitOrderTests(MarkerFixture, TransactionTestCase):
    """The 10/11 inversion, reproduced and ruled out.

    Two transactions take numbers; the one that took the *later* number commits
    first. A reader that saw 11 would move its cursor past 10, and the change
    10 describes would never be fetched -- an order stuck on a screen until
    someone reloaded the page by hand.

    Taking the number under a row lock is what forbids the shape: the second
    writer cannot get a number until the first has committed and let go. So
    "took a later number" and "committed later" become the same statement.
    """

    def test_a_later_number_cannot_commit_first(self):
        took_first = threading.Event()
        second_committed = threading.Event()
        results = {}
        errors = []

        def slow_writer():
            """Takes its number first, commits last."""
            try:
                with transaction.atomic():
                    results["slow"] = revisions.mark()
                    took_first.set()
                    # Hold the transaction open past the point where the other
                    # writer has tried to take its own number. This wait always
                    # runs out: the other thread cannot set the event until it
                    # has the row lock, which it cannot get until this
                    # transaction ends. The row lock is the real
                    # synchronisation, so the timeout only has to be long
                    # enough for the other thread to reach and block on it.
                    second_committed.wait(timeout=0.5)
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)
            finally:
                connection.close()

        def fast_writer():
            try:
                took_first.wait(timeout=5)
                with transaction.atomic():
                    results["fast"] = revisions.mark()
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)
            finally:
                second_committed.set()
                connection.close()

        threads = [threading.Thread(target=slow_writer), threading.Thread(target=fast_writer)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        self.assertEqual(errors, [])
        self.assertIn("slow", results)
        self.assertIn("fast", results)
        # The writer that was made to wait got the higher number, which is only
        # possible if it could not take one until the other had committed.
        self.assertGreater(results["fast"], results["slow"], results)

    def test_another_connection_sees_the_marker_once_it_is_committed(self):
        """A screen is served by a different worker than the one that wrote."""
        with transaction.atomic():
            written = revisions.mark()
        seen = {}
        errors = []

        def other_worker():
            try:
                seen["value"] = revisions.current()
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)
            finally:
                connection.close()

        thread = threading.Thread(target=other_worker)
        thread.start()
        thread.join(timeout=20)
        self.assertEqual(errors, [])
        self.assertEqual(seen.get("value"), written)

    def test_nothing_but_mark_writes_the_counter(self):
        """Monotonicity lives here, not in a database constraint.

        The CHECK on the row only says the value is not negative -- it cannot
        say "never decreases", and an earlier version of its *name* claimed it
        could. What actually keeps the value going up is that `mark()` is the
        only thing that writes it, and it only ever adds one. So that is what
        is pinned, and a future writer that sets the value directly has to
        come here and change this test on purpose (PR #77 review).
        """
        from orders.models import BOARD, ChangeRevision

        with transaction.atomic():
            revisions.mark()
        start = revisions.current()
        self.assertGreater(start, 0)

        # The service offers no way to set it, only to advance it.
        self.assertFalse(hasattr(revisions, "set"))
        with self.assertRaises(ValueError):
            revisions.save_and_mark(ChangeRevision.objects.get(scope=BOARD))

        for _ in range(3):
            with transaction.atomic():
                revisions.mark()
        self.assertEqual(revisions.current(), start + 3)

    def test_marking_outside_a_transaction_is_refused(self):
        """The marker says "something committed".

        Moving it from code that then fails would send every screen to refetch
        a change that does not exist, and nothing would ever put it back. So
        the only way to move it is from inside the transaction that is doing
        the writing -- checked here without one, which a TestCase could not do
        because it wraps every test in a transaction of its own.
        """
        before = revisions.current()
        with self.assertRaises(revisions.NotInTransaction):
            revisions.mark()
        self.assertEqual(revisions.current(), before)

    def test_the_marker_is_read_from_the_database_not_from_memory(self):
        """It has to survive a worker dying the moment after it committed.

        A process-local counter would restart at zero and every screen would
        conclude it was up to date while holding stale orders. Closing the
        connection is as close to a restart as a test gets: nothing of this
        process's state is reused to answer.
        """
        with transaction.atomic():
            written = revisions.mark()
        connection.close()
        self.assertEqual(revisions.current(), written)


@override_settings(**AUTH_SETTINGS)
class ConcurrentOrderWritesDoNotDeadlockTests(MarkerFixture, TransactionTestCase):
    """The lock order the blueprint asked to be reproduced.

    Order creation locks the number counter; cooking progress locks the order
    and then its item. If the marker were locked *before* those, two writers
    taking them in opposite directions would deadlock. It is locked last
    instead -- nothing is acquired after it -- so it cannot be the middle of a
    cycle.
    """

    def test_an_admin_save_and_a_kitchen_update_at_once_both_finish(self):
        """The path the first version of this design got wrong.

        `OrderAdmin` marked in `save_model` and then let Django write the
        inline items, so it locked `Order -> ChangeRevision -> OrderItem`
        while the kitchen locks `Order -> OrderItem -> ChangeRevision`. No
        test ran the two together, so nothing said so (PR #77 security
        review). This runs them together.
        """
        order, item = self.make_order(qty=2)
        operator = get_user_model().objects.create_superuser(
            "op2", "op2@example.invalid", "synthetic-admin-password-for-tests"
        )
        start = threading.Barrier(2)
        codes = {}
        errors = []

        def edit_in_the_admin():
            try:
                client = self.client_class()
                client.force_login(operator)
                start.wait(timeout=5)
                codes["admin"] = client.post(
                    reverse("admin:orders_order_change", args=[order.pk]),
                    {
                        "status": order.status, "note": "동시 편집",
                        "items-TOTAL_FORMS": "1", "items-INITIAL_FORMS": "1",
                        "items-MIN_NUM_FORMS": "0", "items-MAX_NUM_FORMS": "1000",
                        "items-0-id": str(item.pk), "items-0-order": str(order.pk),
                        "items-0-menu_item": str(self.menu.pk), "items-0-qty": "1",
                        "items-0-service_mode": item.service_mode,
                        "items-0-prepared_qty": "0", "_save": "Save",
                    },
                ).status_code
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)
            finally:
                connection.close()

        def cook():
            try:
                client = self.client_class()
                login_client(client, "KITCHEN")
                start.wait(timeout=5)
                codes["progress"] = client.patch(
                    reverse("orders:order-item-progress", args=[item.id]),
                    {"prepared_qty": 1}, content_type="application/json",
                ).status_code
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=edit_in_the_admin),
                   threading.Thread(target=cook)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual(errors, [])
        self.assertEqual(codes.get("admin"), 302, codes)
        self.assertEqual(codes.get("progress"), 200, codes)

    def test_a_new_order_and_a_progress_update_at_once_both_finish(self):
        order, item = self.make_order(qty=2)
        start = threading.Barrier(2)
        codes = {}
        errors = []

        def take_an_order():
            try:
                client = self.client_class()
                login_client(client, "SERVING")
                start.wait(timeout=5)
                codes["create"] = client.post(
                    reverse("orders:orders-collection"),
                    {
                        "request_id": str(uuid.uuid4()),
                        "floor": "B1", "order_type": "DINE_IN",
                        "table_number": str(self.table.number),
                        "payment_method": "CASH",
                        "received_cash_amount": 18000,
                        "items": [{"menu_item_id": self.menu.id, "qty": 2}],
                    },
                    content_type="application/json",
                ).status_code
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)
            finally:
                connection.close()

        def cook():
            try:
                client = self.client_class()
                login_client(client, "KITCHEN")
                start.wait(timeout=5)
                codes["progress"] = client.patch(
                    reverse("orders:order-item-progress", args=[item.id]),
                    {"done": True}, content_type="application/json",
                ).status_code
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=take_an_order), threading.Thread(target=cook)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual(errors, [])
        self.assertEqual(codes.get("create"), 201, codes)
        self.assertEqual(codes.get("progress"), 200, codes)

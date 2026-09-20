"""10C: the data and the version a screen holds are the same instant (D-019).

10B gave the board a number that moves when anything it draws changes. On its
own that number is not yet usable, because "the orders" and "the version" are
two reads, and under Django's default autocommit two reads are two different
PostgreSQL snapshots. Get the order wrong and the failure is silent and
permanent:

* orders first, version second -- a change committing in between is *in* the
  data but the version is the newer one, so the screen stores a version that
  is ahead of what it is showing. It will not refetch until something else
  changes, and what it is showing stays wrong until then;
* orders and version from different snapshots at all -- the screen cannot say
  what it is showing, which is the thing this phase is supposed to give it.

So the snapshot is one REPEATABLE READ transaction (user decision). Both reads
see one instant, and the version it returns is a true statement about the rows
beside it.

Three more properties this file pins, each of which the reviews of 10B asked
for or the phase card names:

* **the version is compared, not ordered.** It carries a generation, so a
  restored counter that climbs back to a number a screen is still holding
  cannot answer `unchanged` and strand it there (`!=`, never `>`);
* **a cursor from another scope is refused.** Permissions are read from the
  database on every request and decide which orders exist for a caller, so a
  version minted for one set of permissions says nothing about another;
* **a truncated queue does not claim to be complete.** `MAX_QUEUE` can cut the
  list, and a version attached to a cut list is not a promise that the screen
  holds everything.
"""

import threading
import uuid

from django.db import connection, transaction
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from django.test.utils import CaptureQueriesContext

from orders.models import (
    ChangeRevision, MenuItem, Order, OrderItem, OrderStatus, OrderType, Table,
)
from orders.views import serializers
from orders.services import revisions, snapshots
from orders.tests.auth_support import AUTH_SETTINGS, login_client, make_account
from orders.roles import HALL_MONITOR, STATS, TAKEOUT_MONITOR


class SnapshotFixture:
    """Orders of both classifications, and a way to ask for a snapshot.

    `TransactionTestCase` throughout, not `TestCase`: the whole point is a
    transaction with its own isolation level, and `TestCase` holds one open
    around every test, which makes `SET TRANSACTION` illegal and the guarantee
    untestable.
    """

    def setUp(self):
        super().setUp()
        self.table = Table.objects.create(number=41)
        self.menu = MenuItem.objects.create(name="Stew", price=9000)
        # `TransactionTestCase` truncates between tests and migration 0028's
        # seed does not run again, so the marker row is absent here in a way
        # it never is in a deployment. Creating it is what a first write would
        # do anyway, and it keeps the generation stable across a test rather
        # than appearing halfway through one.
        with transaction.atomic():
            revisions.mark()

    def make_order(self, *, mode=OrderType.DINE_IN, status=OrderStatus.PREPARING, qty=1):
        order = Order.objects.create(
            table=self.table, floor="B1", order_type="DINE_IN", status=status,
            total_price=9000 * qty, payment_method="CASH",
            received_cash_amount=9000 * qty,
        )
        OrderItem.objects.create(
            order=order, menu_item=self.menu, qty=qty, unit_price=9000,
            service_mode=mode,
        )
        return order

    def everything(self):
        return (STATS,)


class OneInstantTests(SnapshotFixture, TransactionTestCase):

    def test_the_version_describes_the_rows_returned_beside_it(self):
        self.make_order()
        taken = snapshots.waiting(self.everything())
        self.assertEqual(len(taken.orders), 1)
        self.assertEqual(taken.version, snapshots.version_for(self.everything()))

    def test_a_commit_during_the_read_is_not_half_included(self):
        """The property the card asks for, forced rather than hoped for.

        The snapshot is made to pause between reading the version and reading
        the orders. A writer commits a new order in that window. Under
        autocommit the snapshot would come back holding the new order with the
        *old* version, or the old orders with the *new* version -- either way
        a screen that stored the pair would be wrong about what it holds.
        Under one REPEATABLE READ transaction neither half moves.
        """
        self.make_order()
        reached = threading.Event()
        committed = threading.Event()
        taken = {}
        errors = []

        def read_with_a_pause():
            try:
                taken["before"] = revisions.current()
                taken["snapshot"] = snapshots.waiting(
                    self.everything(), _pause=(reached, committed),
                )
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)
            finally:
                connection.close()

        def write_in_the_window():
            try:
                self.assertTrue(reached.wait(timeout=10))
                with transaction.atomic():
                    self.make_order()
                    revisions.mark()
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)
            finally:
                committed.set()
                connection.close()

        threads = [threading.Thread(target=read_with_a_pause),
                   threading.Thread(target=write_in_the_window)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual(errors, [])
        result = taken["snapshot"]
        # The writer committed, so the marker moved -- but not for this reader.
        self.assertGreater(revisions.current(), taken["before"])
        self.assertEqual(len(result.orders), 1, "the new order belongs to the next snapshot")
        self.assertEqual(
            result.version, snapshots.version_from(taken["before"], self.everything()),
            "the version must be the one the rows actually belong to",
        )

    def test_a_snapshot_taken_on_its_own_says_it_is_isolated(self):
        self.make_order()
        self.assertTrue(snapshots.waiting(self.everything()).isolated)

    def test_a_nested_snapshot_says_it_is_not_isolated(self):
        """Nested, `SET TRANSACTION` is illegal, so the snapshot says so.

        An earlier version raised instead, and the only thing that achieved
        was making the endpoint unreachable from every `TestCase` in the
        repository. So the answer is carried out rather than thrown. The
        guarantee *is* weaker here -- see the straddle test below for what it
        degrades to and why that is survivable -- and the endpoint logs it;
        `test_required_settings.py` is what keeps production out of this
        branch in the first place.
        """
        self.make_order()
        with transaction.atomic():
            taken = snapshots.waiting(self.everything())
        self.assertFalse(taken.isolated)
        self.assertEqual(len(taken.orders), 1, "it still answers, just weaker")

    def test_a_nested_snapshot_errs_toward_refetching_never_toward_staleness(self):
        """What the nested branch actually degrades to, pinned.

        Nested, `SET TRANSACTION` is illegal and the enclosing transaction is
        READ COMMITTED, where every statement takes a fresh snapshot. So a
        commit landing between the two reads *is* seen by the second one --
        the same-instant guarantee is genuinely gone, and an earlier version
        of this file claimed otherwise.

        What saves it is the order the two reads happen in, which is why that
        order is load-bearing rather than incidental. The version is read
        first, so the worst pair this can produce is *data newer than its
        version*: the screen refetches once more than it needed to and
        converges. The reverse would be permanent staleness. This test forces
        the straddle and asserts the direction.
        """
        self.make_order()
        reached, released = threading.Event(), threading.Event()
        taken = {}

        def read_nested():
            try:
                with transaction.atomic():           # READ COMMITTED, not ours
                    taken["snapshot"] = snapshots.waiting(
                        self.everything(), _pause=(reached, released)
                    )
            finally:
                connection.close()

        reader = threading.Thread(target=read_nested)
        reader.start()
        try:
            self.assertTrue(reached.wait(timeout=10))
            with transaction.atomic():               # commits inside the window
                self.make_order()
                revisions.mark()
        finally:
            released.set()
            reader.join(timeout=10)

        answer = taken["snapshot"]
        self.assertFalse(answer.isolated)
        self.assertEqual(
            len(answer.orders), 2,
            "READ COMMITTED: the second read does see the new commit",
        )
        self.assertNotEqual(
            answer.version, snapshots.version_for(self.everything()),
            "and the version it carries is the older one -- so the screen "
            "refetches, which is the safe direction",
        )

    def test_the_endpoint_answers_an_isolated_snapshot(self):
        """The path that matters, checked where it actually runs.

        A request arrives outside any transaction, so the view's snapshot is
        the isolated kind. Asserting it through the endpoint rather than the
        service is the point: that is the caller production has.
        """
        from orders.services import snapshots as module

        seen = {}
        original = module.waiting

        def remember(*args, **kwargs):
            taken = original(*args, **kwargs)
            seen["isolated"] = taken.isolated
            return taken

        module.waiting = remember
        try:
            with override_settings(**AUTH_SETTINGS):
                make_account("stats-only", STATS)
                client = self.client_class()
                login_client(client, "STATS")
                response = client.get(reverse("orders:snapshot-waiting"))
        finally:
            module.waiting = original
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(seen.get("isolated"))


class VersionIsComparedNotOrderedTests(SnapshotFixture, TransactionTestCase):

    def test_the_version_changes_when_anything_a_screen_draws_changes(self):
        self.make_order()
        first = snapshots.waiting(self.everything()).version
        with transaction.atomic():
            revisions.mark()
        self.assertNotEqual(snapshots.waiting(self.everything()).version, first)

    def test_a_restore_that_lands_on_a_value_a_screen_holds_is_still_noticed(self):
        """The failure the generation exists for, which is the *collision*.

        An earlier version of this test moved the value as well as the
        generation, and so would have passed with the generation removed from
        the version entirely -- the two versions differed because the numbers
        did. A review caught that, and it also named the hazard correctly:
        receiving a change twice is harmless here, because the contract is
        convergence. What is not harmless is a restored counter climbing back
        to a number a screen is *still holding*, so that its next poll matches,
        answers `unchanged`, and leaves pre-restore data on the wall until
        somebody notices by eye.

        So this rotates the generation and puts the value back exactly where
        the screen left it. Drop the generation from `version_from()` and this
        test fails, which is the only reason it is worth having.
        """
        self.make_order()
        for _ in range(5):
            with transaction.atomic():
                revisions.mark()
        held = snapshots.waiting(self.everything()).version
        value_the_screen_holds = revisions.current()

        restored = ChangeRevision.objects.get(scope="board")
        restored.generation = uuid.uuid4()
        restored.save(update_fields=["generation"])

        self.assertEqual(
            revisions.current(), value_the_screen_holds,
            "the number is deliberately unchanged -- that is the hazard",
        )
        after = snapshots.waiting(self.everything(), since=held)
        self.assertNotEqual(after.version, held)
        self.assertFalse(after.unchanged, "a collision must not answer unchanged")
        self.assertEqual(after.cursor, snapshots.CURSOR_REJECTED)
        self.assertEqual(len(after.orders), 1, "and it hands over the whole list")

    def test_a_restore_that_moves_the_counter_backwards_is_noticed_too(self):
        """The other shape of a restore: the number goes down."""
        self.make_order()
        for _ in range(5):
            with transaction.atomic():
                revisions.mark()
        held = snapshots.waiting(self.everything()).version

        restored = ChangeRevision.objects.get(scope="board")
        restored.value = 1
        restored.generation = uuid.uuid4()
        restored.save(update_fields=["value", "generation"])

        after = snapshots.waiting(self.everything(), since=held)
        self.assertNotEqual(after.version, held)
        self.assertEqual(after.cursor, snapshots.CURSOR_REJECTED)
        self.assertLess(
            revisions.current(), 5,
            "the counter really did go backwards; the generation is what saves it",
        )

    def test_the_version_is_opaque_to_a_screen(self):
        """Nothing about it invites arithmetic."""
        self.make_order()
        version = snapshots.waiting(self.everything()).version
        self.assertIsInstance(version, str)
        with self.assertRaises(ValueError):
            int(version)


class ACursorFromAnotherScopeIsRefusedTests(SnapshotFixture, TransactionTestCase):
    """Permissions decide which orders exist for a caller (D-051, PR #77).

    They are read from the database on every request, so they can change
    between two polls of the same screen. A version minted while the caller
    could see the hall says nothing about what they may see now.
    """

    def test_a_version_minted_for_other_permissions_is_rejected(self):
        self.make_order(mode=OrderType.DINE_IN)
        self.make_order(mode=OrderType.TAKEOUT)
        hall = snapshots.waiting((HALL_MONITOR,))
        self.assertEqual(len(hall.orders), 1)

        takeout = snapshots.waiting((TAKEOUT_MONITOR,), since=hall.version)
        self.assertEqual(takeout.cursor, snapshots.CURSOR_REJECTED)
        self.assertFalse(takeout.unchanged)
        self.assertEqual(len(takeout.orders), 1, "a full answer, not an empty one")

    def test_losing_a_permission_rejects_the_version_held(self):
        self.make_order(mode=OrderType.DINE_IN)
        both = snapshots.waiting((HALL_MONITOR, TAKEOUT_MONITOR))
        narrowed = snapshots.waiting((HALL_MONITOR,), since=both.version)
        self.assertEqual(narrowed.cursor, snapshots.CURSOR_REJECTED)

    def test_the_same_scope_is_accepted_and_answers_unchanged(self):
        self.make_order()
        first = snapshots.waiting(self.everything())
        again = snapshots.waiting(self.everything(), since=first.version)
        self.assertEqual(again.cursor, snapshots.CURSOR_ACCEPTED)
        self.assertTrue(again.unchanged)
        self.assertEqual(again.orders, [], "nothing changed, so nothing is sent")
        self.assertEqual(again.version, first.version)

    def test_a_version_that_is_not_one_is_rejected_rather_than_trusted(self):
        self.make_order()
        for nonsense in ("1", "x:y:z", "..", "0:0:0", "a:b"):
            with self.subTest(since=nonsense):
                answer = snapshots.waiting(self.everything(), since=nonsense)
                self.assertEqual(answer.cursor, snapshots.CURSOR_REJECTED)
                self.assertEqual(len(answer.orders), 1)

    def test_a_stale_version_of_the_right_shape_gets_the_whole_thing(self):
        self.make_order()
        held = snapshots.waiting(self.everything()).version
        with transaction.atomic():
            revisions.mark()
        answer = snapshots.waiting(self.everything(), since=held)
        self.assertEqual(answer.cursor, snapshots.CURSOR_ACCEPTED)
        self.assertFalse(answer.unchanged)
        self.assertEqual(len(answer.orders), 1)


class ATruncatedQueueDoesNotClaimToBeCompleteTests(SnapshotFixture, TransactionTestCase):
    """`MAX_QUEUE` can cut the list; a version on a cut list is not a promise.

    Raised by the 10B architecture review: a screen that stores "version M,
    complete" while holding 500 of 600 orders believes something false, and
    convergence -- the contract the user chose -- breaks exactly at the
    boundary where the kitchen is busiest.
    """

    def only_room_for(self, count):
        from unittest import mock

        return mock.patch("orders.services.queues.MAX_QUEUE", count)

    def test_a_cut_list_says_so(self):
        for _ in range(3):
            self.make_order()
        with self.only_room_for(2):
            answer = snapshots.waiting(self.everything())
        self.assertEqual(len(answer.orders), 2)
        self.assertTrue(answer.has_more)
        self.assertFalse(answer.complete)
        self.assertEqual(answer.total, 3)

    def test_an_uncut_list_is_complete(self):
        for _ in range(3):
            self.make_order()
        answer = snapshots.waiting(self.everything())
        self.assertTrue(answer.complete)
        self.assertFalse(answer.has_more)

    def test_an_incomplete_snapshot_still_carries_its_version(self):
        """It is still useful -- it just is not a claim of completeness."""
        for _ in range(3):
            self.make_order()
        with self.only_room_for(2):
            answer = snapshots.waiting(self.everything())
        self.assertEqual(answer.version, snapshots.version_for(self.everything()))


@override_settings(**AUTH_SETTINGS)
class SnapshotEndpointTests(SnapshotFixture, TransactionTestCase):

    def url(self):
        return reverse("orders:snapshot-waiting")

    def monitor(self):
        make_account("hall-only", HALL_MONITOR)
        client = self.client_class()
        login_client(client, "HALL_MONITOR")
        return client

    def test_an_anonymous_caller_is_refused(self):
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 401)

    def test_a_caller_without_a_reading_permission_is_refused(self):
        client = self.client_class()
        login_client(client, "SERVING")
        self.assertEqual(client.get(self.url()).status_code, 403)

    def test_a_monitor_gets_only_its_own_classification(self):
        self.make_order(mode=OrderType.DINE_IN)
        self.make_order(mode=OrderType.TAKEOUT)
        response = self.monitor().get(self.url())
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(len(body["orders"]), 1)
        self.assertTrue(body["complete"])
        self.assertIn("version", body)

    def test_polling_with_the_version_it_holds_costs_nothing(self):
        self.make_order(mode=OrderType.DINE_IN)
        client = self.monitor()
        first = client.get(self.url()).json()
        again = client.get(self.url(), {"since": first["version"]}).json()
        self.assertTrue(again["unchanged"])
        self.assertEqual(again["orders"], [])
        self.assertEqual(again["version"], first["version"])

    def test_a_change_makes_the_next_poll_return_everything(self):
        self.make_order(mode=OrderType.DINE_IN)
        client = self.monitor()
        first = client.get(self.url()).json()
        with transaction.atomic():
            self.make_order(mode=OrderType.DINE_IN)
            revisions.mark()
        again = client.get(self.url(), {"since": first["version"]}).json()
        self.assertFalse(again["unchanged"])
        self.assertEqual(len(again["orders"]), 2)
        self.assertNotEqual(again["version"], first["version"])

    def test_the_response_is_never_cached(self):
        self.make_order(mode=OrderType.DINE_IN)
        response = self.monitor().get(self.url())
        self.assertIn("no-store", response["Cache-Control"])

    def test_nothing_is_read_after_the_transaction_closes(self):
        """The "same instant" claim covers what is serialized, not just read.

        `snapshot_waiting` serializes outside the block, so a serializer field
        that lazily reached for a row -- an account, an audit line, the event
        series -- would be read at a different instant from everything beside
        it, and no existing test would notice. This one does.
        """
        for _ in range(3):
            self.make_order(mode=OrderType.DINE_IN)
        client = self.monitor()
        client.get(self.url())                      # warm the session lookup
        taken = snapshots.waiting((HALL_MONITOR,))
        with CaptureQueriesContext(connection) as captured:
            [serializers.order(order) for order in taken.orders]
        self.assertEqual(
            len(captured.captured_queries), 0,
            "serialization reached back to the database: " + repr(
                [q["sql"] for q in captured.captured_queries]
            ),
        )


class TheSnapshotAnswersTheSameThingTheBoardAsksForTests(
    SnapshotFixture, TransactionTestCase
):
    """What 10D2 will swap, pinned before it swaps it.

    The kitchen board fetches `orders-collection` with a literal query string
    (`?floor=B1&status=PREPARING&types=DINE_IN,TAKEOUT`). This endpoint
    hard-codes the equivalent filters instead of parsing them, and the two
    agree today only because `OrderType` happens to have exactly two members
    -- an accident nothing was pinning. 10D2 moves the board onto this
    endpoint, so a drift between them is a silent change to what the kitchen
    sees.
    """

    BOARD_QUERY = {"floor": "B1", "status": "PREPARING", "types": "DINE_IN,TAKEOUT"}

    def test_every_order_type_is_included(self):
        """The assumption the hard-coded `types=[]` rests on."""
        self.assertEqual(
            set(OrderType.values), set(self.BOARD_QUERY["types"].split(",")),
            "OrderType gained a member: the board's query string now asks for "
            "less than the snapshot returns",
        )

    def test_the_snapshot_and_the_board_select_the_same_orders(self):
        cooking = [self.make_order(mode=OrderType.DINE_IN),
                   self.make_order(mode=OrderType.TAKEOUT)]
        self.make_order(status=OrderStatus.READY)       # not still cooking
        self.make_order(status=OrderStatus.CANCELLED)

        from orders.views import selectors as board_selectors
        board = board_selectors.visible_orders(
            self.everything(), floor=self.BOARD_QUERY["floor"],
            status=self.BOARD_QUERY["status"],
            types=self.BOARD_QUERY["types"].split(","),
        )
        taken = snapshots.waiting(self.everything())
        self.assertEqual(
            sorted(order.id for order in taken.orders),
            sorted(board.values_list("id", flat=True)),
        )
        self.assertEqual(sorted(o.id for o in taken.orders),
                         sorted(o.id for o in cooking))


class ABusyKitchenStillGetsTheWholeQueueTests(SnapshotFixture, TransactionTestCase):
    """BK-R009's edges, on the new path.

    81 and 201 are the sizes at which the old listing quietly dropped the
    longest-waiting work. `queues.waiting` is shared with the board endpoint
    and already tested there, but the card claims completeness *for this
    endpoint* and inferring it is cheaper than asserting it only until it is
    wrong.
    """

    def bulk(self, count):
        orders = Order.objects.bulk_create([
            Order(table=self.table, floor="B1", order_type="DINE_IN",
                  status=OrderStatus.PREPARING, total_price=9000,
                  payment_method="CASH", received_cash_amount=9000)
            for _ in range(count)
        ])
        OrderItem.objects.bulk_create([
            OrderItem(order=order, menu_item=self.menu, qty=1, unit_price=9000,
                      service_mode=OrderType.DINE_IN)
            for order in orders
        ])

    def test_eighty_one_waiting_orders_all_arrive(self):
        self.bulk(81)
        taken = snapshots.waiting(self.everything())
        self.assertEqual(len(taken.orders), 81)
        self.assertEqual(taken.total, 81)
        self.assertFalse(taken.has_more)
        self.assertTrue(taken.complete)

    def test_two_hundred_and_one_waiting_orders_all_arrive(self):
        self.bulk(201)
        taken = snapshots.waiting(self.everything())
        self.assertEqual(len(taken.orders), 201)
        self.assertEqual(taken.total, 201)
        self.assertTrue(taken.complete)
        self.assertEqual(
            taken.version, snapshots.version_for(self.everything()),
            "and the version still describes exactly these rows",
        )

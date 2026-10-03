#!/usr/bin/env python
"""What one change costs when N screens are watching (10C, D-019).

The counterpart to `marker_contention.py`, which measured the *write* side.
This measures the read side, because that is what decides whether one global
marker stays the right shape.

The marker is one row for the whole board. The hall monitor and the takeout
monitor see disjoint sets of orders (`scope.visible`), but a change to either
moves the same number -- so a hall order being cooked sends the takeout board
and the stats screen to refetch as well. The cost of that is
(open screens) x (change rate) x (cost of one refetch), and the 10B review
pointed out that nobody had measured the last two factors together.

**What this harness fixes, and therefore cannot discover.** The change stream
is 100% hall, and the screens rotate hall/takeout/stats -- so "one screen kind
in three is woken pointlessly" is a property of that mix, not of the design.
And `--polls-per-change` sets how often a poll follows a change; at the
default of 1 every poll refetches *by construction*, because there is always a
bump in between. Read the waste share as "what this deployment shape costs",
not as a constant.

Two more caveats about the cost figures. `DEBUG` is forced on below so that
queries can be counted, which adds a wrapper to every statement; and the whole
run reuses one connection, because nothing here is a request and
`close_old_connections` never fires. In a deployment every poll is a request
and pays a fresh connect plus a TLS handshake (`CONN_MAX_AGE` is 0). So the
latencies here are inflated by the logging and deflated by the connection
reuse, and the second is much the larger of the two.

Two things are reported per screen count:

* **wasted** -- refetches that returned data the screen already had, because
  the change that woke it was in a scope it cannot see. This is the number
  that argues for splitting the marker;
* **cost** -- queries, and latency, for the refetch itself. The query count
  includes BEGIN, the isolation level and COMMIT, so the four data statements
  of a full fetch are reported as seven.

Run it against a disposable database, never a deployment:

    export BK_TEST_DATABASE_URL=postgresql://...      # the control database
    .venv/bin/python scripts/snapshot_amplification.py --screens 1,4,12

It creates its own test database, migrates it, and drops it at the end.
"""

from __future__ import annotations

import argparse
import math
import os
import statistics
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def setup_django():
    os.environ["DJANGO_SETTINGS_MODULE"] = "bazaar_kiosk.settings_test_pg"
    os.environ.setdefault("BK_TEST_APP_DATABASE", "bk_test_app_" + uuid.uuid4().hex)
    import django

    django.setup()


def build_board(hall: int, takeout: int):
    """A kitchen with orders of both classifications still to cook."""
    from django.db import transaction
    from orders.models import MenuItem, Order, OrderItem, OrderStatus, OrderType, Table
    from orders.services import revisions

    table = Table.objects.create(number=1)
    menu = MenuItem.objects.create(name="Bowl", price=8000)
    made = {"HALL": [], "TAKEOUT": []}
    for kind, count in (("HALL", hall), ("TAKEOUT", takeout)):
        mode = OrderType.DINE_IN if kind == "HALL" else OrderType.TAKEOUT
        for _ in range(count):
            order = Order.objects.create(
                table=table, floor="B1", order_type="DINE_IN",
                status=OrderStatus.PREPARING, total_price=8000,
                payment_method="CASH", received_cash_amount=8000,
            )
            OrderItem.objects.create(
                order=order, menu_item=menu, qty=2, unit_price=8000,
                service_mode=mode,
            )
            made[kind].append(order)
    with transaction.atomic():
        revisions.mark()
    return made


def screens(count: int):
    """What the screens watching this board are, in rotation.

    A real kitchen runs a hall board, a takeout board and a counter. Rotating
    through them is what makes the waste visible: two thirds of these cannot
    see a hall change, and all three are woken by one.
    """
    from orders.roles import HALL_MONITOR, STATS, TAKEOUT_MONITOR

    kinds = [("hall", (HALL_MONITOR,)), ("takeout", (TAKEOUT_MONITOR,)),
             ("stats", (STATS,))]
    return [kinds[i % len(kinds)] for i in range(count)]


def poll_round(watchers, held):
    """One poll per screen. Returns (refetched, wasted, queries, ms)."""
    from django.db import connection, reset_queries
    from django.test.utils import CaptureQueriesContext
    from orders.services import snapshots

    refetched = wasted = 0
    queries = 0
    latencies = []
    # "wasted" means the id set came back identical, which is the right
    # question for this harness because its only change is a status flip and
    # the queue filters on status -- an order a screen can see always enters
    # or leaves the list. It would be the wrong question for a `prepared_qty`
    # change, where the ids stay put and the payload genuinely moves.
    for index, (_name, permissions) in enumerate(watchers):
        reset_queries()
        began = time.perf_counter()
        with CaptureQueriesContext(connection) as captured:
            taken = snapshots.waiting(permissions, since=held.get(index))
        latencies.append((time.perf_counter() - began) * 1000)
        queries += len(captured)
        if not taken.unchanged:
            refetched += 1
            fetched = [order.id for order in taken.orders]
            if held.get(("rows", index)) == fetched:
                # Woken, refetched, and handed back exactly what it already
                # had: the change was in a scope this screen cannot see.
                wasted += 1
            held[("rows", index)] = fetched
        held[index] = taken.version
    return refetched, wasted, queries, latencies


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screens", default="1,4,12",
                        help="comma-separated screen counts (default 1,4,12)")
    parser.add_argument("--changes", type=int, default=20,
                        help="hall changes to make per run (default 20)")
    parser.add_argument("--orders", type=int, default=40,
                        help="waiting orders of each classification (default 40)")
    parser.add_argument("--polls-per-change", type=int, default=1,
                        help="polls between changes (default 1). At 1 every "
                             "poll follows a change, so every poll refetches "
                             "by construction -- raise it to see the cheap "
                             "`unchanged` path at a realistic duty cycle")
    args = parser.parse_args()
    if args.polls_per_change < 1:
        parser.error("--polls-per-change must be at least 1")

    setup_django()
    from django.conf import settings
    from django.db import connection, transaction
    from django.test.utils import setup_test_environment, teardown_test_environment

    setup_test_environment()
    connection.creation.create_test_db(verbosity=0, autoclobber=False)
    # CaptureQueriesContext only records when DEBUG is on.
    settings.DEBUG = True
    try:
        from orders.services import revisions, status as status_service
        from orders.models import OrderStatus

        board = build_board(args.orders, args.orders)
        print(f"board: {args.orders} hall + {args.orders} takeout waiting, "
              f"{args.changes} hall changes per run, "
              f"{args.polls_per_change} poll(s) per change\n")
        print(f"{'screens':>8} {'polls':>7} {'refetch':>8} {'wasted':>7} "
              f"{'waste%':>7} {'q/poll':>7} {'median ms':>10} {'p90 ms':>8}")

        for count in [int(value) for value in args.screens.split(",")]:
            watchers = screens(count)
            held: dict = {}
            poll_round(watchers, held)          # settle: everyone is current

            refetched = wasted = queries = polls = 0
            latencies: list[float] = []
            for index in range(args.changes):
                order = board["HALL"][index % len(board["HALL"])]
                target = (OrderStatus.READY if order.status == OrderStatus.PREPARING
                          else OrderStatus.PREPARING)
                with transaction.atomic():
                    locked = status_service.locked(order.pk)
                    status_service.change(locked, target)
                    revisions.mark()
                order.status = target

                for _ in range(args.polls_per_change):
                    got, waste, q, lat = poll_round(watchers, held)
                    refetched += got
                    wasted += waste
                    queries += q
                    polls += len(watchers)
                    latencies.extend(lat)

            share = (wasted / refetched * 100) if refetched else 0.0
            ordered = sorted(latencies)
            # Nearest rank. `int(...)` truncates, which only agrees with p90
            # when the sample is a multiple of ten -- true of this script's
            # own defaults, and quietly false for any other run.
            p90 = ordered[max(math.ceil(len(ordered) * 0.9), 1) - 1]
            print(f"{count:>8} {polls:>7} {refetched:>8} {wasted:>7} "
                  f"{share:>6.0f}% {queries / polls:>7.1f} "
                  f"{statistics.median(ordered):>10.2f} {p90:>8.2f}")
    finally:
        connection.creation.destroy_test_db(
            connection.settings_dict["NAME"], verbosity=0
        )
        teardown_test_environment()


if __name__ == "__main__":
    main()

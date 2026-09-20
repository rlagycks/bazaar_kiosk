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

Two things are reported per screen count:

* **wasted** -- refetches that returned data the screen already had, because
  the change that woke it was in a scope it cannot see. This is the number
  that argues for splitting the marker;
* **cost** -- queries, and latency, for the refetch itself.

Run it against a disposable database, never a deployment:

    export BK_TEST_DATABASE_URL=postgresql://...      # the control database
    .venv/bin/python scripts/snapshot_amplification.py --screens 1,4,12

It creates its own test database, migrates it, and drops it at the end.
"""

from __future__ import annotations

import argparse
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
    args = parser.parse_args()

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
              f"{args.changes} hall changes per run\n")
        print(f"{'screens':>8} {'refetch':>8} {'wasted':>7} {'waste%':>7} "
              f"{'q/poll':>7} {'median ms':>10} {'p90 ms':>8}")

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

                got, waste, q, lat = poll_round(watchers, held)
                refetched += got
                wasted += waste
                queries += q
                polls += len(watchers)
                latencies.extend(lat)

            share = (wasted / refetched * 100) if refetched else 0.0
            ordered = sorted(latencies)
            print(f"{count:>8} {refetched:>8} {wasted:>7} {share:>6.0f}% "
                  f"{queries / polls:>7.1f} "
                  f"{statistics.median(ordered):>10.2f} "
                  f"{ordered[int(len(ordered) * 0.9) - 1]:>8.2f}")
    finally:
        connection.creation.destroy_test_db(
            connection.settings_dict["NAME"], verbosity=0
        )
        teardown_test_environment()


if __name__ == "__main__":
    main()

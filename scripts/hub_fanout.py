#!/usr/bin/env python
"""What one change costs the hub as screens are added (10D1, BK-R040).

10C measured the read side when every screen polls for itself: the cost of a
change was O(screens), and a third of it was wasted on screens that could not
see what changed. 10D1's claim is that a hub makes both of those flat, so this
measures the two numbers that claim rests on:

* **queries per change** -- one batched authorization read plus one snapshot
  per *distinct scope*, not per screen. If this grows with screens, the
  batching is not working and the claim is false;
* **notified vs woken** -- how many screens are told, out of how many are
  open. Under the per-screen polling 10C measured, every screen refetched on
  every change. Here a screen is told only when what *it* can see moved.

Run it against a disposable database, never a deployment:

    export BK_TEST_DATABASE_URL=postgresql://...      # the control database
    .venv/bin/python scripts/hub_fanout.py --screens 1,3,6,12

It creates its own test database, migrates it, and drops it at the end.

Caveat, stated because 10C's harness got this wrong in the other direction:
this drives the hub's dispatch directly rather than over real connections, so
it measures the hub's cost per change and *not* the cost of the streams
themselves. Each open stream still holds a worker slot; that was measured in
10A and is bounded in `orders/views/stream.py`.
"""

from __future__ import annotations

import argparse
import asyncio
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
            OrderItem.objects.create(order=order, menu_item=menu, qty=2,
                                     unit_price=8000, service_mode=mode)
            made[kind].append(order)
    with transaction.atomic():
        revisions.mark()
    return made


def watchers(count: int):
    """The screens a real kitchen runs, in rotation -- the same mix as 10C."""
    from orders.roles import HALL_MONITOR, STATS, TAKEOUT_MONITOR

    kinds = [("hall", (HALL_MONITOR,)), ("takeout", (TAKEOUT_MONITOR,)),
             ("stats", (STATS,))]
    return [kinds[i % len(kinds)] for i in range(count)]


def sessions_for(count: int):
    """Real `AuthDevice` rows, so the batched authorization read is real."""
    from orders.tests.auth_support import EVENT_PASSWORD_HASH, make_account
    from orders.authentication import issue_tokens
    from django.test import override_settings

    made = []
    with override_settings(EVENT_PASSWORD_HASH=EVENT_PASSWORD_HASH):
        for index, (name, permissions) in enumerate(watchers(count)):
            account = make_account(f"{name}-{index}", *permissions)
            made.append((issue_tokens(account).session_id, permissions))
    return made


def _reset_log():
    from django.db import reset_queries

    reset_queries()


def _queries_so_far() -> int:
    from django.db import connection

    return len(connection.queries)


async def one_change(hub_module, subscriptions, change):
    """Commit a change, then run exactly one hub dispatch over it.

    The counting is done through `sync_to_async(thread_sensitive=True)` rather
    than with `CaptureQueriesContext`, which cannot be entered from an async
    context. That is not a workaround: the hub's statements are issued on the
    executor thread, so the query log that matters is *that* thread's, and
    reading it anywhere else would count nothing and look like a triumph.
    """
    from asgiref.sync import sync_to_async

    await sync_to_async(change, thread_sensitive=True)()
    await sync_to_async(_reset_log, thread_sensitive=True)()
    began = time.perf_counter()
    await hub_module._dispatch_for_measurement(subscriptions)
    elapsed = (time.perf_counter() - began) * 1000
    counted = await sync_to_async(_queries_so_far, thread_sensitive=True)()
    return counted, elapsed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screens", default="1,3,6,12")
    parser.add_argument("--changes", type=int, default=20)
    parser.add_argument("--orders", type=int, default=40)
    args = parser.parse_args()

    setup_django()
    from django.conf import settings
    from django.db import connection, transaction
    from django.test.utils import setup_test_environment, teardown_test_environment

    setup_test_environment()
    connection.creation.create_test_db(verbosity=0, autoclobber=False)
    settings.DEBUG = True
    try:
        from orders.models import OrderStatus
        from orders.services import hub as hub_module, revisions, status as status_service
        from orders.tests.auth_support import EVENT_PASSWORD_HASH

        settings.EVENT_PASSWORD_HASH = EVENT_PASSWORD_HASH
        board = build_board(args.orders, args.orders)
        print(f"board: {args.orders} hall + {args.orders} takeout waiting, "
              f"{args.changes} hall changes per run\n")
        print(f"{'screens':>8} {'scopes':>7} {'q/change':>9} {'notified':>9} "
              f"{'woken%':>7} {'median ms':>10} {'p90 ms':>8}")

        for count in [int(value) for value in args.screens.split(",")]:
            made = sessions_for(count)
            subscriptions = [
                hub_module.Subscription(session_id=session, permissions=permissions)
                for session, permissions in made
            ]
            scopes = len({s.scope_key() for s in subscriptions})
            queries = notified = 0
            latencies: list[float] = []

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    hub_module._prime_for_measurement(subscriptions))
                for index in range(args.changes):
                    order = board["HALL"][index % len(board["HALL"])]
                    target = (OrderStatus.READY
                              if order.status == OrderStatus.PREPARING
                              else OrderStatus.PREPARING)

                    def change(order=order, target=target):
                        with transaction.atomic():
                            locked = status_service.locked(order.pk)
                            status_service.change(locked, target)
                            revisions.mark()
                        order.status = target

                    q, ms = loop.run_until_complete(
                        one_change(hub_module, subscriptions, change))
                    queries += q
                    latencies.append(ms)
                    for subscription in subscriptions:
                        while subscription.pending():
                            subscription._queue.popleft()
                            notified += 1
            finally:
                # The hub's work runs on an asgiref executor thread, which
                # holds its own connection (deliberately -- one per worker,
                # not one per screen). Nothing else reaches it, so the last
                # thing done on that thread is to let go, or dropping the test
                # database finds a session still attached.
                from asgiref.sync import sync_to_async
                from django.db import connections as thread_connections

                loop.run_until_complete(sync_to_async(
                    thread_connections.close_all, thread_sensitive=True)())
                loop.close()

            ordered = sorted(latencies)
            import math
            p90 = ordered[max(math.ceil(len(ordered) * 0.9), 1) - 1]
            woken = notified / (count * args.changes) * 100
            print(f"{count:>8} {scopes:>7} {queries / args.changes:>9.1f} "
                  f"{notified:>9} {woken:>6.0f}% "
                  f"{statistics.median(ordered):>10.2f} {p90:>8.2f}")
    finally:
        connection.creation.destroy_test_db(
            connection.settings_dict["NAME"], verbosity=0
        )
        teardown_test_environment()


if __name__ == "__main__":
    main()

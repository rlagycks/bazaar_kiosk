#!/usr/bin/env python
"""What the change marker costs, measured rather than assumed (10B, D-019).

Every writing transaction now takes one row lock before it commits, so writes
serialize on that row for the length of the commit. That is the price of the
guarantee the marker makes -- a later number cannot commit first -- and the
question this script answers is how big it is on this machine, at this
concurrency, against a real PostgreSQL.

It measures the same workload with the marker and without it, by patching the
service rather than by editing the code: `--without` replaces `mark()` with a
function that does nothing, so the difference is the lock and the UPDATE and
nothing else.

Run it against a disposable database, never a deployment:

    export BK_TEST_DATABASE_URL=postgresql://...      # the control database
    .venv/bin/python scripts/marker_contention.py --concurrency 1,4,16

Each run creates its own test database, migrates it, and drops it at the end.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import threading
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


def one_write(order_id: int, item_id: int) -> float:
    """One cooking-progress transaction, timed. The kitchen's hottest write."""
    from django.db import transaction
    from orders.models import OrderItem
    from orders.services import revisions, status as status_service

    started = time.perf_counter()
    with transaction.atomic():
        order = status_service.locked(order_id)
        item = OrderItem.objects.select_for_update().get(id=item_id)
        item.prepared_qty = 1 if item.prepared_qty == 0 else 0
        item.save(update_fields=["prepared_qty"])
        status_service.sync_from_items(order)
        revisions.mark()
    return (time.perf_counter() - started) * 1000


def build_fixture(count: int):
    from orders.models import MenuItem, Order, OrderItem, OrderStatus, Table

    table = Table.objects.create(number=1)
    menu = MenuItem.objects.create(name="Bowl", price=8000)
    pairs = []
    for _ in range(count):
        order = Order.objects.create(
            table=table, floor="B1", order_type="DINE_IN",
            status=OrderStatus.PREPARING, total_price=8000,
            payment_method="CASH", received_cash_amount=8000,
        )
        item = OrderItem.objects.create(
            order=order, menu_item=menu, qty=2, unit_price=8000,
        )
        pairs.append((order.id, item.id))
    return pairs


def run(concurrency: int, rounds: int, pairs) -> dict:
    """`concurrency` writers, each doing `rounds` transactions, all at once.

    Each thread works on its own order, so the only row they contend for is
    the marker. That isolates what is being measured: with separate orders and
    no marker there is nothing to serialize on at all.
    """
    from django.db import connection

    latencies: list[float] = []
    lock = threading.Lock()
    errors: list[Exception] = []
    start = threading.Barrier(concurrency)

    def worker(index: int):
        order_id, item_id = pairs[index]
        mine = []
        try:
            start.wait(timeout=30)
            for _ in range(rounds):
                mine.append(one_write(order_id, item_id))
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)
        finally:
            with lock:
                latencies.extend(mine)
            connection.close()

    began = time.perf_counter()
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(concurrency)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    wall = (time.perf_counter() - began) * 1000

    if errors:
        raise errors[0]
    ordered = sorted(latencies)
    return {
        "concurrency": concurrency,
        "writes": len(ordered),
        "wall_ms": round(wall, 1),
        "median_ms": round(statistics.median(ordered), 2),
        "p90_ms": round(ordered[int(len(ordered) * 0.9) - 1], 2),
        "max_ms": round(ordered[-1], 2),
        "per_second": round(len(ordered) / (wall / 1000), 1),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", default="1,4,16",
                        help="comma-separated writer counts (default 1,4,16)")
    parser.add_argument("--rounds", type=int, default=25,
                        help="transactions per writer (default 25)")
    parser.add_argument("--without", action="store_true",
                        help="neutralise mark() to measure the same work without it")
    args = parser.parse_args()

    setup_django()
    from django.test.utils import setup_test_environment, teardown_test_environment
    from django.db import connection

    setup_test_environment()
    connection.creation.create_test_db(verbosity=0, autoclobber=False)
    try:
        if args.without:
            from orders.services import revisions
            revisions.mark = lambda: 0
            print("marker: DISABLED (baseline)")
        else:
            print("marker: enabled")

        levels = [int(value) for value in args.concurrency.split(",")]
        pairs = build_fixture(max(levels))
        print(f"{'writers':>8} {'writes':>7} {'wall ms':>9} {'median':>8} "
              f"{'p90':>8} {'max':>8} {'writes/s':>9}")
        for level in levels:
            result = run(level, args.rounds, pairs)
            print(f"{result['concurrency']:>8} {result['writes']:>7} "
                  f"{result['wall_ms']:>9} {result['median_ms']:>8} "
                  f"{result['p90_ms']:>8} {result['max_ms']:>8} "
                  f"{result['per_second']:>9}")
    finally:
        connection.creation.destroy_test_db(
            connection.settings_dict["NAME"], verbosity=0
        )
        teardown_test_environment()


if __name__ == "__main__":
    main()

"""V-STREAM: measure a running deployment candidate through its own proxy (10A).

The numbers in docs/modernization/ASGI_RUNTIME.md come from this script. It
lives here rather than in a scratch directory for the same reason
`scripts/test_postgres.py` does: a measurement nobody else can repeat is a
claim, not evidence.

It does not start anything. Bring the stack up first (see ASGI_RUNTIME.md),
then:

    python scripts/stream_smoke.py --project bk10a-stream --token "$ACCESS_TOKEN"

Nothing here writes to the database or touches a deployment; every request is
a read, and the probe it drives answers 404 unless BK_STREAM_PROBE=1.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import time

ROOT = __file__.rsplit("/scripts/", 1)[0]


class Stack:
    """The running compose project, asked about itself."""

    def __init__(self, project: str, base: str, compose_file: str):
        self.compose = ["docker", "compose", "-p", project, "-f", compose_file]
        self.base = base

    def run(self, *args: str) -> str:
        """Ask the stack something, and refuse to guess when it will not say.

        This raised rather than returned empty after the first version did
        the latter: a `docker compose stop` that failed on a missing
        environment variable was reported as a restart that finished in
        0.1 seconds. A measuring tool that turns a failure into a good
        number is worse than no tool.
        """
        done = subprocess.run(self.compose + list(args), cwd=ROOT,
                              capture_output=True, text=True)
        if done.returncode != 0:
            raise SystemExit(
                f"`docker compose {' '.join(args)}` failed ({done.returncode}).\n"
                f"{done.stderr.strip()}\n"
                "The stack's own environment has to be set in this shell too; "
                "see docs/modernization/ASGI_RUNTIME.md."
            )
        return done.stdout

    def database_connections(self) -> int:
        out = self.run("exec", "-T", "postgres", "psql", "-U", "bazaar_bootstrap",
                       "-d", "bazaar", "-tAc",
                       "select count(*) from pg_stat_activity where datname='bazaar'")
        return int(out.strip() or -1)

    def worker_threads(self) -> int:
        """Threads across every process in the application container."""
        out = self.run("exec", "-T", "app", "sh", "-c",
                       "for p in /proc/[0-9]*; do [ -r $p/status ] || continue; "
                       "awk '/^Threads:/{print $2}' $p/status; done")
        return sum(int(value) for value in out.split())

    def open_file_descriptors(self) -> int:
        out = self.run("exec", "-T", "app", "sh", "-c",
                       "for p in /proc/[0-9]*; do [ -d $p/fd ] || continue; "
                       "ls $p/fd 2>/dev/null | wc -l; done")
        return sum(int(value) for value in out.split())


def curl_stream(base: str, token: str, frames: int, interval_ms: int):
    """One `curl -N`, with the wall-clock arrival of every frame."""
    url = f"{base}/orders/api/stream/probe?frames={frames}&interval_ms={interval_ms}"
    started = time.monotonic()
    proc = subprocess.Popen(
        ["curl", "-sN", "--no-buffer", "-H", f"Authorization: Bearer {token}", url],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0,
    )
    arrivals, buffer = [], b""
    while True:
        byte = proc.stdout.read(1)
        if not byte:
            break
        buffer += byte
        if buffer.endswith(b"\n\n"):
            arrivals.append((round((time.monotonic() - started) * 1000),
                             buffer.decode().strip()))
            buffer = b""
    proc.wait()
    return arrivals


def hold_streams(base: str, token: str, count: int):
    """`count` streams opened and left open, for the caller to kill."""
    url = f"{base}/orders/api/stream/probe?frames=200&interval_ms=2000"
    return [
        subprocess.Popen(
            ["curl", "-sN", "--no-buffer", "-H", f"Authorization: Bearer {token}", url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(count)
    ]


def api_latencies(base: str, token: str, path: str, samples: int = 8):
    values = []
    for _ in range(samples):
        started = time.monotonic()
        subprocess.run(["curl", "-s", "-o", "/dev/null",
                        "-H", f"Authorization: Bearer {token}", base + path],
                       capture_output=True)
        values.append(round((time.monotonic() - started) * 1000))
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="bk10a-stream")
    parser.add_argument("--compose-file", default="compose.prod.yaml")
    parser.add_argument("--base", default="http://127.0.0.1:8080")
    parser.add_argument("--token", required=True, help="an access token (Bearer)")
    parser.add_argument("--load", default="0,6,24,48",
                        help="comma-separated counts of simultaneously open streams")
    args = parser.parse_args()
    stack = Stack(args.project, args.base, args.compose_file)

    print("== frames arrive one at a time, before the response ends")
    arrivals = curl_stream(args.base, args.token, frames=5, interval_ms=500)
    for at_ms, block in arrivals:
        print(f"   t+{at_ms:5d} ms  {block.splitlines()[0]:14s} "
              f"{block.splitlines()[-1]}")
    gaps = [arrivals[i][0] - arrivals[i - 1][0] for i in range(1, len(arrivals))]
    print(f"   gaps: {gaps} ms (asked for 500)")

    print()
    print("== what an open stream costs, and whether the API still answers")
    print(f"   {'open':>5} {'threads':>8} {'fds':>6} {'db':>4}   GET /orders/menus/")
    for count in (int(value) for value in args.load.split(",")):
        held = hold_streams(args.base, args.token, count) if count else []
        time.sleep(4)
        threads, fds, db = (stack.worker_threads(), stack.open_file_descriptors(),
                            stack.database_connections())
        latencies = api_latencies(args.base, args.token, "/orders/menus/")
        print(f"   {count:>5} {threads:>8} {fds:>6} {db:>4}   "
              f"median {statistics.median(latencies):.0f} ms  max {max(latencies)} ms")
        for proc in held:
            proc.kill()
        for proc in held:
            proc.wait()
        time.sleep(3)

    time.sleep(3)
    print(f"   after every client is gone: threads={stack.worker_threads()} "
          f"fds={stack.open_file_descriptors()} db={stack.database_connections()}")

    print()
    print("== a restart does not wait forever on an open stream")
    held = hold_streams(args.base, args.token, 1)
    time.sleep(3)
    started = time.monotonic()
    stack.run("stop", "-t", "30", "app")
    stopped = round(time.monotonic() - started, 1)
    stack.run("start", "app")
    time.sleep(4)
    held[0].kill()
    print(f"   `compose stop -t 30 app` returned in {stopped}s "
          "(--timeout-graceful-shutdown bounds it; unbounded waits out the 30)")
    alive = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
         "-H", f"Authorization: Bearer {args.token}", args.base + "/orders/menus/"],
        capture_output=True, text=True).stdout
    print(f"   ordinary API after the restart: {alive}")


if __name__ == "__main__":
    main()

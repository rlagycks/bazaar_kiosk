"""10A: a synthetic stream whose only job is to be measured (BK-R035).

This is an instrument, not a feature. It serves no order data and no screen
calls it. It exists because the claim "this deployment can stream" cannot be
read off a file: `asgi.py` has existed since the project was generated while
the production stack ran `gunicorn ...wsgi:application`, where a streaming
response is collected and sent as one body.

What one run of this proves, against a real uvicorn process behind nginx:

* frames leave the worker one at a time, before the response ends, and survive
  the proxy -- so nothing between the view and the client is buffering;
* an ordinary API request answers while streams are open, so a held connection
  does not occupy a worker;
* *this* view releases the connection authentication opened before the first
  frame, so it costs a worker slot and not a database slot. That is a property
  of this code, not of the runtime: a hub that reads per event (10D1) has to
  release each time or the connection count follows open screens again;
* when the client disconnects, the generator is closed and the request ends;
* the view and its generator share one event loop, with or without a
  synchronous middleware in the chain.

The real kitchen SSE endpoint is 10D1 and shares none of this code. What it
shares is the runtime this file measures.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import connections
from django.http import Http404, JsonResponse, StreamingHttpResponse

from orders.views.guards import require_api_permissions

# Bounds, not preferences. A caller choosing the shape of a stream chooses how
# long a worker is occupied, so what a request may ask for is limited here. A
# request that asks for something unreadable gets the default rather than an
# error: this is a measuring tool, and ending a run over a typo in a query
# string is the wrong trade.
DEFAULT_FRAMES = 5
MAX_FRAMES = 200
DEFAULT_INTERVAL_MS = 200
MAX_INTERVAL_MS = 2000

# How many streams one worker will hold at a time. The bounds above limit how
# long a single stream lasts (200 frames x 2s is nearly seven minutes) but not
# how many a caller may start, and the measurement showed each open stream
# occupies a worker thread. Without this, one authenticated device -- any
# account, since this endpoint uses the "any signed-in caller" sentinel -- can
# grow a worker's thread count for as long as the switch is on.
#
# 32 is chosen against the measurement, not tuned: 48 streams across three
# workers left ordinary API latency unchanged, so 32 per worker is above what
# was shown to be comfortable and far below what would hurt. The real ceiling
# for kitchen displays is 10D1's to set, with D-007's numbers.
MAX_OPEN_STREAMS = 32

_LOCK = threading.Lock()
_open_streams = 0

# Incremented when a stream's generator is closed -- on completion and on
# disconnect alike. Per process, so it answers "did the generator let go?" in
# a test; across workers the same question is answered at the database and by
# the worker's own file descriptor count.
closed_streams = 0


class _Slot:
    """One stream's claim on this worker, given back exactly once.

    Two things can end a stream and only one of them is the generator: a
    response that is created and then never iterated -- the client vanished in
    the moment between -- is closed without the generator ever starting, and a
    generator that never started does not run its `finally`. So the release is
    idempotent and both paths call it. A claim that leaked would not recover:
    it would lower this worker's ceiling until the process restarted.
    """

    __slots__ = ("_released",)

    def __init__(self):
        self._released = False

    def release(self):
        global _open_streams
        with _LOCK:
            if self._released:
                return
            self._released = True
            _open_streams -= 1


def _claim() -> _Slot | None:
    """A slot for a new stream, or None when this worker is already full."""
    global _open_streams
    with _LOCK:
        if _open_streams >= MAX_OPEN_STREAMS:
            return None
        _open_streams += 1
    return _Slot()


def _bounded(raw, default: int, low: int, high: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(low, min(value, high))


def _frame(event: str, payload: dict) -> bytes:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return f"event: {event}\ndata: {body}\n\n".encode("utf-8")


def _database_is_held() -> bool:
    """Whether the caller's execution context is sitting on a connection.

    Django keeps connections in context-local storage keyed by thread, so this
    has to be asked on the thread that did the work. Asked anywhere else it
    would answer `False` about a connection that is still open, which is the
    comfortable answer and the wrong one.
    """
    return connections["default"].connection is not None


async def _frames(count: int, interval: float, db_open: bool, view_loop: int, slot: _Slot):
    global closed_streams
    started = time.monotonic()
    delivered = 0
    # Reported because the answer was assumed before it was measured. A
    # sync-only middleware makes Django run the view under `async_to_sync`,
    # and the obvious worry is that the view then builds loop-bound objects --
    # 10D1's hub queue -- in a loop that dies with it. Measured, that does not
    # happen: asgiref sends the coroutine back to the original loop, so this
    # stays True either way. It is in every frame so that the next person to
    # assume otherwise is contradicted by their own measurement run rather
    # than by a comment.
    same_loop = id(asyncio.get_running_loop()) == view_loop
    try:
        for seq in range(count):
            yield _frame("probe", {
                "seq": seq,
                "pid": os.getpid(),
                "thread": threading.current_thread().name,
                "db_open": db_open,
                "same_loop": same_loop,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            })
            delivered = seq + 1
            if interval:
                await asyncio.sleep(interval)
        yield _frame("done", {"frames": delivered})
    finally:
        # Reached on completion and on disconnect alike: Django closes the
        # iterator when the client goes away, which is how a generator holding
        # anything learns to let go of it. 10D1's hub unsubscribes here.
        slot.release()
        closed_streams += 1


@require_api_permissions()
async def _probe(request):
    frames = _bounded(request.GET.get("frames"), DEFAULT_FRAMES, 1, MAX_FRAMES)
    interval_ms = _bounded(
        request.GET.get("interval_ms"), DEFAULT_INTERVAL_MS, 0, MAX_INTERVAL_MS
    )
    slot = _claim()
    if slot is None:
        # Refused rather than queued: a caller waiting for a slot would hold a
        # connection anyway, which is the thing being rationed.
        response = JsonResponse(
            {"detail": "열린 스트림이 이미 한도에 찼습니다. 잠시 후 다시 시도해 주세요."},
            status=503,
        )
        response["Retry-After"] = "5"
        return response
    # Authentication read the database on this request's own thread. Releasing
    # that connection here rather than leaving it to the end of the request is
    # the whole point: for a streaming response "the end of the request" is
    # when the last frame is sent, which for the kitchen means as long as a
    # screen stays open. `thread_sensitive` keeps the close and the check on
    # the thread where the connection actually lives.
    db_open = await sync_to_async(_release_connection, thread_sensitive=True)()
    response = StreamingHttpResponse(
        _frames(frames, interval_ms / 1000, db_open,
                id(asyncio.get_running_loop()), slot),
        content_type="text/event-stream",
    )
    # The other release path. Django closes the response even when nothing
    # ever iterated it, and in that case the generator's `finally` never runs.
    response._resource_closers.append(slot.release)
    # nginx buffers a proxied response by default, which would hold every
    # frame until the stream ended and make a working runtime look broken.
    # The location block turns buffering off; this header says the same thing
    # to any proxy the location does not cover.
    response["X-Accel-Buffering"] = "no"
    return response


def _release_connection() -> bool:
    """Close this thread's connection; report whether one is still held."""
    connection = connections["default"]
    if connection.in_atomic_block:
        # Only a test reaches this: `TestCase` wraps each request in a
        # transaction, and a connection inside one cannot be released without
        # discarding it. Saying so is better than closing anyway and leaving
        # the caller with a connection marked broken. The path that matters is
        # covered by a `TransactionTestCase`, which has no such wrapper.
        return True
    connection.close()
    return _database_is_held()


async def stream_probe(request):
    """The routed view. Absent unless a measurement run turned it on.

    The switch is read before credentials on purpose: answering 401 first
    would tell an unauthenticated caller that the route exists and is merely
    disabled, which is worth knowing only to someone looking for it.
    """
    if not getattr(settings, "STREAM_PROBE_ENABLED", False):
        raise Http404()
    return await _probe(request)


stream_probe.answers_in_json = True
# The proxy needs this route inside its non-buffering location, or the frames
# are collected and delivered at the end -- a working runtime that looks
# exactly like the WSGI one it replaced. Marking the view rather than writing
# the path down twice is what lets a test check the two against each other,
# and what 10D1's own endpoint has to wear.
stream_probe.streams = True

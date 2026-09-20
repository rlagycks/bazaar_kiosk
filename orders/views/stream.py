"""The kitchen's event stream (10D1, D-060).

Carries no order data. Under the convergence contract D-058 settled, an event
says only "the thing you are showing is no longer current, and here is the
version that is" -- the screen then fetches 10C's snapshot, which is the only
place order data is served and the only place permissions decide what it
contains. An event that carried the orders would be a second copy of that
decision, in a path where the caller was authorized minutes ago.

**Why a cookie and not a Bearer token (user decision, D-060).** `EventSource`
cannot set headers, and the alternative -- `fetch` plus a ReadableStream -- moves
reconnection, backoff, frame parsing and BFCache handling into code we would
write ourselves, which is exactly the surface BK-R020/033 are about. So the
stream authenticates with the refresh cookie, which is `HttpOnly`, `Secure`
and `SameSite=Strict` and therefore out of reach of script. It does *not*
rotate that cookie: this is a read, and rotating on a connection that stays
open all evening would race every other tab.

A refusal here is JSON with a status, never the login redirect the page guard
sends. `EventSource` reports a redirect to an HTML page as an opaque failure
and retries forever, so a screen whose shift ended would reconnect all night
without anyone learning why.
"""

from __future__ import annotations

import asyncio
import json
import threading

from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import JsonResponse, StreamingHttpResponse
from django.utils.cache import patch_cache_control

from orders.authentication import AuthError, refresh_identity
from orders.roles import ORDER_READ_PERMISSIONS
from orders.services import hub

# The same reasoning as the 10A probe's ceiling, for the same resource: each
# open stream holds a worker slot. The probe measured 48 streams across three
# workers with ordinary API latency unchanged, so this sits above what was
# shown to be comfortable. Unlike the probe this is a real screen count -- a
# bazaar with more than 24 kitchen displays on one worker has other problems.
MAX_OPEN_STREAMS = 24

_LOCK = threading.Lock()
_open_streams = 0


def _claim() -> bool:
    global _open_streams
    with _LOCK:
        if _open_streams >= MAX_OPEN_STREAMS:
            return False
        _open_streams += 1
    return True


def _release() -> None:
    global _open_streams
    with _LOCK:
        _open_streams -= 1


def _frame(event: str, payload: dict) -> bytes:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return f"event: {event}\ndata: {body}\n\n".encode("utf-8")


def _identify(request):
    """Who is asking, from the refresh cookie, or a refusal to send."""
    try:
        identity = refresh_identity(
            request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME, "")
        )
    except AuthError:
        response = JsonResponse({"detail": "로그인이 필요합니다."}, status=401)
        patch_cache_control(response, private=True, no_store=True)
        return None, response
    if not (set(ORDER_READ_PERMISSIONS) & set(identity.permissions)):
        response = JsonResponse({"detail": "권한이 없습니다."}, status=403)
        patch_cache_control(response, private=True, no_store=True)
        return None, response
    return identity, None


def _opening_version(permissions) -> str:
    from orders.services import snapshots

    return snapshots.version_for(permissions)


def _releaser(subscription):
    """Give the slot and the subscription back, exactly once.

    Two paths end a stream and both must be safe to take: the generator's
    `finally` on the ordinary path, and the response's resource closer when
    the response is closed without ever being iterated. A slot returned twice
    would lower this worker's ceiling by one for good, which is the same
    failure as leaking it -- just slower to notice.
    """
    done = False

    def give_back():
        nonlocal done
        if done:
            return
        done = True
        hub.unsubscribe(subscription)
        _release()

    return give_back


async def _events(subscription, opening_version, give_back):
    """Frames, until the caller goes away or the hub ends the subscription."""
    try:
        yield _frame("ready", {
            "version": opening_version,
            "heartbeat_ms": int(hub.heartbeat_seconds() * 1000),
            **hub.health().as_frame(),
        })
        while True:
            event = await subscription.next_event(hub.heartbeat_seconds())
            if subscription.closed_reason is not None:
                # Said out loud rather than dropped: `EventSource` treats a
                # closed connection as a transport hiccup and retries, so a
                # screen cut off for cause has to be told it was.
                yield _frame("closed", {"reason": subscription.closed_reason})
                return
            if subscription.overflowed:
                subscription.overflowed = False
                yield _frame("change", {
                    "version": (event or {}).get("version"),
                    "reset": True,
                })
                continue
            if event is None:
                # A heartbeat is not evidence the hub is working -- D-019 is
                # explicit that a client must not stop polling on one. So the
                # beat carries the hub's own last success and lets the screen
                # decide.
                yield _frame("heartbeat", hub.health().as_frame())
                continue
            yield _frame("change", event)
    finally:
        give_back()


async def kitchen_stream(request):
    """Open a stream for this screen."""
    identity, refusal = await sync_to_async(_identify, thread_sensitive=True)(request)
    if refusal is not None:
        return refusal
    if not _claim():
        response = JsonResponse(
            {"detail": "열린 화면이 이미 한도에 찼습니다. 잠시 후 다시 시도해 주세요."},
            status=503,
        )
        response["Retry-After"] = "5"
        return response
    permissions = tuple(identity.permissions)
    try:
        opening = await sync_to_async(_opening_version, thread_sensitive=True)(
            permissions
        )
    except Exception:
        _release()
        raise
    subscription = hub.subscribe(identity.session_id, permissions)
    give_back = _releaser(subscription)
    try:
        response = StreamingHttpResponse(
            _events(subscription, opening, give_back),
            content_type="text/event-stream",
        )
        # Authentication read the database on this request's own thread. For a
        # streaming response "the end of the request" is when the screen
        # closes, so releasing here is what keeps the connection count from
        # following the number of open screens (10A).
        await sync_to_async(_release_connection, thread_sensitive=True)()
        response["X-Accel-Buffering"] = "no"
        patch_cache_control(response, private=True, no_store=True)
    except Exception:
        # Nothing between the claim and the first `yield` may fail silently: a
        # generator that is never advanced never enters its own `try`, so its
        # `finally` is not a safety net for this window. Without this the slot
        # and the subscription are lost for the life of the worker.
        give_back()
        raise

    # The generator's `finally` covers the ordinary path; this covers a
    # response closed without ever being iterated, where it never runs. Django
    # only auto-registers a closer for streaming content exposing a *sync*
    # `close()`, and an async generator has only `aclose()`, so this is the
    # only net. An earlier version defined `give_back` and then registered
    # `lambda: None` beside it, which left the net inert -- enough dropped
    # connections would have pinned the worker at 503 until it restarted.
    response._resource_closers.append(give_back)
    return response


def _release_connection() -> None:
    from django.db import connections

    connection = connections["default"]
    if not connection.in_atomic_block:
        connection.close()


kitchen_stream.answers_in_json = True
# Must sit inside the proxy's non-buffering location or every frame is held
# until the stream ends. `test_runtime_config.py` checks the route against the
# configuration rather than against this comment.
kitchen_stream.streams = True

"""Startup checks for facts that are invisible in the file that breaks them.

10A: the ASGI request path is only async if *every* middleware is. Django
adapts a sync-only entry by wrapping the whole chain inside it in
`async_to_sync`, so adding one -- a third-party package, a debug toolbar, a
future WhiteNoise -- silently puts every request through two thread hops.

What that costs was measured rather than assumed, because the first version of
this file assumed it and was wrong. Running 128 requests at 32-way concurrency
through a real `ASGIHandler`, with and without one sync-only middleware in an
otherwise async chain:

    async-capable only     wall 144-152 ms   median 34-35 ms   p90 36-39 ms
    one sync-only entry    wall 154-180 ms   median 35-41 ms   p90 44-50 ms

So: a consistently worse tail and a few percent of throughput, repeatable
across runs. Not a correctness failure -- asgiref sends the inner coroutine
back to the original event loop, so nothing the view creates is stranded
(`orders/tests/test_asgi_stream.py` pins that, having disproved the opposite
claim). The reason this is an Error rather than a note is that the cost is
invisible: nothing fails, no test goes red, and the deployment simply stops
being what it says it is.
"""

from __future__ import annotations

from django.conf import settings
from django.core.checks import Error, register
from django.utils.module_loading import import_string

STREAM_ASYNC_MIDDLEWARE = "orders.E001"


@register()
def middleware_is_async_capable(app_configs, **kwargs):
    """Refuse a middleware list that puts the request path back on threads."""
    offenders = []
    for path in settings.MIDDLEWARE:
        try:
            middleware = import_string(path)
        except ImportError:
            # Django's own check reports an unimportable middleware with a
            # better message than this one would.
            continue
        if not getattr(middleware, "async_capable", False):
            offenders.append(path)
    if not offenders:
        return []
    return [
        Error(
            "These middleware are synchronous only: " + ", ".join(offenders) + ".",
            hint=(
                "Django wraps everything inside a sync-only middleware in "
                "async_to_sync, so every request -- not just the ones that "
                "middleware cares about -- crosses two thread hops. Serve the "
                "concern outside the application (the proxy handles static "
                "files), or give the middleware an async path and set "
                "async_capable = True."
            ),
            id=STREAM_ASYNC_MIDDLEWARE,
        )
    ]

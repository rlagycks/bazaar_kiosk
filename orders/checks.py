"""Startup checks for facts that are invisible in the file that breaks them.

10A: the ASGI request path is only async if *every* middleware is. Django
adapts a sync-only entry by wrapping the whole chain inside it in
`async_to_sync`, so adding one -- a third-party package, a debug toolbar, a
future WhiteNoise -- silently moves views and their generators onto a borrowed
thread in a second event loop. Nothing fails. The stream keeps working until
something inside it holds a loop-bound object, which is what 10D1's hub queue
will be.

There is no way to see this from the middleware list, so it is a check.
"""

from __future__ import annotations

from django.conf import settings
from django.core.checks import Error, register
from django.utils.module_loading import import_string

STREAM_ASYNC_MIDDLEWARE = "orders.E001"


@register()
def middleware_is_async_capable(app_configs, **kwargs):
    """Refuse a middleware list that takes the request path out of the loop."""
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
                "async_to_sync, so views run in another event loop on a "
                "borrowed thread and streaming responses lose the guarantee "
                "10A establishes. Serve the concern outside the application "
                "(the proxy handles static files), or give the middleware an "
                "async path and set async_capable = True."
            ),
            id=STREAM_ASYNC_MIDDLEWARE,
        )
    ]

# FILE: orders/tests/urls_outside_api.py
"""A URLconf that mounts an API view outside the /orders/api/ prefix.

`_targets_the_api` resolves the request through the URLconf and looks for the
marker `require_api_permissions` sets, rather than matching the path against a
prefix. The docstring argues that this is what keeps the JSON refusal correct
when a route moves or an API view is added elsewhere -- an argument nothing
could check while every API view lived under one prefix. This module gives that
claim a route to be true about.
"""
from django.http import JsonResponse
from django.urls import include, path

from orders.views.guards import require_api_permissions


@require_api_permissions()
def ping(request):
    return JsonResponse({"ok": True})


urlpatterns = [
    # Deliberately not under /orders/api/, and not even under /orders/.
    path("somewhere-else/ping", ping, name="outside-api-ping"),
    path("orders/", include(("orders.urls", "orders"), namespace="orders")),
]

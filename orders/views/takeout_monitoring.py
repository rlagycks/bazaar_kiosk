"""Authenticated adapters for the menu-based takeout monitor."""
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from orders.roles import TAKEOUT_MONITOR
from orders.services import takeout_monitoring as service
from orders.services import workday
from orders.services.monitoring_actions import ActionConflict, InvalidAction
from orders.views import validators
from orders.views.guards import require_api_permissions


@transaction.non_atomic_requests
@require_api_permissions(TAKEOUT_MONITOR)
@require_http_methods(["GET"])
def snapshot(request):
    raw = request.GET.get("page", "1")
    if not raw.isascii() or not raw.isdecimal() or len(raw) > 7:
        return JsonResponse({"detail": "page는 1~1000000의 정수여야 합니다."}, status=400)
    try:
        day = workday.parse_day(request.GET.get("date"))
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    try:
        data = service.read(request.auth_permissions, page=int(raw), since=request.GET.get("since") or None, day=day)
    except ValueError:
        return JsonResponse({"detail": "page는 1~1000000의 정수여야 합니다."}, status=400)
    return JsonResponse(data)


@require_api_permissions(TAKEOUT_MONITOR)
@require_http_methods(["POST"])
def complete(request):
    try:
        result = service.complete(validators.body(request), actor=request.auth_account,
                                  permissions=request.auth_permissions)
    except (validators.InvalidInput, InvalidAction) as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    except ActionConflict as exc:
        return JsonResponse({"detail": str(exc)}, status=409)
    return JsonResponse(result)

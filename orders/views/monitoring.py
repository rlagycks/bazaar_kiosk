"""The UI-05B monitoring read endpoint."""

from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from orders.services import monitoring_snapshot as snapshot_service
from orders.views.guards import require_api_permissions


@transaction.non_atomic_requests
@require_api_permissions()
@require_http_methods(["GET"])
def monitoring_snapshot(request: HttpRequest):
    """GET scope=HALL|TAKEOUT|ALL&page=1&since=<opaque version>."""
    mode = request.GET.get("scope", "ALL")
    raw_page = request.GET.get("page", "1")
    # Bound parsing as well as the value: arbitrarily long integers should
    # consistently answer 400, not depend on Python's digit conversion limit.
    if not raw_page.isascii() or not raw_page.isdecimal() or len(raw_page) > 7:
        return JsonResponse({"detail": "page는 1~1000000의 정수여야 합니다."}, status=400)
    try:
        data = snapshot_service.read(
            request.auth_permissions, mode=mode, page=int(raw_page),
            since=request.GET.get("since") or None,
        )
    except ValueError:
        return JsonResponse({"detail": "scope는 HALL, TAKEOUT, ALL이고 page는 1~1000000이어야 합니다."}, status=400)
    except PermissionError:
        return JsonResponse({"detail": "권한이 없습니다."}, status=403)
    return JsonResponse(data)

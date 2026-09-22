"""HTTP adapter for the atomic monitoring action service."""
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from orders.models import Order
from orders.roles import MONITOR_PERMISSIONS
from orders.services import monitoring_actions
from orders.services.status import TransitionRefused
from orders.views import validators
from orders.views.guards import require_api_permissions


@require_api_permissions(*MONITOR_PERMISSIONS)
@require_http_methods(["PATCH"])
def monitor_order_action(request, order_id):
    try:
        payload = validators.body(request)
        order = monitoring_actions.apply(
            order_id, payload, actor=request.auth_account,
            permissions=request.auth_permissions,
        )
    except (validators.InvalidInput, monitoring_actions.InvalidAction) as exc:
        return HttpResponseBadRequest(str(exc))
    except monitoring_actions.ActionForbidden as exc:
        return JsonResponse({"detail": str(exc)}, status=403)
    except (monitoring_actions.ActionConflict, TransitionRefused) as exc:
        return JsonResponse({"detail": str(exc)}, status=409)
    except Order.DoesNotExist:
        raise Http404("주문이 존재하지 않습니다.")
    return JsonResponse({"id": order.pk, "status": order.status})

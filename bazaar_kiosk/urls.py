# bazaar_kiosk/urls.py
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

def healthz(_):
    return JsonResponse({"ok": True})

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", healthz),         # Render Health Check용
    path("", include("orders.urls")), # 앱 라우트(선택)
]
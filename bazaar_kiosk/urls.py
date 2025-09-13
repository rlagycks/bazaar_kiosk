# FILE: bazaar_kiosk/urls.py
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("orders/", include("orders.urls")),
    path("", RedirectView.as_view(url="/orders/", permanent=False)),  # / → /orders/
]
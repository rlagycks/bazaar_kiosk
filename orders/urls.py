# FILE: orders/urls.py
from __future__ import annotations
from django.urls import path
from django.views.generic import RedirectView
from orders.views import pages, api, auth, stream

app_name = "orders"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="orders:login", permanent=False)),

    path("login/",  auth.login_view,  name="login"),
    path("logout/", auth.logout_view, name="logout"),

    path("auth/refresh/", auth.refresh_view, name="refresh"),

    # 화면
    path("order/",             pages.order_page,          name="order"),
    path("b1-counter/",        pages.b1_counter_page,     name="b1-counter"),
    path("kitchen/",           pages.kitchen_overview_page,    name="kitchen"),
    path("kitchen/hall/",      pages.kitchen_hall_page,       name="kitchen-hall"),
    path("kitchen/takeout/",   pages.kitchen_takeout_page,    name="kitchen-takeout"),

    # API
    path("tables/",                 api.tables_list,          name="tables"),
    path("menus/",                  api.menus_list,           name="menus"),
    path("api/orders/",             api.orders_collection,    name="orders-collection"),
    path("api/orders/<int:order_id>/detail", api.order_detail, name="order-detail"),
    path("api/orders/<int:order_id>/status", api.order_status, name="order-status"),
    path("api/orders/items/<int:item_id>/progress", api.order_item_progress, name="order-item-progress"),
    path("api/stats/menu-counts",   api.stats_menu_counts,    name="stats-menu-counts"),
    path("api/stats/dashboard",     api.stats_dashboard,      name="stats-dashboard"),

    # 10A: the synthetic stream that measures the ASGI runtime. Routed always
    # and answering 404 unless STREAM_PROBE_ENABLED is on, so that turning it
    # on for a measurement run is a setting and not a code change.
    path("api/stream/probe",        stream.stream_probe,      name="stream-probe"),
]

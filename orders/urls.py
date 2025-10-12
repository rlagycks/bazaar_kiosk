# FILE: orders/urls.py
from __future__ import annotations
from django.urls import path
from django.views.generic import RedirectView
from orders.views import pages, api, auth 

app_name = "orders"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="orders:login", permanent=False)),

    path("login/",  auth.login_view,  name="login"),
    path("logout/", auth.logout_view, name="logout"),

    # 화면
    path("order/",             pages.order_page,          name="order"),
    path("b1-counter/",        pages.b1_counter_page,     name="b1-counter"),
    path("kitchen/",           pages.kitchen_page,        name="kitchen"),
    path("kitchen/monitor/",   pages.kitchen_monitor_page, name="kitchen-monitor"),

    # API
    path("tables/",                 api.tables_list,          name="tables"),
    path("menus/",                  api.menus_list,           name="menus"),
    path("api/orders/",             api.orders_collection,    name="orders-collection"),
    path("api/orders/<int:order_id>/status", api.order_status, name="order-status"),
    path("api/orders/items/<int:item_id>/progress", api.order_item_progress, name="order-item-progress"),
    path("api/kitchen/menu-summary", api.kitchen_menu_summary, name="kitchen-menu-summary"),
    path("api/stats/menu-counts",   api.stats_menu_counts,    name="stats-menu-counts"),
]

from __future__ import annotations
from django.urls import path
from orders.views import pages as pages
from orders.views import api as api

app_name = "orders"

urlpatterns = [
    # 화면
    path("order/",       pages.order_page,      name="order"),
    path("b1-counter/",  pages.b1_counter_page, name="b1-counter"),
    path("f1-counter/",  pages.f1_counter_page, name="f1-counter"),
    path("kitchen/",     pages.kitchen_page,    name="kitchen"),
    path("f1-booth/",    pages.f1_booth_page,   name="f1-booth"),

    # API
    path("tables/",                 api.tables_list,          name="tables"),
    path("menus/",                  api.menus_list,           name="menus"),
    path("api/orders/",             api.orders_collection,    name="orders-collection"),
    path("api/orders/<int:order_id>/status", api.order_status, name="order-status"),
    path("api/stats/menu-counts",   api.stats_menu_counts,    name="stats-menu-counts"),
]
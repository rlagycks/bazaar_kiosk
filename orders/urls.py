from django.urls import path
from .views import pages, api, auth

urlpatterns = [
    # Pages (역할/카운터/주방/부스 등)
    path("", pages.role_select, name="role_select"),
    path("b1-counter/", pages.b1_counter, name="b1_counter"),
    path("kitchen/", pages.kitchen, name="kitchen"),
    path("kitchen/supervisor/", pages.kitchen_supervisor, name="kitchen_supervisor"),
    path("booth/", pages.booth, name="booth"),
    path("order/<int:order_id>/", pages.order, name="order_detail"),
    path("serve/", pages.serve, name="serve"),

    # Auth
    path("login/", auth.login_view, name="login"),
    path("logout/", auth.logout_view, name="logout"),

    # APIs (폴링에서 쓰던 것 + 이후 Realtime 초기 로드에 사용)
    path("api/orders/", api.orders_list, name="api_orders_list"),
    path("api/stats/menu-counts", api.menu_counts, name="api_menu_counts"),
]
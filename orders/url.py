from django.urls import path
from .views import ok_view

urlpatterns = [
    path("", ok_view, name="ok"),
]
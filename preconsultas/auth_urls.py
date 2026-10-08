from django.urls import path

from .auth_views import InternalLoginView, InternalLogoutView


app_name = "accounts"

urlpatterns = [
    path("login/", InternalLoginView.as_view(), name="login"),
    path("logout/", InternalLogoutView.as_view(), name="logout"),
]

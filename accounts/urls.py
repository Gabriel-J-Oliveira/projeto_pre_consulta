from django.urls import path
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .views import InternalLoginView, InternalLogoutView


app_name = "accounts"


@login_required
def access_denied(request):
    raise PermissionDenied

urlpatterns = [
    path("sem-acesso/", access_denied, name="access_denied"),
    path("login/", InternalLoginView.as_view(), name="login"),
    path("logout/", InternalLogoutView.as_view(), name="logout"),
]

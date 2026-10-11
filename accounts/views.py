from django.contrib.auth.forms import AuthenticationForm
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from preconsultas.permissions import default_login_destination


class InternalAuthenticationForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "Não foi possível entrar com as credenciais informadas.",
        "inactive": "Não foi possível entrar com as credenciais informadas.",
    }

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request=request, *args, **kwargs)
        self.fields["username"].label = "Usuário"
        self.fields["username"].widget.attrs.update(
            {
                "autocomplete": "username",
                "autofocus": True,
                "placeholder": "Seu usuário interno",
            }
        )
        self.fields["password"].label = "Senha"
        self.fields["password"].widget.attrs.update(
            {
                "autocomplete": "current-password",
                "placeholder": "Sua senha",
            }
        )


class InternalLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = InternalAuthenticationForm
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        if (
            request.path == reverse("admin-login")
            and request.user.is_authenticated
            and not admin.site.has_permission(request)
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_default_redirect_url(self):
        return reverse(default_login_destination(self.request.user))


class InternalLogoutView(LogoutView):
    http_method_names = ["post"]

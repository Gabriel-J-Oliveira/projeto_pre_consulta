from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView, LogoutView


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
    template_name = "preconsultas/login.html"
    authentication_form = InternalAuthenticationForm
    redirect_authenticated_user = True


class InternalLogoutView(LogoutView):
    http_method_names = ["post"]

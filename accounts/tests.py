from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from preconsultas.models import Clinic, Doctor


class AuthenticationTests(TestCase):
    username = "medico-interno-teste"
    password = "credencial-ficticia-apenas-para-testes"

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username=cls.username,
            password=cls.password,
        )
        doctor = Doctor.objects.create(
            name="Médico fictício de teste", display_registration="Registro fictício",
            user=cls.user,
        )
        doctor.clinics.add(Clinic.objects.create(name="Clínica fictícia de teste"))

    def test_internal_routes_redirect_anonymous_users_to_login(self):
        protected_routes = [
            ("get", reverse("preconsultas:dashboard")),
            ("get", reverse("preconsultas:demo")),
            ("get", reverse("recepcao:preconsultations")),
            ("post", reverse("preconsultas:add_note")),
            ("post", reverse("preconsultas:correct_item")),
            ("post", reverse("preconsultas:add_feedback")),
            (
                "get",
                reverse("preconsultas:attachment_status", args=["arquivo-ficticio"]),
            ),
            (
                "get",
                reverse("preconsultas:attachment_content", args=["arquivo-ficticio"]),
            ),
        ]
        login_url = reverse("accounts:login")

        for method, url in protected_routes:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url)
                self.assertRedirects(
                    response,
                    f"{login_url}?next={url}",
                    fetch_redirect_response=False,
                )

    def test_admin_is_protected_and_uses_internal_login_screen(self):
        response = self.client.get("/admin/")
        self.assertRedirects(
            response,
            "/admin/login/?next=/admin/",
            fetch_redirect_response=False,
        )

        login_page = self.client.get("/admin/login/?next=/admin/")
        self.assertEqual(login_page.status_code, 200)
        self.assertTemplateUsed(login_page, "accounts/login.html")
        self.assertContains(login_page, "Acesso restrito a médicos, recepção e administração")

    def test_admin_requires_an_active_staff_user_or_superuser(self):
        staff_user = get_user_model().objects.create_user(
            username="equipe-admin-teste",
            password=self.password,
            is_staff=True,
        )
        inactive_staff_user = get_user_model().objects.create_user(
            username="equipe-inativa-teste",
            password=self.password,
            is_staff=True,
            is_active=False,
        )
        superuser = get_user_model().objects.create_superuser(
            username="superusuario-teste",
            password=self.password,
        )

        for user in (self.user, inactive_staff_user):
            with self.subTest(denied_user=user.username):
                client = Client()
                client.force_login(user)
                self.assertRedirects(
                    client.get("/admin/"),
                    "/admin/login/?next=/admin/",
                    fetch_redirect_response=False,
                )

        for user in (staff_user, superuser):
            with self.subTest(allowed_user=user.username):
                client = Client()
                client.force_login(user)
                self.assertEqual(client.get("/admin/").status_code, 200)

    def test_valid_login_returns_to_requested_internal_page(self):
        destination = reverse("preconsultas:dashboard")
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": self.username,
                "password": self.password,
                "next": destination,
            },
        )

        self.assertRedirects(response, destination)
        self.assertEqual(
            int(self.client.session["_auth_user_id"]),
            self.user.pk,
        )

    def test_external_next_is_rejected(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": self.username,
                "password": self.password,
                "next": "https://example.invalid/fora-do-sistema",
            },
        )

        self.assertRedirects(response, reverse("preconsultas:dashboard"))

    def test_invalid_credentials_use_the_same_generic_error(self):
        login_url = reverse("accounts:login")
        inactive_user = get_user_model().objects.create_user(
            username="usuario-inativo-teste",
            password=self.password,
            is_active=False,
        )
        unknown_user = self.client.post(
            login_url,
            {"username": "usuario-inexistente", "password": self.password},
        )
        wrong_password = self.client.post(
            login_url,
            {"username": self.username, "password": "senha-incorreta"},
        )
        inactive_account = self.client.post(
            login_url,
            {"username": inactive_user.username, "password": self.password},
        )

        expected = ["Não foi possível entrar com as credenciais informadas."]
        for response in (unknown_user, wrong_password, inactive_account):
            with self.subTest(response=response):
                self.assertEqual(
                    list(response.context["form"].non_field_errors()),
                    expected,
                )

    def test_logout_requires_post_and_ends_the_session(self):
        self.client.force_login(self.user)
        logout_url = reverse("accounts:logout")

        for method in ("get", "options", "put", "patch", "delete"):
            with self.subTest(rejected_method=method):
                self.assertEqual(getattr(self.client, method)(logout_url).status_code, 405)
                self.assertIn("_auth_user_id", self.client.session)

        response = self.client.post(logout_url)

        self.assertRedirects(response, reverse("accounts:login"))
        self.assertNotIn("_auth_user_id", self.client.session)
        dashboard = self.client.get(reverse("preconsultas:dashboard"))
        self.assertRedirects(
            dashboard,
            f"{reverse('accounts:login')}?next={reverse('preconsultas:dashboard')}",
            fetch_redirect_response=False,
        )

    def test_login_and_logout_reject_posts_without_csrf_token(self):
        login_url = reverse("accounts:login")
        logout_url = reverse("accounts:logout")

        anonymous_client = Client(enforce_csrf_checks=True)
        login_response = anonymous_client.post(
            login_url,
            {"username": self.username, "password": self.password},
        )
        self.assertEqual(login_response.status_code, 403)

        authenticated_client = Client(enforce_csrf_checks=True)
        authenticated_client.force_login(self.user)
        logout_response = authenticated_client.post(logout_url)
        self.assertEqual(logout_response.status_code, 403)

    def test_login_and_logout_accept_valid_csrf_tokens(self):
        client = Client(enforce_csrf_checks=True)
        login_url = reverse("accounts:login")
        login_page = client.get(login_url)
        login_token = login_page.cookies["csrftoken"].value

        login_response = client.post(
            login_url,
            {"username": self.username, "password": self.password},
            HTTP_X_CSRFTOKEN=login_token,
        )
        self.assertRedirects(login_response, reverse("preconsultas:dashboard"))

        dashboard = client.get(reverse("preconsultas:dashboard"))
        logout_token = client.cookies["csrftoken"].value
        self.assertContains(dashboard, reverse("accounts:logout"))
        logout_response = client.post(
            reverse("accounts:logout"),
            HTTP_X_CSRFTOKEN=logout_token,
        )
        self.assertRedirects(logout_response, login_url)

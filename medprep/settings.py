import os
from pathlib import Path

from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def required_env(name):
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ImproperlyConfigured(
            f"Configuração obrigatória ausente: {name}. "
            "Copie .env.example para .env e preencha o valor."
        )
    return value.strip()


SECRET_KEY = required_env("DJANGO_SECRET_KEY")

debug_value = required_env("DJANGO_DEBUG").lower()
if debug_value not in {"true", "false", "1", "0", "yes", "no"}:
    raise ImproperlyConfigured("DJANGO_DEBUG deve ser True ou False.")
DEBUG = debug_value in {"true", "1", "yes"}

ALLOWED_HOSTS = [
    host.strip()
    for host in required_env("DJANGO_ALLOWED_HOSTS").split(",")
    if host.strip()
]
if "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS não pode conter '*'.")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "preconsultas",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "medprep.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "medprep.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "preconsultas:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

media_root_value = os.getenv("DEMO_MEDIA_ROOT", "demo_media")
DEMO_MEDIA_ROOT = (BASE_DIR / media_root_value).resolve()


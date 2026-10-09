import os

from django.core.exceptions import ImproperlyConfigured


def database_from_env(base_dir):
    """PostgreSQL by default; SQLite must be selected explicitly."""
    backend = os.getenv("DB_BACKEND", "postgresql").strip().lower()
    if backend == "sqlite":
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": base_dir / "db.sqlite3",
        }
    if backend != "postgresql":
        raise ImproperlyConfigured("DB_BACKEND deve ser postgresql ou sqlite.")

    def required(name):
        value = os.getenv(name)
        if value is None or not value.strip():
            raise ImproperlyConfigured(f"Configuração obrigatória ausente: {name}.")
        # Passwords may contain spaces or special characters; never normalize them.
        return value if name == "DB_PASSWORD" else value.strip()

    port = required("DB_PORT")
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ImproperlyConfigured("DB_PORT deve ser uma porta entre 1 e 65535.")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": required("DB_HOST"),
        "PORT": port,
        "NAME": required("DB_NAME"),
        "USER": required("DB_USER"),
        "PASSWORD": required("DB_PASSWORD"),
    }

import os
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from medprep.database import database_from_env


class DatabaseConfigurationTests(SimpleTestCase):
    values = {
        "DB_HOST": "127.0.0.1", "DB_PORT": "5432", "DB_NAME": "fictitious_test",
        "DB_USER": "fictitious_test", "DB_PASSWORD": " fictional password with spaces ",
    }

    def test_postgresql_is_default_and_preserves_password(self):
        with patch.dict(os.environ, self.values, clear=True):
            configuration = database_from_env(Path("."))
        self.assertEqual(configuration["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(configuration["PASSWORD"], self.values["DB_PASSWORD"])
        for name in ("HOST", "PORT", "NAME", "USER"):
            self.assertEqual(configuration[name], self.values[f"DB_{name}"])

    def test_sqlite_requires_explicit_selection_and_no_postgresql_credentials(self):
        with patch.dict(os.environ, {"DB_BACKEND": "sqlite"}, clear=True):
            configuration = database_from_env(Path("local"))
        self.assertEqual(configuration["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(configuration["NAME"], Path("local/db.sqlite3"))

    def test_missing_postgresql_configuration_fails_without_echoing_values(self):
        for name in self.values:
            values = {key: value for key, value in self.values.items() if key != name}
            with self.subTest(variable=name), patch.dict(os.environ, values, clear=True):
                with self.assertRaisesMessage(ImproperlyConfigured, name):
                    database_from_env(Path("."))

    def test_unknown_backend_and_invalid_ports_are_rejected(self):
        with patch.dict(os.environ, {"DB_BACKEND": "unsupported"}, clear=True):
            with self.assertRaisesMessage(ImproperlyConfigured, "DB_BACKEND"):
                database_from_env(Path("."))
        for port in ("abc", "0", "65536"):
            with self.subTest(port=port), patch.dict(
                os.environ, {**self.values, "DB_PORT": port}, clear=True
            ):
                with self.assertRaisesMessage(ImproperlyConfigured, "DB_PORT"):
                    database_from_env(Path("."))

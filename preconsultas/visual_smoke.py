"""Opt-in browser suite: temporary Django DB/live server, NEVER validation ports.

Run explicitly: manage.py test preconsultas.visual_smoke
Not discovered by default test*.py or added as a CI dependency.
"""
import os
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.management import call_command
from django.test import override_settings

from .models import Consultation
from .test_publication import publication_fixture

ROOT = Path(__file__).resolve().parent.parent


class MedicalVisualSmokes(StaticLiveServerTestCase):
    def browser(self, script, actor, **options):
        credential = uuid4().hex + uuid4().hex
        actor.set_password(credential)
        actor.save(update_fields=["password"])
        output = ROOT / "artifacts" / ("pr05-" + uuid4().hex)
        output.mkdir(parents=True, exist_ok=False)
        env = {**os.environ, "SMOKE_BASE_URL": self.live_server_url,
               "SMOKE_USERNAME": actor.username, "SMOKE_PASSWORD": credential,
               **options}
        result = subprocess.run([shutil.which("node"), str(ROOT / "scripts" / script)],
                                cwd=output, env=env, capture_output=True, text=True, timeout=90)
        # Existing scripts log only technical assertions/results, never credentials.
        self.assertEqual(result.returncode, 0, result.stderr)
        print(result.stdout)
        print(f"Capturas fictícias isoladas: {output}")

    def test_existing_desktop_mobile_smokes(self):
        call_command("load_demo", verbosity=0)  # This class uses a TEMPORARY test DB.
        case = Consultation.objects.get(slug="demo-pronta")
        actor = get_user_model().objects.create_user("visual-legado-ficticio")
        case.doctor.user = actor
        case.doctor.save(update_fields=["user"])
        with override_settings(DEMO_MEDIA_ROOT=str(ROOT / "artifacts" / "missing-fictitious-media")):
            self.browser("dashboard_smoke.cjs", actor)
            self.browser("browser_smoke.cjs", actor)

    def test_publication_and_review_desktop_mobile(self):
        case, _, actor, source_id, _ = publication_fixture()
        self.browser("publication_smoke.cjs", actor, SMOKE_CASE_SLUG=case.slug)

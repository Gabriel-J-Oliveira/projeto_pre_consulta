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

from .models import Clinic, Consultation, ReceptionProfile
from .ai_orchestration import execute
from .test_pre_ai_integration import completed_case
from .traceability import materialize_message

ROOT = Path(__file__).resolve().parent.parent


class MedicalVisualSmokes(StaticLiveServerTestCase):
    def browser(self, script, actor, **options):
        node = os.environ.get("SMOKE_NODE_BINARY") or shutil.which("node")
        self.assertTrue(node and Path(node).is_file(),
                        "Node indisponível; instale/configure PATH ou SMOKE_NODE_BINARY. Smoke não executado.")
        credential = uuid4().hex + uuid4().hex
        actor.set_password(credential)
        actor.save(update_fields=["password"])
        output = ROOT / "artifacts" / ("pr06-" + uuid4().hex)
        output.mkdir(parents=True, exist_ok=False)
        env = {**os.environ, "SMOKE_BASE_URL": self.live_server_url,
               "SMOKE_USERNAME": actor.username, "SMOKE_PASSWORD": credential,
               **options}
        result = subprocess.run([node, str(ROOT / "scripts" / script)],
                                cwd=output, env=env, capture_output=True, text=True, timeout=90)
        # Defense in depth if a browser failure contains form-fill diagnostics.
        stderr = result.stderr.replace(credential, "[redacted]")
        stdout = result.stdout.replace(credential, "[redacted]")
        self.assertEqual(result.returncode, 0, stderr)
        print(stdout)
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
        case, _, actor, sources, pending = completed_case()
        execute(case.pk, "build_summary", actor=actor)
        self.browser("publication_smoke.cjs", actor, SMOKE_CASE_SLUG=case.slug)
        materialize_message(case.pk, pending, actor=actor)
        self.browser("publication_smoke.cjs", actor, SMOKE_CASE_SLUG=case.slug,
                     SMOKE_EXPECT_STALE="1", SMOKE_SOURCE_KEY=case.sources.get(kind="pdf").source_key)
        self.assertEqual(case.doctor_notes.count(), 1)  # The obsolete POST must not append.

    def test_reception_permissions_admin_and_patient_choice(self):
        call_command("load_demo", verbosity=0)  # TEMPORARY test database, no live seed.
        reception = get_user_model().objects.create_user("visual-recepcao-ficticia")
        ReceptionProfile.objects.create(user=reception).clinics.add(*Clinic.objects.all())
        self.browser("reception_smoke.cjs", reception)
        self.browser("permissions_smoke.cjs", reception, SMOKE_ROLE="reception")
        admin = get_user_model().objects.create_user("visual-admin-ficticio", is_staff=True, is_superuser=True)
        self.browser("permissions_smoke.cjs", admin, SMOKE_ROLE="admin")
        case = Consultation.objects.get(slug="demo-pronta")
        self.browser("patient_registration_smoke.cjs", reception,
                     SMOKE_PATIENT_NAME=case.patient.name, SMOKE_PATIENT_PHONE=case.patient.phone,
                     SMOKE_PATIENT_ID=str(case.patient_id), SMOKE_DOCTOR_ID=str(case.doctor_id),
                     SMOKE_CLINIC_ID=str(case.clinic_id))

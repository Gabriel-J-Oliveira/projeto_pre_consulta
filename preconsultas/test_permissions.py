from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from pathlib import Path
from tempfile import TemporaryDirectory

from .demo_media import DEMO_MEDIA_FILES

from .models import (
    Clinic, Consultation, Doctor, DoctorNote, Correction, Feedback,
    Patient, ReceptionProfile, SourceItem, SummaryItem,
)


class PermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_demo", verbosity=0)
        cls.case = Consultation.objects.get(slug="demo-pronta")
        cls.doctor = cls.case.doctor
        cls.medical_user = get_user_model().objects.create_user("medico-ficticio-teste")
        cls.doctor.user = cls.medical_user
        cls.doctor.save()
        cls.other_user = get_user_model().objects.create_user("outro-medico-ficticio")
        cls.other_doctor = Doctor.objects.exclude(pk=cls.doctor.pk).get()
        cls.other_doctor.user = cls.other_user
        cls.other_doctor.save()
        cls.reception_user = get_user_model().objects.create_user("recepcao-ficticia")
        cls.profile = ReceptionProfile.objects.create(user=cls.reception_user)
        cls.profile.clinics.add(cls.case.clinic)
        cls.staff = get_user_model().objects.create_user("tecnico-ficticio", is_staff=True)
        cls.admin = get_user_model().objects.create_superuser("admin-ficticio", password=None)
        cls.unassigned = get_user_model().objects.create_user("sem-vinculo-ficticio")
        cls.pdf = cls.case.sources.filter(kind=SourceItem.KIND_PDF).first()
        cls.item = cls.case.summary_items.first()

    def medical_routes(self):
        return [
            ("get", reverse("preconsultas:demo"), {}),
            ("get", reverse("preconsultas:attachment_status", args=[self.pdf.source_key]), {}),
            ("get", reverse("preconsultas:attachment_content", args=[self.pdf.source_key]), {}),
            ("post", reverse("preconsultas:add_note"), {"text": "Nota fictícia"}),
            ("post", reverse("preconsultas:correct_item"), {
                "summary_item_id": self.item.pk, "action": "update", "new_value": "Teste fictício",
            }),
            ("post", reverse("preconsultas:add_feedback"), {"kind": "useful"}),
            ("get", reverse("preconsultas:detail", args=[self.case.slug]), {}),
            ("post", reverse("preconsultas:detail_note", args=[self.case.slug]), {"text": "Nota fictícia"}),
            ("post", reverse("preconsultas:detail_correction", args=[self.case.slug]), {
                "summary_item_id": self.item.pk, "action": "update", "new_value": "Teste",
            }),
            ("post", reverse("preconsultas:detail_feedback", args=[self.case.slug]), {"kind": "useful"}),
        ]

    def assert_medical_denied(self, user, expected):
        self.client.force_login(user)
        for method, url, data in self.medical_routes():
            with self.subTest(user=user.username, route=url):
                self.assertEqual(getattr(self.client, method)(url, data).status_code, expected)
        self.assertFalse(DoctorNote.objects.exists())
        self.assertFalse(Correction.objects.exists())
        self.assertFalse(Feedback.objects.exists())

    def test_assigned_doctor_can_open_own_ready_case(self):
        self.client.force_login(self.medical_user)
        self.assertEqual(self.client.get(reverse("preconsultas:demo")).status_code, 200)
        self.assertEqual(self.client.get(reverse("preconsultas:attachment_status", args=[self.pdf.source_key])).status_code, 200)

    def test_real_fictitious_attachment_bytes_require_assignment_and_clinic(self):
        with TemporaryDirectory() as directory, override_settings(DEMO_MEDIA_ROOT=directory):
            for source in self.case.sources.filter(kind__in=["pdf", "audio"]):
                content = b"FICTITIOUS FILE FOR AUTHORIZATION TEST ONLY"
                Path(directory, DEMO_MEDIA_FILES[source.source_key]).write_bytes(content)
                url = reverse("preconsultas:attachment_content", args=[source.source_key])
                self.client.force_login(self.medical_user)
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(b"".join(response.streaming_content), content)
                # The test client closes the response when the iterator ends.
                # Closing it again emits request_finished outside its DB guard.
                self.assertTrue(response.closed)
                for user, expected in (
                    (self.other_user, 404), (self.reception_user, 403), (self.admin, 403),
                ):
                    self.client.force_login(user)
                    self.assertEqual(self.client.get(url).status_code, expected)
            self.doctor.clinics.remove(self.case.clinic)
            self.client.force_login(self.medical_user)
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_other_doctor_cannot_open_case_or_modify_it_even_in_same_clinic(self):
        self.other_doctor.clinics.add(self.case.clinic)
        self.assert_medical_denied(self.other_user, 404)
        self.assertEqual(self.client.get(reverse("preconsultas:detail", args=[self.case.slug])).status_code, 404)
        for name in ("detail_note", "detail_correction", "detail_feedback"):
            response = self.client.post(reverse(f"preconsultas:{name}", args=[self.case.slug]), {
                "text": "Tentativa fictícia", "kind": "useful",
                "summary_item_id": self.item.pk, "action": "update", "new_value": "Teste",
            })
            self.assertEqual(response.status_code, 404)

    def test_other_doctor_can_open_own_ready_case_without_demo_identity(self):
        case = Consultation.objects.filter(doctor=self.other_doctor).get()
        case.status = Consultation.STATUS_READY
        case.save()
        self.client.force_login(self.other_user)
        detail = reverse("preconsultas:detail", args=[case.slug])
        response = self.client.get(detail)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, case.patient.name)
        self.assertNotContains(response, self.case.patient.name)
        response = self.client.get(reverse("preconsultas:dashboard"))
        self.assertContains(response, detail)
        self.assertNotContains(response, self.case.patient.name)
        note = self.client.post(reverse("preconsultas:detail_note", args=[case.slug]), {
            "text": "Nota fictícia vinculada ao outro médico",
        })
        self.assertRedirects(note, detail)
        self.assertEqual(DoctorNote.objects.get().consultation_id, case.pk)
        response = self.client.post(reverse("preconsultas:detail_correction", args=[case.slug]), {
            "summary_item_id": self.item.pk, "action": "update", "new_value": "Invasão",
        })
        self.assertEqual(response.status_code, 404)
        response = self.client.post(reverse("preconsultas:detail_feedback", args=[case.slug]), {
            "summary_item_id": self.item.pk, "kind": "useful",
        })
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Correction.objects.exists())
        self.assertFalse(Feedback.objects.exists())

    def test_non_ready_cases_remain_blocked(self):
        self.client.force_login(self.medical_user)
        case = Consultation.objects.filter(doctor=self.doctor, status=Consultation.STATUS_INCOMPLETE).get()
        self.assertEqual(self.client.get(reverse("preconsultas:detail", args=[case.slug])).status_code, 403)

    def test_assigned_doctor_without_clinic_link_cannot_open_case(self):
        self.doctor.clinics.remove(self.case.clinic)
        self.assert_medical_denied(self.medical_user, 404)
        dashboard = self.client.get(reverse("preconsultas:dashboard"))
        self.assertNotContains(dashboard, self.case.patient.name)

    def test_reception_is_scoped_and_has_no_clinical_payload(self):
        self.client.force_login(self.reception_user)
        response = self.client.get(reverse("recepcao:preconsultations"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["appointments"])
        for case in response.context["appointments"]:
            self.assertEqual(case.clinic_id, self.case.clinic_id)
        self.assertEqual(list(response.context["clinics"]), [self.case.clinic])
        for key in ("Transcrição fictícia", "Visão geral", "Ver origem", self.item.original_value):
            self.assertNotContains(response, key)
        self.assert_medical_denied(self.reception_user, 403)
        self.assertEqual(self.client.get(reverse("preconsultas:dashboard")).status_code, 403)

    def test_reception_cannot_create_in_an_unlinked_clinic(self):
        self.client.force_login(self.reception_user)
        other_clinic = Clinic.objects.exclude(pk=self.case.clinic_id).get()
        before = Consultation.objects.count()
        response = self.client.post(reverse("recepcao:preconsultations"), {
            "patient_name": "Paciente fictício bloqueado", "phone": "11988884321",
            "doctor": self.doctor.pk, "clinic": other_clinic.pk,
            "scheduled_date": "2026-10-08", "scheduled_time": "12:00",
            "appointment_type": "Teste", "contact_lead_hours": "48",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("clinic"))
        self.assertEqual(Consultation.objects.count(), before)
        self.assertFalse(Patient.objects.filter(name="Paciente fictício bloqueado").exists())
        response = self.client.get(reverse("recepcao:preconsultations"), {
            "clinica": other_clinic.pk, "selecionar": self.case.pk,
        })
        self.assertTrue(all(case.clinic_id == self.case.clinic_id for case in response.context["appointments"]))
        self.assertTrue(all(set(ids) <= {self.case.clinic_id} for ids in response.context["doctor_clinic_map"].values()))

    def test_staff_superuser_and_unassigned_users_have_no_implicit_clinical_access(self):
        for user in (self.staff, self.admin, self.unassigned):
            self.assert_medical_denied(user, 403)
            self.assertEqual(self.client.get(reverse("recepcao:preconsultations")).status_code, 403)
            self.assertEqual(self.client.get(reverse("preconsultas:dashboard")).status_code, 403)

    def test_doctor_has_no_implicit_reception_access(self):
        self.client.force_login(self.medical_user)
        self.assertEqual(self.client.get(reverse("recepcao:preconsultations")).status_code, 403)
        self.assertEqual(self.client.get("/admin/", follow=True).status_code, 403)

    def test_default_login_destination_matches_explicit_profile(self):
        for user, destination in (
            (self.medical_user, reverse("preconsultas:dashboard")),
            (self.reception_user, reverse("recepcao:preconsultations")),
            (self.admin, reverse("admin:index")),
            (self.unassigned, reverse("accounts:access_denied")),
        ):
            with self.subTest(user=user.username):
                user.set_password("credencial-ficticia-de-teste")
                user.save()
                self.client.logout()
                response = self.client.post(reverse("accounts:login"), {
                    "username": user.username, "password": "credencial-ficticia-de-teste",
                    "next": "https://example.invalid/",
                })
                self.assertRedirects(response, destination, fetch_redirect_response=False)

    def test_admin_cannot_expose_clinical_models_even_for_superuser(self):
        self.client.force_login(self.admin)
        for model in ("patient", "consultation", "sourceitem", "summaryitem", "doctornote", "correction", "feedback", "operationalevent"):
            self.assertEqual(self.client.get(f"/admin/preconsultas/{model}/").status_code, 404)
        for model in ("clinic", "doctor", "receptionprofile"):
            self.assertEqual(self.client.get(f"/admin/preconsultas/{model}/").status_code, 200)
        self.assertEqual(self.client.get("/admin/auth/user/").status_code, 200)

    def test_anonymous_users_still_redirect_to_login(self):
        for method, url, data in self.medical_routes():
            self.assertEqual(getattr(self.client, method)(url, data).status_code, 302)
        self.assertEqual(self.client.get(reverse("recepcao:preconsultations")).status_code, 302)

    def test_profile_without_any_clinic_is_denied(self):
        self.profile.clinics.clear()
        self.client.force_login(self.reception_user)
        self.assertEqual(self.client.get(reverse("recepcao:preconsultations")).status_code, 403)
        self.doctor.clinics.clear()
        self.assert_medical_denied(self.medical_user, 403)

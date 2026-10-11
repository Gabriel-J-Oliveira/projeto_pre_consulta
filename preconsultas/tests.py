from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Clinic,
    Consultation,
    Correction,
    Doctor,
    DoctorNote,
    Feedback,
    OperationalEvent,
    Patient,
    SourceItem,
    SummaryItem,
    ReceptionProfile,
)


class DemoDataMixin:
    @classmethod
    def setUpTestData(cls):
        call_command("load_demo", verbosity=0)
        cls.user = get_user_model().objects.create_user(username="usuario-interno-teste")
        doctor = Doctor.objects.get(display_registration="CRM-SP 000000 (fictício)")
        doctor.user = cls.user
        doctor.save(update_fields=["user"])

    def setUp(self):
        self.client.force_login(self.user)


class DemoPageTests(DemoDataMixin, TestCase):
    def test_named_route_is_stable_and_returns_200(self):
        url = reverse("preconsultas:demo")
        self.assertEqual(url, "/medico/pre-consultas/demo/")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_page_contains_fictitious_ready_case_and_safety_labels(self):
        response = self.client.get(reverse("preconsultas:demo"))
        self.assertContains(response, "Marina Alves (paciente fictícia)")
        self.assertContains(response, "Protótipo — dados fictícios")
        self.assertContains(response, "Perfil demonstrativo: <strong>Médico</strong>", html=True)
        self.assertContains(response, "Pronta")
        self.assertContains(response, "Transcrição fictícia de demonstração")
        self.assertContains(response, "não contém diagnóstico")

    def test_static_assets_are_discoverable(self):
        self.assertIsNotNone(finders.find("preconsultas/demo.css"))
        self.assertIsNotNone(finders.find("preconsultas/demo.js"))


class DemoSeedTests(TestCase):
    def test_load_demo_is_idempotent_and_preserves_unrelated_rows(self):
        unrelated = Clinic.objects.create(name="Outra clínica já existente")
        call_command("load_demo", verbosity=0)
        counts = (
            Consultation.objects.count(),
            SourceItem.objects.count(),
            SummaryItem.objects.count(),
        )
        call_command("load_demo", verbosity=0)
        self.assertEqual(
            counts,
            (
                Consultation.objects.count(),
                SourceItem.objects.count(),
                SummaryItem.objects.count(),
            ),
        )
        self.assertTrue(Clinic.objects.filter(pk=unrelated.pk).exists())
        self.assertEqual(SourceItem.objects.filter(kind="pdf").count(), 3)
        self.assertEqual(SourceItem.objects.filter(kind="audio").count(), 1)

    def test_reset_interactions_is_scoped_to_demo_case(self):
        call_command("load_demo", verbosity=0)
        consultation = Consultation.objects.get(slug="demo-pronta")
        item = consultation.summary_items.first()
        DoctorNote.objects.create(consultation=consultation, text="Nota de teste")
        Feedback.objects.create(consultation=consultation, kind=Feedback.KIND_USEFUL)
        Correction.objects.create(
            summary_item=item,
            action=Correction.ACTION_UPDATE,
            previous_value=item.original_value,
            new_value="Ajuste de teste",
        )
        call_command("load_demo", reset_interactions=True, verbosity=0)
        self.assertFalse(DoctorNote.objects.filter(consultation=consultation).exists())
        self.assertFalse(Feedback.objects.filter(consultation=consultation).exists())
        self.assertFalse(
            Correction.objects.filter(summary_item__consultation=consultation).exists()
        )
        self.assertEqual(consultation.sources.count(), 9)


class DemoActionTests(DemoDataMixin, TestCase):
    def test_note_post_validates_and_persists(self):
        response = self.client.post(
            reverse("preconsultas:add_note"),
            {"text": "Confirmar cronologia durante a consulta."},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DoctorNote.objects.count(), 1)

        invalid = self.client.post(
            reverse("preconsultas:add_note"),
            {"text": ""},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(invalid.status_code, 400)

    def test_correction_preserves_original_item_and_linked_source(self):
        item = SummaryItem.objects.get(item_key="medication")
        original_value = item.original_value
        source = item.sources.get()
        original_source_body = source.body

        response = self.client.post(
            reverse("preconsultas:correct_item"),
            {
                "summary_item_id": item.id,
                "action": Correction.ACTION_UPDATE,
                "new_value": "Levotiroxina 75 mcg pela manhã (ajuste demonstrativo).",
            },
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        source.refresh_from_db()
        self.assertEqual(item.original_value, original_value)
        self.assertEqual(source.body, original_source_body)
        self.assertTrue(item.sources.filter(pk=source.pk).exists())
        self.assertEqual(item.corrections.count(), 1)

    def test_hide_action_does_not_delete_source(self):
        item = SummaryItem.objects.get(item_key="history")
        source_ids = list(item.sources.values_list("id", flat=True))
        response = self.client.post(
            reverse("preconsultas:correct_item"),
            {
                "summary_item_id": item.id,
                "action": Correction.ACTION_HIDE,
                "new_value": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(SummaryItem.objects.filter(pk=item.pk).exists())
        self.assertEqual(
            list(item.sources.values_list("id", flat=True)),
            source_ids,
        )
        page = self.client.get(reverse("preconsultas:demo"))
        self.assertNotContains(page, 'aria-label="Corrigir Histórico familiar"')
        self.assertContains(page, "Remover da visualização:</strong> Histórico familiar")

    def test_feedback_post_persists(self):
        response = self.client.post(
            reverse("preconsultas:add_feedback"),
            {"kind": Feedback.KIND_USEFUL},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Feedback.objects.filter(kind=Feedback.KIND_USEFUL).exists())

    def test_posts_require_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        response = csrf_client.post(
            reverse("preconsultas:add_feedback"),
            {"kind": Feedback.KIND_USEFUL},
        )
        self.assertEqual(response.status_code, 403)


class AttachmentTests(DemoDataMixin, TestCase):
    def test_missing_pdf_has_friendly_status_and_no_broken_url(self):
        source = SourceItem.objects.get(source_key="pdf-exames-laboratoriais")
        response = self.client.get(
            reverse("preconsultas:attachment_status", args=[source.source_key])
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["available"])
        self.assertEqual(payload["url"], "")
        self.assertIn("ainda não fornecido", payload["message"])

        content = self.client.get(
            reverse("preconsultas:attachment_content", args=[source.source_key])
        )
        self.assertEqual(content.status_code, 404)


class DoctorDashboardTests(DemoDataMixin, TestCase):
    def test_named_dashboard_route_returns_200(self):
        url = reverse("preconsultas:dashboard")
        self.assertEqual(url, "/medico/painel/")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sua agenda")
        self.assertContains(response, "Protótipo — dados fictícios")

    def test_demo_schedule_has_no_duplicates_and_uses_two_clinics(self):
        self.assertEqual(Consultation.objects.filter(slug__startswith="demo-").count(), 7)
        doctor_consultations = Consultation.objects.filter(
            doctor__display_registration="CRM-SP 000000 (fictício)"
        )
        self.assertEqual(doctor_consultations.values("clinic").distinct().count(), 2)
        call_command("load_demo", verbosity=0)
        self.assertEqual(Consultation.objects.filter(slug__startswith="demo-").count(), 7)

    def test_appointments_are_ordered_by_time(self):
        response = self.client.get(reverse("preconsultas:dashboard"))
        appointments = response.context["appointments"]
        times = [item.display_scheduled_for for item in appointments]
        self.assertEqual(times, sorted(times))
        self.assertEqual([value.strftime("%H:%M") for value in times], ["09:00", "10:30", "14:30", "16:00", "17:30"])

    def test_search_filters_patient_and_has_distinct_empty_state(self):
        response = self.client.get(
            reverse("preconsultas:dashboard"),
            {"q": "Rafael"},
        )
        self.assertEqual(len(response.context["appointments"]), 1)
        self.assertEqual(response.context["appointments"][0].slug, "demo-em-andamento")

        empty = self.client.get(
            reverse("preconsultas:dashboard"),
            {"q": "Paciente inexistente"},
        )
        self.assertEqual(empty.context["empty_state"], "search")
        self.assertContains(empty, "Nenhum paciente encontrado")

    def test_date_selection_and_empty_date(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        response = self.client.get(
            reverse("preconsultas:dashboard"),
            {"data": tomorrow.isoformat()},
        )
        self.assertEqual(len(response.context["appointments"]), 1)
        self.assertEqual(response.context["appointments"][0].slug, "demo-amanha")

        empty_date = timezone.localdate() + timedelta(days=8)
        empty = self.client.get(
            reverse("preconsultas:dashboard"),
            {"data": empty_date.isoformat()},
        )
        self.assertEqual(empty.context["empty_state"], "date")
        self.assertContains(empty, "Nenhuma consulta nesta data")

    def test_clinic_filter_keeps_indicators_coherent(self):
        clinic = Clinic.objects.get(name="Centro Médico Aurora — Unidade Itaim")
        response = self.client.get(
            reverse("preconsultas:dashboard"),
            {"clinica": clinic.id},
        )
        self.assertEqual(response.context["indicators"], {"total": 2, "ready": 0, "progress": 1})
        self.assertTrue(
            all(item.clinic_id == clinic.id for item in response.context["appointments"])
        )

    def test_default_indicators_match_today(self):
        response = self.client.get(reverse("preconsultas:dashboard"))
        self.assertEqual(response.context["indicators"], {"total": 5, "ready": 1, "progress": 1})

    def test_only_ready_case_links_to_existing_preconsultation(self):
        response = self.client.get(reverse("preconsultas:dashboard"))
        ready = Consultation.objects.get(slug="demo-pronta")
        self.assertEqual(ready.summary_items.count(), 12)
        self.assertContains(response, reverse("preconsultas:demo"), count=1)
        self.assertContains(response, "Abrir pré-consulta")

        non_ready = [
            item for item in response.context["appointments"] if item.status != Consultation.STATUS_READY
        ]
        self.assertTrue(non_ready)
        self.assertTrue(all(not item.can_open for item in non_ready))
        self.assertNotContains(response, "Ver conversa")
        self.assertNotContains(response, "Abrir anexos")

    def test_dashboard_static_assets_are_discoverable(self):
        self.assertIsNotNone(finders.find("preconsultas/dashboard.css"))
        self.assertIsNotNone(finders.find("preconsultas/dashboard.js"))


class ReceptionPreconsultationTests(DemoDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Doctor.objects.filter(user=cls.user).update(user=None)
        profile = ReceptionProfile.objects.create(user=cls.user)
        profile.clinics.set(Clinic.objects.all())

    def valid_payload(self, **overrides):
        doctor = Doctor.objects.get(display_registration="CRM-SP 000000 (fictício)")
        clinic = Clinic.objects.get(name="Clínica Horizonte — Unidade Jardins")
        payload = {
            "patient_name": "Novo Paciente Fictício",
            "phone": "(11) 98888-4321",
            "doctor": doctor.id,
            "clinic": clinic.id,
            "scheduled_date": timezone.localdate().isoformat(),
            "scheduled_time": "18:30",
            "appointment_type": "Consulta demonstrativa",
            "contact_lead_hours": "48",
        }
        payload.update(overrides)
        return payload

    def test_named_reception_route_returns_200_and_lists_demo_records(self):
        url = reverse("recepcao:preconsultations")
        self.assertEqual(url, "/recepcao/pre-consultas/")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pré-consultas")
        self.assertContains(response, "Marina Alves (paciente fictícia)")
        self.assertContains(response, "(11) *****-1234")
        self.assertEqual(len(response.context["appointments"]), 6)

    def test_search_and_operational_filters(self):
        url = reverse("recepcao:preconsultations")
        search = self.client.get(url, {"q": "Paulo"})
        self.assertEqual(len(search.context["appointments"]), 1)
        self.assertEqual(search.context["appointments"][0].slug, "demo-recepcao-andre")

        doctor = Doctor.objects.get(display_registration="CRM-SP 111111 (fictício)")
        clinic = Clinic.objects.get(name="Centro Médico Aurora — Unidade Itaim")
        filtered = self.client.get(
            url,
            {
                "medico": doctor.id,
                "clinica": clinic.id,
                "estado": Consultation.STATUS_NOT_STARTED,
            },
        )
        self.assertEqual(len(filtered.context["appointments"]), 1)
        self.assertEqual(filtered.context["appointments"][0].patient.name, "Paulo Mendes (paciente fictício)")

        tomorrow = self.client.get(
            url,
            {"data": (timezone.localdate() + timedelta(days=1)).isoformat()},
        )
        self.assertEqual(len(tomorrow.context["appointments"]), 1)
        self.assertEqual(tomorrow.context["appointments"][0].slug, "demo-amanha")

    def test_valid_registration_creates_visible_initial_record(self):
        url = reverse("recepcao:preconsultations")
        response = self.client.post(url, self.valid_payload(), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pré-consulta fictícia cadastrada")
        self.assertContains(response, "Novo Paciente Fictício")
        consultation = Consultation.objects.get(patient__name="Novo Paciente Fictício")
        self.assertEqual(consultation.status, Consultation.STATUS_NOT_STARTED)
        self.assertEqual(consultation.operational_events.count(), 2)
        self.assertEqual(consultation.sources.count(), 0)
        self.assertEqual(consultation.summary_items.count(), 0)

    def test_invalid_registration_preserves_values_and_shows_errors(self):
        url = reverse("recepcao:preconsultations")
        response = self.client.post(
            url,
            self.valid_payload(phone="123", appointment_type=""),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Novo Paciente Fictício")
        self.assertContains(response, "Informe um telefone fictício")
        self.assertContains(response, "Este campo é obrigatório")
        self.assertFalse(Patient.objects.filter(name="Novo Paciente Fictício").exists())

    def test_manipulated_post_rejects_invalid_doctor_clinic_link(self):
        doctor = Doctor.objects.get(display_registration="CRM-SP 111111 (fictício)")
        invalid_clinic = Clinic.objects.get(name="Clínica Horizonte — Unidade Jardins")
        response = self.client.post(
            reverse("recepcao:preconsultations"),
            self.valid_payload(doctor=doctor.id, clinic=invalid_clinic.id),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "não está vinculada a este médico")
        self.assertFalse(Patient.objects.filter(name="Novo Paciente Fictício").exists())

    def test_reception_response_contains_no_clinical_payload(self):
        response = self.client.get(reverse("recepcao:preconsultations"))
        self.assertNotContains(response, "Visão geral")
        self.assertNotContains(response, "Transcrição fictícia")
        self.assertNotContains(response, "Ver origem")
        forbidden_keys = {"summary", "sources", "transcript", "audio", "attachments"}
        for record in response.context["records_json"]:
            self.assertTrue(forbidden_keys.isdisjoint(record.keys()))

    def test_simulated_invitation_events_are_explicit(self):
        events = OperationalEvent.objects.filter(
            kind=OperationalEvent.KIND_INVITE_SIMULATED
        )
        self.assertTrue(events.exists())
        self.assertTrue(all(event.is_simulated for event in events))
        self.assertTrue(all("nenhum WhatsApp" in event.detail for event in events))
        response = self.client.get(reverse("recepcao:preconsultations"))
        self.assertContains(response, "SIMULADO")

    def test_operational_event_seed_is_idempotent(self):
        event_count = OperationalEvent.objects.count()
        call_command("load_demo", verbosity=0)
        self.assertEqual(OperationalEvent.objects.count(), event_count)

    def test_load_demo_preserves_reception_created_record(self):
        response = self.client.post(
            reverse("recepcao:preconsultations"),
            self.valid_payload(),
        )
        self.assertEqual(response.status_code, 302)
        consultation = Consultation.objects.get(patient__name="Novo Paciente Fictício")
        call_command("load_demo", verbosity=0)
        self.assertTrue(Consultation.objects.filter(pk=consultation.pk).exists())
        self.assertEqual(OperationalEvent.objects.filter(consultation=consultation).count(), 2)

    def test_reception_post_requires_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        response = csrf_client.post(
            reverse("recepcao:preconsultations"),
            self.valid_payload(),
        )
        self.assertEqual(response.status_code, 403)

    def test_reception_static_assets_are_discoverable(self):
        self.assertIsNotNone(finders.find("preconsultas/reception.css"))
        self.assertIsNotNone(finders.find("preconsultas/reception.js"))

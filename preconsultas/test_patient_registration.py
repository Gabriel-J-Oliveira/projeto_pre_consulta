from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import ReceptionPreconsultationForm
from .models import Clinic, Consultation, Doctor, OperationalEvent, Patient, ReceptionProfile


class PatientRegistrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.clinic = Clinic.objects.create(name="Clínica fictícia autorizada")
        cls.other_clinic = Clinic.objects.create(name="Clínica fictícia externa")
        cls.doctor = Doctor.objects.create(name="Médico fictício")
        cls.doctor.clinics.add(cls.clinic, cls.other_clinic)
        cls.user = get_user_model().objects.create_user("recepcao-teste-pacientes")
        cls.profile = ReceptionProfile.objects.create(user=cls.user)
        cls.profile.clinics.add(cls.clinic)
        cls.patient = Patient.objects.create(name="Paciente Fictício", phone="(11) 98888-4321")
        cls.other_patient = Patient.objects.create(name="PACIENTE FICTÍCIO", phone="11988884321")
        for patient, clinic in [(cls.patient, cls.clinic), (cls.other_patient, cls.other_clinic)]:
            Consultation.objects.create(slug=f"teste-{patient.pk}", patient=patient,
                                        clinic=clinic, doctor=cls.doctor, scheduled_for=timezone.now(),
                                        status=Consultation.STATUS_NOT_STARTED)

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("recepcao:preconsultations")

    def payload(self, **overrides):
        payload = {
            "patient_name": "  PACIENTE   FICTÍCIO  ", "phone": "11988884321",
            "clinic": self.clinic.pk, "doctor": self.doctor.pk,
            "scheduled_date": timezone.localdate().isoformat(), "scheduled_time": "18:30",
            "appointment_type": "Consulta fictícia", "contact_lead_hours": "48",
        }
        payload.update(overrides)
        return payload

    def form(self, **overrides):
        return ReceptionPreconsultationForm(self.payload(**overrides), allowed_clinics=self.profile.clinics.all())

    def assert_counts_unchanged(self, payload):
        before = (Patient.objects.count(), Consultation.objects.count(), OperationalEvent.objects.count())
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(before, (Patient.objects.count(), Consultation.objects.count(), OperationalEvent.objects.count()))
        return response

    def test_matching_candidates_require_explicit_choice_and_are_scoped(self):
        response = self.assert_counts_unchanged(self.payload())
        self.assertEqual([p.pk for p in response.context["form"].patient_candidates], [self.patient.pk])
        self.assertContains(response, "Escolha reutilizar")
        self.assertContains(response, "Criar novo registro")
        self.assertNotContains(response, f"registro {self.other_patient.pk}</option>")

    def test_explicit_reuse_does_not_create_patient_or_change_identity(self):
        before = Patient.objects.count()
        response = self.client.post(self.url, self.payload(patient_choice=str(self.patient.pk)))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Patient.objects.count(), before)
        consultation = Consultation.objects.latest("pk")
        self.assertEqual(consultation.patient_id, self.patient.pk)
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.name, "Paciente Fictício")
        self.assertEqual(consultation.sources.count(), 0)
        self.assertEqual(consultation.summary_items.count(), 0)
        self.assertEqual(set(consultation.operational_events.values_list("kind", flat=True)),
                         {OperationalEvent.KIND_CREATED, OperationalEvent.KIND_INVITE_PLANNED})
        response = self.client.get(response.url)
        self.assertContains(response, "Nenhum convite foi enviado")
        self.assertNotContains(response, "Transcrição fictícia")
        self.assertNotContains(response, "Ver origem")

    def test_create_new_even_with_matching_candidate(self):
        before = Patient.objects.count()
        response = self.client.post(self.url, self.payload(patient_choice="new"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Patient.objects.count(), before + 1)
        self.assertNotEqual(Consultation.objects.latest("pk").patient_id, self.patient.pk)

    def test_no_candidate_creates_new_patient(self):
        before = Patient.objects.count()
        response = self.client.post(self.url, self.payload(patient_name="Outra pessoa fictícia", phone="11977774321"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Patient.objects.count(), before + 1)

    def test_phone_alone_never_reuses_patient(self):
        response = self.client.post(self.url, self.payload(patient_name="Nome diferente fictício"))
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(Consultation.objects.latest("pk").patient_id, self.patient.pk)

    def test_matching_patient_without_authorized_consultation_is_not_a_candidate(self):
        unlinked = Patient.objects.create(name="Sem consulta fictícia", phone="11977774321")
        form = self.form(patient_name=unlinked.name, phone=unlinked.phone)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.patient_candidates, [])
        self.assertNotEqual(form.save().patient_id, unlinked.pk)

    def test_invalid_form_cannot_be_saved_directly(self):
        form = self.form(phone="123")
        self.assertFalse(form.is_valid())
        before = (Patient.objects.count(), Consultation.objects.count())
        with self.assertRaises(ValueError):
            form.save()
        self.assertEqual((Patient.objects.count(), Consultation.objects.count()), before)

    def test_same_name_with_different_phone_never_reuses(self):
        response = self.client.post(self.url, self.payload(phone="11977774321"))
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(Consultation.objects.latest("pk").patient_id, self.patient.pk)

    def test_forged_external_patient_is_rejected(self):
        self.assert_counts_unchanged(self.payload(patient_choice=str(self.other_patient.pk)))

    def test_forged_selection_with_changed_identity_is_rejected(self):
        self.assert_counts_unchanged(self.payload(patient_name="Diferente fictício", patient_choice=str(self.patient.pk)))

    def test_invalid_input_creates_no_patient_consultation_or_event(self):
        for overrides in ({"phone": "123"}, {"clinic": self.other_clinic.pk},
                          {"appointment_type": ""}, {"scheduled_date": "inválida"}):
            with self.subTest(overrides=overrides):
                self.assert_counts_unchanged(self.payload(patient_choice="new", **overrides))

    def test_multiple_candidates_are_preserved_without_merging(self):
        duplicate = Patient.objects.create(name="paciente fictício", phone="11988884321")
        Consultation.objects.create(slug="duplicate-ficticio", patient=duplicate, clinic=self.clinic,
                                    doctor=self.doctor, scheduled_for=timezone.now(),
                                    status=Consultation.STATUS_NOT_STARTED)
        form = self.form(patient_choice=str(duplicate.pk))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual([p.pk for p in form.patient_candidates], [self.patient.pk, duplicate.pk])
        self.assertEqual(form.save().patient_id, duplicate.pk)

    def test_scope_is_rechecked_before_saving(self):
        form = self.form(patient_choice=str(self.patient.pk))
        self.assertTrue(form.is_valid(), form.errors)
        self.profile.clinics.clear()
        before = Consultation.objects.count()
        with self.assertRaises(ValidationError):
            form.save()
        self.assertEqual(Consultation.objects.count(), before)

    def test_new_patient_rolls_back_if_consultation_creation_fails(self):
        form = self.form(patient_name="Novo fictício")
        self.assertTrue(form.is_valid(), form.errors)
        before = Patient.objects.count()
        with patch("preconsultas.forms.Consultation.objects.create", side_effect=IntegrityError):
            with self.assertRaises(IntegrityError):
                form.save()
        self.assertEqual(Patient.objects.count(), before)

    def test_new_patient_and_consultation_roll_back_if_event_creation_fails(self):
        form = self.form(patient_name="Novo fictício")
        self.assertTrue(form.is_valid(), form.errors)
        before = (Patient.objects.count(), Consultation.objects.count())
        with patch("preconsultas.forms.OperationalEvent.objects.create", side_effect=IntegrityError):
            with self.assertRaises(IntegrityError):
                form.save()
        self.assertEqual((Patient.objects.count(), Consultation.objects.count()), before)

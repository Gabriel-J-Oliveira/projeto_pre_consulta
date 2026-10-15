from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .consent import record_simulated_consent
from .models import Clinic, ConsentEvidence, Consultation, Doctor, OperationalEvent, Patient, ReceptionProfile
from .state_engine import ALLOWED_TRANSITIONS, InvalidTransition, transition


class StateEngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.clinic = Clinic.objects.create(name="Clínica de estados fictícia")
        cls.other_clinic = Clinic.objects.create(name="Outra clínica fictícia")
        cls.doctor_user = get_user_model().objects.create_user("medico-estados-ficticio")
        cls.doctor = Doctor.objects.create(name="Médico fictício", user=cls.doctor_user)
        cls.doctor.clinics.add(cls.clinic)
        cls.other_doctor = Doctor.objects.create(name="Outro médico fictício")
        cls.other_doctor.clinics.add(cls.clinic, cls.other_clinic)
        cls.reception = get_user_model().objects.create_user("recepcao-estados-ficticia")
        profile = ReceptionProfile.objects.create(user=cls.reception)
        profile.clinics.add(cls.clinic)
        cls.admin = get_user_model().objects.create_superuser("admin-estados-ficticio", password=None)
        cls.unassigned = get_user_model().objects.create_user("sem-perfil-estados")
        cls.patient = Patient.objects.create(name="Paciente de estados fictício", phone="11900000000")
        cls.case = Consultation.objects.create(
            slug="estados-ficticio", patient=cls.patient, doctor=cls.doctor,
            clinic=cls.clinic, scheduled_for=timezone.now(),
            status=Consultation.STATUS_NOT_STARTED,
        )
        cls.other_case = Consultation.objects.create(
            slug="estados-externo-ficticio", patient=cls.patient, doctor=cls.other_doctor,
            clinic=cls.other_clinic, scheduled_for=timezone.now(),
            status=Consultation.STATUS_NOT_STARTED,
        )

    def assert_unchanged(self, case, status, event_count):
        case.refresh_from_db()
        self.assertEqual(case.status, status)
        self.assertEqual(OperationalEvent.objects.count(), event_count)

    def test_complete_explicit_simulation_records_each_transition(self):
        before = timezone.now()
        path = [Consultation.STATUS_AWAITING_CONSENT, Consultation.STATUS_IN_PROGRESS,
                Consultation.STATUS_AWAITING_PATIENT, Consultation.STATUS_COMPLETED]
        previous = self.case.status
        for target in path:
            if target == Consultation.STATUS_IN_PROGRESS:
                record_simulated_consent(self.case.pk, term_version="sim-v1",
                                         manifestation=ConsentEvidence.ACCEPTED, actor=self.reception)
            consultation = transition(self.case.pk, target, actor=self.reception, consent_version="sim-v1")
            self.assertEqual(consultation.status, target)
            self.case.refresh_from_db()
            self.assertEqual(self.case.status, target)
            event = self.case.operational_events.latest("pk")
            self.assertEqual(event.kind, OperationalEvent.KIND_STATE_CHANGED)
            self.assertEqual((event.previous_status, event.next_status), (previous, target))
            self.assertEqual(event.actor_id, self.reception.pk)
            self.assertEqual(event.origin, "local_simulation")
            self.assertTrue(event.is_simulated)
            self.assertGreaterEqual(event.occurred_at, before)
            self.assertLessEqual(event.occurred_at, timezone.now())
            previous = target
        self.assertEqual(self.case.operational_events.count(), 5)
        self.assertEqual(self.case.sources.count(), 0)
        self.assertEqual(self.case.summary_items.count(), 0)

    def test_transition_matrix_accepts_exactly_the_declared_edges(self):
        for source, destinations in ALLOWED_TRANSITIONS.items():
            for target in [*ALLOWED_TRANSITIONS, "unknown"]:
                with self.subTest(source=source, target=target):
                    # Fixture setup only; production transitions go through the service.
                    Consultation.objects.filter(pk=self.case.pk).update(status=source)
                    self.case.consent_evidence.all().delete()  # Test fixture, not domain API.
                    if source == Consultation.STATUS_AWAITING_CONSENT and target in {
                        Consultation.STATUS_IN_PROGRESS, Consultation.STATUS_CONSENT_DECLINED,
                    }:
                        event = OperationalEvent.objects.create(
                            consultation=self.case, event_key=f"matrix-{source}-{target}",
                            kind=OperationalEvent.KIND_CONSENT_RECORDED, occurred_at=timezone.now(),
                            detail="Fixture simulada.", is_simulated=True, origin="local_simulation",
                            actor=self.doctor_user,
                        )
                        ConsentEvidence.objects.create(
                            consultation=self.case, term_version="sim-v1", operator=self.doctor_user,
                            occurred_at=event.occurred_at, event=event,
                            manifestation=(ConsentEvidence.ACCEPTED if target == Consultation.STATUS_IN_PROGRESS
                                           else ConsentEvidence.DECLINED),
                        )
                    count = OperationalEvent.objects.count()
                    if target in destinations:
                        transition(self.case.pk, target, actor=self.doctor_user, consent_version="sim-v1")
                        self.assert_unchanged(self.case, target, count + 1)
                    else:
                        with self.assertRaises(InvalidTransition):
                            transition(self.case.pk, target, actor=self.doctor_user)
                        self.assert_unchanged(self.case, source, count)

    def test_transition_does_not_release_clinical_access(self):
        self.client.force_login(self.doctor_user)
        url = reverse("preconsultas:detail", args=[self.case.slug])
        for state in [Consultation.STATUS_AWAITING_CONSENT, Consultation.STATUS_IN_PROGRESS,
                      Consultation.STATUS_AWAITING_PATIENT, Consultation.STATUS_COMPLETED]:
            if state == Consultation.STATUS_IN_PROGRESS:
                record_simulated_consent(self.case.pk, term_version="sim-v1",
                                         manifestation=ConsentEvidence.ACCEPTED, actor=self.reception)
            transition(self.case.pk, state, actor=self.reception, consent_version="sim-v1")
            self.assertEqual(self.client.get(url).status_code, 403)
            dashboard = self.client.get(reverse("preconsultas:dashboard"))
            self.assertEqual(dashboard.status_code, 200)
            self.assertFalse(dashboard.context["appointments"][0].can_open)
            self.client.force_login(self.reception)
            operational = self.client.get(reverse("recepcao:preconsultations"))
            self.assertEqual(operational.status_code, 200)
            events = operational.context["records_json"][0]["events"]
            self.assertIn("Nenhum serviço externo acionado", events[-1]["detail"])
            self.assertNotContains(operational, "summary_items")
            self.assertEqual(self.client.get(url).status_code, 403)
            self.client.force_login(self.doctor_user)

    def test_other_clinic_and_nonexistent_ids_are_denied_without_change(self):
        for actor in [self.reception, self.doctor_user]:
            for pk in [self.other_case.pk, 999999]:
                with self.subTest(actor=actor.pk, pk=pk):
                    with self.assertRaises(PermissionDenied):
                        transition(pk, Consultation.STATUS_AWAITING_CONSENT, actor=actor)
        self.assert_unchanged(self.other_case, Consultation.STATUS_NOT_STARTED, 0)

    def test_doctor_cannot_modify_another_doctors_case_in_same_clinic(self):
        self.other_case.clinic = self.clinic
        self.other_case.save(update_fields=["clinic"])
        with self.assertRaises(PermissionDenied):
            transition(self.other_case.pk, Consultation.STATUS_AWAITING_CONSENT, actor=self.doctor_user)
        self.assert_unchanged(self.other_case, Consultation.STATUS_NOT_STARTED, 0)

    def test_doctor_clinic_membership_is_required(self):
        self.doctor.clinics.clear()
        with self.assertRaises(PermissionDenied):
            transition(self.case.pk, Consultation.STATUS_AWAITING_CONSENT, actor=self.doctor_user)
        self.assert_unchanged(self.case, Consultation.STATUS_NOT_STARTED, 0)

    def test_inactive_anonymous_unassigned_and_technical_admin_are_denied(self):
        self.reception.is_active = False
        self.reception.save(update_fields=["is_active"])
        for actor in [self.reception, self.admin, self.unassigned, AnonymousUser(), None]:
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    transition(self.case.pk, Consultation.STATUS_AWAITING_CONSENT, actor=actor)
        self.assert_unchanged(self.case, Consultation.STATUS_NOT_STARTED, 0)

    def test_unknown_origin_cannot_be_recorded_as_real_consent_or_service(self):
        for origin in ["whatsapp", "llm", "patient", "", None]:
            with self.subTest(origin=origin):
                with self.assertRaises(ValidationError):
                    transition(self.case.pk, Consultation.STATUS_AWAITING_CONSENT,
                               actor=self.reception, origin=origin)
        self.assert_unchanged(self.case, Consultation.STATUS_NOT_STARTED, 0)

    def test_event_failure_rolls_back_state(self):
        with patch("preconsultas.state_engine.OperationalEvent.objects.create", side_effect=IntegrityError):
            with self.assertRaises(IntegrityError):
                transition(self.case.pk, Consultation.STATUS_AWAITING_CONSENT, actor=self.reception)
        self.assert_unchanged(self.case, Consultation.STATUS_NOT_STARTED, 0)

    def test_stale_update_produces_no_event(self):
        with patch("django.db.models.query.QuerySet.update", return_value=0):
            with self.assertRaises(InvalidTransition):
                transition(self.case.pk, Consultation.STATUS_AWAITING_CONSENT, actor=self.reception)
        self.assert_unchanged(self.case, Consultation.STATUS_NOT_STARTED, 0)

    def test_legacy_ready_remains_visible_and_no_transition_can_create_it(self):
        Consultation.objects.filter(pk=self.case.pk).update(status=Consultation.STATUS_READY, legacy_demo=True)
        self.client.force_login(self.doctor_user)
        response = self.client.get(reverse("preconsultas:detail", args=[self.case.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(Consultation.STATUS_READY not in targets for targets in ALLOWED_TRANSITIONS.values()))
        self.assertEqual(ALLOWED_TRANSITIONS[Consultation.STATUS_READY], frozenset())

    def test_existing_event_without_new_metadata_remains_supported(self):
        event = OperationalEvent.objects.create(
            consultation=self.case, event_key="legacy-ficticio", kind=OperationalEvent.KIND_CREATED,
            occurred_at=timezone.now(), detail="Registro fictício legado.",
        )
        self.assertEqual(event.origin, "")
        self.assertIsNone(event.actor_id)
        self.assertEqual(event.previous_status, "")

    def test_state_event_keeps_real_time_even_for_relative_demo_dates(self):
        from datetime import timedelta
        from .views import _decorate_appointment, _decorate_operational_events

        self.case.scheduled_for = timezone.now() - timedelta(days=3)
        self.case.demo_day_offset = 0
        self.case.save(update_fields=["scheduled_for", "demo_day_offset"])
        consultation = transition(self.case.pk, Consultation.STATUS_AWAITING_CONSENT, actor=self.reception)
        _decorate_appointment(consultation)
        _decorate_operational_events(consultation)
        event = consultation.display_events[0]
        self.assertEqual(event.display_occurred_at, timezone.localtime(event.occurred_at))

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from .consent import record_simulated_consent
from .models import Clinic, ConsentEvidence, Consultation, Doctor, OperationalEvent, Patient, ReceptionProfile
from .state_engine import InvalidTransition, transition


def create_fixture():
    clinic = Clinic.objects.create(name="Clínica fictícia de consentimento")
    actor = get_user_model().objects.create_user("operador-consentimento-ficticio")
    profile = ReceptionProfile.objects.create(user=actor)
    profile.clinics.add(clinic)
    doctor = Doctor.objects.create(name="Médico fictício")
    doctor.clinics.add(clinic)
    patient = Patient.objects.create(name="Paciente fictício", phone="11900000000")
    case = Consultation.objects.create(
        slug="consentimento-ficticio", patient=patient, doctor=doctor, clinic=clinic,
        scheduled_for=timezone.now(), status=Consultation.STATUS_AWAITING_CONSENT,
    )
    return case, actor


class ConsentTests(TestCase):
    def setUp(self):
        self.case, self.actor = create_fixture()

    def record(self, version="sim-v1", manifestation=ConsentEvidence.ACCEPTED, **kwargs):
        return record_simulated_consent(self.case.pk, term_version=version,
                                        manifestation=manifestation, actor=kwargs.pop("actor", self.actor),
                                        **kwargs)

    def assert_counts(self, evidence, events, status=Consultation.STATUS_AWAITING_CONSENT):
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, status)
        self.assertEqual(ConsentEvidence.objects.count(), evidence)
        self.assertEqual(OperationalEvent.objects.count(), events)

    def test_acceptance_records_version_operator_origin_time_and_audit(self):
        before = timezone.now()
        evidence = self.record()
        self.assert_counts(1, 1)
        self.assertEqual(evidence.consultation_id, self.case.pk)
        self.assertEqual(evidence.term_version, "sim-v1")
        self.assertEqual(evidence.manifestation, ConsentEvidence.ACCEPTED)
        self.assertEqual(evidence.operator_id, self.actor.pk)
        self.assertTrue(evidence.is_simulated)
        self.assertEqual(evidence.origin, "local_simulation")
        self.assertGreaterEqual(evidence.occurred_at, before)
        self.assertEqual(evidence.event.occurred_at, evidence.occurred_at)
        self.assertEqual(evidence.event.actor_id, self.actor.pk)
        self.assertEqual(evidence.event.consultation_id, self.case.pk)
        self.assertTrue(evidence.event.is_simulated)
        self.assertIn("não é prova real", evidence.event.detail)
        transition(self.case.pk, Consultation.STATUS_IN_PROGRESS, actor=self.actor, consent_version="sim-v1")
        self.assert_counts(1, 2, Consultation.STATUS_IN_PROGRESS)

    def test_absent_missing_or_wrong_version_blocks_collection_without_events(self):
        with self.assertRaises(InvalidTransition):
            transition(self.case.pk, Consultation.STATUS_IN_PROGRESS, actor=self.actor, consent_version="sim-v1")
        self.assert_counts(0, 0)
        self.record()
        for version in [None, "", "outro-termo", " sim-v1 "]:
            with self.subTest(version=version), self.assertRaises(InvalidTransition):
                transition(self.case.pk, Consultation.STATUS_IN_PROGRESS, actor=self.actor, consent_version=version)
        self.assert_counts(1, 1)

    def test_versions_append_history_and_old_acceptance_cannot_start_collection(self):
        first = self.record()
        second = self.record("sim-v2")
        first.refresh_from_db()
        self.assertEqual(first.term_version, "sim-v1")
        self.assertNotEqual(first.event_id, second.event_id)
        self.assert_counts(2, 2)
        with self.assertRaises(InvalidTransition):
            transition(self.case.pk, Consultation.STATUS_IN_PROGRESS, actor=self.actor, consent_version="sim-v1")
        transition(self.case.pk, Consultation.STATUS_IN_PROGRESS, actor=self.actor, consent_version="sim-v2")
        self.assert_counts(2, 3, Consultation.STATUS_IN_PROGRESS)

    def test_duplicate_or_reversed_manifestation_is_rejected_without_overwrite(self):
        evidence = self.record()
        for manifestation in [ConsentEvidence.ACCEPTED, ConsentEvidence.DECLINED]:
            with self.assertRaises(ValidationError):
                self.record(manifestation=manifestation)
        evidence.refresh_from_db()
        self.assertEqual(evidence.manifestation, ConsentEvidence.ACCEPTED)
        self.assert_counts(1, 1)

    def test_refusal_atomically_ends_flow_and_prevents_old_acceptance(self):
        self.record()
        evidence = self.record("sim-v2", ConsentEvidence.DECLINED)
        self.assertEqual(evidence.manifestation, ConsentEvidence.DECLINED)
        self.assert_counts(2, 3, Consultation.STATUS_CONSENT_DECLINED)
        for target in [Consultation.STATUS_IN_PROGRESS, Consultation.STATUS_AWAITING_CONSENT,
                       Consultation.STATUS_CANCELLED, Consultation.STATUS_READY]:
            with self.assertRaises(InvalidTransition):
                transition(self.case.pk, target, actor=self.actor, consent_version="sim-v1")
        with self.assertRaises(InvalidTransition):
            self.record("sim-v3")
        self.assert_counts(2, 3, Consultation.STATUS_CONSENT_DECLINED)

    def test_direct_refusal_requires_evidence(self):
        with self.assertRaises(InvalidTransition):
            transition(self.case.pk, Consultation.STATUS_CONSENT_DECLINED, actor=self.actor,
                       consent_version="sim-v1")
        self.assert_counts(0, 0)

    def test_invalid_input_and_origin_do_not_write(self):
        for version in [None, "", " ", "v" * 81, " v1", "v1\n", "v\x00"]:
            with self.subTest(version=version), self.assertRaises(ValidationError):
                self.record(version)
        for manifestation in [None, "", "real", "ACCEPTED"]:
            with self.assertRaises(ValidationError):
                self.record(manifestation=manifestation)
        for origin in [None, "", "patient", "whatsapp", "local_simulation "]:
            with self.assertRaises(ValidationError):
                self.record(origin=origin)
        self.assert_counts(0, 0)

    def test_anonymous_unassigned_inactive_and_technical_admin_denied(self):
        inactive = get_user_model().objects.create_user("inativo-ficticio", is_active=False)
        profile = ReceptionProfile.objects.create(user=inactive)
        profile.clinics.add(self.case.clinic)
        actors = [AnonymousUser(), None, inactive,
                  get_user_model().objects.create_user("sem-vinculo-ficticio"),
                  get_user_model().objects.create_superuser("admin-consentimento-ficticio", password=None)]
        for actor in actors:
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                self.record(actor=actor)
        self.assert_counts(0, 0)

    def test_outside_clinic_or_nonexistent_consultation_denied(self):
        self.actor.reception_profile.clinics.clear()
        for pk in [self.case.pk, 999999]:
            with self.assertRaises(PermissionDenied):
                record_simulated_consent(pk, term_version="sim-v1", manifestation=ConsentEvidence.ACCEPTED,
                                         actor=self.actor)
        self.assert_counts(0, 0)

    def test_doctor_requires_assignment_and_clinic(self):
        doctor_actor = get_user_model().objects.create_user("medico-consentimento-ficticio")
        self.case.doctor.user = doctor_actor
        self.case.doctor.save(update_fields=["user"])
        self.record(actor=doctor_actor)
        self.case.doctor.clinics.clear()
        with self.assertRaises(PermissionDenied):
            self.record("sim-v2", actor=doctor_actor)
        self.case.doctor.clinics.add(self.case.clinic)
        other = Doctor.objects.create(name="Outro médico fictício")
        other.clinics.add(self.case.clinic)
        self.case.doctor = other
        self.case.save(update_fields=["doctor"])
        with self.assertRaises(PermissionDenied):
            self.record("sim-v2", actor=doctor_actor)
        self.assert_counts(1, 1)

    def test_evidence_from_other_consultation_never_satisfies_gate(self):
        self.record()
        other = Consultation.objects.create(
            slug="outra-consulta-ficticia", patient=self.case.patient, doctor=self.case.doctor,
            clinic=self.case.clinic, scheduled_for=timezone.now(), status=Consultation.STATUS_AWAITING_CONSENT,
        )
        with self.assertRaises(InvalidTransition):
            transition(other.pk, Consultation.STATUS_IN_PROGRESS, actor=self.actor, consent_version="sim-v1")
        other.refresh_from_db()
        self.assertEqual(other.status, Consultation.STATUS_AWAITING_CONSENT)

    def test_inconsistent_audit_or_declined_evidence_cannot_start_collection(self):
        evidence = self.record()
        original_actor = evidence.event.actor_id
        for updates in [{"is_simulated": False}, {"origin": "patient"},
                        {"kind": OperationalEvent.KIND_CREATED}, {"actor_id": None}]:
            with self.subTest(updates=updates):
                OperationalEvent.objects.filter(pk=evidence.event_id).update(**updates)
                with self.assertRaises(InvalidTransition):
                    transition(self.case.pk, Consultation.STATUS_IN_PROGRESS, actor=self.actor,
                               consent_version="sim-v1")
                OperationalEvent.objects.filter(pk=evidence.event_id).update(
                    is_simulated=True, origin="local_simulation", kind=OperationalEvent.KIND_CONSENT_RECORDED,
                    actor_id=original_actor,
                )
        ConsentEvidence.objects.filter(pk=evidence.pk).update(manifestation=ConsentEvidence.DECLINED)
        with self.assertRaises(InvalidTransition):
            transition(self.case.pk, Consultation.STATUS_IN_PROGRESS, actor=self.actor, consent_version="sim-v1")
        self.assert_counts(1, 1)

    def test_only_awaiting_consent_accepts_records_and_terminal_states_stay_closed(self):
        for state, _ in Consultation.STATUS_CHOICES:
            if state == Consultation.STATUS_AWAITING_CONSENT:
                continue
            Consultation.objects.filter(pk=self.case.pk).update(status=state)  # Fixture only.
            with self.subTest(state=state), self.assertRaises(InvalidTransition):
                self.record()
        self.assertEqual(ConsentEvidence.objects.count(), 0)
        self.assertEqual(OperationalEvent.objects.count(), 0)

    def test_failure_in_consent_event_or_evidence_rolls_back_everything(self):
        for method in ["preconsultas.consent.OperationalEvent.objects.create",
                       "preconsultas.consent.ConsentEvidence.objects.create"]:
            with patch(method, side_effect=IntegrityError), self.assertRaises(IntegrityError):
                self.record()
            self.assert_counts(0, 0)

    def test_refusal_state_event_failure_rolls_back_evidence_and_both_events(self):
        real_create = OperationalEvent.objects.create

        def fail_state_event(**kwargs):
            if kwargs["kind"] == OperationalEvent.KIND_STATE_CHANGED:
                raise IntegrityError("Falha fictícia de auditoria")
            return real_create(**kwargs)

        with patch("preconsultas.state_engine.OperationalEvent.objects.create", side_effect=fail_state_event):
            with self.assertRaises(IntegrityError):
                self.record(manifestation=ConsentEvidence.DECLINED)
        self.assert_counts(0, 0)

    def test_model_preserves_evidence_and_database_constraints(self):
        evidence = self.record()
        evidence.term_version = "alterada"
        with self.assertRaises(ValidationError):
            evidence.save()
        with self.assertRaises(ValidationError):
            evidence.delete()
        for updates in [{"is_simulated": False}, {"origin": "patient"},
                        {"manifestation": "invalid"}, {"term_version": ""}]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                ConsentEvidence.objects.filter(pk=evidence.pk).update(**updates)
        evidence.refresh_from_db()
        self.assertEqual(evidence.term_version, "sim-v1")

    def test_clinical_access_remains_denied_and_consent_is_not_in_admin(self):
        self.record()
        transition(self.case.pk, Consultation.STATUS_IN_PROGRESS, actor=self.actor, consent_version="sim-v1")
        transition(self.case.pk, Consultation.STATUS_AWAITING_PATIENT, actor=self.actor)
        transition(self.case.pk, Consultation.STATUS_COMPLETED, actor=self.actor)
        self.assert_counts(1, 4, Consultation.STATUS_COMPLETED)
        self.client.force_login(self.actor)
        self.assertEqual(self.client.get(reverse("preconsultas:detail", args=[self.case.slug])).status_code, 403)
        operational = self.client.get(reverse("recepcao:preconsultations"))
        self.assertEqual(operational.status_code, 200)
        self.assertNotContains(operational, "summary_items")
        self.assertFalse(admin.site.is_registered(ConsentEvidence))

    def test_audit_time_not_shifted_by_demonstrative_schedule(self):
        from datetime import timedelta
        from .views import _decorate_appointment, _decorate_operational_events

        self.case.scheduled_for -= timedelta(days=3)
        self.case.demo_day_offset = 0
        self.case.save(update_fields=["scheduled_for", "demo_day_offset"])
        evidence = self.record()
        _decorate_appointment(self.case)
        _decorate_operational_events(self.case)
        self.assertEqual(self.case.display_events[0].display_occurred_at,
                         timezone.localtime(evidence.occurred_at))

    def test_load_demo_remains_idempotent_without_inventing_consent(self):
        # Test DB only, never the preserved validation database.
        self.record()
        call_command("load_demo", verbosity=0)
        count = Consultation.objects.count()
        call_command("load_demo", verbosity=0)
        self.assertEqual(Consultation.objects.count(), count)
        self.assertEqual(ConsentEvidence.objects.count(), 1)
        self.assertFalse(ConsentEvidence.objects.exclude(consultation=self.case).exists())


class ConsentConcurrencyTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_parallel_same_version_is_serialized(self):
        case, actor = create_fixture()
        barrier = Barrier(2)

        def worker():
            try:
                local_actor = get_user_model().objects.get(pk=actor.pk)
                barrier.wait(timeout=10)
                try:
                    record_simulated_consent(case.pk, term_version="sim-v1",
                                             manifestation=ConsentEvidence.ACCEPTED, actor=local_actor)
                    return "recorded"
                except ValidationError:
                    return "rejected"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker) for _ in range(2)]
            results = [future.result(timeout=20) for future in futures]
        self.assertCountEqual(results, ["recorded", "rejected"])
        self.assertEqual(ConsentEvidence.objects.count(), 1)
        self.assertEqual(OperationalEvent.objects.count(), 1)

    @skipUnlessDBFeature("has_select_for_update")
    def test_parallel_collection_starts_create_one_state_event(self):
        case, actor = create_fixture()
        record_simulated_consent(case.pk, term_version="sim-v1",
                                 manifestation=ConsentEvidence.ACCEPTED, actor=actor)
        barrier = Barrier(2)

        def worker():
            try:
                local_actor = get_user_model().objects.get(pk=actor.pk)
                barrier.wait(timeout=10)
                try:
                    transition(case.pk, Consultation.STATUS_IN_PROGRESS, actor=local_actor,
                               consent_version="sim-v1")
                    return "started"
                except InvalidTransition:
                    return "rejected"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker) for _ in range(2)]
            results = [future.result(timeout=20) for future in futures]
        self.assertCountEqual(results, ["started", "rejected"])
        case.refresh_from_db()
        self.assertEqual(case.status, Consultation.STATUS_IN_PROGRESS)
        self.assertEqual(OperationalEvent.objects.filter(kind=OperationalEvent.KIND_STATE_CHANGED).count(), 1)


class ConsentMigrationTests(TransactionTestCase):
    def test_additive_migration_keeps_legacy_states_and_events_without_consent(self):
        connection = connections["default"]
        before = [("preconsultas", "0005_operational_state_engine")]
        after = [("preconsultas", "0006_simulated_consent_evidence")]
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        try:
            old = executor.loader.project_state(before).apps
            clinic = old.get_model("preconsultas", "Clinic").objects.create(name="Clínica legada fictícia")
            doctor = old.get_model("preconsultas", "Doctor").objects.create(name="Médico legado fictício")
            patient = old.get_model("preconsultas", "Patient").objects.create(name="Paciente legado fictício")
            for state in ["ready", "in_progress", "consent_declined"]:
                case = old.get_model("preconsultas", "Consultation").objects.create(
                    slug=f"legado-{state}", doctor=doctor, patient=patient, clinic=clinic,
                    scheduled_for=timezone.now(), status=state,
                )
                old.get_model("preconsultas", "OperationalEvent").objects.create(
                    consultation=case, event_key=f"evento-{state}", kind="created",
                    occurred_at=timezone.now(), detail="Fixture legada fictícia.",
                )
        finally:
            MigrationExecutor(connection).migrate(after)
        self.assertCountEqual(Consultation.objects.values_list("status", flat=True),
                              ["ready", "in_progress", "consent_declined"])
        self.assertEqual(OperationalEvent.objects.count(), 3)
        self.assertEqual(OperationalEvent.objects.filter(actor__isnull=True, origin="").count(), 3)
        self.assertFalse(ConsentEvidence.objects.exists())

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
from threading import Barrier
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from .consent import record_simulated_consent
from .ingestion import IngestionPersistenceError, InvalidEnvelope, ingest_message
from .ingestion_simulator import run_simulation, simulation_envelopes
from .models import (
    Clinic, ConsentEvidence, Consultation, Doctor, InboundMessage,
    OperationalEvent, ReceptionProfile, SourceItem, SummaryItem,
)
from .state_engine import InvalidTransition, transition
from .test_consent import create_fixture


def collecting_fixture():
    case, actor = create_fixture()
    record_simulated_consent(case.pk, term_version="sim-v1",
                             manifestation=ConsentEvidence.ACCEPTED, actor=actor)
    transition(case.pk, Consultation.STATUS_IN_PROGRESS, actor=actor, consent_version="sim-v1")
    return case, actor


class IngestionTests(TestCase):
    def setUp(self):
        self.case, self.actor = collecting_fixture()
        self.payload = simulation_envelopes(self.case.pk)[0]
        self.events_before = OperationalEvent.objects.count()

    def ingest(self, **updates):
        return ingest_message({**self.payload, **updates}, actor=self.actor)

    def assert_no_side_effects(self, messages=0):
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, Consultation.STATUS_IN_PROGRESS)
        self.assertEqual(InboundMessage.objects.count(), messages)
        self.assertEqual(OperationalEvent.objects.count(), self.events_before)
        self.assertFalse(SourceItem.objects.exists())
        self.assertFalse(SummaryItem.objects.exists())

    def test_text_persists_origin_version_operator_consent_and_both_times(self):
        before = timezone.now()
        receipt = self.ingest()
        self.assertEqual(receipt.status, "created")
        message = InboundMessage.objects.get(pk=receipt.message_id)
        self.assertEqual(message.text, self.payload["text"])
        self.assertEqual(message.media, {})
        self.assertEqual(message.operator_id, self.actor.pk)
        self.assertEqual(message.consent.consultation_id, self.case.pk)
        self.assertEqual(message.origin, "local_simulation")
        self.assertEqual(message.contract_version, "sim.v1")
        self.assertTrue(message.is_simulated)
        self.assertGreaterEqual(message.received_at, before)
        self.assertEqual(message.declared_at.isoformat(), "2026-01-01T12:02:00+00:00")
        self.assert_no_side_effects(1)

    def test_audio_image_and_pdf_metadata_without_processing(self):
        for payload in simulation_envelopes(self.case.pk)[3:]:
            receipt = ingest_message(payload, actor=self.actor)
            message = InboundMessage.objects.get(pk=receipt.message_id)
            self.assertEqual(message.media, payload["media"])
            self.assertEqual(message.text, "")
        self.assert_no_side_effects(3)

    def test_identical_replay_returns_same_id_without_new_receipt_time(self):
        first = self.ingest()
        received_at = InboundMessage.objects.get().received_at
        replay = self.ingest()
        self.assertEqual(replay.status, "redelivered")
        self.assertEqual(first.message_id, replay.message_id)
        self.assertEqual(InboundMessage.objects.get().received_at, received_at)
        self.assert_no_side_effects(1)

    def test_conflict_never_overwrites_original_and_receipt_has_no_payload(self):
        first = self.ingest()
        conflict = self.ingest(text="Outro conteúdo clínico FICTÍCIO.")
        self.assertEqual(conflict.status, "conflict")
        self.assertEqual(conflict.message_id, first.message_id)
        self.assertEqual(InboundMessage.objects.get().text, self.payload["text"])
        self.assertEqual(set(asdict(conflict)), {"status", "message_id", "is_simulated"})
        self.assert_no_side_effects(1)

    def test_declared_time_change_is_a_conflict(self):
        self.ingest()
        self.assertEqual(self.ingest(declared_at="2026-01-01T12:05:00Z").status, "conflict")
        self.assert_no_side_effects(1)

    def test_distinct_identifiers_with_equal_content_are_distinct_messages(self):
        first = self.ingest()
        second = self.ingest(external_event_id="outra-mensagem")
        self.assertNotEqual(first.message_id, second.message_id)
        self.assert_no_side_effects(2)

    def test_same_identifier_in_two_authorized_consultations_is_valid(self):
        other = Consultation.objects.create(
            slug="outra-consulta-ingestao", patient=self.case.patient, doctor=self.case.doctor,
            clinic=self.case.clinic, scheduled_for=timezone.now(), status=Consultation.STATUS_AWAITING_CONSENT,
        )
        record_simulated_consent(other.pk, term_version="sim-v1", manifestation=ConsentEvidence.ACCEPTED, actor=self.actor)
        transition(other.pk, Consultation.STATUS_IN_PROGRESS, actor=self.actor, consent_version="sim-v1")
        first = self.ingest()
        second = self.ingest(consultation_id=other.pk)
        self.assertEqual(second.status, "created")
        self.assertNotEqual(first.message_id, second.message_id)

    def test_canonical_key_order_and_equivalent_timezone_are_idempotent(self):
        self.ingest()
        reordered = dict(reversed(list(self.payload.items())))
        reordered["declared_at"] = "2026-01-01T09:02:00-03:00"
        self.assertEqual(ingest_message(reordered, actor=self.actor).status, "redelivered")
        media = simulation_envelopes(self.case.pk)[3]
        ingest_message(media, actor=self.actor)
        media["media"] = dict(reversed(list(media["media"].items())))
        self.assertEqual(ingest_message(media, actor=self.actor).status, "redelivered")
        self.assert_no_side_effects(2)

    def test_out_of_order_preserves_declared_and_arrival_order(self):
        receipts = run_simulation(self.case.pk, actor=self.actor)
        self.assertEqual([item.status for item in receipts],
                         ["created", "created", "redelivered", "created", "created", "created"])
        self.assertEqual(list(InboundMessage.objects.values_list("external_event_id", flat=True))[:2],
                         ["sim-text-2", "sim-text-1"])
        self.assertEqual(list(InboundMessage.objects.order_by("declared_at", "id")
                              .values_list("external_event_id", flat=True))[:2], ["sim-text-1", "sim-text-2"])
        self.assertEqual([item.status for item in run_simulation(self.case.pk, actor=self.actor)],
                         ["redelivered"] * 6)
        self.assert_no_side_effects(5)

    def test_invalid_structure_and_contract_version_never_echo_content(self):
        invalid = [None, [], {}, {**self.payload, "contract_version": "v2"},
                   {**self.payload, "kind": "video"}, {**self.payload, "kind": []},
                   {**self.payload, "text": ""}, {**self.payload, "text": " "},
                   {**self.payload, "text": "x" * 8001}, {**self.payload, "text": b"binary"},
                   {**self.payload, "text": "\x00"}, {**self.payload, "text": "\ud800"}]
        for payload in invalid:
            with self.subTest(payload_type=type(payload)), self.assertRaises(InvalidEnvelope) as caught:
                ingest_message(payload, actor=self.actor)
            self.assertEqual(caught.exception.messages, ["Contrato de entrada simulado inválido."])
        self.assert_no_side_effects()

    def test_identity_operator_binary_and_unknown_fields_are_not_trusted(self):
        for key in ["patient_id", "operator_id", "actor", "is_simulated", "binary", "media", "extra"]:
            with self.subTest(key=key), self.assertRaises(InvalidEnvelope):
                self.ingest(**{key: "FICTÍCIO"})
        self.assert_no_side_effects()

    def test_invalid_ids_times_and_origins(self):
        for key, values in {
            "consultation_id": [None, True, 0, -1, "1", 2**63],
            "external_event_id": [None, "", "../arquivo", "x" * 121, "id com espaço"],
            "origin": [None, [], "whatsapp", "patient", "local_simulation "],
            "declared_at": [None, "não é data", "2026-01-01T12:00:00", "2026-99-99T12:00:00Z"],
        }.items():
            for value in values:
                with self.subTest(key=key), self.assertRaises(InvalidEnvelope):
                    self.ingest(**{key: value})
        self.assert_no_side_effects()

    def test_invalid_media_shape_limits_mime_url_and_filename(self):
        payload = simulation_envelopes(self.case.pk)[3]
        invalid = [None, {}, {**payload["media"], "mime_type": "image/png"},
                   {**payload["media"], "reference": "https://example.invalid/private"},
                   {**payload["media"], "filename": "../documento.pdf"},
                   {**payload["media"], "size_bytes": True}, {**payload["media"], "size_bytes": 0},
                   {**payload["media"], "size_bytes": 25 * 1024 * 1024 + 1},
                   {**payload["media"], "transcript": "Texto fictício"}]
        for media in invalid:
            with self.assertRaises(InvalidEnvelope):
                ingest_message({**payload, "media": media}, actor=self.actor)
        self.assert_no_side_effects()

    def test_missing_or_wrong_consent_blocks_legacy_collecting_case(self):
        for version in ["", None, "outro-termo"]:
            with self.assertRaises(ValidationError):
                self.ingest(consent_version=version)
        # Raw fixture setup, not a domain service: no backfilled consent.
        self.case.consent_evidence.all().delete()
        with self.assertRaises(InvalidTransition):
            self.ingest()
        self.assert_no_side_effects()

    def test_declined_or_inconsistent_consent_never_allows_ingestion(self):
        evidence = self.case.consent_evidence.get()
        ConsentEvidence.objects.filter(pk=evidence.pk).update(manifestation=ConsentEvidence.DECLINED)
        with self.assertRaises(InvalidTransition):
            self.ingest()
        ConsentEvidence.objects.filter(pk=evidence.pk).update(manifestation=ConsentEvidence.ACCEPTED)
        OperationalEvent.objects.filter(pk=evidence.event_id).update(is_simulated=False)
        with self.assertRaises(InvalidTransition):
            self.ingest()
        self.assert_no_side_effects()

    def test_every_non_collecting_state_blocks_even_replays(self):
        self.ingest()
        for state, _ in Consultation.STATUS_CHOICES:
            if state == Consultation.STATUS_IN_PROGRESS:
                continue
            Consultation.objects.filter(pk=self.case.pk).update(status=state)
            with self.subTest(state=state), self.assertRaises(InvalidTransition):
                self.ingest()
        self.assertEqual(InboundMessage.objects.count(), 1)
        self.assertEqual(OperationalEvent.objects.count(), self.events_before)

    def test_nonexistent_and_outside_clinic_share_uniform_denial(self):
        external_clinic = Clinic.objects.create(name="Outra clínica fictícia")
        external = Consultation.objects.create(
            slug="consulta-externa-ingestao", patient=self.case.patient, doctor=self.case.doctor,
            clinic=external_clinic, status=Consultation.STATUS_IN_PROGRESS, scheduled_for=timezone.now(),
        )
        for pk in [999999, external.pk]:
            with self.assertRaises(PermissionDenied):
                self.ingest(consultation_id=pk)
        self.assert_no_side_effects()

    def test_anonymous_inactive_unassigned_and_technical_admin_denied(self):
        inactive = get_user_model().objects.create_user("ingestao-inativo", is_active=False)
        profile = ReceptionProfile.objects.create(user=inactive)
        profile.clinics.add(self.case.clinic)
        for actor in [None, AnonymousUser(), inactive,
                      get_user_model().objects.create_user("ingestao-sem-perfil"),
                      get_user_model().objects.create_superuser("ingestao-admin-ficticio", password=None)]:
            with self.assertRaises(PermissionDenied):
                ingest_message(self.payload, actor=actor)
        self.assert_no_side_effects()

    def test_doctor_requires_assignment_and_clinic(self):
        doctor_actor = get_user_model().objects.create_user("ingestao-medico-ficticio")
        self.case.doctor.user = doctor_actor
        self.case.doctor.save(update_fields=["user"])
        ingest_message(self.payload, actor=doctor_actor)
        self.case.doctor.clinics.clear()
        with self.assertRaises(PermissionDenied):
            ingest_message(self.payload, actor=doctor_actor)
        self.case.doctor.clinics.add(self.case.clinic)
        other = Doctor.objects.create(name="Outro médico fictício de ingestão")
        other.clinics.add(self.case.clinic)
        self.case.doctor = other
        self.case.save(update_fields=["doctor"])
        with self.assertRaises(PermissionDenied):
            ingest_message(self.payload, actor=doctor_actor)
        self.assert_no_side_effects(1)

    def test_authorization_rechecked_on_replay_and_operator_not_part_of_equivalence(self):
        self.ingest()
        other = get_user_model().objects.create_user("ingestao-outro-operador")
        profile = ReceptionProfile.objects.create(user=other)
        profile.clinics.add(self.case.clinic)
        self.assertEqual(ingest_message(self.payload, actor=other).status, "redelivered")
        self.assertEqual(InboundMessage.objects.get().operator_id, self.actor.pk)
        self.actor.reception_profile.clinics.clear()
        with self.assertRaises(PermissionDenied):
            self.ingest()
        self.assert_no_side_effects(1)

    def test_persistence_failure_after_insert_rolls_back_and_sanitizes_error(self):
        create = InboundMessage.objects.create

        def fail(**kwargs):
            create(**kwargs)
            raise IntegrityError("Erro fictício com conteúdo que não deve sair do serviço")

        with self.assertNoLogs(), patch("preconsultas.ingestion.InboundMessage.objects.create", side_effect=fail):
            with self.assertRaises(IngestionPersistenceError) as caught:
                self.ingest()
        self.assertEqual(str(caught.exception), "Não foi possível persistir a entrada simulada.")
        self.assert_no_side_effects()

    def test_content_absent_from_receipts_operational_events_and_reception(self):
        secret_fictitious_text = "CONTEÚDO CLÍNICO SOMENTE FICTÍCIO PARA TESTE"
        with self.assertNoLogs():
            receipt = self.ingest(text=secret_fictitious_text)
            conflict = self.ingest(text="OUTRO TEXTO FICTÍCIO")
        self.assertNotIn(secret_fictitious_text, repr(receipt))
        self.assertNotIn(secret_fictitious_text, repr(conflict))
        self.assertFalse(OperationalEvent.objects.filter(detail__contains=secret_fictitious_text).exists())
        self.client.force_login(self.actor)
        page = self.client.get(reverse("recepcao:preconsultations"))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, secret_fictitious_text)
        self.assertNotContains(page, "inbound_messages")
        self.assertEqual(self.client.get(reverse("preconsultas:detail", args=[self.case.slug])).status_code, 403)
        self.assertFalse(admin.site.is_registered(InboundMessage))
        self.assert_no_side_effects(1)

    def test_unique_constraint_and_simulation_integrity_at_database_level(self):
        self.ingest()
        message = InboundMessage.objects.get()
        with self.assertRaises(ValidationError):
            message.save()
        with self.assertRaises(ValidationError):
            message.delete()
        for changes in [{"origin": "whatsapp"}, {"is_simulated": False}, {"contract_version": "v2"},
                        {"kind": "video"}, {"external_event_id": ""}, {"media": {"reference": "mixed"}}]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                InboundMessage.objects.filter(pk=message.pk).update(**changes)
        fields = {field.name: getattr(message, field.name) for field in message._meta.fields if field.name != "id"}
        with self.assertRaises(IntegrityError), transaction.atomic():
            InboundMessage.objects.create(**fields)
        self.assert_no_side_effects(1)

    def test_media_conflict_preserves_original_metadata(self):
        payload = simulation_envelopes(self.case.pk)[3]
        first = ingest_message(payload, actor=self.actor)
        changed = deepcopy(payload)
        changed["media"]["size_bytes"] += 1
        conflict = ingest_message(changed, actor=self.actor)
        self.assertEqual(conflict.status, "conflict")
        self.assertEqual(conflict.message_id, first.message_id)
        self.assertEqual(InboundMessage.objects.get().media, payload["media"])
        self.assert_no_side_effects(1)


class IngestionConcurrencyTests(TransactionTestCase):
    def exercise_race(self, *, different=False):
        case, actor = collecting_fixture()
        first_payload = simulation_envelopes(case.pk)[0]
        second_payload = {**first_payload, "text": "Outra mensagem fictícia."} if different else dict(first_payload)
        barrier = Barrier(2)

        def worker(payload):
            try:
                local_actor = get_user_model().objects.get(pk=actor.pk)
                barrier.wait(timeout=10)
                return ingest_message(payload, actor=local_actor)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, payload) for payload in [first_payload, second_payload]]
            results = [future.result(timeout=20) for future in futures]
        self.assertCountEqual([item.status for item in results],
                              ["created", "conflict" if different else "redelivered"])
        self.assertEqual(len({item.message_id for item in results}), 1)
        self.assertEqual(InboundMessage.objects.count(), 1)
        self.assertEqual(OperationalEvent.objects.count(), 2)
        case.refresh_from_db()
        self.assertEqual(case.status, Consultation.STATUS_IN_PROGRESS)

    @skipUnlessDBFeature("has_select_for_update")
    def test_duplicate_messages_concurrently_create_one_row(self):
        self.exercise_race()

    @skipUnlessDBFeature("has_select_for_update")
    def test_conflicting_messages_concurrently_preserve_one_winner(self):
        self.exercise_race(different=True)


class IngestionMigrationTests(TransactionTestCase):
    def test_upgrade_0006_preserves_consent_clinical_sources_and_states(self):
        connection = connections["default"]
        before = [("preconsultas", "0006_simulated_consent_evidence")]
        executor = MigrationExecutor(connection)
        case, actor = collecting_fixture()
        executor.migrate(before)
        try:
            old = executor.loader.project_state(before).apps
            source = old.get_model("preconsultas", "SourceItem").objects.create(
                consultation_id=case.pk, source_key="fonte-legada-ingestao", kind="message", author="patient",
                sent_at=timezone.now(), body="Fonte fictícia legada preservada.",
            )
            summary = old.get_model("preconsultas", "SummaryItem").objects.create(
                consultation_id=case.pk, item_key="resumo-legado-ingestao", section="Teste",
                label="Item fictício", original_value="Síntese fictícia legada.", attribution="ai",
            )
            summary.sources.add(source)
        finally:
            restored = MigrationExecutor(connection)
            restored.migrate(restored.loader.graph.leaf_nodes())
        self.assertFalse(InboundMessage.objects.exists())
        self.assertEqual(ConsentEvidence.objects.count(), 1)
        self.assertEqual(OperationalEvent.objects.count(), 2)
        self.assertEqual(SourceItem.objects.get().body, "Fonte fictícia legada preservada.")
        self.assertEqual(SummaryItem.objects.get().sources.get().pk, source.pk)
        self.assertEqual(Consultation.objects.get().status, Consultation.STATUS_IN_PROGRESS)

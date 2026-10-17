"""PR 06: exercise actual services/HTTP across the simulated pipeline, no shortcuts.

All accounts have unusable passwords; the visual runner sets ephemeral ones only
inside its temporary database. No fixture promotes a case by ORM status update.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connections
from django.test import Client, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from .ai_contract import validate_response
from .ai_orchestration import OrchestrationError, current_result, execute
from .ai_provider import FakeAIProvider
from .consent import record_simulated_consent
from .ingestion import InvalidEnvelope, ingest_message
from .models import (AIAttempt, AIExecution, Clinic, ClinicalPublication, ConsentEvidence,
                     Consultation, Correction, Doctor, DoctorNote, Feedback, InboundMessage,
                     OperationalEvent, Patient, ReceptionProfile, SourceItem, SummaryItem, SummaryRevision)
from .publication import PublicationError, publish_consultation, review_action
from .state_engine import InvalidTransition, transition
from .traceability import (TraceabilityPersistenceError, materialize_message, patient_history,
                           source_provenance, summary_revisions)


def registered_case():
    """The production reception POST creates the patient, case and planned events."""
    tag = uuid4().hex
    clinic = Clinic.objects.create(name=f"Clínica fictícia integrada {tag[:6]}")
    reception = get_user_model().objects.create_user(f"recepcao-ficticia-{tag}")
    ReceptionProfile.objects.create(user=reception).clinics.add(clinic)
    actor = get_user_model().objects.create_user(f"medico-ficticio-{tag}")
    doctor = Doctor.objects.create(name="Médico fictício integrado", user=actor)
    doctor.clinics.add(clinic)
    client = Client()
    client.force_login(reception)
    response = client.post(reverse("recepcao:preconsultations"), {
        "patient_name": f"Paciente fictício integrado {tag[:6]}", "phone": "11900000000",
        "doctor": doctor.pk, "clinic": clinic.pk,
        "scheduled_date": timezone.localdate().isoformat(), "scheduled_time": "10:30",
        "appointment_type": "Consulta fictícia integrada", "contact_lead_hours": 48,
    })
    if response.status_code != 302:
        raise AssertionError("Cadastro fictício integrado não retornou redirecionamento.")
    return Consultation.objects.get(doctor=doctor), reception, actor


def collecting(case, reception):
    transition(case.pk, "awaiting_consent", actor=reception)
    evidence = record_simulated_consent(case.pk, term_version="sim-e2e-v1", manifestation="accepted", actor=reception)
    transition(case.pk, "in_progress", actor=reception, consent_version=evidence.term_version)
    return evidence


def envelope(case, identifier="texto-1", kind="text"):
    payload = {"contract_version": "sim.v1", "origin": "local_simulation",
               "consultation_id": case.pk, "external_event_id": identifier, "kind": kind,
               "declared_at": "2026-01-01T12:00:00Z", "consent_version": "sim-e2e-v1"}
    if kind == "text":
        payload["text"] = "Mensagem exclusivamente fictícia do fluxo integrado."
    else:
        mime, extension = {"pdf": ("application/pdf", "pdf"), "audio": ("audio/mpeg", "mp3"),
                           "image": ("image/png", "png")}[kind]
        payload["media"] = {"reference": f"sim-{identifier}", "mime_type": mime,
                            "filename": f"ficticio.{extension}", "size_bytes": 128}
    return payload


def ingest_sources(case, reception, actor):
    sources = []
    for kind in ("text", "audio", "image", "pdf"):
        receipt = ingest_message(envelope(case, f"entrada-{kind}", kind), actor=reception)
        sources.append(materialize_message(case.pk, receipt.message_id, actor=actor).source_id)
    return sources


def completed_case():
    case, reception, actor = registered_case()
    collecting(case, reception)
    sources = ingest_sources(case, reception, actor)
    # Validated historical input may be materialized later, changing context.
    pending = ingest_message(envelope(case, "entrada-pendente"), actor=reception).message_id
    transition(case.pk, "awaiting_patient", actor=reception)
    transition(case.pk, "completed", actor=reception)
    return case, reception, actor, sources, pending


class PreAIIntegrationTests(TransactionTestCase):
    def setUp(self):
        self.case, self.reception, self.actor = registered_case()

    def prepare(self):
        collecting(self.case, self.reception)
        sources = ingest_sources(self.case, self.reception, self.actor)
        return sources

    def complete(self):
        sources = self.prepare()
        transition(self.case.pk, "awaiting_patient", actor=self.reception)
        transition(self.case.pk, "completed", actor=self.reception)
        return sources

    def build(self):
        self.complete()
        return execute(self.case.pk, "build_summary", actor=self.actor)

    @patch("socket.create_connection", side_effect=AssertionError("Serviços externos proibidos no teste."))
    def test_full_reception_consent_ingestion_provenance_three_operations_publication_review(self, _network):
        self.assertEqual(self.case.status, "not_started")
        self.assertEqual(Patient.objects.count(), 1)
        self.assertFalse(self.case.legacy_demo)
        self.assertFalse(self.actor.has_usable_password())
        self.assertEqual(set(self.case.operational_events.values_list("kind", flat=True)), {"created", "invite_planned"})
        sources = self.prepare()
        evidence = self.case.consent_evidence.get()
        self.assertEqual(evidence.consultation_id, self.case.pk)
        self.assertEqual(evidence.operator_id, self.reception.pk)
        for source in SourceItem.objects.filter(pk__in=sources):
            message = source.inbound_message
            self.assertEqual(message.consent_id, evidence.pk)
            self.assertEqual(message.operator_id, self.reception.pk)
            self.assertEqual(source.sent_at, message.declared_at)
            self.assertIsNotNone(message.received_at)
            self.assertEqual(source.materialized_by_id, self.actor.pk)
            self.assertFalse(materialize_message(self.case.pk, message.pk, actor=self.actor).created)
        question = execute(self.case.pk, "next_question", actor=self.actor)
        extraction = execute(self.case.pk, "extract_structured", actor=self.actor)
        self.assertEqual([question.status, extraction.status], ["succeeded", "succeeded"])
        transition(self.case.pk, "awaiting_patient", actor=self.reception)
        transition(self.case.pk, "completed", actor=self.reception)
        receipt = execute(self.case.pk, "build_summary", actor=self.actor)
        execution = AIExecution.objects.get(pk=receipt.execution_id)
        original_result = deepcopy(execution.result)
        for run in AIExecution.objects.all():
            validate_response(run.result, run.request)
            self.assertEqual(run.source_references.count(), 4)
            self.assertEqual(run.attempts.count(), 1)
            self.assertEqual(run.attempts.get().result, run.result)
        self.assertEqual(self.case.summary_items.count(), 0)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, "completed")
        with self.assertRaises(PermissionDenied):
            current_result(self.case.pk, receipt.execution_id, actor=self.actor)
        self.client.force_login(self.actor)
        detail = reverse("preconsultas:detail", args=[self.case.slug])
        self.assertEqual(self.client.get(detail).status_code, 403)
        self.assertEqual(self.client.post(reverse("preconsultas:publish", args=[self.case.slug]),
                                          {"execution_id": receipt.execution_id}).status_code, 302)
        publication = ClinicalPublication.objects.get(consultation=self.case)
        self.assertEqual(publication.actor_id, self.actor.pk)
        self.assertEqual(publication.context_id, execution.context_id)
        self.assertEqual(publication.result_snapshot, original_result)
        self.assertEqual(publication.event.previous_status, "completed")
        self.assertEqual(publication.event.next_status, "ready")
        self.assertEqual(self.case.summary_items.count(), 4)
        self.assertEqual(SummaryRevision.objects.count(), 4)
        self.assertContains(self.client.get(detail), "Publicação SIMULADA")
        item = self.case.summary_items.order_by("pk").first()
        for name, data in (("detail_note", {"text": "Nota exclusivamente fictícia integrada."}),
                           ("detail_correction", {"summary_item_id": item.pk, "action": "update", "new_value": "Ajuste fictício integrado."}),
                           ("detail_feedback", {"kind": "useful", "summary_item_id": item.pk})):
            self.assertEqual(self.client.post(reverse(f"preconsultas:{name}", args=[self.case.slug]), data,
                                              HTTP_X_REQUESTED_WITH="XMLHttpRequest").status_code, 200)
        self.assertEqual(DoctorNote.objects.get().actor_id, self.actor.pk)
        self.assertEqual(Correction.objects.get().actor_id, self.actor.pk)
        self.assertEqual(Feedback.objects.get().actor_id, self.actor.pk)
        revisions = summary_revisions(self.case.pk, item.pk, actor=self.actor)
        self.assertEqual([r["number"] for r in revisions], [1, 2])
        self.assertEqual(revisions[0]["presented_value"], item.original_value)
        self.assertEqual(revisions[1]["presented_value"], "Ajuste fictício integrado.")
        self.assertEqual(revisions[0]["source_ids"], revisions[1]["source_ids"])
        self.assertEqual(current_result(self.case.pk, receipt.execution_id, actor=self.actor), original_result)
        self.assertEqual(patient_history(self.case.patient_id, actor=self.actor)[0]["id"], self.case.pk)
        self.assertEqual(source_provenance(self.case.pk, sources[0], actor=self.actor)["consent_id"], evidence.pk)
        self.assertEqual(SourceItem.objects.get(pk=sources[0]).body, envelope(self.case)["text"])
        self.assertNotIn(envelope(self.case)["text"], repr(list(self.case.operational_events.values())))
        self.client.force_login(self.reception)
        self.assertNotContains(self.client.get(reverse("recepcao:preconsultations")), envelope(self.case)["text"])

    def test_replays_conflicts_equal_content_distinct_ids_and_out_of_order_materialization(self):
        collecting(self.case, self.reception)
        payload = envelope(self.case)
        first = ingest_message(payload, actor=self.reception)
        stored = InboundMessage.objects.get(pk=first.message_id)
        received_at = stored.received_at
        again = ingest_message(payload, actor=self.actor)
        self.assertEqual((again.status, again.message_id), ("redelivered", first.message_id))
        conflict = ingest_message({**payload, "text": "Outro conteúdo fictício."}, actor=self.reception)
        self.assertEqual(conflict.status, "conflict")
        stored.refresh_from_db()
        self.assertEqual(stored.text, payload["text"])
        self.assertEqual(stored.operator_id, self.reception.pk)
        self.assertEqual(stored.received_at, received_at)
        second = ingest_message({**payload, "external_event_id": "texto-2", "declared_at": "2026-01-01T11:00:00Z"}, actor=self.reception)
        third = ingest_message({**payload, "external_event_id": "texto-3"}, actor=self.reception)
        self.assertEqual(InboundMessage.objects.count(), 3)
        self.assertLess(InboundMessage.objects.get(pk=second.message_id).declared_at, stored.declared_at)
        self.assertGreaterEqual(InboundMessage.objects.get(pk=third.message_id).received_at, stored.received_at)
        first_source = materialize_message(self.case.pk, first.message_id, actor=self.actor)
        self.assertEqual(materialize_message(self.case.pk, first.message_id, actor=self.actor).source_id, first_source.source_id)
        self.assertEqual(SourceItem.objects.count(), 1)
        self.assertFalse(AIExecution.objects.exists())
        self.assertFalse(ClinicalPublication.objects.exists())

    def test_absent_wrong_declined_consent_and_terminal_state_block_the_pipeline(self):
        transition(self.case.pk, "awaiting_consent", actor=self.reception)
        with self.assertRaises(InvalidTransition):
            transition(self.case.pk, "in_progress", actor=self.reception, consent_version="sim-e2e-v1")
        record_simulated_consent(self.case.pk, term_version="sim-e2e-v1", manifestation="accepted", actor=self.reception)
        with self.assertRaises(InvalidTransition):
            transition(self.case.pk, "in_progress", actor=self.reception, consent_version="versao-incorreta")
        record_simulated_consent(self.case.pk, term_version="sim-e2e-v2", manifestation="declined", actor=self.reception)
        for action in (lambda: transition(self.case.pk, "in_progress", actor=self.reception, consent_version="sim-e2e-v1"),
                       lambda: ingest_message(envelope(self.case), actor=self.reception),
                       lambda: execute(self.case.pk, "build_summary", actor=self.actor)):
            with self.assertRaises((InvalidTransition, OrchestrationError)):
                action()
        self.assertEqual(Consultation.objects.get(pk=self.case.pk).status, "consent_declined")
        self.assertFalse(InboundMessage.objects.exists())
        self.assertFalse(AIExecution.objects.exists())

    def test_operation_state_gates_and_invalid_media_leave_no_partial_pipeline(self):
        self.prepare()
        with self.assertRaises(OrchestrationError):
            execute(self.case.pk, "build_summary", actor=self.actor)
        for media in ({"reference": "https://example.invalid/file", "mime_type": "application/pdf", "filename": "x.pdf", "size_bytes": 1},
                      {"reference": "sim-file", "mime_type": "image/png", "filename": "../x.pdf", "size_bytes": 1}):
            with self.assertRaises(InvalidEnvelope):
                ingest_message({**envelope(self.case, "invalid-media", "pdf"), "media": media}, actor=self.reception)
        self.assertEqual(InboundMessage.objects.count(), 4)
        self.assertFalse(AIExecution.objects.exists())
        transition(self.case.pk, "awaiting_patient", actor=self.actor)
        transition(self.case.pk, "completed", actor=self.actor)
        with self.assertRaises(OrchestrationError):
            execute(self.case.pk, "next_question", actor=self.actor)
        with self.assertRaises(InvalidTransition):
            transition(self.case.pk, "in_progress", actor=self.actor)

    def test_invalid_contract_source_version_external_reference_and_empty_result_never_publish(self):
        self.complete()
        other, _, other_actor, other_sources, _ = completed_case()
        for index, mutation in enumerate((lambda r: r.update(contract_version="ai.v99"),
                                        lambda r: r["result"]["items"][0]["references"][0].update(version="0" * 64),
                                        lambda r: r["result"]["items"][0]["references"][0].update(source_id=other_sources[0]),
                                        lambda r: r["result"].update(items=[]))):
            provider = FakeAIProvider()
            provider.provider_version = f"e2e-invalid-{index}"
            original = provider.build_summary
            def malformed(request, original=original, mutation=mutation):
                result = original(request)
                mutation(result)
                return result
            provider.build_summary = malformed
            receipt = execute(self.case.pk, "build_summary", actor=self.actor, provider=provider)
            with self.assertRaises(PublicationError):
                publish_consultation(self.case.pk, receipt.execution_id, actor=self.actor)
        self.assertFalse(ClinicalPublication.objects.exists())
        self.assertFalse(SummaryItem.objects.exists())
        self.assertEqual(Consultation.objects.get(pk=self.case.pk).status, "completed")

    def test_transient_failure_explicit_retry_success_preserves_attempt_then_publishes(self):
        self.complete()
        provider = FakeAIProvider("transient")
        first = execute(self.case.pk, "build_summary", actor=self.actor, provider=provider)
        self.assertEqual(first.status, "failed")
        self.assertEqual(execute(self.case.pk, "build_summary", actor=self.actor, provider=provider), first)
        provider.scenario = "normal"  # Same fake identity, explicit successful retry.
        second = execute(self.case.pk, "build_summary", actor=self.actor, provider=provider, retry=True)
        self.assertEqual(second.execution_id, first.execution_id)
        self.assertEqual(second.attempt_count, 2)
        self.assertEqual(list(AIAttempt.objects.order_by("number").values_list("status", flat=True)), ["failed", "succeeded"])
        publish_consultation(self.case.pk, second.execution_id, actor=self.actor)
        self.assertEqual(ClinicalPublication.objects.count(), 1)

    def test_three_attempt_limit_never_retries_automatically_or_publishes(self):
        self.complete()
        provider = FakeAIProvider("transient")
        for _ in range(5):
            receipt = execute(self.case.pk, "build_summary", actor=self.actor, provider=provider, retry=True)
        self.assertEqual(receipt.attempt_count, 3)
        self.assertEqual(AIAttempt.objects.count(), 3)
        with self.assertRaises(PublicationError):
            publish_consultation(self.case.pk, receipt.execution_id, actor=self.actor)
        self.assertFalse(ClinicalPublication.objects.exists())

    def test_finalization_failure_preserves_running_and_sanitizes_errors_without_reexecution(self):
        self.complete()
        save = AIExecution.save
        def fail(instance, *args, **kwargs):
            if instance.status == "succeeded":
                raise DatabaseError(envelope(self.case)["text"])
            return save(instance, *args, **kwargs)
        with patch.object(AIExecution, "save", fail), self.assertNoLogs():
            with self.assertRaises(OrchestrationError) as caught:
                execute(self.case.pk, "build_summary", actor=self.actor)
        self.assertNotIn(envelope(self.case)["text"], str(caught.exception))
        self.assertEqual(AIExecution.objects.get().status, "running")
        self.assertEqual(AIAttempt.objects.get().status, "running")
        with patch.object(FakeAIProvider, "build_summary", side_effect=AssertionError("Não deve chamar")):
            receipt = execute(self.case.pk, "build_summary", actor=self.actor, retry=True)
        self.assertEqual(receipt.status, "running")
        with self.assertRaises(PublicationError):
            publish_consultation(self.case.pk, receipt.execution_id, actor=self.actor)
        self.assertFalse(SummaryItem.objects.exists())

    def test_publication_snapshot_failure_rolls_back_but_keeps_original_execution_and_sources(self):
        receipt = self.build()
        events = self.case.operational_events.count()
        with patch("preconsultas.publication.record_summary_revision", side_effect=DatabaseError("detalhe fictício privado")):
            with self.assertRaises(PublicationError):
                publish_consultation(self.case.pk, receipt.execution_id, actor=self.actor)
        self.assertFalse(ClinicalPublication.objects.exists())
        self.assertFalse(SummaryItem.objects.exists())
        self.assertFalse(SummaryRevision.objects.exists())
        self.assertEqual(self.case.operational_events.count(), events)
        self.assertEqual(SourceItem.objects.count(), 4)
        self.assertEqual(AIExecution.objects.get().status, "succeeded")
        self.assertEqual(Consultation.objects.get(pk=self.case.pk).status, "completed")

    def test_correction_failure_after_write_rolls_back_and_repetition_is_idempotent(self):
        receipt = self.build()
        publish_consultation(self.case.pk, receipt.execution_id, actor=self.actor)
        item = self.case.summary_items.order_by("pk").first()
        data = {"summary_item_id": item.pk, "action": "update", "new_value": "Ajuste fictício."}
        with patch("preconsultas.traceability.SummaryRevisionSource.objects.create", side_effect=DatabaseError):
            with self.assertRaises(TraceabilityPersistenceError):
                review_action(self.case.pk, actor=self.actor, action="correction", data=data)
        self.assertFalse(Correction.objects.exists())
        self.assertEqual(item.revisions.count(), 1)
        correction = review_action(self.case.pk, actor=self.actor, action="correction", data=data)
        self.assertEqual(review_action(self.case.pk, actor=self.actor, action="correction", data=data).pk, correction.pk)
        self.assertEqual(item.revisions.count(), 2)
        self.assertFalse(publish_consultation(self.case.pk, receipt.execution_id, actor=self.actor).created)

    def test_roles_other_doctor_and_unlinked_clinic_never_publish_or_read(self):
        receipt = self.build()
        admin = get_user_model().objects.create_user("admin-tecnico-ficticio", is_staff=True, is_superuser=True)
        other = get_user_model().objects.create_user("outro-medico-ficticio")
        Doctor.objects.create(name="Outro médico fictício", user=other).clinics.add(self.case.clinic)
        for actor in (self.reception, admin, other):
            with self.subTest(actor=actor.pk):
                for action in (lambda: publish_consultation(self.case.pk, receipt.execution_id, actor=actor),
                               lambda: materialize_message(self.case.pk, InboundMessage.objects.first().pk, actor=actor),
                               lambda: current_result(self.case.pk, receipt.execution_id, actor=actor)):
                    with self.assertRaises(PermissionDenied):
                        action()
        self.case.doctor.clinics.clear()
        with self.assertRaises(PermissionDenied):
            publish_consultation(self.case.pk, receipt.execution_id, actor=self.actor)
        self.assertFalse(ClinicalPublication.objects.exists())

    def test_patient_identity_does_not_expand_history_or_allow_foreign_corrections(self):
        receipt = self.build()
        publish_consultation(self.case.pk, receipt.execution_id, actor=self.actor)
        other, _, actor, _, _ = completed_case()
        # Same fictional patient is intentionally shared, never an authorization key.
        Consultation.objects.filter(pk=other.pk).update(patient_id=self.case.patient_id)
        other_receipt = execute(other.pk, "build_summary", actor=actor)
        publish_consultation(other.pk, other_receipt.execution_id, actor=actor)
        self.assertEqual([r["id"] for r in patient_history(self.case.patient_id, actor=self.actor)], [self.case.pk])
        foreign_item = other.summary_items.first()
        with self.assertRaises(PermissionDenied):
            review_action(self.case.pk, actor=self.actor, action="correction", data={
                "summary_item_id": foreign_item.pk, "action": "hide"})
        with self.assertRaises(PermissionDenied):
            materialize_message(self.case.pk, other.inbound_messages.first().pk, actor=self.actor)
        with self.assertRaises(PermissionDenied):
            publish_consultation(self.case.pk, other_receipt.execution_id, actor=self.actor)
        self.assertFalse(Correction.objects.exists())

    def test_new_materialized_source_invalidates_all_clinical_surfaces_without_state_change(self):
        self.prepare()
        pending = ingest_message(envelope(self.case, "pendente"), actor=self.reception)
        transition(self.case.pk, "awaiting_patient", actor=self.reception)
        transition(self.case.pk, "completed", actor=self.reception)
        receipt = execute(self.case.pk, "build_summary", actor=self.actor)
        publish_consultation(self.case.pk, receipt.execution_id, actor=self.actor)
        original = deepcopy(AIExecution.objects.get(pk=receipt.execution_id).result)
        materialize_message(self.case.pk, pending.message_id, actor=self.actor)
        self.client.force_login(self.actor)
        pdf = self.case.sources.get(kind="pdf")
        for name, args in (("detail", [self.case.slug]), ("attachment_status", [pdf.source_key]),
                           ("attachment_content", [pdf.source_key])):
            self.assertEqual(self.client.get(reverse(f"preconsultas:{name}", args=args)).status_code, 403)
        self.assertEqual(self.client.post(reverse("preconsultas:detail_note", args=[self.case.slug]), {"text": "Nota fictícia."}).status_code, 403)
        with self.assertRaises(PermissionDenied):
            current_result(self.case.pk, receipt.execution_id, actor=self.actor)
        self.assertEqual(patient_history(self.case.patient_id, actor=self.actor), ())
        self.assertContains(self.client.get(reverse("preconsultas:dashboard")), "nova validação explícita")
        publication = ClinicalPublication.objects.get()
        self.assertIsNotNone(publication.requires_validation_at)
        self.assertEqual(publication.validation_requested_by_id, self.actor.pk)
        self.assertEqual(AIExecution.objects.get(pk=receipt.execution_id).result, original)
        self.assertEqual(Consultation.objects.get(pk=self.case.pk).status, "ready")
        self.assertFalse(DoctorNote.objects.exists())
        self.assertEqual(ClinicalPublication.objects.count(), 1)

    def test_authorization_loss_and_forged_ready_do_not_grant_new_clinical_access(self):
        receipt = self.build()
        Consultation.objects.filter(pk=self.case.pk).update(status="ready")  # Explicit hostile write, not a fixture shortcut.
        with self.assertRaises(PermissionDenied):
            current_result(self.case.pk, receipt.execution_id, actor=self.actor)
        self.assertFalse(ClinicalPublication.objects.exists())
        get_user_model().objects.filter(pk=self.actor.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            execute(self.case.pk, "build_summary", actor=self.actor)
        self.client.force_login(self.actor)
        self.assertEqual(self.client.get(reverse("preconsultas:detail", args=[self.case.slug])).status_code, 302)


class PreAIConcurrencyTests(TransactionTestCase):
    def process_while(self, case, actor, operation, mutation):
        entered, release = Event(), Event()
        class BlockingFake(FakeAIProvider):
            def _run(self, request, op):
                entered.set()
                if not release.wait(15):
                    raise AssertionError("O teste não liberou o fake.")
                return super()._run(request, op)
        def worker():
            try:
                return execute(case.pk, operation, actor=get_user_model().objects.get(pk=actor.pk), provider=BlockingFake())
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(worker)
            try:
                self.assertTrue(entered.wait(10), "O fake não foi chamado.")
                duplicate = execute(case.pk, operation, actor=actor)
                self.assertEqual(duplicate.status, "running")
                mutation()
            finally:
                release.set()
            receipt = future.result(timeout=20)
        self.assertEqual(receipt.status, "obsolete")
        self.assertEqual(AIAttempt.objects.filter(execution_id=receipt.execution_id).count(), 1)
        self.assertFalse(ClinicalPublication.objects.exists())
        return receipt

    @skipUnlessDBFeature("has_select_for_update")
    def test_operational_transition_during_processing_invalidates_reserved_result(self):
        case, reception, actor = registered_case()
        collecting(case, reception)
        ingest_sources(case, reception, actor)
        self.process_while(case, actor, "next_question", lambda: transition(case.pk, "incomplete", actor=reception))
        self.assertEqual(Consultation.objects.get(pk=case.pk).status, "incomplete")
        self.assertFalse(SummaryItem.objects.exists())

    @skipUnlessDBFeature("has_select_for_update")
    def test_materialization_during_build_requires_new_context_before_publication(self):
        case, reception, actor, sources, pending = completed_case()
        previous = self.process_while(case, actor, "build_summary",
                                      lambda: materialize_message(case.pk, pending, actor=actor))
        with self.assertRaises(PublicationError):
            publish_consultation(case.pk, previous.execution_id, actor=actor)
        current = execute(case.pk, "build_summary", actor=actor)
        self.assertNotEqual(previous.execution_id, current.execution_id)
        publish_consultation(case.pk, current.execution_id, actor=actor)
        self.assertEqual(ClinicalPublication.objects.get().execution_id, current.execution_id)
        self.assertEqual(SummaryItem.objects.count(), 5)

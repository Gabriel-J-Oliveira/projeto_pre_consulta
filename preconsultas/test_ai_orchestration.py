from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier, Event, Lock
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, IntegrityError, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone

from .ai_contract import ContractError
from .ai_orchestration import OrchestrationError, current_result, execute
from .ai_provider import FakeAIProvider
from .models import (AIAttempt, AIExecution, AIExecutionSource, Clinic, ConsentEvidence, Consultation,
                     Correction, Doctor, OperationalEvent, SourceItem, SummaryItem, SummaryRevision)
from .test_traceability import traceability_fixture
from .traceability import materialize_message


def orchestration_fixture():
    case, reception, doctor, message_id = traceability_fixture()
    source_id = materialize_message(case.pk, message_id, actor=doctor).source_id
    return case, reception, doctor, source_id


class HookProvider(FakeAIProvider):
    def __init__(self, hook):
        super().__init__()
        self.hook = hook

    def next_question(self, request):
        response = super().next_question(request)
        self.hook()
        return response


class OrchestrationTests(TestCase):
    def setUp(self):
        self.case, self.reception, self.doctor, self.source_id = orchestration_fixture()
        self.events = list(OperationalEvent.objects.values())

    def run_operation(self, operation="next_question", **kwargs):
        return execute(self.case.pk, operation, actor=self.doctor, **kwargs)

    def state(self, status):
        # Fixture ONLY; orchestration never publishes/advances the consultation.
        Consultation.objects.filter(pk=self.case.pk).update(status=status)

    def legacy(self):
        return SourceItem.objects.create(consultation=self.case, source_key="legacy-ai-ficticia",
                                         kind="message", author="patient", sent_at=timezone.now(),
                                         body="Texto fictício legado.")

    def test_three_operations_persist_context_attempts_and_references_not_domain(self):
        with self.assertNoLogs():
            first = self.run_operation()
            second = self.run_operation("extract_structured")
            self.state("completed")
            third = self.run_operation("build_summary")
        for receipt in (first, second, third):
            execution = AIExecution.objects.get(pk=receipt.execution_id)
            self.assertEqual(receipt.status, "succeeded")
            self.assertEqual(receipt.attempt_count, 1)
            self.assertEqual(execution.contract_version, "ai.v1")
            self.assertEqual(execution.created_by_id, self.doctor.pk)
            self.assertEqual(execution.source_references.get().source_id, self.source_id)
            self.assertEqual(execution.attempts.get().result, execution.result)
            self.assertIsNotNone(execution.finished_at)
            self.assertNotIn("result", receipt.__dict__)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, "completed")
        self.assertEqual(list(OperationalEvent.objects.values()), self.events)
        self.assertFalse(SummaryItem.objects.exists())
        self.assertFalse(SummaryRevision.objects.exists())
        self.assertFalse(Correction.objects.exists())

    def test_replay_reuses_result_without_provider_call_or_new_attempt(self):
        first = self.run_operation()
        with patch.object(FakeAIProvider, "next_question", side_effect=AssertionError("Not called")):
            again = self.run_operation(retry=True)
        self.assertEqual(first, again)
        self.assertEqual(AIExecution.objects.count(), 1)
        self.assertEqual(AIAttempt.objects.count(), 1)

    def test_provider_version_participates_in_identity(self):
        first = self.run_operation()
        provider = FakeAIProvider()
        provider.provider_version = "2.normal"
        second = self.run_operation(provider=provider)
        self.assertNotEqual(first.execution_id, second.execution_id)

    def test_legacy_body_change_creates_new_version_preserves_previous_and_marks_obsolete(self):
        source = self.legacy()
        first = self.run_operation()
        old = deepcopy(AIExecution.objects.get(pk=first.execution_id).request)
        source.body = "Texto fictício atualizado."
        source.save()
        second = self.run_operation()
        prior = AIExecution.objects.get(pk=first.execution_id)
        self.assertEqual(prior.status, "obsolete")
        self.assertEqual(prior.request, old)
        self.assertIsNotNone(prior.result)
        self.assertNotEqual(first.execution_id, second.execution_id)
        self.assertNotEqual(prior.context_id, AIExecution.objects.get(pk=second.execution_id).context_id)

    def test_new_source_changes_context(self):
        first = self.run_operation()
        self.legacy()
        second = self.run_operation()
        self.assertNotEqual(first.execution_id, second.execution_id)

    def test_operation_state_matrix_without_ready_promotion(self):
        allowed = {"next_question": {"in_progress"},
                   "extract_structured": {"in_progress", "awaiting_patient", "completed", "ready"},
                   "build_summary": {"completed", "ready"}}
        for operation, permitted in allowed.items():
            for state, _ in Consultation.STATUS_CHOICES:
                self.state(state)
                if state in permitted:
                    self.assertEqual(self.run_operation(operation).status, "succeeded")
                else:
                    with self.assertRaises(OrchestrationError):
                        self.run_operation(operation)
                self.case.refresh_from_db()
                self.assertEqual(self.case.status, state)

    def test_missing_declined_or_inconsistent_consent_blocks_processing(self):
        evidence = ConsentEvidence.objects.get(consultation=self.case)
        for changes in [{"manifestation": "declined"}, {"origin": "invalid"}]:
            if "origin" in changes:
                # DB rejects invalid simulation origin; test corrupted event instead.
                OperationalEvent.objects.filter(pk=evidence.event_id).update(actor=None)
            else:
                ConsentEvidence.objects.filter(pk=evidence.pk).update(**changes)
            with self.assertRaises(OrchestrationError):
                self.run_operation()
            ConsentEvidence.objects.filter(pk=evidence.pk).update(manifestation="accepted")
        self.assertFalse(AIExecution.objects.exists())

    def test_case_without_consent_or_sources_rejected(self):
        other = Consultation.objects.create(slug="sem-consentimento-ficticio", patient=self.case.patient,
                                            doctor=self.case.doctor, clinic=self.case.clinic,
                                            scheduled_for=timezone.now(), status="in_progress")
        with self.assertRaises(OrchestrationError):
            execute(other.pk, "next_question", actor=self.doctor)
        # Existing consent but no source: explicit precondition, no invented input.
        SourceItem.objects.filter(pk=self.source_id).delete()
        with self.assertRaises(ContractError):
            self.run_operation()
        self.assertFalse(AIExecution.objects.exists())

    def test_reception_admin_anonymous_and_unlinked_users_denied_in_all_interfaces(self):
        outsider = get_user_model().objects.create_user("medico-externo-ficticio")
        technical = get_user_model().objects.create_user("admin-tecnico-ficticio", is_staff=True, is_superuser=True)
        existing = self.run_operation()
        self.state("ready")
        for actor in [self.reception, technical, outsider, AnonymousUser()]:
            for operation in ("next_question", "extract_structured", "build_summary"):
                with self.assertRaises(PermissionDenied):
                    execute(self.case.pk, operation, actor=actor)
            with self.assertRaises(PermissionDenied):
                current_result(self.case.pk, existing.execution_id, actor=actor)
        for model in (AIExecution, AIAttempt, AIExecutionSource):
            self.assertNotIn(model, admin.site._registry)

    def test_other_doctor_clinic_and_forged_ids_denied(self):
        receipt = self.run_operation()
        clinic = Clinic.objects.create(name="Outra clínica fictícia")
        Consultation.objects.filter(pk=self.case.pk).update(clinic=clinic)
        with self.assertRaises(PermissionDenied):
            self.run_operation()
        self.case.doctor.clinics.add(clinic)
        other_doctor = Doctor.objects.create(name="Outro médico fictício", display_registration="FICTÍCIO")
        Consultation.objects.filter(pk=self.case.pk).update(doctor=other_doctor)
        with self.assertRaises(PermissionDenied):
            self.run_operation()
        with self.assertRaises(PermissionDenied):
            current_result(self.case.pk, receipt.execution_id, actor=self.doctor)
        with self.assertRaises(PermissionDenied):
            execute(999999, "next_question", actor=self.doctor)

    def test_read_requires_ready_rechecks_active_user_and_scope(self):
        receipt = self.run_operation()
        with self.assertRaises(PermissionDenied):
            current_result(self.case.pk, receipt.execution_id, actor=self.doctor)
        self.state("ready")
        self.assertIsNotNone(current_result(self.case.pk, receipt.execution_id, actor=self.doctor))
        get_user_model().objects.filter(pk=self.doctor.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            current_result(self.case.pk, receipt.execution_id, actor=self.doctor)

    def test_external_source_reference_and_wrong_version_are_failed_not_accepted(self):
        for wrong in [{"source_id": 999999}, {"version": "0" * 64}]:
            provider = FakeAIProvider()
            provider.provider_version = "1." + next(iter(wrong))
            original = provider.next_question

            def invalid(request):
                response = original(request)
                response["result"]["references"][0].update(wrong)
                return response

            provider.next_question = invalid
            receipt = self.run_operation(provider=provider)
            self.assertEqual(receipt.status, "failed")
            self.assertEqual(receipt.error_code, "invalid_provenance")
            self.assertIsNone(AIExecution.objects.get(pk=receipt.execution_id).result)

    def test_existing_source_from_another_consultation_cannot_be_referenced(self):
        other = Consultation.objects.create(slug="fonte-externa-caso-ficticio", patient=self.case.patient,
                                            doctor=self.case.doctor, clinic=self.case.clinic,
                                            scheduled_for=timezone.now(), status="in_progress")
        external = SourceItem.objects.create(consultation=other, source_key="fonte-externa-ai",
                                             kind="message", author="patient", body="Texto externo fictício.",
                                             sent_at=timezone.now())
        provider = FakeAIProvider()
        original = provider.next_question

        def forged(request):
            response = original(request)
            self.assertNotIn(external.pk, [s["source_id"] for s in request["sources"]])
            response["result"]["references"][0]["source_id"] = external.pk
            return response

        provider.next_question = forged
        receipt = self.run_operation(provider=provider)
        self.assertEqual(receipt.error_code, "invalid_provenance")
        self.assertIsNone(AIExecution.objects.get().result)

    def test_invalid_response_generic_exception_and_version_failure_sanitized(self):
        receipt = self.run_operation(provider=FakeAIProvider("invalid"))
        self.assertEqual(receipt.error_code, "invalid_contract")
        provider = FakeAIProvider()
        with patch.object(provider, "next_question", side_effect=RuntimeError("PRIVATE INPUT MUST NOT APPEAR")):
            with self.assertNoLogs():
                failed = self.run_operation(provider=provider)
        execution = AIExecution.objects.get(pk=failed.execution_id)
        self.assertEqual(execution.error_code, "provider_failure")
        self.assertIsNone(execution.result)
        self.assertNotIn("PRIVATE INPUT", str(list(AIAttempt.objects.values("error_code", "result"))))
        self.assertEqual(list(OperationalEvent.objects.values()), self.events)

    def test_retry_explicit_transient_max_three_attempts(self):
        provider = FakeAIProvider("transient")
        first = self.run_operation(provider=provider)
        self.assertEqual(first.attempt_count, 1)
        self.assertEqual(self.run_operation(provider=provider).attempt_count, 1)
        self.assertEqual(self.run_operation(provider=provider, retry=True).attempt_count, 2)
        self.assertEqual(self.run_operation(provider=provider, retry=True).attempt_count, 3)
        self.assertEqual(self.run_operation(provider=provider, retry=True).attempt_count, 3)
        self.assertEqual(AIExecution.objects.count(), 1)

    def test_transient_retry_can_succeed_without_overwriting_previous_attempt(self):
        provider = FakeAIProvider("transient")
        first = self.run_operation(provider=provider)
        provider.scenario = "normal"  # Same adapter/version, recovered availability.
        second = self.run_operation(provider=provider, retry=True)
        self.assertEqual(first.execution_id, second.execution_id)
        self.assertEqual(second.status, "succeeded")
        self.assertEqual(list(AIAttempt.objects.values_list("status", flat=True)), ["failed", "succeeded"])

    def test_non_retryable_failure_not_reexecuted(self):
        provider = FakeAIProvider("invalid")
        first = self.run_operation(provider=provider)
        self.assertEqual(self.run_operation(provider=provider, retry=True), first)

    def test_context_changed_during_provider_keeps_valid_but_obsolete_result(self):
        legacy = self.legacy()
        provider = HookProvider(lambda: SourceItem.objects.filter(pk=legacy.pk).update(body="Nova versão fictícia."))
        receipt = self.run_operation(provider=provider)
        self.assertEqual(receipt.status, "obsolete")
        self.assertIsNotNone(AIAttempt.objects.get().result)
        self.state("ready")
        self.assertIsNone(current_result(self.case.pk, receipt.execution_id, actor=self.doctor))

    def test_state_changed_during_provider_not_accepted_or_advanced(self):
        receipt = self.run_operation(provider=HookProvider(lambda: self.state("cancelled")))
        self.assertEqual(receipt.status, "obsolete")
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, "cancelled")

    def test_authorization_revoked_during_provider_discards_result(self):
        provider = HookProvider(lambda: self.case.doctor.clinics.clear())
        receipt = self.run_operation(provider=provider)
        self.assertEqual(receipt.status, "failed")
        self.assertEqual(receipt.error_code, "authorization_changed")
        self.assertIsNone(AIAttempt.objects.get().result)

    def test_current_result_rechecks_content_and_rejects_obsolete_on_use(self):
        source = self.legacy()
        receipt = self.run_operation()
        self.state("ready")
        source.body = "Fonte fictícia mudou depois do processamento."
        source.save()
        self.assertIsNone(current_result(self.case.pk, receipt.execution_id, actor=self.doctor))
        execution = AIExecution.objects.get(pk=receipt.execution_id)
        self.assertEqual(execution.status, "obsolete")
        self.assertIsNotNone(execution.result)

    def test_current_result_revalidates_persisted_output_and_reference_rows(self):
        receipt = self.run_operation()
        self.state("ready")
        AIExecutionSource.objects.filter(execution_id=receipt.execution_id).update(version="0" * 64)
        self.assertIsNone(current_result(self.case.pk, receipt.execution_id, actor=self.doctor))

    def test_persisted_invalid_response_is_not_consumed(self):
        receipt = self.run_operation()
        self.state("ready")
        AIExecution.objects.filter(pk=receipt.execution_id).update(result={"contract_version": "ai.v999"})
        self.assertIsNone(current_result(self.case.pk, receipt.execution_id, actor=self.doctor))
        self.assertEqual(AIExecution.objects.get().status, "obsolete")

    def test_unsupported_provider_contract_recorded_as_failure(self):
        provider = FakeAIProvider()
        original = provider.next_question

        def wrong_version(request):
            response = original(request)
            response["contract_version"] = "ai.v2"
            return response

        provider.next_question = wrong_version
        receipt = self.run_operation(provider=provider)
        self.assertEqual(receipt.error_code, "unsupported_version")
        self.assertIsNone(AIExecution.objects.get().result)

    def test_reservation_failure_rolls_back_execution_attempt_and_source_references(self):
        with patch.object(AIAttempt.objects, "create", side_effect=DatabaseError("PRIVATE DB DETAIL")):
            with self.assertRaises(OrchestrationError) as caught:
                self.run_operation()
        self.assertEqual(caught.exception.code, "persistence_failure")
        self.assertNotIn("PRIVATE", str(caught.exception))
        self.assertFalse(AIExecution.objects.exists())
        self.assertFalse(AIExecutionSource.objects.exists())
        self.assertFalse(AIAttempt.objects.exists())

    def test_finalization_failure_rolls_back_both_results_leaves_running_for_investigation(self):
        original = AIExecution.save

        def fail(instance, *args, **kwargs):
            if instance.status == "succeeded":
                raise DatabaseError("PRIVATE DB DETAIL")
            return original(instance, *args, **kwargs)

        with patch.object(AIExecution, "save", fail):
            with self.assertRaises(OrchestrationError):
                self.run_operation()
        self.assertEqual(AIExecution.objects.get().status, "running")
        self.assertEqual(AIAttempt.objects.get().status, "running")
        self.assertIsNone(AIAttempt.objects.get().result)
        self.assertEqual(self.run_operation().status, "running")

    def test_database_identity_unique_and_attempt_limit(self):
        receipt = self.run_operation()
        execution = AIExecution.objects.get(pk=receipt.execution_id)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AIAttempt.objects.create(execution=execution, number=4, actor=self.doctor, started_at=timezone.now())
        with self.assertRaises(IntegrityError), transaction.atomic():
            AIExecution.objects.create(consultation=self.case, operation=execution.operation, contract_version="ai.v1",
                                       provider_id="fake", provider_version="1.normal", context_id=execution.context_id,
                                       identity=execution.identity, request=execution.request,
                                       created_at=timezone.now(), created_by=self.doctor)

    def test_final_attempt_and_source_reference_instance_mutation_is_rejected(self):
        self.run_operation()
        attempt = AIAttempt.objects.get()
        with self.assertRaises(ValidationError):
            attempt.save()
        with self.assertRaises(ValidationError):
            attempt.delete()
        ref = AIExecutionSource.objects.get()
        with self.assertRaises(ValidationError):
            ref.save()
        with self.assertRaises(ValidationError):
            ref.delete()

    def test_other_consultation_execution_cannot_be_read(self):
        receipt = self.run_operation()
        other = Consultation.objects.create(slug="outro-caso-ficticio", patient=self.case.patient,
                                            doctor=self.case.doctor, clinic=self.case.clinic,
                                            scheduled_for=timezone.now(), status="ready")
        with self.assertRaises(PermissionDenied):
            current_result(other.pk, receipt.execution_id, actor=self.doctor)


class OrchestrationConcurrencyTests(TransactionTestCase):
    def test_outer_transaction_rejected_before_provider_and_reservation(self):
        case, _, actor, _ = orchestration_fixture()
        with transaction.atomic():
            with self.assertRaises(OrchestrationError) as caught:
                execute(case.pk, "next_question", actor=actor)
        self.assertEqual(caught.exception.code, "transaction_boundary")
        self.assertFalse(AIExecution.objects.exists())

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_identical_calls_reserve_only_one_execution_attempt_and_provider_call(self):
        case, _, actor, _ = orchestration_fixture()
        barrier, release, counter_lock = Barrier(2), Event(), Lock()
        calls = []

        class BlockingFake(FakeAIProvider):
            def next_question(self, request):
                with counter_lock:
                    calls.append(1)
                if not release.wait(10):
                    raise AssertionError("Duplicate receipt did not release fake")
                return super().next_question(request)

        provider = BlockingFake()

        def worker():
            try:
                user = get_user_model().objects.get(pk=actor.pk)
                barrier.wait(timeout=10)
                receipt = execute(case.pk, "next_question", actor=user, provider=provider)
                release.set()
                return receipt
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = [f.result(timeout=20) for f in [pool.submit(worker) for _ in range(2)]]
        self.assertEqual(len({r.execution_id for r in receipts}), 1)
        self.assertCountEqual([r.status for r in receipts], ["running", "succeeded"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(AIAttempt.objects.count(), 1)
        self.assertEqual(AIExecution.objects.get().status, "succeeded")

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_retry_reserves_only_one_new_attempt(self):
        case, _, actor, _ = orchestration_fixture()
        provider = FakeAIProvider("transient")
        first = execute(case.pk, "next_question", actor=actor, provider=provider)
        barrier, release = Barrier(2), Event()

        class RecoveredFake(FakeAIProvider):
            provider_version = "1.transient"

            def __init__(self):
                super().__init__()
                self.provider_version = "1.transient"

            def next_question(self, request):
                if not release.wait(10):
                    raise AssertionError("Retry duplicate did not return")
                return super().next_question(request)

        recovered = RecoveredFake()

        def worker():
            try:
                user = get_user_model().objects.get(pk=actor.pk)
                barrier.wait(timeout=10)
                receipt = execute(case.pk, "next_question", actor=user, provider=recovered, retry=True)
                release.set()
                return receipt
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = [f.result(timeout=20) for f in [pool.submit(worker) for _ in range(2)]]
        self.assertEqual({r.execution_id for r in receipts}, {first.execution_id})
        self.assertEqual(AIAttempt.objects.count(), 2)
        self.assertEqual(AIExecution.objects.get().status, "succeeded")


class OrchestrationMigrationTests(TransactionTestCase):
    def test_upgrade_0008_preserves_origin_snapshots_and_does_not_invent_processing(self):
        connection = connections["default"]
        executor = MigrationExecutor(connection)
        before = [("preconsultas", "0008_source_provenance_summary_revisions")]
        executor.migrate(before)
        try:
            case, reception, doctor, source_id = orchestration_fixture()
            source_values = dict(SourceItem.objects.filter(pk=source_id).values().get())
            source = SourceItem.objects.get(pk=source_id)
            item = SummaryItem.objects.create(consultation=case, item_key="upgrade-ai-ficticio", section="Teste",
                                              label="Teste", original_value="Fictício", attribution="ai")
            item.sources.add(source)
            old = executor.loader.project_state(before).apps
            old.get_model("preconsultas", "SummaryRevision").objects.create(
                consultation_id=case.pk, summary_item_id=item.pk, logical_key=item.item_key, number=1,
                created_at=timezone.now(), created_by_id=doctor.pk, section="Teste", label="Teste", attribution="ai",
                original_value="Fictício", presented_value="Fictício")
        finally:
            restored = MigrationExecutor(connection)
            restored.migrate(restored.loader.graph.leaf_nodes())
        self.assertEqual(SourceItem.objects.filter(pk=source_id).values().get(), source_values)
        self.assertEqual(SummaryRevision.objects.count(), 1)
        self.assertEqual(ConsentEvidence.objects.count(), 1)
        self.assertEqual(Consultation.objects.get(pk=case.pk).status, "in_progress")
        self.assertFalse(AIExecution.objects.exists())
        self.assertFalse(AIAttempt.objects.exists())
        self.assertFalse(AIExecutionSource.objects.exists())

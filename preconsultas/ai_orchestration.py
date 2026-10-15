"""Synchronous technical orchestration. No release, domain state writes or logs."""
from copy import deepcopy
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.utils import timezone

from .ai_contract import ContractError, ERROR_CODES, OPERATIONS, VERSION, fingerprint, token, validate_request, validate_response
from .ai_provider import FakeAIProvider, ProviderFailure
from .clinical_access import clinical_guard
from .models import AIExecution, AIExecutionSource, AIAttempt, Consultation
from .state_engine import require_consent, InvalidTransition
from .traceability import _case, _check_source, _id

STATES = {
    "next_question": frozenset({Consultation.STATUS_IN_PROGRESS}),
    "extract_structured": frozenset({Consultation.STATUS_IN_PROGRESS, Consultation.STATUS_AWAITING_PATIENT,
                                     Consultation.STATUS_COMPLETED, Consultation.STATUS_READY}),
    "build_summary": frozenset({Consultation.STATUS_COMPLETED, Consultation.STATUS_READY}),
}
RETRYABLE = frozenset({"provider_unavailable", "transient_failure"})


class OrchestrationError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__("Não foi possível concluir a operação técnica de IA.")


@dataclass(frozen=True)
class ExecutionReceipt:
    execution_id: int
    status: str
    attempt_count: int
    error_code: str = ""


def _actor(actor):
    if not actor or not actor.is_authenticated or not actor.is_active:
        raise PermissionDenied
    current = get_user_model().objects.filter(pk=actor.pk, is_active=True).first()
    if current is None:
        raise PermissionDenied
    return current


def _consent(case):
    evidence = case.consent_evidence.order_by("-pk").first()
    try:
        require_consent(case, Consultation.STATUS_IN_PROGRESS, evidence.term_version if evidence else None)
    except InvalidTransition:
        raise OrchestrationError("precondition_failed") from None
    return evidence


def _request(case, operation, *, lock=False):
    evidence = _consent(case)
    query = case.sources.order_by("pk")
    if lock:
        query = query.select_for_update()
    sources = list(query[:101])
    wire = []
    for source in sources:
        try:
            _check_source(source)
        except ValidationError:
            raise OrchestrationError("invalid_provenance") from None
        message = source.inbound_message if source.inbound_message_id else None
        # Content, metadata and provenance participate, not merely row IDs.
        snapshot = {"id": source.pk, "consultation_id": source.consultation_id,
                    "key": source.source_key, "kind": source.kind, "author": source.author,
                    "sent_at": source.sent_at.isoformat(), "body": source.body,
                    "filename": source.filename, "description": source.description,
                    "duration_seconds": source.duration_seconds, "transcript": source.demo_transcript,
                    "materialized_at": source.materialized_at.isoformat() if source.materialized_at else None,
                    "materialized_by": source.materialized_by_id,
                    "inbound": None if not message else {
                        "id": message.pk, "text": message.text, "media": message.media,
                        "declared_at": message.declared_at.isoformat(), "received_at": message.received_at.isoformat(),
                        "operator": message.operator_id, "consent": message.consent_id,
                        "version": message.contract_version, "external_id": message.external_event_id,
                        "origin": message.origin}}
        # Media references without processed content are never interpreted as transcripts.
        content = source.body if source.kind == "message" else source.demo_transcript
        wire.append({"source_id": source.pk, "version": fingerprint(snapshot), "kind": source.kind,
                     "author": source.author, "text": content,
                     "media": deepcopy(message.media) if message and message.kind != "text" else None,
                     "provenance": None if not message else {
                         "message_id": message.pk, "consent_id": message.consent_id,
                         "input_contract": message.contract_version, "origin": message.origin,
                         "external_event_id": message.external_event_id}})
    request = {"contract_version": VERSION, "operation": operation, "consultation_id": case.pk,
               "consent": {"id": evidence.pk, "version": evidence.term_version}, "sources": wire}
    request["context_id"] = fingerprint(request)
    validate_request(request)
    return request


def _receipt(execution):
    return ExecutionReceipt(execution.pk, execution.status, execution.attempts.count(), execution.error_code)


def _stale(execution):
    execution.status = "obsolete"
    execution.error_code = "obsolete_context"
    execution.finished_at = timezone.now()
    execution.save(update_fields=["status", "error_code", "finished_at"])


def execute(consultation_id, operation, *, actor, provider=None, retry=False):
    """Two transactions around an untrusted provider call; no network in the fake.

    Duplicate in-flight calls return running. Only explicit transient retries (3
    total attempts). A crash leaves running for human investigation, no timeout.
    """
    if type(operation) is not str or operation not in OPERATIONS or type(retry) is not bool:
        raise ContractError()
    actor = _actor(actor)
    provider = provider if provider is not None else FakeAIProvider()
    token(provider.provider_id)
    token(provider.provider_version)
    try:
        with transaction.atomic(durable=True):
            case = _case(consultation_id, actor, lock=True)
            if case.status not in STATES[operation]:
                raise OrchestrationError("precondition_failed")
            request = _request(case, operation, lock=True)
            identity = fingerprint({"context": request["context_id"], "provider": provider.provider_id,
                                    "provider_version": provider.provider_version})
            execution = AIExecution.objects.filter(identity=identity).first()
            if execution:
                if (execution.status != "failed" or not retry or execution.error_code not in RETRYABLE
                        or execution.attempts.count() >= 3):
                    return _receipt(execution)
            else:
                # Superseded outputs are kept, never rewritten into a new context.
                AIExecution.objects.filter(consultation=case, operation=operation, status="succeeded").exclude(
                    context_id=request["context_id"]).update(status="obsolete", error_code="obsolete_context")
                execution = AIExecution.objects.create(
                    consultation=case, operation=operation, contract_version=VERSION,
                    provider_id=provider.provider_id, provider_version=provider.provider_version,
                    context_id=request["context_id"], identity=identity, request=request,
                    created_at=timezone.now(), created_by=actor,
                )
                for source in request["sources"]:
                    AIExecutionSource.objects.create(execution=execution, source_id=source["source_id"], version=source["version"])
            attempt = AIAttempt.objects.create(execution=execution, number=execution.attempts.count() + 1,
                                               actor=actor, started_at=timezone.now())
            execution.status, execution.error_code, execution.finished_at = "running", "", None
            execution.save(update_fields=["status", "error_code", "finished_at"])
        result, error = None, ""
        try:
            raw = getattr(provider, operation)(deepcopy(request))
            result = validate_response(raw, request)
        except ContractError as failure:
            error = failure.code if type(failure.code) is str and failure.code in ERROR_CODES else "invalid_contract"
        except ProviderFailure as failure:
            error = failure.code if type(failure.code) is str and failure.code in RETRYABLE else "provider_failure"
        except Exception:
            # Never persist exception strings, tracebacks or malformed payloads.
            error = "provider_failure"
        with transaction.atomic(durable=True):
            # Provider cannot authorize persistence; recheck active actor and scope.
            try:
                current_actor = _actor(actor)
                case = _case(consultation_id, current_actor, lock=True)
            except PermissionDenied:
                # Lock same row without reading clinical content; failed receipt only.
                case = Consultation.objects.select_for_update().get(pk=consultation_id)
                error, result = "authorization_changed", None
            execution = AIExecution.objects.select_for_update().get(pk=execution.pk)
            attempt = AIAttempt.objects.get(pk=attempt.pk)
            obsolete = False
            if error != "authorization_changed":
                try:
                    current = _request(case, operation, lock=True)
                    obsolete = (case.status not in STATES[operation] or current != request)
                except (ContractError, OrchestrationError):
                    obsolete = True
            status = "obsolete" if obsolete else "failed" if error else "succeeded"
            attempt.status, attempt.error_code = status, "obsolete_context" if obsolete else error
            attempt.result, attempt.finished_at = result, timezone.now()
            attempt.save(update_fields=["status", "error_code", "result", "finished_at"])
            execution.status, execution.error_code = status, attempt.error_code
            execution.result, execution.finished_at = result, attempt.finished_at
            execution.save(update_fields=["status", "error_code", "result", "finished_at"])
            return _receipt(execution)
    except DatabaseError:
        raise OrchestrationError("persistence_failure") from None
    except RuntimeError:
        # Durable transactions reject outer atomic callers before provider calls.
        raise OrchestrationError("transaction_boundary") from None


@clinical_guard
def current_result(consultation_id, execution_id, *, actor):
    """Clinical read only ready; validate freshness AND output at consumption."""
    actor = _actor(actor)
    _id(execution_id)
    try:
        with transaction.atomic():
            case = _case(consultation_id, actor, clinical=True, lock=True)
            from .models import ClinicalPublication
            publication = ClinicalPublication.objects.filter(consultation=case).first()
            if publication and publication.execution_id != execution_id:
                raise PermissionDenied
            execution = AIExecution.objects.filter(pk=execution_id, consultation=case).first()
            if execution is None:
                raise PermissionDenied
            if execution.status != "succeeded":
                return None
            try:
                return _validated_result(case, execution, lock=True)
            except (ContractError, OrchestrationError):
                _stale(execution)
                return None
    except DatabaseError:
        raise OrchestrationError("persistence_failure") from None


def _validated_result(case, execution, *, lock=False):
    """INTERNAL, no read authorization: caller must enforce read OR publication scope.

    Allows completed validation without pretending clinical content is released.
    No state mutation, no provider call, no public HTTP endpoint.
    """
    if (execution.consultation_id != case.pk or execution.status != "succeeded"
            or execution.finished_at is None
            or execution.contract_version != VERSION or execution.operation not in OPERATIONS):
        raise ContractError("invalid_contract")
    token(execution.provider_id)
    token(execution.provider_version)
    accepted = execution.attempts.order_by("-number").first()
    if not accepted or accepted.status != "succeeded" or accepted.result != execution.result or accepted.finished_at is None:
        raise ContractError("invalid_contract")
    request = _request(case, execution.operation, lock=lock)
    if request != execution.request or request["context_id"] != execution.context_id:
        raise ContractError("obsolete_context")
    identity = fingerprint({"context": execution.context_id, "provider": execution.provider_id,
                            "provider_version": execution.provider_version})
    if identity != execution.identity:
        raise ContractError("context_mismatch")
    refs = list(execution.source_references.order_by("source_id").values("source_id", "version"))
    if refs != [{"source_id": s["source_id"], "version": s["version"]} for s in request["sources"]]:
        raise ContractError("invalid_provenance")
    return validate_response(execution.result, request)

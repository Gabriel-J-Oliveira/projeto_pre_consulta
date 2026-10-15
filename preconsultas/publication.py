"""Controlled simulated publication and clinical writes. No provider invocation."""
from dataclasses import dataclass
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.utils import timezone

from .ai_contract import ContractError
from .ai_orchestration import OrchestrationError, _actor, _validated_result
from .models import (AIExecution, ClinicalPublication, Consultation, Correction, DoctorNote,
                     Feedback, OperationalEvent, SummaryItem)
from .traceability import _case, _id, record_summary_revision
from .clinical_access import clinical_guard


class PublicationError(Exception):
    def __init__(self):
        super().__init__("Publicação indisponível; exige resultado válido e nova validação explícita.")


@dataclass(frozen=True)
class PublicationReceipt:
    publication_id: int
    created: bool


def _result(case, execution, *, lock=False):
    if execution.operation != "build_summary" or execution.provider_id != "fake":
        raise PublicationError()
    try:
        return _validated_result(case, execution, lock=lock)
    except (ContractError, OrchestrationError, ValidationError):
        raise PublicationError() from None


def validate_publication(case, publication, *, lock=False):
    """Internal validity only; require_clinical applies authenticated scope separately."""
    try:
        result = _result(case, publication.execution, lock=lock)
        refs = list(publication.execution.source_references.order_by("source_id").values("source_id", "version"))
        if (publication.consultation_id != case.pk or not publication.is_simulated
                or publication.requires_validation_at is not None
                or publication.doctor_id != case.doctor_id or publication.clinic_id != case.clinic_id
                or publication.context_id != publication.execution.context_id
                or publication.source_snapshot != refs or publication.result_snapshot != result
                or publication.event.consultation_id != case.pk or publication.event.actor_id != publication.actor_id
                or publication.event.kind != OperationalEvent.KIND_READY or not publication.event.is_simulated
                or publication.event.origin != "local_simulation" or publication.event.previous_status != "completed"
                or publication.event.next_status != "ready" or publication.event.occurred_at != publication.published_at):
            raise PublicationError()
        expected = {(kind, item["key"]): item for kind, items in
                    (("item", result["result"]["items"]), ("attention", result["result"]["attention_points"]))
                    for item in items}
        items = list(case.summary_items.prefetch_related("sources"))
        if len(items) != len(expected) or not expected:
            raise PublicationError()
        for item in items:
            value = expected.get((item.publication_kind, item.publication_key))
            if (item.publication_id != publication.pk or not value or item.original_value != value["text"]
                    or item.publication_basis != value["basis"] or item.attribution != SummaryItem.ATTR_AI
                    or sorted(item.sources.values_list("pk", flat=True)) != sorted(r["source_id"] for r in value["references"])):
                raise PublicationError()
    except PublicationError:
        # Uniform denial, not exception payload, on ALL clinical readers/POSTs.
        raise PermissionDenied("Publicação exige nova validação explícita.") from None
    return result


@clinical_guard
def publish_consultation(consultation_id, execution_id, *, actor):
    actor = _actor(actor)
    _id(execution_id)
    try:
        with transaction.atomic():
            case = _case(consultation_id, actor, lock=True)
            execution = AIExecution.objects.filter(pk=execution_id, consultation=case).first()
            if execution is None:
                raise PermissionDenied
            existing = ClinicalPublication.objects.filter(consultation=case).select_related("execution").first()
            if existing:
                if case.status == "ready" and existing.execution_id == execution_id:
                    from .clinical_access import require_clinical
                    require_clinical(case, actor=actor, lock=True)
                    return PublicationReceipt(existing.pk, False)
                raise PublicationError()
            if case.status != Consultation.STATUS_COMPLETED or case.summary_items.exists() or case.legacy_demo:
                raise PublicationError()
            result = _result(case, execution, lock=True)
            if not result["result"]["items"]:
                # Conservative acceptance: attention-only/empty output is not a summary.
                raise PublicationError()
            now = timezone.now()
            event = OperationalEvent.objects.create(
                consultation=case, event_key=f"publish-{uuid4().hex}", kind=OperationalEvent.KIND_READY,
                occurred_at=now, actor=actor, is_simulated=True, origin="local_simulation",
                previous_status="completed", next_status="ready",
                detail="Publicação SIMULADA explícita; material disponível para revisão, não aprovação clínica.")
            publication = ClinicalPublication.objects.create(
                consultation=case, doctor=case.doctor, clinic=case.clinic, actor=actor, execution=execution, published_at=now,
                context_id=execution.context_id, result_snapshot=result,
                source_snapshot=list(execution.source_references.order_by("source_id").values("source_id", "version")),
                event=event)
            order = 0
            for kind, values in (("item", result["result"]["items"]), ("attention", result["result"]["attention_points"])):
                for value in values:
                    order += 1
                    item = SummaryItem.objects.create(
                        consultation=case, publication=publication, publication_key=value["key"],
                        publication_kind=kind, publication_basis=value["basis"],
                        item_key=f"pub-{publication.pk}-{kind}-{order}",
                        section="Síntese simulada" if kind == "item" else "Pontos para revisão médica",
                        label=f"Informação {order}" if kind == "item" else f"Observação para revisão {order}",
                        original_value=value["text"], attribution=SummaryItem.ATTR_AI, display_order=order)
                    item.sources.set([ref["source_id"] for ref in value["references"]])
            if Consultation.objects.filter(pk=case.pk, status="completed").update(status="ready") != 1:
                raise PublicationError()
            case.status = "ready"
            # Initial presentation snapshots have known capturing author.
            for item in publication.items.all():
                record_summary_revision(case.pk, item.pk, actor=actor)
            return PublicationReceipt(publication.pk, True)
    except DatabaseError:
        raise PublicationError() from None


def publication_candidate(consultation_id, *, actor):
    """Dashboard receives only a validated execution ID, NEVER its clinical payload."""
    actor = _actor(actor)
    with transaction.atomic():
        case = _case(consultation_id, actor, lock=True)
        if case.status != "completed" or case.legacy_demo or case.summary_items.exists():
            return None
        for execution in case.ai_executions.filter(operation="build_summary", status="succeeded").order_by("-pk"):
            try:
                result = _result(case, execution, lock=True)
                if result["result"]["items"]:
                    return execution.pk
            except PublicationError:
                pass
    return None


@clinical_guard
def review_action(consultation_id, *, actor, action, data):
    """Serialize review on consultation, recheck scope/publication and capture atomically."""
    actor = _actor(actor)
    try:
        with transaction.atomic():
            case = _case(consultation_id, actor, clinical=True, lock=True)
            if action == "note":
                from .forms import DoctorNoteForm
                form = DoctorNoteForm(data)
            elif action == "correction":
                from .forms import CorrectionForm
                form = CorrectionForm(data)
            elif action == "feedback":
                from .forms import FeedbackForm
                form = FeedbackForm(data)
            else:
                raise ValidationError("Ação de revisão inválida.")
            if not form.is_valid():
                raise ValidationError("Dados de revisão inválidos.")
            values = form.cleaned_data
            if action == "note":
                return DoctorNote.objects.create(consultation=case, actor=actor, text=values["text"])
            item_id = values.get("summary_item_id")
            item = case.summary_items.filter(pk=item_id).first() if item_id else None
            if item_id and item is None:
                raise PermissionDenied
            if action == "feedback":
                return Feedback.objects.create(consultation=case, actor=actor, summary_item=item, kind=values["kind"])
            updates = item.corrections.filter(action="update").order_by("created_at", "pk")
            previous_action = item.corrections.order_by("created_at", "pk").last()
            if (previous_action and previous_action.actor_id == actor.pk and previous_action.action == values["action"]
                    and previous_action.new_value == values["new_value"].strip()):
                return previous_action
            latest = updates.last()
            # Preserve the observed pre-correction presentation, including legacy
            # cases with no prior snapshot. Capturing actor is not historic author.
            record_summary_revision(case.pk, item.pk, actor=actor)
            correction = Correction.objects.create(summary_item=item, actor=actor, action=values["action"],
                                                     previous_value=latest.new_value if latest else item.original_value,
                                                     new_value=values["new_value"].strip())
            record_summary_revision(case.pk, item.pk, actor=actor)
            return correction
    except DatabaseError:
        raise PublicationError() from None

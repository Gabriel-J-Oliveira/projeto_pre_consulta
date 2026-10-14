"""Internal provenance and snapshots. No generation, publication or transport."""
from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.utils import timezone

from .ingestion import validate_envelope
from .models import (
    ConsentEvidence, Consultation, Correction, InboundMessage, OperationalEvent,
    SourceItem, SummaryItem, SummaryRevision, SummaryRevisionSource,
)
from .permissions import doctor_consultations


class TraceabilityPersistenceError(Exception):
    pass


@dataclass(frozen=True)
class MaterializationReceipt:
    source_id: int
    created: bool


def _id(value):
    if type(value) is not int or not 0 < value <= 2**63 - 1:
        raise PermissionDenied
    return value


def _medical_cases(actor):
    if not actor or not actor.is_authenticated or not actor.is_active:
        raise PermissionDenied
    return doctor_consultations(actor)


def _case(consultation_id, actor, *, clinical=False, lock=False):
    _id(consultation_id)
    cases = _medical_cases(actor)
    if lock:
        cases = cases.select_for_update()
    case = cases.filter(pk=consultation_id).first()
    if not case or (clinical and case.status != Consultation.STATUS_READY):
        raise PermissionDenied
    return case


def _validated_message(message):
    evidence = message.consent
    event = evidence.event
    if (not message.is_simulated or evidence.consultation_id != message.consultation_id
            or evidence.manifestation != ConsentEvidence.ACCEPTED or not evidence.is_simulated
            or evidence.origin != message.origin or event.consultation_id != message.consultation_id
            or event.kind != OperationalEvent.KIND_CONSENT_RECORDED or not event.is_simulated
            or event.origin != message.origin or event.actor_id != evidence.operator_id):
        raise ValidationError("Proveniência da entrada inconsistente.")
    payload = {"consultation_id": message.consultation_id, "origin": message.origin,
               "contract_version": message.contract_version, "external_event_id": message.external_event_id,
               "kind": message.kind, "declared_at": message.declared_at.isoformat(),
               "consent_version": evidence.term_version}
    payload["text" if message.kind == "text" else "media"] = message.text if message.kind == "text" else message.media
    validate_envelope(payload)


def _source_values(message):
    return {
        "kind": SourceItem.KIND_MESSAGE if message.kind == "text" else message.kind,
        "author": SourceItem.AUTHOR_SIMULATION, "sent_at": message.declared_at,
        "body": message.text if message.kind == "text" else "Referência simulada de mídia; conteúdo não processado.",
        "filename": message.media.get("filename", ""),
        "description": "Origem local_simulation; não comprova identidade ou consentimento real.",
    }


def _check_source(source):
    if source.inbound_message_id:
        message = source.inbound_message
        _validated_message(message)
        if (source.consultation_id != message.consultation_id or not source.materialized_at
                or not source.materialized_by_id
                or any(getattr(source, key) != value for key, value in _source_values(message).items())):
            raise ValidationError("Proveniência da fonte inconsistente.")


def materialize_message(consultation_id, message_id, *, actor):
    """Doctor-scoped write returns IDs only, even on unpublished cases.

    A validated historical entry may be materialized after collection: this
    preserves evidence, never grants a clinical read or changes state.
    """
    _id(message_id)
    try:
        with transaction.atomic():
            case = _case(consultation_id, actor, lock=True)
            message = InboundMessage.objects.filter(pk=message_id, consultation=case).select_related("consent__event").first()
            if message is None:
                raise PermissionDenied
            _validated_message(message)
            existing = SourceItem.objects.filter(inbound_message=message).first()
            if existing:
                _check_source(existing)
                return MaterializationReceipt(existing.pk, False)
            source = SourceItem.objects.create(
                consultation=case, inbound_message=message, source_key=f"inbound-{message.pk}",
                materialized_at=timezone.now(), materialized_by=actor, **_source_values(message),
            )
            return MaterializationReceipt(source.pk, True)
    except DatabaseError:
        raise TraceabilityPersistenceError("Não foi possível persistir a rastreabilidade.") from None


def source_provenance(consultation_id, source_id, *, actor):
    _id(source_id)
    case = _case(consultation_id, actor, clinical=True)
    source = SourceItem.objects.filter(pk=source_id, consultation=case).select_related("inbound_message__consent__event").first()
    if source is None:
        raise PermissionDenied
    _check_source(source)
    if not source.inbound_message_id:
        return {"legacy": True, "source_id": source.pk, "message_id": None}
    message = source.inbound_message
    return {
        "legacy": False, "source_id": source.pk, "message_id": message.pk,
        "consultation_id": case.pk, "origin": message.origin, "external_event_id": message.external_event_id,
        "contract_version": message.contract_version, "consent_id": message.consent_id,
        "consent_version": message.consent.term_version, "declared_at": message.declared_at,
        "received_at": message.received_at, "operator_id": message.operator_id,
        "materialized_at": source.materialized_at, "materialized_by_id": source.materialized_by_id,
        "is_simulated": message.is_simulated, "media": dict(message.media),
    }


def record_summary_revision(consultation_id, item_id, *, actor):
    """Snapshot existing values/corrections/references, never generate a summary.

    Same observed snapshot is idempotent. Capturing actor is not retroactive
    authorship of legacy corrections. No writes to SummaryItem/Correction.
    """
    _id(item_id)
    try:
        with transaction.atomic():
            case = _case(consultation_id, actor, clinical=True, lock=True)
            item = SummaryItem.objects.filter(pk=item_id, consultation=case).first()
            if not item:
                raise PermissionDenied
            sources = list(item.sources.select_related("inbound_message__consent__event").order_by("pk"))
            for source in sources:
                if source.consultation_id != case.pk:
                    raise ValidationError("Referências de fontes inconsistentes.")
                _check_source(source)
            corrections = list(item.corrections.order_by("created_at", "pk"))
            updates = [c for c in corrections if c.action == Correction.ACTION_UPDATE]
            latest = corrections[-1] if corrections else None
            values = {
                "section": item.section, "label": item.label, "attribution": item.attribution,
                "original_value": item.original_value,
                "presented_value": updates[-1].new_value if updates else item.original_value,
                "is_hidden": bool(latest and latest.action == Correction.ACTION_HIDE),
                "correction_reference": latest.pk if latest else None,
            }
            previous = SummaryRevision.objects.filter(consultation=case, logical_key=item.item_key).order_by("-number").first()
            source_ids = [source.pk for source in sources]
            if (previous and all(getattr(previous, key) == value for key, value in values.items())
                    and list(previous.sources.order_by("pk").values_list("pk", flat=True)) == source_ids):
                return previous.pk
            revision = SummaryRevision.objects.create(
                consultation=case, summary_item=item, logical_key=item.item_key,
                number=previous.number + 1 if previous else 1,
                created_at=timezone.now(), created_by=actor, **values,
            )
            for source in sources:
                SummaryRevisionSource.objects.create(revision=revision, source=source)
            return revision.pk
    except DatabaseError:
        raise TraceabilityPersistenceError("Não foi possível persistir a rastreabilidade.") from None


def summary_revisions(consultation_id, item_id, *, actor):
    _id(item_id)
    case = _case(consultation_id, actor, clinical=True)
    if not SummaryItem.objects.filter(pk=item_id, consultation=case).exists():
        raise PermissionDenied
    revisions = SummaryRevision.objects.filter(consultation=case, summary_item_id=item_id).prefetch_related("sources")
    result = []
    for revision in revisions:
        sources = list(revision.sources.all())
        if any(source.consultation_id != case.pk for source in sources):
            raise ValidationError("Referências de fontes inconsistentes.")
        for source in sources:
            _check_source(source)
        result.append({
            "id": revision.pk, "logical_key": revision.logical_key, "number": revision.number,
            "created_at": revision.created_at, "created_by_id": revision.created_by_id,
            "original_value": revision.original_value, "presented_value": revision.presented_value,
            "section": revision.section, "label": revision.label, "attribution": revision.attribution,
            "is_hidden": revision.is_hidden, "correction_reference": revision.correction_reference,
            "source_ids": tuple(source.pk for source in sources),
        })
    return tuple(result)


def patient_history(patient_id, *, actor):
    """No lookup outside current doctor's ready scope and no sources prefetched."""
    _id(patient_id)
    cases = _medical_cases(actor).filter(patient_id=patient_id, status=Consultation.STATUS_READY).order_by("scheduled_for", "pk")
    return tuple(cases.values("id", "slug", "scheduled_for", "doctor_id", "clinic_id", "status"))

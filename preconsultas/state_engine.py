"""Operational state transitions. No clinical release or external integrations."""
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Consultation, OperationalEvent
from .permissions import doctor_consultations, reception_clinics


# Keep persisted legacy values and presentation intact: not_started = registered,
# in_progress = collecting. ready is a legacy clinical-release state, NOT completed.
ALLOWED_TRANSITIONS = {
    Consultation.STATUS_NOT_STARTED: frozenset({
        Consultation.STATUS_AWAITING_CONSENT, Consultation.STATUS_CANCELLED,
    }),
    Consultation.STATUS_AWAITING_CONSENT: frozenset({
        Consultation.STATUS_IN_PROGRESS, Consultation.STATUS_CONSENT_DECLINED,
        Consultation.STATUS_CANCELLED,
    }),
    Consultation.STATUS_IN_PROGRESS: frozenset({
        Consultation.STATUS_AWAITING_PATIENT, Consultation.STATUS_INCOMPLETE,
        Consultation.STATUS_CANCELLED,
    }),
    Consultation.STATUS_AWAITING_PATIENT: frozenset({
        Consultation.STATUS_COMPLETED, Consultation.STATUS_INCOMPLETE,
        Consultation.STATUS_CANCELLED,
    }),
    Consultation.STATUS_CONSENT_DECLINED: frozenset(),
    Consultation.STATUS_COMPLETED: frozenset(),
    Consultation.STATUS_INCOMPLETE: frozenset(),
    Consultation.STATUS_CANCELLED: frozenset(),
    Consultation.STATUS_READY: frozenset(),
}


class InvalidTransition(ValidationError):
    pass


def scoped_consultations(actor):
    """Membership, never staff/superuser flags, establishes operational scope."""
    if not actor or not actor.is_authenticated or not actor.is_active:
        raise PermissionDenied
    permitted = Consultation.objects.none()
    try:
        permitted = permitted | doctor_consultations(actor)
    except PermissionDenied:
        pass
    try:
        permitted = permitted | Consultation.objects.filter(clinic__in=reception_clinics(actor))
    except PermissionDenied:
        pass
    return permitted


@transaction.atomic
def transition(consultation_id, target, *, actor, origin="local_simulation"):
    """Explicit authenticated simulation; lock, validate, persist state and audit.

    Only local simulation is enabled now. This is not evidence of real consent,
    confirmation, messaging or processing. No public HTTP transition route exists.
    """
    if origin != "local_simulation":
        raise ValidationError("Somente simulação local de estados está habilitada.")
    consultation = scoped_consultations(actor).select_for_update().filter(pk=consultation_id).first()
    if consultation is None:
        # Uniform denial for nonexistent and out-of-scope IDs; no state disclosure.
        raise PermissionDenied
    previous = consultation.status
    if target not in ALLOWED_TRANSITIONS.get(previous, ()):
        raise InvalidTransition("Transição operacional não permitida.")
    # Conditional update also prevents stale writes on backends without row locks.
    updated = Consultation.objects.filter(pk=consultation.pk, status=previous).update(status=target)
    if updated != 1:
        raise InvalidTransition("O estado mudou durante a operação. Recarregue o registro.")
    OperationalEvent.objects.create(
        consultation=consultation, event_key=f"state-{uuid4().hex}",
        kind=OperationalEvent.KIND_STATE_CHANGED, occurred_at=timezone.now(),
        detail=f"Simulação local: {previous} → {target}. Nenhum serviço externo acionado.",
        is_simulated=True, previous_status=previous, next_status=target,
        origin=origin, actor=actor,
    )
    consultation.status = target
    return consultation

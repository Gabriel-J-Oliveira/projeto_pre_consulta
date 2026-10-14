"""Operational state transitions. No clinical release or external integrations."""
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import ConsentEvidence, Consultation, OperationalEvent
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


# Simulation policy only: both existing internal profiles retain their scopes.
# Unknown origins/roles have no edges; this is not the production actor matrix.
TRANSITION_POLICY = {
    "local_simulation": {
        "doctor": ALLOWED_TRANSITIONS,
        "reception": ALLOWED_TRANSITIONS,
    },
}


def authorized_roles(actor, consultation):
    roles = set()
    try:
        if doctor_consultations(actor).filter(pk=consultation.pk).exists():
            roles.add("doctor")
    except PermissionDenied:
        pass
    try:
        if reception_clinics(actor).filter(pk=consultation.clinic_id).exists():
            roles.add("reception")
    except PermissionDenied:
        pass
    return roles


def lock_scoped_consultation(consultation_id, *, actor, origin):
    if not isinstance(origin, str) or origin not in TRANSITION_POLICY:
        raise ValidationError("Somente simulação local de estados está habilitada.")
    consultation = scoped_consultations(actor).select_for_update().filter(pk=consultation_id).first()
    if consultation is None:
        raise PermissionDenied
    return consultation


def require_consent(consultation, target, consent_version):
    if target not in {Consultation.STATUS_IN_PROGRESS, Consultation.STATUS_CONSENT_DECLINED}:
        return
    evidence = consultation.consent_evidence.order_by("-pk").first()
    expected = (ConsentEvidence.ACCEPTED if target == Consultation.STATUS_IN_PROGRESS
                else ConsentEvidence.DECLINED)
    if (not evidence or not isinstance(consent_version, str) or not consent_version.strip()
            or evidence.term_version != consent_version or evidence.manifestation != expected
            or not evidence.is_simulated or evidence.origin != "local_simulation"
            or evidence.event.consultation_id != consultation.pk
            or evidence.event.kind != OperationalEvent.KIND_CONSENT_RECORDED
            or evidence.event.origin != evidence.origin or not evidence.event.is_simulated
            or evidence.event.actor_id != evidence.operator_id):
        raise InvalidTransition("A manifestação simulada mais recente e sua versão são obrigatórias.")


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
def transition(consultation_id, target, *, actor, origin="local_simulation", consent_version=None):
    """Explicit authenticated simulation; lock, validate, persist state and audit.

    Only local simulation is enabled now. This is not evidence of real consent,
    confirmation, messaging or processing. No public HTTP transition route exists.
    """
    consultation = lock_scoped_consultation(consultation_id, actor=actor, origin=origin)
    previous = consultation.status
    if target not in ALLOWED_TRANSITIONS.get(previous, ()):
        raise InvalidTransition("Transição operacional não permitida.")
    roles = authorized_roles(actor, consultation)
    if not any(target in TRANSITION_POLICY[origin].get(role, {}).get(previous, ()) for role in roles):
        raise PermissionDenied
    require_consent(consultation, target, consent_version)
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

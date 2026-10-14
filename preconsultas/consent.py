"""Internal simulated consent service. No patient authentication or real consent."""
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import ConsentEvidence, Consultation, OperationalEvent
from .state_engine import (
    InvalidTransition, TRANSITION_POLICY, authorized_roles, lock_scoped_consultation, transition,
)


@transaction.atomic
def record_simulated_consent(consultation_id, *, term_version, manifestation, actor,
                             origin="local_simulation"):
    """Append one manifestation per consultation/version while awaiting consent.

    Acceptance does not start collection. Refusal ends this simulated flow
    atomically, preventing collection using an older accepted version.
    operator is the internal simulator, NEVER an authenticated patient.
    """
    consultation = lock_scoped_consultation(consultation_id, actor=actor, origin=origin)
    if consultation.status != Consultation.STATUS_AWAITING_CONSENT:
        raise InvalidTransition("O registro deve estar aguardando consentimento.")
    if not authorized_roles(actor, consultation).intersection(TRANSITION_POLICY[origin]):
        raise ValidationError("Perfil não habilitado para simulação de consentimento.")
    if (not isinstance(term_version, str) or not term_version.strip()
            or term_version != term_version.strip() or len(term_version) > 80
            or any(ord(character) < 32 for character in term_version)):
        raise ValidationError("Informe uma referência de versão válida, com até 80 caracteres.")
    if manifestation not in {ConsentEvidence.ACCEPTED, ConsentEvidence.DECLINED}:
        raise ValidationError("Manifestação simulada inválida.")
    if consultation.consent_evidence.filter(term_version=term_version).exists():
        raise ValidationError("Já existe manifestação para esta consulta e versão.")
    occurred_at = timezone.now()
    event = OperationalEvent.objects.create(
        consultation=consultation, event_key=f"consent-{uuid4().hex}",
        kind=OperationalEvent.KIND_CONSENT_RECORDED, occurred_at=occurred_at,
        detail="Manifestação SIMULADA registrada por operador interno; não é prova real de consentimento.",
        is_simulated=True, origin=origin, actor=actor,
    )
    evidence = ConsentEvidence.objects.create(
        consultation=consultation, term_version=term_version, manifestation=manifestation,
        origin=origin, occurred_at=occurred_at, is_simulated=True, operator=actor, event=event,
    )
    if manifestation == ConsentEvidence.DECLINED:
        transition(consultation.pk, Consultation.STATUS_CONSENT_DECLINED, actor=actor,
                   origin=origin, consent_version=term_version)
    return evidence

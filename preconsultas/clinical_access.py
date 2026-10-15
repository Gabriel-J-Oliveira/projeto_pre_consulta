"""One gate for new published clinical content and explicitly marked demo fixtures."""
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from functools import wraps

from .models import ClinicalPublication, Consultation
from .permissions import doctor_consultations


class ClinicalAccessDenied(PermissionDenied):
    def __init__(self, publication_id, actor):
        self.publication_id = publication_id
        self.actor = actor
        super().__init__("Publicação exige nova validação explícita; republicação não habilitada.")


def clinical_guard(function):
    """Rollback any clinical writes, then persist a metadata-only sticky invalidation."""
    @wraps(function)
    def guarded(*args, **kwargs):
        try:
            with transaction.atomic():
                return function(*args, **kwargs)
        except ClinicalAccessDenied as denied:
            with transaction.atomic():
                publication = ClinicalPublication.objects.get(pk=denied.publication_id)
                Consultation.objects.select_for_update().get(pk=publication.consultation_id)
                if (get_user_model().objects.filter(pk=denied.actor.pk, is_active=True).exists()
                        and doctor_consultations(denied.actor).filter(pk=publication.consultation_id).exists()):
                    ClinicalPublication.objects.filter(pk=publication.pk, requires_validation_at__isnull=True).update(
                        requires_validation_at=timezone.now(), validation_requested_by=denied.actor)
                    from .models import AIExecution
                    AIExecution.objects.filter(pk=publication.execution_id, status="succeeded").update(
                        status="obsolete", error_code="obsolete_context")
            raise
    return guarded


@clinical_guard
def require_clinical(case, *, actor, lock=False):
    if lock:
        case = Consultation.objects.select_for_update().get(pk=case.pk)
    if (not actor or not actor.is_authenticated or not actor.is_active
            or not get_user_model().objects.filter(pk=actor.pk, is_active=True).exists()
            or not doctor_consultations(actor).filter(pk=case.pk).exists()
            or case.status != Consultation.STATUS_READY):
        raise PermissionDenied
    publication = ClinicalPublication.objects.filter(consultation=case).select_related("execution").first()
    if publication is None:
        # Default false. Set only by narrow data migration/demo seed or explicit test fixtures.
        if not case.legacy_demo:
            raise PermissionDenied
        return None
    from .publication import validate_publication
    try:
        if publication.requires_validation_at:
            raise PermissionDenied
        validate_publication(case, publication, lock=lock)
    except PermissionDenied:
        raise ClinicalAccessDenied(publication.pk, actor) from None
    return publication

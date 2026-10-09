from django.core.exceptions import PermissionDenied

from .models import Consultation, Doctor, ReceptionProfile


def default_login_destination(user):
    """Public domain policy consumed by the model-free authentication app."""
    if Doctor.objects.filter(user=user, clinics__isnull=False).exists():
        return "preconsultas:dashboard"
    if ReceptionProfile.objects.filter(user=user, clinics__isnull=False).exists():
        return "recepcao:preconsultations"
    if user.is_active and user.is_staff:
        return "admin:index"
    return "accounts:access_denied"


def doctor_for(user):
    doctor = Doctor.objects.filter(user=user).first()
    if not doctor or not doctor.clinics.exists():
        raise PermissionDenied
    return doctor


def doctor_consultations(user):
    doctor = doctor_for(user)
    return Consultation.objects.filter(doctor=doctor, clinic__in=doctor.clinics.all())


def reception_clinics(user):
    profile = ReceptionProfile.objects.filter(user=user).first()
    if not profile or not profile.clinics.exists():
        raise PermissionDenied
    return profile.clinics.all()

from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .demo_media import DEMO_MEDIA_FILES
from .permissions import doctor_for, doctor_consultations, reception_clinics
from .forms import (
    CorrectionForm,
    DoctorNoteForm,
    FeedbackForm,
    ReceptionPreconsultationForm,
)
from .models import (
    Clinic,
    Consultation,
    Correction,
    Doctor,
    Feedback,
    SourceItem,
    SummaryItem,
)


DEMO_SLUG = "demo-pronta"

STATUS_PRESENTATION = {
    Consultation.STATUS_READY: {
        "css": "ready",
        "help": "Síntese disponível para revisão.",
    },
    Consultation.STATUS_IN_PROGRESS: {
        "css": "progress",
        "help": "Paciente ainda está respondendo.",
    },
    Consultation.STATUS_NOT_STARTED: {
        "css": "not-started",
        "help": "Pré-consulta ainda não iniciada.",
    },
    Consultation.STATUS_INCOMPLETE: {
        "css": "incomplete",
        "help": "Acesso médico pendente de definição.",
    },
    Consultation.STATUS_CONSENT_DECLINED: {
        "css": "declined",
        "help": "Conteúdo indisponível; consentimento não concedido.",
    },
}


def _effective_scheduled_for(consultation, today=None):
    local_value = timezone.localtime(consultation.scheduled_for)
    if consultation.demo_day_offset is None:
        return local_value
    today = today or timezone.localdate()
    effective_date = today + timedelta(days=consultation.demo_day_offset)
    naive_value = datetime.combine(effective_date, local_value.time().replace(tzinfo=None))
    return timezone.make_aware(naive_value, timezone.get_current_timezone())


def _decorate_appointment(consultation, today=None):
    consultation.display_scheduled_for = _effective_scheduled_for(consultation, today)
    presentation = STATUS_PRESENTATION[consultation.status]
    consultation.status_css = presentation["css"]
    consultation.status_help = presentation["help"]
    consultation.can_open = (
        consultation.status == Consultation.STATUS_READY
    )
    consultation.detail_url = (
        reverse("preconsultas:demo") if consultation.slug == DEMO_SLUG
        else reverse("preconsultas:detail", args=[consultation.slug])
    )
    return consultation


def _decorate_operational_events(consultation):
    stored_appointment = timezone.localtime(consultation.scheduled_for)
    delta = consultation.display_scheduled_for - stored_appointment
    events = list(consultation.operational_events.all())
    for event in events:
        event.display_occurred_at = timezone.localtime(event.occurred_at) + delta
    consultation.display_events = events
    return consultation


def _consultation(request, slug=DEMO_SLUG):
    consultation = get_object_or_404(
        doctor_consultations(request.user).select_related("patient", "doctor", "clinic"),
        slug=slug,
    )
    if consultation.status != Consultation.STATUS_READY:
        raise PermissionDenied
    consultation.scheduled_for = _effective_scheduled_for(consultation)
    return consultation


@login_required
@require_GET
def dashboard(request):
    doctor = doctor_for(request.user)
    today = timezone.localdate()
    selected_date = parse_date(request.GET.get("data", "")) or today
    query = request.GET.get("q", "").strip()[:100]
    clinic_value = request.GET.get("clinica", "").strip()

    appointments = list(
        doctor_consultations(request.user).select_related("patient", "doctor", "clinic")
    )
    for appointment in appointments:
        _decorate_appointment(appointment, today)
    appointments.sort(key=lambda item: item.display_scheduled_for)

    clinics = sorted(
        {appointment.clinic for appointment in appointments},
        key=lambda clinic: clinic.name,
    )
    allowed_clinic_ids = {str(clinic.id) for clinic in clinics}
    if clinic_value not in allowed_clinic_ids:
        clinic_value = ""

    day_appointments = [
        item
        for item in appointments
        if item.display_scheduled_for.date() == selected_date
        and (not clinic_value or str(item.clinic_id) == clinic_value)
    ]
    visible_appointments = [
        item
        for item in day_appointments
        if not query or query.casefold() in item.patient.name.casefold()
    ]

    now = timezone.localtime()
    upcoming = [
        item
        for item in day_appointments
        if item.display_scheduled_for >= now
    ] if selected_date == today else (day_appointments if selected_date > today else [])
    next_appointment = upcoming[0] if upcoming else None
    for item in visible_appointments:
        item.is_next = bool(next_appointment and item.pk == next_appointment.pk)

    if query and not visible_appointments:
        empty_state = "search"
    elif not day_appointments:
        empty_state = "date"
    else:
        empty_state = ""

    hour = now.hour
    greeting = "Bom dia" if hour < 12 else "Boa tarde" if hour < 18 else "Boa noite"

    return render(
        request,
        "preconsultas/dashboard.html",
        {
            "doctor": doctor,
            "greeting": greeting,
            "today": today,
            "selected_date": selected_date,
            "is_today": selected_date == today,
            "query": query,
            "clinics": clinics,
            "selected_clinic": clinic_value,
            "appointments": visible_appointments,
            "next_appointment": next_appointment,
            "empty_state": empty_state,
            "indicators": {
                "total": len(day_appointments),
                "ready": sum(item.status == Consultation.STATUS_READY for item in day_appointments),
                "progress": sum(item.status == Consultation.STATUS_IN_PROGRESS for item in day_appointments),
            },
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def reception_preconsultations(request):
    allowed_clinics = reception_clinics(request.user)
    today = timezone.localdate()
    form = ReceptionPreconsultationForm(
        request.POST if request.method == "POST" else None,
        allowed_clinics=allowed_clinics,
        initial={
            "scheduled_date": today,
            "scheduled_time": "09:00",
            "contact_lead_hours": 48,
        },
    )
    open_form = request.method == "POST"
    if request.method == "POST" and form.is_valid():
        consultation = form.save()
        messages.success(
            request,
            "Pré-consulta fictícia cadastrada. Nenhum convite foi enviado.",
        )
        consultation_date = timezone.localtime(consultation.scheduled_for).date()
        return redirect(
            f"{reverse('recepcao:preconsultations')}?data={consultation_date.isoformat()}"
            f"&selecionar={consultation.id}&criado=1"
        )

    selected_date = parse_date(request.GET.get("data", "")) or today
    query = request.GET.get("q", "").strip()[:100]
    doctor_value = request.GET.get("medico", "").strip()
    clinic_value = request.GET.get("clinica", "").strip()
    status_value = request.GET.get("estado", "").strip()

    doctors = list(Doctor.objects.filter(clinics__in=allowed_clinics).distinct().prefetch_related("clinics").order_by("name"))
    clinics = list(allowed_clinics.order_by("name"))
    allowed_doctors = {str(doctor.id) for doctor in doctors}
    allowed_clinic_ids = {str(clinic.id) for clinic in clinics}
    allowed_statuses = {value for value, _ in Consultation.STATUS_CHOICES}
    if doctor_value not in allowed_doctors:
        doctor_value = ""
    if clinic_value not in allowed_clinic_ids:
        clinic_value = ""
    if status_value not in allowed_statuses:
        status_value = ""

    appointments = list(
        Consultation.objects.filter(clinic__in=allowed_clinics)
        .select_related("patient", "doctor", "clinic")
        .prefetch_related("operational_events")
    )
    for appointment in appointments:
        _decorate_appointment(appointment, today)
        _decorate_operational_events(appointment)

    appointments = [
        item
        for item in appointments
        if item.display_scheduled_for.date() == selected_date
        and (not query or query.casefold() in item.patient.name.casefold())
        and (not doctor_value or str(item.doctor_id) == doctor_value)
        and (not clinic_value or str(item.clinic_id) == clinic_value)
        and (not status_value or item.status == status_value)
    ]
    appointments.sort(key=lambda item: item.display_scheduled_for)

    records_json = []
    for item in appointments:
        records_json.append(
            {
                "id": item.id,
                "patient": item.patient.name,
                "phone": item.patient.masked_phone,
                "doctor": item.doctor.name,
                "doctor_registration": item.doctor.display_registration,
                "clinic": item.clinic.name,
                "scheduled_date": item.display_scheduled_for.strftime("%d/%m/%Y"),
                "scheduled_time": item.display_scheduled_for.strftime("%H:%M"),
                "appointment_type": item.appointment_type,
                "contact_lead": f"{item.contact_lead_hours} horas — demonstrativo",
                "status": item.get_status_display(),
                "status_css": item.status_css,
                "status_help": item.status_help,
                "events": [
                    {
                        "label": event.get_kind_display(),
                        "date": event.display_occurred_at.strftime("%d/%m/%Y"),
                        "time": event.display_occurred_at.strftime("%H:%M"),
                        "detail": event.detail,
                        "simulated": event.is_simulated,
                    }
                    for event in item.display_events
                ],
            }
        )

    doctor_clinic_map = {
        str(doctor.id): [clinic.id for clinic in doctor.clinics.all() if str(clinic.id) in allowed_clinic_ids]
        for doctor in doctors
    }
    has_filters = bool(query or doctor_value or clinic_value or status_value)

    return render(
        request,
        "preconsultas/reception.html",
        {
            "form": form,
            "open_form": open_form,
            "appointments": appointments,
            "records_json": records_json,
            "doctor_clinic_map": doctor_clinic_map,
            "doctors": doctors,
            "clinics": clinics,
            "status_choices": Consultation.STATUS_CHOICES,
            "selected_date": selected_date,
            "query": query,
            "selected_doctor": doctor_value,
            "selected_clinic": clinic_value,
            "selected_status": status_value,
            "has_filters": has_filters,
            "selected_record_id": request.GET.get("selecionar", ""),
            "created": request.GET.get("criado") == "1",
        },
    )


def _file_for(source):
    filename = DEMO_MEDIA_FILES.get(source.source_key)
    if not filename:
        return None
    root = Path(settings.DEMO_MEDIA_ROOT).resolve()
    candidate = (root / filename).resolve()
    if not candidate.is_relative_to(root):
        return None
    return candidate


def _media_state(source):
    path = _file_for(source)
    available = bool(path and path.is_file())
    return {
        "available": available,
        "url": reverse("preconsultas:attachment_content", args=[source.source_key])
        if available
        else "",
        "message": (
            "Arquivo local pronto para visualização."
            if available
            else "Arquivo demonstrativo ainda não fornecido. A referência foi preservada, mas nenhum conteúdo foi processado."
        ),
    }


@login_required
@require_GET
def demo(request, slug=DEMO_SLUG):
    consultation = _consultation(request, slug)
    items = list(
        consultation.summary_items.prefetch_related("sources", "corrections").all()
    )
    sections = OrderedDict()
    for item in items:
        corrections = list(item.corrections.all())
        updates = [c for c in corrections if c.action == Correction.ACTION_UPDATE]
        latest = corrections[-1] if corrections else None
        item.presented_value = updates[-1].new_value if updates else item.original_value
        item.was_adjusted = bool(updates)
        item.is_hidden = bool(latest and latest.action == Correction.ACTION_HIDE)
        if not item.is_hidden:
            sections.setdefault(item.section, []).append(item)

    timeline = list(consultation.sources.all())
    for source in timeline:
        source.media_state = _media_state(source)
    attachments = [source for source in timeline if source.kind == SourceItem.KIND_PDF]
    audio = next((source for source in timeline if source.kind == SourceItem.KIND_AUDIO), None)

    return render(
        request,
        "preconsultas/demo.html",
        {
            "consultation": consultation,
            "note_url": reverse("preconsultas:add_note") if slug == DEMO_SLUG else reverse("preconsultas:detail_note", args=[slug]),
            "correction_url": reverse("preconsultas:correct_item") if slug == DEMO_SLUG else reverse("preconsultas:detail_correction", args=[slug]),
            "feedback_url": reverse("preconsultas:add_feedback") if slug == DEMO_SLUG else reverse("preconsultas:detail_feedback", args=[slug]),
            "sections": sections.items(),
            "timeline": timeline,
            "attachments": attachments,
            "audio": audio,
            "note_form": DoctorNoteForm(),
            "recent_notes": consultation.doctor_notes.order_by("-created_at")[:3],
            "recent_corrections": Correction.objects.filter(
                summary_item__consultation=consultation
            ).select_related("summary_item").order_by("-created_at", "-id")[:5],
        },
    )


def _form_error(form):
    return JsonResponse(
        {"ok": False, "errors": form.errors.get_json_data()}, status=400
    )


@login_required
@require_POST
def add_note(request, slug=DEMO_SLUG):
    consultation = _consultation(request, slug)
    form = DoctorNoteForm(request.POST)
    if not form.is_valid():
        return _form_error(form)
    note = form.save(commit=False)
    note.consultation = consultation
    note.save()
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "message": "Apontamento salvo na demonstração."})
    messages.success(request, "Apontamento salvo na demonstração.")
    return redirect("preconsultas:demo") if slug == DEMO_SLUG else redirect("preconsultas:detail", slug=slug)


@login_required
@require_POST
def correct_item(request, slug=DEMO_SLUG):
    consultation = _consultation(request, slug)
    form = CorrectionForm(request.POST)
    if not form.is_valid():
        return _form_error(form)
    item = get_object_or_404(
        SummaryItem,
        id=form.cleaned_data["summary_item_id"],
        consultation=consultation,
    )
    updates = item.corrections.filter(action=Correction.ACTION_UPDATE)
    previous_value = updates.last().new_value if updates.exists() else item.original_value
    correction = Correction.objects.create(
        summary_item=item,
        action=form.cleaned_data["action"],
        previous_value=previous_value,
        new_value=form.cleaned_data["new_value"].strip(),
    )
    message = (
        "Informação removida apenas da visualização; a fonte original foi preservada."
        if correction.action == Correction.ACTION_HIDE
        else "Correção demonstrativa salva; a fonte original foi preservada."
    )
    return JsonResponse(
        {
            "ok": True,
            "message": message,
            "item_id": item.id,
            "action": correction.action,
            "new_value": correction.new_value,
        }
    )


@login_required
@require_POST
def add_feedback(request, slug=DEMO_SLUG):
    consultation = _consultation(request, slug)
    form = FeedbackForm(request.POST)
    if not form.is_valid():
        return _form_error(form)
    item = None
    if form.cleaned_data.get("summary_item_id"):
        item = get_object_or_404(
            SummaryItem,
            id=form.cleaned_data["summary_item_id"],
            consultation=consultation,
        )
    kind = form.cleaned_data["kind"]
    Feedback.objects.create(consultation=consultation, summary_item=item, kind=kind)
    return JsonResponse(
        {
            "ok": True,
            "message": f"Feedback “{dict(Feedback.KIND_CHOICES)[kind]}” registrado.",
        }
    )


@login_required
@require_GET
def attachment_status(request, source_key):
    source = get_object_or_404(
        SourceItem,
        consultation__in=doctor_consultations(request.user).filter(status=Consultation.STATUS_READY),
        source_key=source_key,
        kind__in=[SourceItem.KIND_PDF, SourceItem.KIND_AUDIO],
    )
    state = _media_state(source)
    return JsonResponse(
        {
            "ok": True,
            "available": state["available"],
            "url": state["url"],
            "message": state["message"],
            "filename": source.filename or DEMO_MEDIA_FILES.get(source.source_key, ""),
            "description": source.description,
        }
    )


@login_required
@require_GET
def attachment_content(request, source_key):
    source = get_object_or_404(
        SourceItem,
        consultation__in=doctor_consultations(request.user).filter(status=Consultation.STATUS_READY),
        source_key=source_key,
        kind__in=[SourceItem.KIND_PDF, SourceItem.KIND_AUDIO],
    )
    path = _file_for(source)
    if not path or not path.is_file():
        raise Http404("Arquivo demonstrativo ainda não fornecido.")
    content_type = "application/pdf" if source.kind == SourceItem.KIND_PDF else "audio/mpeg"
    return FileResponse(
        path.open("rb"),
        content_type=content_type,
        as_attachment=False,
        filename=path.name,
    )

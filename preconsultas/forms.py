import re
import unicodedata
from datetime import datetime
from uuid import uuid4

from django import forms
from django.db import transaction
from django.utils import timezone

from .models import (
    Clinic,
    Consultation,
    Correction,
    Doctor,
    DoctorNote,
    Feedback,
    OperationalEvent,
    Patient,
)


class DoctorNoteForm(forms.ModelForm):
    class Meta:
        model = DoctorNote
        fields = ["text"]
        widgets = {
            "text": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Ex.: confirmar data do último exame durante a consulta",
                    "aria-label": "Apontamento ou complemento do médico",
                }
            )
        }


class CorrectionForm(forms.Form):
    summary_item_id = forms.IntegerField(min_value=1)
    action = forms.ChoiceField(choices=Correction.ACTION_CHOICES)
    new_value = forms.CharField(max_length=1500, required=False)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("action") == Correction.ACTION_UPDATE and not cleaned.get(
            "new_value", ""
        ).strip():
            self.add_error("new_value", "Informe o novo valor para salvar a correção.")
        return cleaned


class FeedbackForm(forms.Form):
    kind = forms.ChoiceField(choices=Feedback.KIND_CHOICES)
    summary_item_id = forms.IntegerField(min_value=1, required=False)


class ReceptionPreconsultationForm(forms.Form):
    CONTACT_LEAD_CHOICES = [
        (24, "24 horas antes — demonstrativo"),
        (48, "48 horas antes — demonstrativo"),
        (72, "72 horas antes — demonstrativo"),
    ]

    patient_name = forms.CharField(
        label="Nome do paciente",
        max_length=160,
        widget=forms.TextInput(attrs={"placeholder": "Nome fictício para demonstração"}),
    )
    phone = forms.CharField(
        label="Telefone",
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "placeholder": "(11) 99999-0000",
                "inputmode": "tel",
                "autocomplete": "tel",
            }
        ),
    )
    patient_choice = forms.ChoiceField(
        label="Cadastro do paciente", required=False,
        choices=[("", "Selecione uma opção"), ("new", "Criar novo registro")],
        help_text="Nome completo e telefone coincidem. Escolha explicitamente; nenhum cadastro será mesclado.",
    )
    doctor = forms.ModelChoiceField(
        label="Médico",
        queryset=Doctor.objects.none(),
        empty_label="Selecione o médico",
    )
    clinic = forms.ModelChoiceField(
        label="Clínica / local",
        queryset=Clinic.objects.none(),
        empty_label="Selecione a clínica",
    )
    scheduled_date = forms.DateField(
        label="Data da consulta",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    scheduled_time = forms.TimeField(
        label="Hora da consulta",
        widget=forms.TimeInput(attrs={"type": "time"}),
    )
    appointment_type = forms.CharField(
        label="Tipo ou especialidade",
        max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "Ex.: Consulta clínica"}),
    )
    contact_lead_hours = forms.TypedChoiceField(
        label="Antecedência planejada",
        choices=CONTACT_LEAD_CHOICES,
        coerce=int,
        initial=48,
    )

    def __init__(self, *args, allowed_clinics=None, **kwargs):
        super().__init__(*args, **kwargs)
        clinics = allowed_clinics if allowed_clinics is not None else Clinic.objects.none()
        self.allowed_clinics = clinics
        self.patient_candidates = self.find_patient_candidates(
            self.data.get("patient_name", ""), self.data.get("phone", "")
        ) if self.is_bound else []
        if self.patient_candidates:
            self.fields["patient_choice"].choices += [
                (str(patient.pk), f"Reutilizar: {patient.name} · {patient.masked_phone} · registro {patient.pk}")
                for patient in self.patient_candidates
            ]
        else:
            self.fields["patient_choice"].widget = forms.HiddenInput()
        self.fields["doctor"].queryset = Doctor.objects.filter(clinics__in=clinics).distinct().prefetch_related(
            "clinics"
        ).order_by("name")
        self.fields["clinic"].queryset = clinics.order_by("name")

    def clean_phone(self):
        digits = re.sub(r"\D", "", self.cleaned_data["phone"])
        if len(digits) not in {10, 11}:
            raise forms.ValidationError(
                "Informe um telefone fictício com DDD e 10 ou 11 dígitos."
            )
        return digits

    @staticmethod
    def normalize_name(value):
        return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()

    def find_patient_candidates(self, name, phone):
        name = self.normalize_name(name)
        phone = re.sub(r"\D", "", phone)
        if not name or len(phone) not in {10, 11}:
            return []
        # Normalize existing records without changing them or adding unique fields.
        patients = Patient.objects.filter(
            consultation__clinic__in=self.allowed_clinics
        ).only("id", "name", "phone").distinct().order_by("pk")
        return [patient for patient in patients
                if self.normalize_name(patient.name) == name
                and re.sub(r"\D", "", patient.phone) == phone]

    def clean(self):
        cleaned = super().clean()
        doctor = cleaned.get("doctor")
        clinic = cleaned.get("clinic")
        if self.patient_candidates and not cleaned.get("patient_choice"):
            self.add_error("patient_choice", "Escolha reutilizar um paciente ou criar um novo registro.")
        if doctor and clinic and not doctor.clinics.filter(pk=clinic.pk).exists():
            self.add_error(
                "clinic",
                "A clínica selecionada não está vinculada a este médico.",
            )
        return cleaned

    @transaction.atomic
    def save(self):
        if not self.is_valid():
            raise ValueError("Não é possível salvar um formulário inválido.")
        token = uuid4().hex[:12]
        choice = self.cleaned_data.get("patient_choice")
        if choice and choice != "new":
            # Recheck both the identity match and clinic scope at persistence time.
            patient = next((patient for patient in self.find_patient_candidates(
                self.cleaned_data["patient_name"], self.cleaned_data["phone"]
            ) if str(patient.pk) == choice), None)
            if patient is None:
                raise forms.ValidationError("O cadastro selecionado não está mais disponível. Confira os dados.")
        else:
            patient = Patient.objects.create(
                name=self.cleaned_data["patient_name"].strip(),
                phone=self.cleaned_data["phone"],
                age=None,
            )
        scheduled_for = timezone.make_aware(
            datetime.combine(
                self.cleaned_data["scheduled_date"],
                self.cleaned_data["scheduled_time"],
            ),
            timezone.get_current_timezone(),
        )
        consultation = Consultation.objects.create(
            slug=f"recepcao-{token}",
            patient=patient,
            doctor=self.cleaned_data["doctor"],
            clinic=self.cleaned_data["clinic"],
            scheduled_for=scheduled_for,
            appointment_type=self.cleaned_data["appointment_type"].strip(),
            contact_lead_hours=self.cleaned_data["contact_lead_hours"],
            status=Consultation.STATUS_NOT_STARTED,
        )
        now = timezone.now()
        OperationalEvent.objects.create(
            consultation=consultation,
            event_key=f"{consultation.slug}-created",
            kind=OperationalEvent.KIND_CREATED,
            occurred_at=now,
            detail="Registro operacional fictício criado pela recepção.",
        )
        OperationalEvent.objects.create(
            consultation=consultation,
            event_key=f"{consultation.slug}-invite-planned",
            kind=OperationalEvent.KIND_INVITE_PLANNED,
            occurred_at=now,
            detail=(
                f"Contato planejado para {consultation.contact_lead_hours} horas antes "
                "— regra demonstrativa, sem agendamento real."
            ),
        )
        return consultation

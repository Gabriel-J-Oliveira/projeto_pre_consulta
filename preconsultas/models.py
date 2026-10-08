import re

from django.db import models


class Clinic(models.Model):
    name = models.CharField(max_length=160)

    def __str__(self):
        return self.name


class Doctor(models.Model):
    name = models.CharField(max_length=160)
    display_registration = models.CharField(max_length=80)
    clinics = models.ManyToManyField(Clinic, related_name="doctors", blank=True)

    def __str__(self):
        return self.name


class Patient(models.Model):
    name = models.CharField(max_length=160)
    age = models.PositiveSmallIntegerField(null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True)

    @property
    def masked_phone(self):
        digits = re.sub(r"\D", "", self.phone)
        if len(digits) < 4:
            return "Não informado"
        area = digits[:2] if len(digits) >= 10 else "**"
        return f"({area}) *****-{digits[-4:]}"

    def __str__(self):
        return self.name


class Consultation(models.Model):
    STATUS_READY = "ready"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_NOT_STARTED = "not_started"
    STATUS_INCOMPLETE = "incomplete"
    STATUS_CONSENT_DECLINED = "consent_declined"
    STATUS_CHOICES = [
        (STATUS_READY, "Pronta"),
        (STATUS_IN_PROGRESS, "Em andamento"),
        (STATUS_NOT_STARTED, "Não iniciada"),
        (STATUS_INCOMPLETE, "Incompleta"),
        (STATUS_CONSENT_DECLINED, "Consentimento recusado"),
    ]

    slug = models.SlugField(unique=True)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    doctor = models.ForeignKey(Doctor, on_delete=models.PROTECT)
    clinic = models.ForeignKey(Clinic, on_delete=models.PROTECT)
    scheduled_for = models.DateTimeField()
    appointment_type = models.CharField(max_length=100, default="Consulta clínica")
    contact_lead_hours = models.PositiveSmallIntegerField(
        default=48,
        help_text="Valor demonstrativo; a regra definitiva ainda não foi definida.",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    demo_day_offset = models.SmallIntegerField(
        null=True,
        blank=True,
        help_text="Deslocamento relativo à data local, usado somente nos dados fictícios.",
    )

    def __str__(self):
        return f"{self.patient} — {self.get_status_display()}"


class SourceItem(models.Model):
    KIND_MESSAGE = "message"
    KIND_AUDIO = "audio"
    KIND_PDF = "pdf"
    KIND_CHOICES = [
        (KIND_MESSAGE, "Mensagem"),
        (KIND_AUDIO, "Áudio"),
        (KIND_PDF, "PDF"),
    ]

    AUTHOR_PATIENT = "patient"
    AUTHOR_AI = "ai"
    AUTHOR_CHOICES = [
        (AUTHOR_PATIENT, "Paciente"),
        (AUTHOR_AI, "Assistente virtual"),
    ]

    consultation = models.ForeignKey(
        Consultation, related_name="sources", on_delete=models.CASCADE
    )
    source_key = models.SlugField(unique=True)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    author = models.CharField(max_length=20, choices=AUTHOR_CHOICES)
    sent_at = models.DateTimeField()
    body = models.TextField(blank=True)
    filename = models.CharField(max_length=180, blank=True)
    description = models.CharField(max_length=240, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    demo_transcript = models.TextField(blank=True)

    class Meta:
        ordering = ["sent_at", "id"]

    def __str__(self):
        return self.source_key


class SummaryItem(models.Model):
    ATTR_PATIENT = "patient"
    ATTR_AI = "ai"
    ATTR_DOCTOR = "doctor"
    ATTRIBUTION_CHOICES = [
        (ATTR_PATIENT, "Relatado pelo paciente"),
        (ATTR_AI, "Síntese da IA"),
        (ATTR_DOCTOR, "Ajustado pelo médico"),
    ]

    consultation = models.ForeignKey(
        Consultation, related_name="summary_items", on_delete=models.CASCADE
    )
    item_key = models.SlugField(unique=True)
    section = models.CharField(max_length=80)
    label = models.CharField(max_length=120)
    original_value = models.TextField()
    attribution = models.CharField(max_length=20, choices=ATTRIBUTION_CHOICES)
    display_order = models.PositiveIntegerField(default=0)
    sources = models.ManyToManyField(SourceItem, related_name="summary_items")

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return self.label


class DoctorNote(models.Model):
    consultation = models.ForeignKey(
        Consultation, related_name="doctor_notes", on_delete=models.CASCADE
    )
    text = models.TextField(max_length=1200)
    created_at = models.DateTimeField(auto_now_add=True)


class Correction(models.Model):
    ACTION_UPDATE = "update"
    ACTION_HIDE = "hide"
    ACTION_CHOICES = [
        (ACTION_UPDATE, "Corrigir"),
        (ACTION_HIDE, "Remover da visualização"),
    ]

    summary_item = models.ForeignKey(
        SummaryItem, related_name="corrections", on_delete=models.CASCADE
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    previous_value = models.TextField()
    new_value = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class Feedback(models.Model):
    KIND_USEFUL = "useful"
    KIND_IRRELEVANT = "irrelevant"
    KIND_CORRECT = "correct"
    KIND_REMOVE = "remove"
    KIND_CHOICES = [
        (KIND_USEFUL, "Útil"),
        (KIND_IRRELEVANT, "Irrelevante"),
        (KIND_CORRECT, "Corrigir"),
        (KIND_REMOVE, "Remover da visualização"),
    ]

    consultation = models.ForeignKey(
        Consultation, related_name="feedback_entries", on_delete=models.CASCADE
    )
    summary_item = models.ForeignKey(
        SummaryItem, null=True, blank=True, on_delete=models.SET_NULL
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)


class OperationalEvent(models.Model):
    KIND_CREATED = "created"
    KIND_INVITE_PLANNED = "invite_planned"
    KIND_INVITE_SIMULATED = "invite_simulated"
    KIND_AWAITING_CONSENT = "awaiting_consent"
    KIND_INTERVIEW_IN_PROGRESS = "interview_in_progress"
    KIND_READY = "ready"
    KIND_INCOMPLETE = "incomplete"
    KIND_CONSENT_DECLINED = "consent_declined"
    KIND_CHOICES = [
        (KIND_CREATED, "Registro criado"),
        (KIND_INVITE_PLANNED, "Convite previsto"),
        (KIND_INVITE_SIMULATED, "Convite demonstrativo"),
        (KIND_AWAITING_CONSENT, "Aguardando consentimento"),
        (KIND_INTERVIEW_IN_PROGRESS, "Entrevista em andamento"),
        (KIND_READY, "Pré-consulta pronta"),
        (KIND_INCOMPLETE, "Pré-consulta incompleta"),
        (KIND_CONSENT_DECLINED, "Consentimento recusado"),
    ]

    consultation = models.ForeignKey(
        Consultation, related_name="operational_events", on_delete=models.CASCADE
    )
    event_key = models.SlugField(unique=True)
    kind = models.CharField(max_length=30, choices=KIND_CHOICES)
    occurred_at = models.DateTimeField()
    detail = models.CharField(max_length=240)
    is_simulated = models.BooleanField(default=False)

    class Meta:
        ordering = ["occurred_at", "id"]

    def __str__(self):
        return f"{self.consultation.slug}: {self.get_kind_display()}"

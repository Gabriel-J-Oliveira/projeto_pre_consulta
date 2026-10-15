import re
from django.conf import settings
from django.core.exceptions import ValidationError

from django.db import models


class Clinic(models.Model):
    name = models.CharField(max_length=160)

    def __str__(self):
        return self.name


class Doctor(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="doctor",
    )
    name = models.CharField(max_length=160)
    display_registration = models.CharField(max_length=80)
    clinics = models.ManyToManyField(Clinic, related_name="doctors", blank=True)

    def __str__(self):
        return self.name


class ReceptionProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="reception_profile",
    )
    clinics = models.ManyToManyField(Clinic, related_name="reception_profiles", blank=True)

    def __str__(self):
        return str(self.user)


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
    STATUS_AWAITING_CONSENT = "awaiting_consent"
    STATUS_AWAITING_PATIENT = "awaiting_patient"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_READY, "Pronta"),
        (STATUS_IN_PROGRESS, "Em andamento"),
        (STATUS_NOT_STARTED, "Não iniciada"),
        (STATUS_INCOMPLETE, "Incompleta"),
        (STATUS_CONSENT_DECLINED, "Consentimento recusado"),
        (STATUS_AWAITING_CONSENT, "Aguardando consentimento"),
        (STATUS_AWAITING_PATIENT, "Aguardando confirmação do paciente"),
        (STATUS_COMPLETED, "Concluída"),
        (STATUS_CANCELLED, "Cancelada"),
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
    legacy_demo = models.BooleanField(default=False, editable=False)
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
    KIND_IMAGE = "image"
    KIND_CHOICES = [
        (KIND_MESSAGE, "Mensagem"),
        (KIND_AUDIO, "Áudio"),
        (KIND_PDF, "PDF"),
        (KIND_IMAGE, "Referência de imagem"),
    ]

    AUTHOR_PATIENT = "patient"
    AUTHOR_AI = "ai"
    AUTHOR_SIMULATION = "simulation"
    AUTHOR_CHOICES = [
        (AUTHOR_PATIENT, "Paciente"),
        (AUTHOR_AI, "Assistente virtual"),
        (AUTHOR_SIMULATION, "Entrada simulada"),
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
    inbound_message = models.OneToOneField(
        "InboundMessage", null=True, blank=True, on_delete=models.PROTECT,
        related_name="clinical_source",
    )
    materialized_at = models.DateTimeField(null=True, blank=True, editable=False)
    materialized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="materialized_sources",
    )

    class Meta:
        ordering = ["sent_at", "id"]

    def __str__(self):
        return self.source_key

    def clean(self):
        if self.inbound_message_id:
            if (self.consultation_id != self.inbound_message.consultation_id
                    or not self.materialized_at or not self.materialized_by_id):
                raise ValidationError("Proveniência da fonte inconsistente.")

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk, inbound_message__isnull=False).exists():
            raise ValidationError("Fontes materializadas devem preservar a origem.")
        self.clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk, inbound_message__isnull=False).exists():
            raise ValidationError("Fontes materializadas devem ser preservadas.")
        return super().delete(*args, **kwargs)


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
    publication = models.ForeignKey("ClinicalPublication", null=True, blank=True, on_delete=models.PROTECT,
                                    related_name="items")
    publication_key = models.CharField(max_length=120, blank=True)
    publication_kind = models.CharField(max_length=10, blank=True)
    publication_basis = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["display_order", "id"]
        constraints = [models.UniqueConstraint(fields=["publication", "publication_kind", "publication_key"],
                                               name="unique_publication_item")]

    def __str__(self):
        return self.label


class DoctorNote(models.Model):
    consultation = models.ForeignKey(
        Consultation, related_name="doctor_notes", on_delete=models.CASCADE
    )
    text = models.TextField(max_length=1200)
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                              related_name="clinical_notes")


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
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                              related_name="clinical_corrections")

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
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                              related_name="clinical_feedback")


class OperationalEvent(models.Model):
    KIND_CONSENT_RECORDED = "consent_recorded"
    KIND_STATE_CHANGED = "state_changed"
    KIND_CREATED = "created"
    KIND_INVITE_PLANNED = "invite_planned"
    KIND_INVITE_SIMULATED = "invite_simulated"
    KIND_AWAITING_CONSENT = "awaiting_consent"
    KIND_INTERVIEW_IN_PROGRESS = "interview_in_progress"
    KIND_READY = "ready"
    KIND_INCOMPLETE = "incomplete"
    KIND_CONSENT_DECLINED = "consent_declined"
    KIND_CHOICES = [
        (KIND_CONSENT_RECORDED, "Manifestação simulada registrada"),
        (KIND_STATE_CHANGED, "Estado operacional alterado"),
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
    previous_status = models.CharField(max_length=20, blank=True)
    next_status = models.CharField(max_length=20, blank=True)
    origin = models.CharField(max_length=30, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="preconsultation_state_events",
    )

    class Meta:
        ordering = ["occurred_at", "id"]

    def __str__(self):
        return f"{self.consultation.slug}: {self.get_kind_display()}"


class ConsentEvidence(models.Model):
    """Simulated manifestation, not patient identity or legal proof.

    Domain services append records; there is no consent Admin or public endpoint.
    Raw SQL/QuerySet writes are not an immutable storage boundary.
    """
    ACCEPTED = "accepted"
    DECLINED = "declined"
    LOCAL_SIMULATION = "local_simulation"
    consultation = models.ForeignKey(
        Consultation, related_name="consent_evidence", on_delete=models.PROTECT,
    )
    term_version = models.CharField(max_length=80)
    manifestation = models.CharField(
        max_length=8, choices=[(ACCEPTED, "Aceite simulado"), (DECLINED, "Recusa simulada")],
    )
    origin = models.CharField(max_length=30, default=LOCAL_SIMULATION, editable=False)
    occurred_at = models.DateTimeField(editable=False)
    is_simulated = models.BooleanField(default=True, editable=False)
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="simulated_consent_evidence",
    )
    event = models.OneToOneField(
        OperationalEvent, on_delete=models.PROTECT, related_name="consent_evidence",
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["consultation", "term_version"], name="unique_consent_consultation_version",
            ),
            models.CheckConstraint(
                condition=models.Q(is_simulated=True, origin="local_simulation"),
                name="consent_simulation_only",
            ),
            models.CheckConstraint(
                condition=models.Q(manifestation__in=["accepted", "declined"]),
                name="consent_manifestation_valid",
            ),
            models.CheckConstraint(
                condition=~models.Q(term_version=""), name="consent_version_not_empty",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Evidências não podem ser sobrescritas; registre uma nova versão.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Evidências simuladas devem ser preservadas.")


class InboundMessage(models.Model):
    """Durable private input; NOT a clinical SourceItem or operational payload."""
    consultation = models.ForeignKey(Consultation, on_delete=models.PROTECT, related_name="inbound_messages")
    origin = models.CharField(max_length=30, default="local_simulation")
    external_event_id = models.CharField(max_length=120)
    contract_version = models.CharField(max_length=20)
    kind = models.CharField(max_length=5, choices=[
        ("text", "Texto"), ("audio", "Referência de áudio"),
        ("image", "Referência de imagem"), ("pdf", "Referência de PDF"),
    ])
    text = models.TextField(blank=True)
    media = models.JSONField(default=dict, blank=True)
    declared_at = models.DateTimeField()
    received_at = models.DateTimeField(editable=False)
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                 related_name="simulated_inbound_messages")
    consent = models.ForeignKey(ConsentEvidence, on_delete=models.PROTECT, related_name="inbound_messages")
    is_simulated = models.BooleanField(default=True, editable=False)

    class Meta:
        ordering = ["received_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["origin", "consultation", "external_event_id"],
                                    name="unique_inbound_namespace_event"),
            models.CheckConstraint(condition=models.Q(origin="local_simulation", is_simulated=True),
                                   name="inbound_simulation_only"),
            models.CheckConstraint(condition=models.Q(contract_version="sim.v1"), name="inbound_contract_v1"),
            models.CheckConstraint(condition=models.Q(kind__in=["text", "audio", "image", "pdf"]),
                                   name="inbound_kind_valid"),
            models.CheckConstraint(condition=~models.Q(external_event_id=""), name="inbound_id_not_empty"),
            models.CheckConstraint(
                condition=(models.Q(kind="text", media={}) & ~models.Q(text=""))
                | (models.Q(kind__in=["audio", "image", "pdf"], text="") & ~models.Q(media={})),
                name="inbound_content_matches_kind",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Mensagens recebidas não podem ser sobrescritas.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Mensagens recebidas devem ser preservadas.")


class SummaryRevision(models.Model):
    """Append-only snapshot of the EXISTING SummaryItem presentation, not AI DTOs."""
    consultation = models.ForeignKey(Consultation, on_delete=models.PROTECT, related_name="summary_revisions")
    summary_item = models.ForeignKey(SummaryItem, on_delete=models.PROTECT, related_name="revisions")
    logical_key = models.SlugField()
    number = models.PositiveIntegerField()
    created_at = models.DateTimeField(editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name="summary_revisions")
    section = models.CharField(max_length=80)
    label = models.CharField(max_length=120)
    attribution = models.CharField(max_length=20, choices=SummaryItem.ATTRIBUTION_CHOICES)
    original_value = models.TextField()
    presented_value = models.TextField()
    is_hidden = models.BooleanField(default=False)
    # Snapshot reference only: demo reset may delete Correction without erasing history.
    correction_reference = models.PositiveBigIntegerField(null=True, blank=True)
    sources = models.ManyToManyField(SourceItem, through="SummaryRevisionSource", related_name="revisions")

    class Meta:
        ordering = ["number", "id"]
        constraints = [
            models.UniqueConstraint(fields=["consultation", "logical_key", "number"], name="unique_summary_revision"),
            models.CheckConstraint(condition=models.Q(number__gte=1), name="summary_revision_positive"),
        ]

    def clean(self):
        if (self.summary_item.consultation_id != self.consultation_id
                or self.summary_item.item_key != self.logical_key):
            raise ValidationError("Contexto da revisão inconsistente.")

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Revisões anteriores não podem ser sobrescritas.")
        self.clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Revisões anteriores devem ser preservadas.")


class SummaryRevisionSource(models.Model):
    revision = models.ForeignKey(SummaryRevision, on_delete=models.PROTECT, related_name="source_references")
    source = models.ForeignKey(SourceItem, on_delete=models.PROTECT, related_name="revision_references")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["revision", "source"], name="unique_revision_source")]

    def clean(self):
        if self.revision.consultation_id != self.source.consultation_id:
            raise ValidationError("Fonte e revisão devem pertencer à mesma consulta.")

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Referências de revisão não podem ser sobrescritas.")
        self.clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Referências de revisão devem ser preservadas.")


class AIExecution(models.Model):
    """Private technical processing, NEVER a clinical presentation or release."""
    consultation = models.ForeignKey(Consultation, on_delete=models.PROTECT, related_name="ai_executions")
    operation = models.CharField(max_length=20)
    contract_version = models.CharField(max_length=20)
    provider_id = models.CharField(max_length=120)
    provider_version = models.CharField(max_length=120)
    context_id = models.CharField(max_length=64)
    identity = models.CharField(max_length=64, unique=True)
    request = models.JSONField()
    status = models.CharField(max_length=12, default="running")
    result = models.JSONField(null=True, blank=True)
    error_code = models.CharField(max_length=30, blank=True)
    created_at = models.DateTimeField(editable=False)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name="ai_executions")

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(operation__in=["next_question", "extract_structured", "build_summary"]),
                                   name="ai_execution_operation"),
            models.CheckConstraint(condition=models.Q(contract_version="ai.v1"), name="ai_execution_contract"),
            models.CheckConstraint(condition=models.Q(status__in=["running", "succeeded", "failed", "obsolete"]),
                                   name="ai_execution_status"),
            models.CheckConstraint(condition=~models.Q(status="succeeded") | models.Q(result__isnull=False),
                                   name="ai_execution_success_result"),
        ]


class AIAttempt(models.Model):
    execution = models.ForeignKey(AIExecution, on_delete=models.PROTECT, related_name="attempts")
    number = models.PositiveSmallIntegerField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ai_attempts")
    started_at = models.DateTimeField(editable=False)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, default="running")
    error_code = models.CharField(max_length=30, blank=True)
    # Only structurally validated output; malformed/raw provider errors are discarded.
    result = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["execution", "number"], name="ai_attempt_number"),
            models.CheckConstraint(condition=models.Q(number__gte=1, number__lte=3), name="ai_attempt_bounds"),
            models.CheckConstraint(condition=models.Q(status__in=["running", "succeeded", "failed", "obsolete"]),
                                   name="ai_attempt_status"),
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exclude(status="running").exists():
            raise ValidationError("Tentativas finalizadas devem ser preservadas.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Tentativas técnicas devem ser preservadas.")


class AIExecutionSource(models.Model):
    execution = models.ForeignKey(AIExecution, on_delete=models.PROTECT, related_name="source_references")
    source = models.ForeignKey(SourceItem, on_delete=models.PROTECT, related_name="ai_references")
    version = models.CharField(max_length=64)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["execution", "source"], name="ai_execution_source_unique")]

    def clean(self):
        if self.execution.consultation_id != self.source.consultation_id:
            raise ValidationError("Referência técnica fora da consulta.")

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Referência técnica deve ser preservada.")
        self.clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Referências técnicas devem ser preservadas.")


class ClinicalPublication(models.Model):
    """Explicit initial simulated publication; not a signed clinical approval."""
    consultation = models.OneToOneField(Consultation, on_delete=models.PROTECT, related_name="publication")
    doctor = models.ForeignKey(Doctor, on_delete=models.PROTECT, related_name="publications")
    clinic = models.ForeignKey(Clinic, on_delete=models.PROTECT, related_name="publications")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="clinical_publications")
    execution = models.ForeignKey(AIExecution, on_delete=models.PROTECT, related_name="publications")
    published_at = models.DateTimeField(editable=False)
    context_id = models.CharField(max_length=64)
    result_snapshot = models.JSONField()
    source_snapshot = models.JSONField()
    is_simulated = models.BooleanField(default=True, editable=False)
    requires_validation_at = models.DateTimeField(null=True, blank=True, editable=False)
    validation_requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                                on_delete=models.PROTECT, related_name="publication_validations")
    event = models.OneToOneField(OperationalEvent, on_delete=models.PROTECT, related_name="clinical_publication")

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(is_simulated=True), name="publication_simulation_only")]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Publicações anteriores devem ser preservadas.")
        if (self.execution.consultation_id != self.consultation_id or self.execution.operation != "build_summary"
                or self.event.consultation_id != self.consultation_id):
            raise ValidationError("Publicação inconsistente.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Publicações anteriores devem ser preservadas.")

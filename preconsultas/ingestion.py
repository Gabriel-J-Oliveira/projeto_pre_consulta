"""Channel-independent internal ingestion of strictly simulated messages."""
import json
import re
from dataclasses import dataclass
from datetime import timezone as datetime_timezone

from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Consultation, InboundMessage
from .state_engine import InvalidTransition, lock_scoped_consultation, require_consent

CONTRACT_VERSION = "sim.v1"
MAX_TEXT_LENGTH = 8000
MAX_MEDIA_SIZE = 25 * 1024 * 1024  # Declared metadata only; never a download.
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}\Z")
MIME_TYPES = {
    "audio": {"audio/mpeg", "audio/ogg", "audio/wav"},
    "image": {"image/jpeg", "image/png", "image/webp"},
    "pdf": {"application/pdf"},
}


class InvalidEnvelope(ValidationError):
    def __init__(self):
        # Never interpolate the payload, identifiers, text or media into errors.
        super().__init__("Contrato de entrada simulado inválido.", code="invalid_envelope")


class IngestionPersistenceError(Exception):
    """Sanitized persistence failure; the transaction has been rolled back."""


@dataclass(frozen=True)
class IngestionReceipt:
    status: str  # created | redelivered | conflict
    message_id: int
    is_simulated: bool = True


def _string(value, maximum, *, identifier=False):
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or "\x00" in value or any(0xD800 <= ord(char) <= 0xDFFF for char in value)):
        raise InvalidEnvelope()
    if identifier and not IDENTIFIER.fullmatch(value):
        raise InvalidEnvelope()
    return value


def validate_envelope(payload):
    common = {"origin", "contract_version", "consultation_id", "external_event_id",
              "kind", "declared_at", "consent_version"}
    if not isinstance(payload, dict) or not common <= payload.keys():
        raise InvalidEnvelope()
    if payload["origin"] != "local_simulation" or payload["contract_version"] != CONTRACT_VERSION:
        raise InvalidEnvelope()
    if type(payload["consultation_id"]) is not int or not 0 < payload["consultation_id"] <= 2**63 - 1:
        raise InvalidEnvelope()
    external_id = _string(payload["external_event_id"], 120, identifier=True)
    consent_version = _string(payload["consent_version"], 80)
    kind = payload["kind"]
    if not isinstance(kind, str) or kind not in {"text", *MIME_TYPES}:
        raise InvalidEnvelope()
    expected = common | ({"text"} if kind == "text" else {"media"})
    if payload.keys() != expected:
        # Unknown identity/auth fields and mixed content are rejected, not trusted.
        raise InvalidEnvelope()
    declared = _string(payload["declared_at"], 40)
    try:
        declared_at = parse_datetime(declared)
        if declared_at is None or timezone.is_naive(declared_at):
            raise ValueError
        declared_at = declared_at.astimezone(datetime_timezone.utc)
    except (ValueError, OverflowError):
        raise InvalidEnvelope() from None
    text, media = "", {}
    if kind == "text":
        text = _string(payload["text"], MAX_TEXT_LENGTH)
    else:
        media = payload["media"]
        if not isinstance(media, dict) or media.keys() != {"reference", "mime_type", "filename", "size_bytes"}:
            raise InvalidEnvelope()
        _string(media["reference"], 120, identifier=True)  # Opaque fictitious reference, not URL/path.
        mime_type = _string(media["mime_type"], 40)
        if mime_type not in MIME_TYPES[kind]:
            raise InvalidEnvelope()
        filename = _string(media["filename"], 180)
        if any(ord(char) < 32 or char in "/\\" for char in filename):
            raise InvalidEnvelope()
        if type(media["size_bytes"]) is not int or not 0 < media["size_bytes"] <= MAX_MEDIA_SIZE:
            raise InvalidEnvelope()
        media = dict(media)
    return {
        "origin": "local_simulation", "contract_version": CONTRACT_VERSION,
        "consultation_id": payload["consultation_id"], "external_event_id": external_id,
        "kind": kind, "text": text, "media": media, "declared_at": declared_at,
        "consent_version": consent_version,
    }


def canonical_content(data):
    """Stable equivalence excluding receiver/operator/generated time/DB IDs."""
    return json.dumps({
        "contract_version": data["contract_version"], "kind": data["kind"],
        "text": data["text"], "media": data["media"],
        "declared_at": data["declared_at"].astimezone(datetime_timezone.utc).isoformat(timespec="microseconds"),
        "consent_version": data["consent_version"],
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def ingest_message(payload, *, actor):
    """Validate current scope/state/consent even on replay; return metadata only.

    Serializes on Consultation with consent/state services in PostgreSQL, backed
    by a namespace unique constraint. No state update, SourceItem or clinical read.
    """
    data = validate_envelope(payload)
    try:
        with transaction.atomic():
            consultation = lock_scoped_consultation(data["consultation_id"], actor=actor, origin=data["origin"])
            if consultation.status != Consultation.STATUS_IN_PROGRESS:
                raise InvalidTransition("Ingestão simulada disponível somente durante a coleta.")
            require_consent(consultation, Consultation.STATUS_IN_PROGRESS, data["consent_version"])
            existing = InboundMessage.objects.filter(
                origin=data["origin"], consultation=consultation,
                external_event_id=data["external_event_id"],
            ).select_related("consent").first()
            if existing:
                stored = {
                    "contract_version": existing.contract_version, "kind": existing.kind,
                    "text": existing.text, "media": existing.media, "declared_at": existing.declared_at,
                    "consent_version": existing.consent.term_version,
                }
                status = "redelivered" if canonical_content(stored) == canonical_content(data) else "conflict"
                return IngestionReceipt(status, existing.pk)
            evidence = consultation.consent_evidence.latest("pk")
            message = InboundMessage.objects.create(
                consultation=consultation, origin=data["origin"], external_event_id=data["external_event_id"],
                contract_version=data["contract_version"], kind=data["kind"], text=data["text"], media=data["media"],
                declared_at=data["declared_at"], received_at=timezone.now(), operator=actor,
                consent=evidence, is_simulated=True,
            )
            return IngestionReceipt("created", message.pk)
    except DatabaseError:
        raise IngestionPersistenceError("Não foi possível persistir a entrada simulada.") from None

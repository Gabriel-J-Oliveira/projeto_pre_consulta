"""Deterministic fixtures, invoked by tests only; never seeds a preserved DB."""
from .ingestion import ingest_message


def simulation_envelopes(consultation_id, *, consent_version="sim-v1"):
    base = {"origin": "local_simulation", "contract_version": "sim.v1",
            "consultation_id": consultation_id, "consent_version": consent_version}
    messages = [
        {**base, "external_event_id": "sim-text-2", "kind": "text",
         "declared_at": "2026-01-01T12:02:00Z", "text": "Mensagem fictícia número dois."},
        {**base, "external_event_id": "sim-text-1", "kind": "text",
         "declared_at": "2026-01-01T12:01:00Z", "text": "Mensagem fictícia número um."},
    ]
    messages.append(dict(messages[0]))  # Explicit replay, no duplicate persistence.
    for kind, mime_type, extension in [
        ("audio", "audio/mpeg", "mp3"), ("image", "image/png", "png"), ("pdf", "application/pdf", "pdf"),
    ]:
        messages.append({**base, "external_event_id": f"sim-{kind}", "kind": kind,
                         "declared_at": "2026-01-01T12:03:00Z", "media": {
                             "reference": f"sim-media-{kind}", "mime_type": mime_type,
                             "filename": f"arquivo-ficticio.{extension}", "size_bytes": 1024,
                         }})
    return messages


def run_simulation(consultation_id, *, actor, consent_version="sim-v1"):
    """Caller must supply an isolated fictitious collecting case and valid actor.

    Does not create users/consent, infer patient identity or change state.
    No production/validation DB guard can prove fictitiousness; use test runner.
    """
    return [ingest_message(payload, actor=actor) for payload in
            simulation_envelopes(consultation_id, consent_version=consent_version)]

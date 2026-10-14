"""Reusable offline fixtures and provider conformance harness, without Django."""
from copy import deepcopy

from .ai_contract import OPERATIONS, fingerprint, validate_request, validate_response


def sample_request(operation="next_question", kind="message"):
    request = {"contract_version": "ai.v1", "operation": operation, "consultation_id": 123,
               "consent": {"id": 10, "version": "sim-v1"}, "sources": [{
                   "source_id": 1, "version": fingerprint({"fixture": "ficticia-v1"}),
                   "kind": "message", "author": "simulation", "text": "Informação exclusivamente fictícia.",
                   "media": None, "provenance": {"message_id": 2, "consent_id": 10,
                       "input_contract": "sim.v1", "origin": "local_simulation", "external_event_id": "sim-1"}}]}
    if kind != "message":
        mime, filename = {"audio": ("audio/mpeg", "ficticio.mp3"), "image": ("image/png", "ficticio.png"),
                          "pdf": ("application/pdf", "ficticio.pdf")}[kind]
        request["sources"][0].update(kind=kind, text="", version=fingerprint({"fixture": kind}),
                                     media={"reference": "sim-" + kind, "mime_type": mime,
                                            "filename": filename, "size_bytes": 1024})
    request["context_id"] = fingerprint(request)
    return request


def check_provider(provider, *, deterministic=False):
    """Call with network-free adapter in tests. Real adapter must stub transport.

    Structural conformance is not semantic/clinical safety certification.
    Returns responses for inspection; never stores or logs input/output.
    """
    results = {}
    for operation in sorted(OPERATIONS):
        request = sample_request(operation)
        original = deepcopy(request)
        validate_request(request)
        response = getattr(provider, operation)(request)
        validated = validate_response(response, original)
        if request != original:
            raise AssertionError("Provider mutated its input.")
        if deterministic and validated != validate_response(getattr(provider, operation)(deepcopy(original)), original):
            raise AssertionError("Provider is not deterministic.")
        results[operation] = validated
        for kind in ("audio", "image", "pdf"):
            media_request = sample_request(operation, kind)
            media_original = deepcopy(media_request)
            media_result = validate_response(getattr(provider, operation)(media_request), media_original)
            if media_request != media_original:
                raise AssertionError("Provider mutated its input.")
            if deterministic and media_result != validate_response(
                    getattr(provider, operation)(deepcopy(media_original)), media_original):
                raise AssertionError("Provider is not deterministic.")
    return results

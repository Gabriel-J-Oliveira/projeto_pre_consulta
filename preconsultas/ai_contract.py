"""Pure Python ai.v1 wire contract. No Django, credentials or transport."""
import hashlib
import json
import re

VERSION = "ai.v1"
OPERATIONS = frozenset({"next_question", "extract_structured", "build_summary"})
MAX_SOURCES = 100
MAX_TEXT = 8000
MAX_ITEMS = 50
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}\Z")
DIGEST = re.compile(r"[a-f0-9]{64}\Z")
ERROR_CODES = frozenset({"invalid_contract", "unsupported_version", "context_mismatch", "invalid_provenance",
                         "provider_unavailable", "transient_failure", "provider_failure"})
MIME = {"audio": {"audio/mpeg", "audio/ogg", "audio/wav"},
        "image": {"image/jpeg", "image/png", "image/webp"}, "pdf": {"application/pdf"}}


class ContractError(Exception):
    def __init__(self, code="invalid_contract"):
        self.code = code
        super().__init__("Contrato técnico de IA inválido.")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode("ascii")).hexdigest()


def fields(value, expected):
    if type(value) is not dict or value.keys() != set(expected):
        raise ContractError()


def text(value, maximum=MAX_TEXT):
    if (type(value) is not str or not value.strip() or len(value) > maximum
            or any(ord(c) < 32 and c not in "\n\t\r" or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
        raise ContractError()


def positive(value):
    if type(value) is not int or not 0 < value <= 2**63 - 1:
        raise ContractError()


def digest(value):
    if type(value) is not str or not DIGEST.fullmatch(value):
        raise ContractError()


def token(value):
    if type(value) is not str or not TOKEN.fullmatch(value):
        raise ContractError()


def _header(value):
    if value["contract_version"] != VERSION:
        raise ContractError("unsupported_version")
    if type(value["operation"]) is not str or value["operation"] not in OPERATIONS:
        raise ContractError()
    digest(value["context_id"])


def validate_request(request):
    fields(request, {"contract_version", "operation", "context_id", "consultation_id", "consent", "sources"})
    _header(request)
    positive(request["consultation_id"])
    fields(request["consent"], {"id", "version"})
    positive(request["consent"]["id"])
    text(request["consent"]["version"], 80)
    sources = request["sources"]
    if type(sources) is not list or not 1 <= len(sources) <= MAX_SOURCES:
        raise ContractError()
    ids = []
    for source in sources:
        fields(source, {"source_id", "version", "kind", "author", "text", "media", "provenance"})
        positive(source["source_id"])
        ids.append(source["source_id"])
        digest(source["version"])
        if source["kind"] not in ("message", "audio", "image", "pdf") or source["author"] not in ("patient", "ai", "simulation"):
            raise ContractError()
        if source["text"] != "":
            text(source["text"])
        if type(source["text"]) is not str:
            raise ContractError()
        media = source["media"]
        if media is not None:
            fields(media, {"reference", "mime_type", "filename", "size_bytes"})
            token(media["reference"])
            text(media["mime_type"], 40)
            text(media["filename"], 180)
            positive(media["size_bytes"])
            if (media["size_bytes"] > 25 * 1024 * 1024
                    or any(ord(c) < 32 or c in "/\\" for c in media["filename"])):
                raise ContractError()
            if media["mime_type"] not in MIME.get(source["kind"], set()):
                raise ContractError()
        provenance = source["provenance"]
        if provenance is not None:
            fields(provenance, {"message_id", "consent_id", "input_contract", "origin", "external_event_id"})
            positive(provenance["message_id"])
            positive(provenance["consent_id"])
            token(provenance["external_event_id"])
            if provenance["input_contract"] != "sim.v1" or provenance["origin"] != "local_simulation":
                raise ContractError()
        if source["kind"] == "message" and (not source["text"].strip() or media is not None):
            raise ContractError()
    if len(ids) != len(set(ids)) or ids != sorted(ids):
        raise ContractError()
    unsigned = {k: v for k, v in request.items() if k != "context_id"}
    if fingerprint(unsigned) != request["context_id"]:
        raise ContractError("context_mismatch")
    return request


def _refs(refs, available):
    if type(refs) is not list or not 1 <= len(refs) <= MAX_SOURCES:
        raise ContractError("invalid_provenance")
    ids = []
    for ref in refs:
        fields(ref, {"source_id", "version"})
        positive(ref["source_id"])
        digest(ref["version"])
        if available.get(ref["source_id"]) != ref["version"]:
            raise ContractError("invalid_provenance")
        ids.append(ref["source_id"])
    if len(ids) != len(set(ids)):
        raise ContractError("invalid_provenance")


def _items(items, available):
    if type(items) is not list or len(items) > MAX_ITEMS:
        raise ContractError()
    keys = []
    for item in items:
        fields(item, {"key", "text", "basis", "references"})
        token(item["key"])
        keys.append(item["key"])
        text(item["text"], 2000)
        # Derived/simulated is deliberately NOT an authenticated patient statement.
        if item["basis"] not in ("source_excerpt", "derived", "simulation"):
            raise ContractError()
        _refs(item["references"], available)
    if len(keys) != len(set(keys)):
        raise ContractError()


def error_envelope(request, code):
    """Portable sanitized error DTO; Python providers raise ProviderFailure instead."""
    validate_request(request)
    if code not in ERROR_CODES:
        raise ContractError()
    return {"contract_version": VERSION, "operation": request["operation"], "context_id": request["context_id"],
            "error": {"code": code, "retryable": code in {"provider_unavailable", "transient_failure"},
                      "message": "Falha técnica de IA; nenhum conteúdo publicado."}}


def validate_response(response, request):
    validate_request(request)
    fields(response, {"contract_version", "operation", "context_id", "result"})
    _header(response)
    if response["operation"] != request["operation"] or response["context_id"] != request["context_id"]:
        raise ContractError("context_mismatch")
    available = {s["source_id"]: s["version"] for s in request["sources"]}
    result = response["result"]
    if request["operation"] == "next_question":
        fields(result, {"question", "references"})
        text(result["question"], 1000)
        _refs(result["references"], available)
    elif request["operation"] == "extract_structured":
        fields(result, {"items"})
        _items(result["items"], available)
    else:
        fields(result, {"items", "attention_points"})
        _items(result["items"], available)
        _items(result["attention_points"], available)
    if request["operation"] != "next_question":
        source_texts = {s["source_id"]: s["text"] for s in request["sources"]}
        for item in result["items"] + result.get("attention_points", []):
            if item["basis"] == "source_excerpt" and not any(
                    item["text"] in source_texts[ref["source_id"]] for ref in item["references"]):
                raise ContractError("invalid_provenance")
    # Snapshot decoupled from provider-owned mutable objects; bounded by schema.
    return json.loads(canonical(response))

"""Provider port and offline deterministic fake; no domain imports or network."""
from copy import deepcopy
from typing import Protocol

from .ai_contract import validate_request


class ProviderFailure(Exception):
    def __init__(self, code="provider_unavailable"):
        self.code = code if code in {"provider_unavailable", "transient_failure"} else "provider_failure"
        super().__init__("Falha técnica do provedor.")


class AIProvider(Protocol):
    provider_id: str
    provider_version: str

    def next_question(self, request: dict) -> dict: ...
    def extract_structured(self, request: dict) -> dict: ...
    def build_summary(self, request: dict) -> dict: ...


class FakeAIProvider:
    provider_id = "fake"

    def __init__(self, scenario="normal"):
        if scenario not in {"normal", "invalid", "unavailable", "transient"}:
            raise ValueError("Cenário fictício inválido.")
        self.scenario = scenario
        self.provider_version = f"1.{scenario}"

    def _run(self, request, operation):
        validate_request(request)
        if request["operation"] != operation:
            from .ai_contract import ContractError
            raise ContractError()
        if self.scenario in {"unavailable", "transient"}:
            raise ProviderFailure("provider_unavailable" if self.scenario == "unavailable" else "transient_failure")
        refs = [{"source_id": s["source_id"], "version": s["version"]} for s in request["sources"]]
        items = [{"key": f"source-{s['source_id']}",
                  "text": s["text"].strip()[:2000] if s["text"] else "Referência fictícia de mídia não processada.",
                  "basis": "source_excerpt" if s["text"] else "simulation", "references": [ref]}
                 for s, ref in zip(request["sources"][:50], refs[:50])]
        if operation == "next_question":
            result = {"question": "SIMULAÇÃO: deseja acrescentar alguma informação fictícia?", "references": refs}
        elif operation == "extract_structured":
            result = {"items": items}
        else:
            result = {"items": items, "attention_points": []}
        response = {"contract_version": "ai.v1", "operation": operation,
                    "context_id": request["context_id"], "result": result}
        if self.scenario == "invalid":
            response["unexpected"] = "Resposta fictícia propositalmente inválida."
        return deepcopy(response)

    def next_question(self, request):
        return self._run(request, "next_question")

    def extract_structured(self, request):
        return self._run(request, "extract_structured")

    def build_summary(self, request):
        return self._run(request, "build_summary")

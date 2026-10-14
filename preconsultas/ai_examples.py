"""Print ONLY fixed fictitious DTOs; no Django setup, database or provider network."""
import json

from .ai_conformance import sample_request
from .ai_contract import error_envelope
from .ai_provider import FakeAIProvider


def examples():
    provider = FakeAIProvider()
    return {operation: {"request": sample_request(operation),
                        "response": getattr(provider, operation)(sample_request(operation)),
                        "error": error_envelope(sample_request(operation), "transient_failure")}
            for operation in ("next_question", "extract_structured", "build_summary")}


if __name__ == "__main__":
    print(json.dumps(examples(), ensure_ascii=True, indent=2))

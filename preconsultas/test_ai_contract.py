from copy import deepcopy
from unittest.mock import patch

from django.test import SimpleTestCase

from .ai_conformance import check_provider, sample_request
from .ai_contract import ContractError, error_envelope, fingerprint, validate_request, validate_response
from .ai_provider import FakeAIProvider, ProviderFailure


class ContractTests(SimpleTestCase):
    def test_three_operations_conformance_and_determinism(self):
        with patch("socket.create_connection", side_effect=AssertionError("Network forbidden")):
            results = check_provider(FakeAIProvider(), deterministic=True)
        self.assertEqual(set(results), {"next_question", "extract_structured", "build_summary"})
        self.assertEqual(results["build_summary"]["result"]["attention_points"], [])

    def test_executable_examples_are_complete_and_match_contract(self):
        from .ai_examples import examples
        for sample in examples().values():
            validate_request(sample["request"])
            validate_response(sample["response"], sample["request"])
            self.assertEqual(sample["error"]["context_id"], sample["request"]["context_id"])

    def test_request_strict_fields_types_versions_and_limits(self):
        mutations = [lambda p: p.update(unknown=True), lambda p: p.update(contract_version="ai.v2"),
                     lambda p: p.update(consultation_id=True), lambda p: p.update(operation="publish"),
                     lambda p: p.update(sources=[]), lambda p: p.update(sources=p["sources"] * 101),
                     lambda p: p["sources"][0].update(text="x" * 8001),
                     lambda p: p["sources"][0].update(author="doctor"),
                     lambda p: p["sources"][0].update(source_id=True),
                     lambda p: p["sources"][0].update(version="not-a-version"),
                     lambda p: p.update(context_id="0" * 64)]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                payload = sample_request()
                mutate(payload)
                with self.assertRaises(ContractError):
                    validate_request(payload)

    def test_response_strict_fields_types_context_versions_and_references(self):
        request = sample_request()
        mutations = [lambda p: p.update(unknown=True), lambda p: p.update(contract_version="ai.v2"),
                     lambda p: p.update(operation="build_summary"), lambda p: p.update(context_id="0" * 64),
                     lambda p: p["result"].update(question=False), lambda p: p["result"].update(question="x" * 1001),
                     lambda p: p["result"].update(references=[]),
                     lambda p: p["result"]["references"][0].update(source_id=999),
                     lambda p: p["result"]["references"][0].update(version="0" * 64),
                     lambda p: p["result"]["references"][0].update(source_id=True)]
        for mutate in mutations:
            response = FakeAIProvider().next_question(request)
            mutate(response)
            with self.assertRaises(ContractError):
                validate_response(response, request)

    def test_derived_outputs_require_provenance_and_explicit_basis(self):
        for operation in ("extract_structured", "build_summary"):
            request = sample_request(operation)
            for field, value in [("references", []), ("basis", "patient"), ("key", ""), ("text", 123)]:
                response = getattr(FakeAIProvider(), operation)(request)
                response["result"]["items"][0][field] = value
                with self.assertRaises(ContractError):
                    validate_response(response, request)

    def test_excerpt_cannot_claim_absent_text_and_attention_requires_provenance(self):
        request = sample_request("build_summary")
        response = FakeAIProvider().build_summary(request)
        response["result"]["items"][0]["text"] = "Informação ausente nas fontes."
        with self.assertRaises(ContractError):
            validate_response(response, request)
        response = FakeAIProvider().build_summary(request)
        response["result"]["attention_points"] = [{"key": "attention", "text": "Pergunta fictícia para revisão.",
                                                    "basis": "derived", "references": []}]
        with self.assertRaises(ContractError):
            validate_response(response, request)

    def test_fake_errors_and_generic_portable_error(self):
        request = sample_request()
        with self.assertRaises(ContractError):
            validate_response(FakeAIProvider("invalid").next_question(request), request)
        for scenario in ("unavailable", "transient"):
            with self.assertRaises(ProviderFailure):
                FakeAIProvider(scenario).next_question(request)
        error = error_envelope(request, "transient_failure")
        self.assertTrue(error["error"]["retryable"])
        self.assertNotIn(request["sources"][0]["text"], str(error))

    def test_version_tracks_content_without_changing_source_ids(self):
        old = sample_request()
        new = deepcopy(old)
        new["sources"][0]["text"] = "Outra informação fictícia."
        new["sources"][0]["version"] = fingerprint({"fixture": "ficticia-v2"})
        new["context_id"] = fingerprint({k: v for k, v in new.items() if k != "context_id"})
        validate_request(new)
        self.assertNotEqual(old["context_id"], new["context_id"])
        with self.assertRaises(ContractError):
            validate_response(FakeAIProvider().next_question(old), new)

    def test_fake_accepts_valid_text_with_long_leading_whitespace(self):
        request = sample_request("build_summary")
        request["sources"][0]["text"] = " " * 3000 + "Informação fictícia."
        request["context_id"] = fingerprint({k: v for k, v in request.items() if k != "context_id"})
        validate_response(FakeAIProvider().build_summary(request), request)

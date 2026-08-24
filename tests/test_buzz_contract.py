"""
SPATHODEA R4 FASTLAB — BUZZ Gateway Contract Tests
Validates all contract guarantees defined in docs/BUZZ_INTEGRATION_CONTRACT.md.

Run with: python -m pytest tests/test_buzz_contract.py -v
   or:    python tests/test_buzz_contract.py
"""

import sys
import os
import unittest

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.provider_request import ProviderRequest
from adapters.provider_response import ProviderResponse
from adapters.buzz_client import BuzzClient


# =============================================================================
# Helper: default mock config
# =============================================================================

def _mock_config():
    """Return a minimal mock-mode BUZZ config dict."""
    return {
        "mode": "mock",
        "mock": {
            "model_name": "buzz-mock-v1",
            "latency_ms": 0,
            "deterministic": True,
            "seed": 42,
            "error_rate": 0.0,
            "response_style": "helpful",
            "languages": ["en", "ms", "mixed"],
            "max_output_tokens": 2048,
        },
        "local_http": {"enabled": False, "base_url": "http://localhost:11434"},
        "local_cli": {"enabled": False, "binary": "ollama"},
        "generation_defaults": {
            "temperature": 0.8,
            "max_tokens": 2048,
            "top_p": 0.95,
        },
        "retry": {"max_retries": 3},
        "logging": {"log_requests": False},
    }


# =============================================================================
# Test: ProviderRequest Contract
# =============================================================================

class TestProviderRequestContract(unittest.TestCase):
    """Verify ProviderRequest data model contract."""

    def test_valid_request_passes_validation(self):
        req = ProviderRequest(prompt="Hello, how are you?")
        errors = req.validate()
        self.assertEqual(errors, [])

    def test_empty_prompt_fails_validation(self):
        req = ProviderRequest(prompt="")
        errors = req.validate()
        self.assertTrue(any("prompt" in e for e in errors))

    def test_whitespace_only_prompt_fails_validation(self):
        req = ProviderRequest(prompt="   ")
        errors = req.validate()
        self.assertTrue(any("prompt" in e for e in errors))

    def test_temperature_below_zero_fails(self):
        req = ProviderRequest(prompt="test", temperature=-0.1)
        errors = req.validate()
        self.assertTrue(any("temperature" in e for e in errors))

    def test_temperature_above_two_fails(self):
        req = ProviderRequest(prompt="test", temperature=2.5)
        errors = req.validate()
        self.assertTrue(any("temperature" in e for e in errors))

    def test_max_tokens_zero_fails(self):
        req = ProviderRequest(prompt="test", max_tokens=0)
        errors = req.validate()
        self.assertTrue(any("max_tokens" in e for e in errors))

    def test_top_p_out_of_range_fails(self):
        req = ProviderRequest(prompt="test", top_p=1.5)
        errors = req.validate()
        self.assertTrue(any("top_p" in e for e in errors))

    def test_to_dict_roundtrip(self):
        req = ProviderRequest(
            prompt="What is 2+2?",
            system_prompt="You are a math tutor.",
            model="test-model",
            temperature=0.5,
            max_tokens=100,
            top_p=0.9,
            stop_sequences=["END"],
            request_id="req-001",
            metadata={"language": "en"},
        )
        d = req.to_dict()
        restored = ProviderRequest.from_dict(d)
        self.assertEqual(req.prompt, restored.prompt)
        self.assertEqual(req.system_prompt, restored.system_prompt)
        self.assertEqual(req.model, restored.model)
        self.assertEqual(req.temperature, restored.temperature)
        self.assertEqual(req.max_tokens, restored.max_tokens)
        self.assertEqual(req.top_p, restored.top_p)
        self.assertEqual(req.stop_sequences, restored.stop_sequences)
        self.assertEqual(req.request_id, restored.request_id)
        self.assertEqual(req.metadata, restored.metadata)

    def test_defaults_are_sane(self):
        req = ProviderRequest(prompt="test")
        self.assertEqual(req.temperature, 0.8)
        self.assertEqual(req.max_tokens, 2048)
        self.assertEqual(req.top_p, 0.95)
        self.assertIsNone(req.stop_sequences)
        self.assertIsNone(req.request_id)


# =============================================================================
# Test: ProviderResponse Contract
# =============================================================================

class TestProviderResponseContract(unittest.TestCase):
    """Verify ProviderResponse data model contract."""

    def test_successful_response_properties(self):
        resp = ProviderResponse(content="Hello!", model="m", finish_reason="stop")
        self.assertTrue(resp.is_success)
        self.assertFalse(resp.is_error)

    def test_error_response_properties(self):
        resp = ProviderResponse.error_response("something broke", provider="mock")
        self.assertFalse(resp.is_success)
        self.assertTrue(resp.is_error)
        self.assertEqual(resp.error, "something broke")
        self.assertEqual(resp.content, "")
        self.assertEqual(resp.finish_reason, "error")

    def test_successful_response_validation(self):
        resp = ProviderResponse(content="Valid content", finish_reason="stop")
        errors = resp.validate()
        self.assertEqual(errors, [])

    def test_empty_content_on_success_fails_validation(self):
        resp = ProviderResponse(content="", finish_reason="stop", error=None)
        errors = resp.validate()
        self.assertTrue(any("content" in e for e in errors))

    def test_negative_latency_fails_validation(self):
        resp = ProviderResponse(content="ok", finish_reason="stop", latency_ms=-1.0)
        errors = resp.validate()
        self.assertTrue(any("latency" in e for e in errors))

    def test_to_dict_roundtrip(self):
        resp = ProviderResponse(
            content="Answer is 4",
            model="buzz-mock-v1",
            request_id="req-001",
            finish_reason="mock",
            usage={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            latency_ms=12.5,
            provider="mock",
            metadata={"language": "en"},
        )
        d = resp.to_dict()
        restored = ProviderResponse.from_dict(d)
        self.assertEqual(resp.content, restored.content)
        self.assertEqual(resp.model, restored.model)
        self.assertEqual(resp.request_id, restored.request_id)
        self.assertEqual(resp.finish_reason, restored.finish_reason)
        self.assertEqual(resp.usage, restored.usage)
        self.assertEqual(resp.latency_ms, restored.latency_ms)
        self.assertEqual(resp.provider, restored.provider)
        self.assertEqual(resp.metadata, restored.metadata)


# =============================================================================
# Test: BuzzClient Mock Mode — Core Guarantees
# =============================================================================

class TestBuzzClientMockMode(unittest.TestCase):
    """Verify BuzzClient mock mode contract guarantees."""

    def setUp(self):
        self.client = BuzzClient(config=_mock_config())

    def test_mode_is_mock(self):
        self.assertEqual(self.client.mode, "mock")
        self.assertTrue(self.client.is_mock)

    def test_send_returns_provider_response(self):
        req = ProviderRequest(prompt="Test prompt", metadata={"language": "en"})
        resp = self.client.send(req)
        self.assertIsInstance(resp, ProviderResponse)

    def test_successful_response_has_content(self):
        req = ProviderRequest(prompt="Test prompt", metadata={"language": "en"})
        resp = self.client.send(req)
        self.assertTrue(resp.is_success)
        self.assertTrue(len(resp.content) > 0)

    def test_response_provider_is_mock(self):
        req = ProviderRequest(prompt="Hello", metadata={"language": "en"})
        resp = self.client.send(req)
        self.assertEqual(resp.provider, "mock")

    def test_response_finish_reason_is_mock(self):
        req = ProviderRequest(prompt="Hello", metadata={"language": "en"})
        resp = self.client.send(req)
        self.assertEqual(resp.finish_reason, "mock")

    def test_response_has_usage_dict(self):
        req = ProviderRequest(prompt="Hello world", metadata={"language": "en"})
        resp = self.client.send(req)
        self.assertIn("prompt_tokens", resp.usage)
        self.assertIn("completion_tokens", resp.usage)
        self.assertIn("total_tokens", resp.usage)
        self.assertEqual(
            resp.usage["total_tokens"],
            resp.usage["prompt_tokens"] + resp.usage["completion_tokens"],
        )

    def test_latency_is_non_negative(self):
        req = ProviderRequest(prompt="Hello", metadata={"language": "en"})
        resp = self.client.send(req)
        self.assertGreaterEqual(resp.latency_ms, 0)

    def test_request_count_increments(self):
        req = ProviderRequest(prompt="Hello", metadata={"language": "en"})
        self.assertEqual(self.client.request_count, 0)
        self.client.send(req)
        self.assertEqual(self.client.request_count, 1)
        self.client.send(req)
        self.assertEqual(self.client.request_count, 2)


# =============================================================================
# Test: Deterministic Behavior
# =============================================================================

class TestBuzzClientDeterminism(unittest.TestCase):
    """Verify deterministic mock responses — same prompt → same output."""

    def setUp(self):
        self.client = BuzzClient(config=_mock_config())

    def test_same_prompt_same_response(self):
        req = ProviderRequest(prompt="What is the weather?", metadata={"language": "en"})
        resp1 = self.client.send(req)
        resp2 = self.client.send(req)
        self.assertEqual(resp1.content, resp2.content)

    def test_different_prompts_may_differ(self):
        req_a = ProviderRequest(prompt="Question A about billing", metadata={"language": "en"})
        req_b = ProviderRequest(prompt="Question B about coverage", metadata={"language": "en"})
        resp_a = self.client.send(req_a)
        resp_b = self.client.send(req_b)
        # Different prompts hash differently — responses may or may not differ
        # but the test verifies no crash and valid responses
        self.assertTrue(resp_a.is_success)
        self.assertTrue(resp_b.is_success)

    def test_reset_preserves_determinism(self):
        req = ProviderRequest(prompt="Consistent test", metadata={"language": "en"})
        resp1 = self.client.send(req)
        self.client.reset()
        resp2 = self.client.send(req)
        self.assertEqual(resp1.content, resp2.content)


# =============================================================================
# Test: Language Routing
# =============================================================================

class TestBuzzClientLanguageRouting(unittest.TestCase):
    """Verify language-based response pool selection."""

    def setUp(self):
        self.client = BuzzClient(config=_mock_config())

    def test_english_prompt_returns_content(self):
        req = ProviderRequest(prompt="Help me with my account", metadata={"language": "en"})
        resp = self.client.send(req)
        self.assertTrue(resp.is_success)
        self.assertTrue(len(resp.content) > 20)

    def test_malay_prompt_returns_content(self):
        req = ProviderRequest(prompt="Tolong saya dengan akaun", metadata={"language": "ms"})
        resp = self.client.send(req)
        self.assertTrue(resp.is_success)
        self.assertTrue(len(resp.content) > 20)

    def test_mixed_prompt_returns_content(self):
        req = ProviderRequest(prompt="Boleh explain billing?", metadata={"language": "mixed"})
        resp = self.client.send(req)
        self.assertTrue(resp.is_success)
        self.assertTrue(len(resp.content) > 20)

    def test_default_language_is_english(self):
        req = ProviderRequest(prompt="No language metadata")
        resp = self.client.send(req)
        self.assertTrue(resp.is_success)
        self.assertEqual(resp.metadata.get("language"), "en")


# =============================================================================
# Test: Invalid Request Handling
# =============================================================================

class TestBuzzClientInvalidRequests(unittest.TestCase):
    """Verify that invalid requests return error responses (never exceptions)."""

    def setUp(self):
        self.client = BuzzClient(config=_mock_config())

    def test_empty_prompt_returns_error_response(self):
        req = ProviderRequest(prompt="", request_id="bad-001")
        resp = self.client.send(req)
        self.assertIsInstance(resp, ProviderResponse)
        self.assertTrue(resp.is_error)
        self.assertIn("validation failed", resp.error.lower())

    def test_invalid_temperature_returns_error_response(self):
        req = ProviderRequest(prompt="test", temperature=5.0, request_id="bad-002")
        resp = self.client.send(req)
        self.assertTrue(resp.is_error)

    def test_invalid_request_preserves_request_id(self):
        req = ProviderRequest(prompt="", request_id="trace-xyz")
        resp = self.client.send(req)
        self.assertEqual(resp.request_id, "trace-xyz")

    def test_send_never_raises_exception(self):
        """Contract guarantee: send() NEVER raises — always returns ProviderResponse."""
        bad_requests = [
            ProviderRequest(prompt=""),
            ProviderRequest(prompt="   "),
            ProviderRequest(prompt="x", temperature=-99),
            ProviderRequest(prompt="x", max_tokens=-1),
            ProviderRequest(prompt="x", top_p=5.0),
        ]
        for req in bad_requests:
            resp = self.client.send(req)
            self.assertIsInstance(resp, ProviderResponse)


# =============================================================================
# Test: Batch Processing
# =============================================================================

class TestBuzzClientBatch(unittest.TestCase):
    """Verify batch processing returns correct number of responses."""

    def setUp(self):
        self.client = BuzzClient(config=_mock_config())

    def test_batch_returns_same_count(self):
        requests = [
            ProviderRequest(prompt=f"Question {i}", metadata={"language": "en"})
            for i in range(5)
        ]
        responses = self.client.send_batch(requests)
        self.assertEqual(len(responses), 5)

    def test_batch_all_successful(self):
        requests = [
            ProviderRequest(prompt=f"Query {i}", metadata={"language": "ms"})
            for i in range(3)
        ]
        responses = self.client.send_batch(requests)
        for resp in responses:
            self.assertTrue(resp.is_success)

    def test_batch_with_mixed_validity(self):
        requests = [
            ProviderRequest(prompt="Valid prompt", metadata={"language": "en"}),
            ProviderRequest(prompt=""),  # Invalid
            ProviderRequest(prompt="Another valid", metadata={"language": "ms"}),
        ]
        responses = self.client.send_batch(requests)
        self.assertEqual(len(responses), 3)
        self.assertTrue(responses[0].is_success)
        self.assertTrue(responses[1].is_error)
        self.assertTrue(responses[2].is_success)

    def test_empty_batch_returns_empty(self):
        responses = self.client.send_batch([])
        self.assertEqual(responses, [])


# =============================================================================
# Test: Health Check
# =============================================================================

class TestBuzzClientHealthCheck(unittest.TestCase):
    """Verify health_check returns expected structure."""

    def setUp(self):
        self.client = BuzzClient(config=_mock_config())

    def test_health_check_structure(self):
        health = self.client.health_check()
        self.assertEqual(health["status"], "healthy")
        self.assertEqual(health["mode"], "mock")
        self.assertIn("model", health)
        self.assertIn("deterministic", health)
        self.assertIn("response_templates", health)

    def test_get_status_returns_pass(self):
        self.assertEqual(self.client.get_status(), "PASS")

    def test_local_http_stub_status(self):
        cfg = _mock_config()
        cfg["mode"] = "local_http"
        client = BuzzClient(config=cfg)
        self.assertEqual(client.get_status(), "STUB")

    def test_local_cli_stub_status(self):
        cfg = _mock_config()
        cfg["mode"] = "local_cli"
        client = BuzzClient(config=cfg)
        self.assertEqual(client.get_status(), "STUB")


# =============================================================================
# Test: Error Rate Simulation
# =============================================================================

class TestBuzzClientErrorRate(unittest.TestCase):
    """Verify error_rate simulation works."""

    def test_zero_error_rate_no_failures(self):
        cfg = _mock_config()
        cfg["mock"]["error_rate"] = 0.0
        client = BuzzClient(config=cfg)
        for i in range(20):
            req = ProviderRequest(prompt=f"Prompt {i}", metadata={"language": "en"})
            resp = client.send(req)
            self.assertTrue(resp.is_success)

    def test_full_error_rate_all_failures(self):
        cfg = _mock_config()
        cfg["mock"]["error_rate"] = 1.0
        cfg["mock"]["deterministic"] = False  # Need RNG for error rate
        client = BuzzClient(config=cfg)
        failures = 0
        for i in range(10):
            req = ProviderRequest(prompt=f"Prompt {i}", metadata={"language": "en"})
            resp = client.send(req)
            if resp.is_error:
                failures += 1
        self.assertEqual(failures, 10)


# =============================================================================
# Test: request_id Propagation
# =============================================================================

class TestBuzzClientRequestIdPropagation(unittest.TestCase):
    """Verify request_id flows from request to response."""

    def setUp(self):
        self.client = BuzzClient(config=_mock_config())

    def test_request_id_propagates(self):
        req = ProviderRequest(prompt="Test", request_id="my-trace-id", metadata={"language": "en"})
        resp = self.client.send(req)
        self.assertEqual(resp.request_id, "my-trace-id")

    def test_none_request_id_gets_generated(self):
        req = ProviderRequest(prompt="Test", request_id=None, metadata={"language": "en"})
        resp = self.client.send(req)
        self.assertIsNotNone(resp.request_id)
        self.assertTrue(resp.request_id.startswith("mock-"))


# =============================================================================
# Test: Stub Modes Return Proper Errors
# =============================================================================

class TestBuzzClientStubModes(unittest.TestCase):
    """Verify stub modes return descriptive error responses without crashing."""

    def test_local_http_returns_error(self):
        cfg = _mock_config()
        cfg["mode"] = "local_http"
        client = BuzzClient(config=cfg)
        req = ProviderRequest(prompt="Test", metadata={"language": "en"})
        resp = client.send(req)
        self.assertIsInstance(resp, ProviderResponse)
        self.assertTrue(resp.is_error)
        self.assertIn("not implemented", resp.error.lower())

    def test_local_cli_returns_error(self):
        cfg = _mock_config()
        cfg["mode"] = "local_cli"
        client = BuzzClient(config=cfg)
        req = ProviderRequest(prompt="Test", metadata={"language": "en"})
        resp = client.send(req)
        self.assertIsInstance(resp, ProviderResponse)
        self.assertTrue(resp.is_error)
        self.assertIn("not implemented", resp.error.lower())


# =============================================================================
# Runner
# =============================================================================

def run_tests_with_report() -> dict:
    """Run all tests and return structured results for CLI integration."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])

    # Run with a result object
    runner = unittest.TextTestRunner(verbosity=0, stream=open(os.devnull, "w"))
    result = runner.run(suite)

    passed = result.testsRun - len(result.failures) - len(result.errors)
    return {
        "total": result.testsRun,
        "passed": passed,
        "failed": len(result.failures),
        "errors": len(result.errors),
        "failure_details": [
            {"test": str(t), "message": msg} for t, msg in result.failures
        ],
        "error_details": [
            {"test": str(t), "message": msg} for t, msg in result.errors
        ],
        "success": len(result.failures) == 0 and len(result.errors) == 0,
    }


if __name__ == "__main__":
    unittest.main(verbosity=2)

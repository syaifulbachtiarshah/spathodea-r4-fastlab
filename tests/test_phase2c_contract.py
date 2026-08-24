"""
SPATHODEA R4 FASTLAB — Phase 2C Contract-Hardening Tests
Validates v0.2.0 contract extensions:
- Endpoint: 127.0.0.1:8765, POST /v1/generate, GET /health
- New fields: provider_preference, reviewer_preference, execution_mode, task_type
- Backward compatibility with v0.1.0 payloads
- Localhost-only security enforcement
- Total max attempts = 3

Run with: python tests/test_phase2c_contract.py
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.provider_request import ProviderRequest, CONTRACT_VERSION, VALID_EXECUTION_MODES, VALID_TASK_TYPES
from adapters.provider_response import ProviderResponse
from adapters.provider_response import CONTRACT_VERSION as RESP_CONTRACT_VERSION
from adapters.buzz_client import BuzzClient


def _v020_config():
    """Return Phase 2C (v0.2.0) mock config."""
    return {
        "mode": "mock",
        "endpoint": {
            "host": "127.0.0.1",
            "port": 8765,
            "generate_path": "/v1/generate",
            "health_path": "/health",
        },
        "provider_preference": None,
        "reviewer_preference": None,
        "execution_mode": "sync",
        "mock": {
            "model_name": "buzz-mock-v1",
            "latency_ms": 0,
            "deterministic": True,
            "seed": 42,
            "error_rate": 0.0,
        },
        "local_http": {"enabled": False, "base_url": "http://127.0.0.1:8765"},
        "local_cli": {"enabled": False, "binary": "ollama"},
        "generation_defaults": {"temperature": 0.8, "max_tokens": 2048, "top_p": 0.95},
        "retry": {"max_attempts": 3, "backoff_base_seconds": 1.0, "backoff_max_seconds": 30.0},
        "logging": {"log_requests": False},
    }


# =============================================================================
# Test: Contract Version
# =============================================================================

class TestContractVersion(unittest.TestCase):
    """Verify contract version is 0.2.0."""

    def test_request_contract_version(self):
        self.assertEqual(CONTRACT_VERSION, "0.2.0")

    def test_response_contract_version(self):
        self.assertEqual(RESP_CONTRACT_VERSION, "0.2.0")

    def test_to_dict_includes_contract_version(self):
        req = ProviderRequest(prompt="test")
        d = req.to_dict()
        self.assertEqual(d["contract_version"], "0.2.0")

    def test_response_to_dict_includes_contract_version(self):
        resp = ProviderResponse(content="ok", finish_reason="stop")
        d = resp.to_dict()
        self.assertEqual(d["contract_version"], "0.2.0")


# =============================================================================
# Test: Endpoint Configuration
# =============================================================================

class TestEndpointConfig(unittest.TestCase):
    """Verify endpoint is 127.0.0.1:8765 with POST /v1/generate and GET /health."""

    def setUp(self):
        self.client = BuzzClient(config=_v020_config())

    def test_endpoint_url(self):
        self.assertEqual(self.client.endpoint_url, "http://127.0.0.1:8765/v1/generate")

    def test_health_url(self):
        self.assertEqual(self.client.health_url, "http://127.0.0.1:8765/health")

    def test_health_check_includes_endpoint(self):
        health = self.client.health_check()
        self.assertEqual(health["endpoint"], "http://127.0.0.1:8765/v1/generate")
        self.assertEqual(health["health_endpoint"], "http://127.0.0.1:8765/health")
        self.assertEqual(health["host"], "127.0.0.1")
        self.assertEqual(health["port"], 8765)

    def test_default_endpoint_without_config(self):
        client = BuzzClient(config={"mode": "mock", "mock": {"latency_ms": 0}})
        self.assertEqual(client.endpoint_url, "http://127.0.0.1:8765/v1/generate")
        self.assertEqual(client.health_url, "http://127.0.0.1:8765/health")


# =============================================================================
# Test: Localhost-Only Security
# =============================================================================

class TestLocalhostSecurity(unittest.TestCase):
    """Verify external hosts are rejected and forced to 127.0.0.1."""

    def test_external_host_forced_to_localhost(self):
        cfg = _v020_config()
        cfg["endpoint"]["host"] = "192.168.1.100"
        client = BuzzClient(config=cfg)
        self.assertIn("127.0.0.1", client.endpoint_url)

    def test_public_host_forced_to_localhost(self):
        cfg = _v020_config()
        cfg["endpoint"]["host"] = "api.example.com"
        client = BuzzClient(config=cfg)
        self.assertIn("127.0.0.1", client.endpoint_url)

    def test_localhost_string_allowed(self):
        cfg = _v020_config()
        cfg["endpoint"]["host"] = "localhost"
        client = BuzzClient(config=cfg)
        self.assertIn("localhost", client.endpoint_url)

    def test_ipv6_loopback_allowed(self):
        cfg = _v020_config()
        cfg["endpoint"]["host"] = "::1"
        client = BuzzClient(config=cfg)
        self.assertIn("::1", client.endpoint_url)


# =============================================================================
# Test: New v0.2.0 Request Fields
# =============================================================================

class TestRequestNewFields(unittest.TestCase):
    """Verify provider_preference, reviewer_preference, execution_mode, task_type."""

    def test_defaults_for_new_fields(self):
        req = ProviderRequest(prompt="test")
        self.assertIsNone(req.provider_preference)
        self.assertIsNone(req.reviewer_preference)
        self.assertEqual(req.execution_mode, "sync")
        self.assertEqual(req.task_type, "generate")

    def test_new_fields_settable(self):
        req = ProviderRequest(
            prompt="test",
            provider_preference="ollama",
            reviewer_preference="openai",
            execution_mode="batch",
            task_type="review",
        )
        self.assertEqual(req.provider_preference, "ollama")
        self.assertEqual(req.reviewer_preference, "openai")
        self.assertEqual(req.execution_mode, "batch")
        self.assertEqual(req.task_type, "review")

    def test_to_dict_includes_new_fields(self):
        req = ProviderRequest(
            prompt="test",
            provider_preference="local",
            task_type="adversarial",
        )
        d = req.to_dict()
        self.assertEqual(d["provider_preference"], "local")
        self.assertIsNone(d["reviewer_preference"])
        self.assertEqual(d["execution_mode"], "sync")
        self.assertEqual(d["task_type"], "adversarial")

    def test_from_dict_parses_new_fields(self):
        d = {
            "prompt": "hello",
            "provider_preference": "gemini",
            "reviewer_preference": "openai",
            "execution_mode": "async",
            "task_type": "score",
        }
        req = ProviderRequest.from_dict(d)
        self.assertEqual(req.provider_preference, "gemini")
        self.assertEqual(req.reviewer_preference, "openai")
        self.assertEqual(req.execution_mode, "async")
        self.assertEqual(req.task_type, "score")

    def test_valid_execution_modes(self):
        for mode in VALID_EXECUTION_MODES:
            req = ProviderRequest(prompt="test", execution_mode=mode)
            self.assertEqual(req.validate(), [])

    def test_invalid_execution_mode(self):
        req = ProviderRequest(prompt="test", execution_mode="streaming")
        errors = req.validate()
        self.assertTrue(any("execution_mode" in e for e in errors))

    def test_valid_task_types(self):
        for tt in VALID_TASK_TYPES:
            req = ProviderRequest(prompt="test", task_type=tt)
            self.assertEqual(req.validate(), [])

    def test_invalid_task_type(self):
        req = ProviderRequest(prompt="test", task_type="summarize")
        errors = req.validate()
        self.assertTrue(any("task_type" in e for e in errors))


# =============================================================================
# Test: Backward Compatibility with v0.1.0 Payloads
# =============================================================================

class TestBackwardCompatibility(unittest.TestCase):
    """Verify v0.1.0 payloads (without new fields) still work correctly."""

    def test_v010_payload_deserializes(self):
        """A v0.1.0 payload without new fields should deserialize with defaults."""
        v010_payload = {
            "prompt": "How do I reset my password?",
            "system_prompt": "You are helpful.",
            "model": "llama3.2:3b",
            "temperature": 0.7,
            "max_tokens": 1024,
            "top_p": 0.9,
            "stop_sequences": None,
            "request_id": "old-req-001",
            "metadata": {"language": "en"},
        }
        req = ProviderRequest.from_dict(v010_payload)
        self.assertEqual(req.prompt, "How do I reset my password?")
        self.assertEqual(req.model, "llama3.2:3b")
        # New fields default gracefully
        self.assertIsNone(req.provider_preference)
        self.assertIsNone(req.reviewer_preference)
        self.assertEqual(req.execution_mode, "sync")
        self.assertEqual(req.task_type, "generate")
        # Validation passes
        self.assertEqual(req.validate(), [])

    def test_v010_request_still_sends_successfully(self):
        """A request built with only v0.1.0 fields works with v0.2.0 client."""
        client = BuzzClient(config=_v020_config())
        req = ProviderRequest(prompt="Hello from v0.1.0", metadata={"language": "en"})
        resp = client.send(req)
        self.assertTrue(resp.is_success)
        self.assertTrue(len(resp.content) > 0)

    def test_v010_response_from_dict_still_works(self):
        """A response without contract_version field still deserializes."""
        v010_resp = {
            "content": "Some answer",
            "model": "buzz-mock-v1",
            "request_id": "old-001",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
            "latency_ms": 50.0,
            "provider": "mock",
            "error": None,
            "metadata": {},
        }
        resp = ProviderResponse.from_dict(v010_resp)
        self.assertTrue(resp.is_success)
        self.assertEqual(resp.content, "Some answer")


# =============================================================================
# Test: Max Attempts = 3
# =============================================================================

class TestMaxAttempts(unittest.TestCase):
    """Verify retry logic respects total max attempts = 3."""

    def test_max_attempts_property(self):
        client = BuzzClient(config=_v020_config())
        self.assertEqual(client.max_attempts, 3)

    def test_custom_max_attempts(self):
        cfg = _v020_config()
        cfg["retry"]["max_attempts"] = 5
        client = BuzzClient(config=cfg)
        self.assertEqual(client.max_attempts, 5)

    def test_success_on_first_attempt_no_retry(self):
        """With error_rate=0, first attempt succeeds, no retries needed."""
        cfg = _v020_config()
        cfg["mock"]["error_rate"] = 0.0
        client = BuzzClient(config=cfg)
        req = ProviderRequest(prompt="Hello", metadata={"language": "en"})
        resp = client.send(req)
        self.assertTrue(resp.is_success)
        self.assertEqual(client.request_count, 1)

    def test_error_rate_1_exhausts_all_attempts(self):
        """With error_rate=1.0, all 3 attempts fail and error is returned."""
        cfg = _v020_config()
        cfg["mock"]["error_rate"] = 1.0
        cfg["mock"]["deterministic"] = False
        client = BuzzClient(config=cfg)
        req = ProviderRequest(prompt="Will fail", metadata={"language": "en"})
        resp = client.send(req)
        self.assertTrue(resp.is_error)
        # request_count is 1 (send increments once), _dispatch called 3 times internally

    def test_default_max_attempts_is_3(self):
        """Without explicit config, default is 3."""
        client = BuzzClient(config={"mode": "mock", "mock": {"latency_ms": 0}})
        self.assertEqual(client.max_attempts, 3)


# =============================================================================
# Test: Health Check v0.2.0 Structure
# =============================================================================

class TestHealthCheckV020(unittest.TestCase):
    """Verify health check includes v0.2.0 fields."""

    def setUp(self):
        self.client = BuzzClient(config=_v020_config())

    def test_includes_contract_version(self):
        health = self.client.health_check()
        self.assertEqual(health["contract_version"], "0.2.0")

    def test_includes_max_attempts(self):
        health = self.client.health_check()
        self.assertEqual(health["max_attempts"], 3)

    def test_includes_preferences(self):
        health = self.client.health_check()
        self.assertIn("provider_preference", health)
        self.assertIn("reviewer_preference", health)
        self.assertIn("execution_mode", health)

    def test_mock_still_healthy(self):
        health = self.client.health_check()
        self.assertEqual(health["status"], "healthy")
        self.assertEqual(health["mode"], "mock")


# =============================================================================
# Test: task_type Routing (mock just accepts all)
# =============================================================================

class TestTaskTypeRouting(unittest.TestCase):
    """Verify different task_types work through mock mode."""

    def setUp(self):
        self.client = BuzzClient(config=_v020_config())

    def test_generate_task(self):
        req = ProviderRequest(prompt="Generate something", task_type="generate", metadata={"language": "en"})
        resp = self.client.send(req)
        self.assertTrue(resp.is_success)

    def test_review_task(self):
        req = ProviderRequest(prompt="Review this output", task_type="review", metadata={"language": "en"})
        resp = self.client.send(req)
        self.assertTrue(resp.is_success)

    def test_score_task(self):
        req = ProviderRequest(prompt="Score this", task_type="score", metadata={"language": "ms"})
        resp = self.client.send(req)
        self.assertTrue(resp.is_success)

    def test_adversarial_task(self):
        req = ProviderRequest(prompt="Trick question", task_type="adversarial", metadata={"language": "en"})
        resp = self.client.send(req)
        self.assertTrue(resp.is_success)

    def test_paraphrase_task(self):
        req = ProviderRequest(prompt="Rephrase this", task_type="paraphrase", metadata={"language": "mixed"})
        resp = self.client.send(req)
        self.assertTrue(resp.is_success)


# =============================================================================
# Runner
# =============================================================================

def run_phase2c_tests() -> dict:
    """Run Phase 2C tests and return structured results."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=0, stream=open(os.devnull, "w"))
    result = runner.run(suite)

    passed = result.testsRun - len(result.failures) - len(result.errors)
    return {
        "total": result.testsRun,
        "passed": passed,
        "failed": len(result.failures),
        "errors": len(result.errors),
        "failure_details": [{"test": str(t), "message": msg} for t, msg in result.failures],
        "error_details": [{"test": str(t), "message": msg} for t, msg in result.errors],
        "success": len(result.failures) == 0 and len(result.errors) == 0,
    }


if __name__ == "__main__":
    unittest.main(verbosity=2)

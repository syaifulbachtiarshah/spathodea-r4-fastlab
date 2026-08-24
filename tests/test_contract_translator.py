"""
SPATHODEA R4 FASTLAB — Phase 2F Part 3A Contract Translator Tests
Deterministic offline tests for FASTLAB → ATAN BUZZ wire translation.

18 test scenarios:
    1.  Valid game request → single wire request
    2.  task_type generate → game_navigation on wire
    3.  sync is NOT blindly treated as provider strategy
    4.  Explicit single execution mode
    5.  Explicit fallback execution mode
    6.  Explicit consensus execution mode
    7.  Provider preservation
    8.  Reviewer preservation
    9.  Invalid provider rejected
   10.  Invalid reviewer rejected
   11.  Consensus configuration error (no reviewer)
   12.  FASTLAB validation failure (empty prompt)
   13.  Metadata preservation
   14.  Source/target contract namespace
   15.  contract_version remains 0.2.0
   16.  No mutation of original ProviderRequest
   17.  Deterministic translation
   18.  No secret-like metadata added

All tests are deterministic — no randomness, no network, no LLM.

Run with: python -m unittest tests.test_contract_translator -v
"""

import sys
import os
import copy
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.contract_translator import (
    ContractTranslator,
    TranslatorConfig,
    TranslationResult,
    SOURCE_CONTRACT,
    TARGET_CONTRACT,
    WIRE_CONTRACT_VERSION,
    WIRE_EXECUTION_MODES,
    WIRE_PROVIDERS,
    WIRE_REVIEWERS,
)
from adapters.provider_request import ProviderRequest, CONTRACT_VERSION


# =============================================================================
# Helper
# =============================================================================

def _valid_game_request(**overrides) -> ProviderRequest:
    """Build a valid FASTLAB game navigation request."""
    defaults = dict(
        prompt="Grid: 5x5 | Position: A1 | Goal: E5 | Respond with action: UP, DOWN, LEFT, RIGHT, or WAIT",
        system_prompt=None,
        model="auto",
        temperature=0.3,
        max_tokens=50,
        top_p=0.9,
        stop_sequences=None,
        request_id="game-turn-0001",
        metadata={
            "source": "SPATHODEA_GAME",
            "task_intent": "game_navigation",
            "turn": 1,
            "agent_position": "A1",
            "strategy": "adaptive",
            "grid_width": 5,
            "grid_height": 5,
            "known_rewards": 2,
            "known_hazards": 1,
            "known_enemies": 0,
            "goal": "E5",
        },
        provider_preference="mock",
        reviewer_preference=None,
        execution_mode="sync",
        task_type="generate",
    )
    defaults.update(overrides)
    return ProviderRequest(**defaults)


# =============================================================================
# Test 1: Valid game request → single wire request
# =============================================================================

class TestValidGameToSingle(unittest.TestCase):
    """Valid FASTLAB game request translates to single wire request."""

    def test_valid_translation(self):
        request = _valid_game_request()
        translator = ContractTranslator(config=TranslatorConfig(
            wire_execution_mode="single",
            wire_provider="mock",
            wire_reviewer="none",
        ))

        result = translator.translate(request)

        self.assertTrue(result.success)
        self.assertEqual(result.errors, [])
        self.assertIsNotNone(result.wire_payload)
        self.assertEqual(result.wire_payload["execution_mode"], "single")
        self.assertEqual(result.wire_payload["task_type"], "game_navigation")
        self.assertEqual(result.wire_payload["prompt"], request.prompt)


# =============================================================================
# Test 2: task_type generate → game_navigation on wire
# =============================================================================

class TestTaskTypeTranslation(unittest.TestCase):
    """FASTLAB task_type='generate' becomes wire task_type='game_navigation'."""

    def test_generate_becomes_game_navigation(self):
        request = _valid_game_request(task_type="generate")
        translator = ContractTranslator()

        result = translator.translate(request)

        self.assertTrue(result.success)
        self.assertEqual(result.wire_payload["task_type"], "game_navigation")

    def test_source_task_type_is_generate(self):
        request = _valid_game_request()
        self.assertEqual(request.task_type, "generate")


# =============================================================================
# Test 3: sync is NOT blindly treated as provider strategy
# =============================================================================

class TestSyncNotBlindlyMapped(unittest.TestCase):
    """FASTLAB execution_mode='sync' does NOT become wire 'single' automatically.
    Wire execution mode comes from translator config, not from FASTLAB field."""

    def test_sync_does_not_equal_single(self):
        request = _valid_game_request(execution_mode="sync")

        # Translator configured for fallback — sync should NOT override
        translator = ContractTranslator(config=TranslatorConfig(
            wire_execution_mode="fallback",
            wire_provider="auto",
            wire_reviewer="none",
        ))

        result = translator.translate(request)

        self.assertTrue(result.success)
        # Wire mode is from config, NOT from FASTLAB execution_mode
        self.assertEqual(result.wire_payload["execution_mode"], "fallback")
        self.assertNotEqual(result.wire_payload["execution_mode"], "sync")

    def test_async_does_not_affect_wire(self):
        request = _valid_game_request(execution_mode="async")

        translator = ContractTranslator(config=TranslatorConfig(
            wire_execution_mode="single",
            wire_provider="mock",
            wire_reviewer="none",
        ))

        result = translator.translate(request)

        self.assertTrue(result.success)
        self.assertEqual(result.wire_payload["execution_mode"], "single")


# =============================================================================
# Test 4: Explicit single execution mode
# =============================================================================

class TestExplicitSingle(unittest.TestCase):
    """Translator configured for single execution mode."""

    def test_single_mode(self):
        request = _valid_game_request()
        translator = ContractTranslator(config=TranslatorConfig(
            wire_execution_mode="single",
            wire_provider="openai",
            wire_reviewer="none",
        ))

        result = translator.translate(request)

        self.assertTrue(result.success)
        self.assertEqual(result.wire_payload["execution_mode"], "single")
        self.assertEqual(result.wire_payload["provider_preference"], "openai")
        self.assertEqual(result.wire_payload["reviewer_preference"], "none")


# =============================================================================
# Test 5: Explicit fallback execution mode
# =============================================================================

class TestExplicitFallback(unittest.TestCase):
    """Translator configured for fallback execution mode."""

    def test_fallback_mode(self):
        request = _valid_game_request()
        translator = ContractTranslator(config=TranslatorConfig(
            wire_execution_mode="fallback",
            wire_provider="auto",
            wire_reviewer="none",
        ))

        result = translator.translate(request)

        self.assertTrue(result.success)
        self.assertEqual(result.wire_payload["execution_mode"], "fallback")


# =============================================================================
# Test 6: Explicit consensus execution mode
# =============================================================================

class TestExplicitConsensus(unittest.TestCase):
    """Translator configured for consensus execution mode (requires reviewer)."""

    def test_consensus_with_reviewer(self):
        request = _valid_game_request()
        translator = ContractTranslator(config=TranslatorConfig(
            wire_execution_mode="consensus",
            wire_provider="openai",
            wire_reviewer="gemini",
        ))

        result = translator.translate(request)

        self.assertTrue(result.success)
        self.assertEqual(result.wire_payload["execution_mode"], "consensus")
        self.assertEqual(result.wire_payload["provider_preference"], "openai")
        self.assertEqual(result.wire_payload["reviewer_preference"], "gemini")


# =============================================================================
# Test 7: Provider preservation
# =============================================================================

class TestProviderPreservation(unittest.TestCase):
    """Wire provider preference is set from translator config."""

    def test_openai_provider(self):
        request = _valid_game_request()
        translator = ContractTranslator(config=TranslatorConfig(
            wire_provider="openai",
        ))
        result = translator.translate(request)
        self.assertTrue(result.success)
        self.assertEqual(result.wire_payload["provider_preference"], "openai")

    def test_gemini_provider(self):
        request = _valid_game_request()
        translator = ContractTranslator(config=TranslatorConfig(
            wire_provider="gemini",
        ))
        result = translator.translate(request)
        self.assertTrue(result.success)
        self.assertEqual(result.wire_payload["provider_preference"], "gemini")

    def test_ollama_provider(self):
        request = _valid_game_request()
        translator = ContractTranslator(config=TranslatorConfig(
            wire_provider="ollama",
        ))
        result = translator.translate(request)
        self.assertTrue(result.success)
        self.assertEqual(result.wire_payload["provider_preference"], "ollama")

    def test_auto_provider(self):
        request = _valid_game_request()
        translator = ContractTranslator(config=TranslatorConfig(
            wire_provider="auto",
        ))
        result = translator.translate(request)
        self.assertTrue(result.success)
        self.assertEqual(result.wire_payload["provider_preference"], "auto")


# =============================================================================
# Test 8: Reviewer preservation
# =============================================================================

class TestReviewerPreservation(unittest.TestCase):
    """Wire reviewer preference is set from translator config."""

    def test_none_reviewer(self):
        request = _valid_game_request()
        translator = ContractTranslator(config=TranslatorConfig(
            wire_reviewer="none",
        ))
        result = translator.translate(request)
        self.assertTrue(result.success)
        self.assertEqual(result.wire_payload["reviewer_preference"], "none")

    def test_auto_reviewer_with_consensus(self):
        request = _valid_game_request()
        translator = ContractTranslator(config=TranslatorConfig(
            wire_execution_mode="consensus",
            wire_reviewer="auto",
        ))
        result = translator.translate(request)
        self.assertTrue(result.success)
        self.assertEqual(result.wire_payload["reviewer_preference"], "auto")

    def test_gemini_reviewer_with_consensus(self):
        request = _valid_game_request()
        translator = ContractTranslator(config=TranslatorConfig(
            wire_execution_mode="consensus",
            wire_provider="openai",
            wire_reviewer="gemini",
        ))
        result = translator.translate(request)
        self.assertTrue(result.success)
        self.assertEqual(result.wire_payload["reviewer_preference"], "gemini")


# =============================================================================
# Test 9: Invalid provider rejected
# =============================================================================

class TestInvalidProvider(unittest.TestCase):
    """Unsupported wire provider is rejected."""

    def test_unknown_provider(self):
        request = _valid_game_request()
        translator = ContractTranslator(config=TranslatorConfig(
            wire_provider="anthropic",
        ))
        result = translator.translate(request)

        self.assertFalse(result.success)
        self.assertTrue(any("provider" in e.lower() for e in result.errors))

    def test_empty_string_provider(self):
        request = _valid_game_request()
        translator = ContractTranslator(config=TranslatorConfig(
            wire_provider="",
        ))
        result = translator.translate(request)

        self.assertFalse(result.success)
        self.assertTrue(any("provider" in e.lower() for e in result.errors))


# =============================================================================
# Test 10: Invalid reviewer rejected
# =============================================================================

class TestInvalidReviewer(unittest.TestCase):
    """Unsupported wire reviewer is rejected."""

    def test_unknown_reviewer(self):
        request = _valid_game_request()
        translator = ContractTranslator(config=TranslatorConfig(
            wire_reviewer="anthropic",
        ))
        result = translator.translate(request)

        self.assertFalse(result.success)
        self.assertTrue(any("reviewer" in e.lower() for e in result.errors))

    def test_ollama_not_valid_reviewer(self):
        request = _valid_game_request()
        translator = ContractTranslator(config=TranslatorConfig(
            wire_reviewer="ollama",
        ))
        result = translator.translate(request)

        self.assertFalse(result.success)
        self.assertTrue(any("reviewer" in e.lower() for e in result.errors))


# =============================================================================
# Test 11: Consensus configuration error (no reviewer)
# =============================================================================

class TestConsensusNoReviewer(unittest.TestCase):
    """Consensus execution mode without reviewer is rejected."""

    def test_consensus_without_reviewer(self):
        request = _valid_game_request()
        translator = ContractTranslator(config=TranslatorConfig(
            wire_execution_mode="consensus",
            wire_provider="openai",
            wire_reviewer="none",
        ))

        result = translator.translate(request)

        self.assertFalse(result.success)
        self.assertTrue(any("consensus" in e.lower() for e in result.errors))
        self.assertTrue(any("reviewer" in e.lower() for e in result.errors))

    def test_consensus_with_null_reviewer(self):
        request = _valid_game_request()
        translator = ContractTranslator(config=TranslatorConfig(
            wire_execution_mode="consensus",
            wire_provider="openai",
            wire_reviewer=None,
        ))

        result = translator.translate(request)

        self.assertFalse(result.success)


# =============================================================================
# Test 12: FASTLAB validation failure (empty prompt)
# =============================================================================

class TestFASTLABValidationFailure(unittest.TestCase):
    """FASTLAB request that fails validate() is rejected before translation."""

    def test_empty_prompt_rejected(self):
        request = _valid_game_request(prompt="")
        translator = ContractTranslator()

        result = translator.translate(request)

        self.assertFalse(result.success)
        self.assertTrue(any("FASTLAB validation" in e for e in result.errors))
        self.assertIsNone(result.wire_payload)

    def test_invalid_temperature_rejected(self):
        request = _valid_game_request(temperature=5.0)
        translator = ContractTranslator()

        result = translator.translate(request)

        self.assertFalse(result.success)
        self.assertTrue(any("FASTLAB validation" in e for e in result.errors))

    def test_missing_task_intent_rejected(self):
        """Request without metadata.task_intent = 'game_navigation' is rejected."""
        metadata = {
            "source": "SPATHODEA_GAME",
            "turn": 1,
            "agent_position": "A1",
        }
        request = _valid_game_request(metadata=metadata)
        translator = ContractTranslator()

        result = translator.translate(request)

        self.assertFalse(result.success)
        self.assertTrue(any("task_intent" in e for e in result.errors))


# =============================================================================
# Test 13: Metadata preservation
# =============================================================================

class TestMetadataPreservation(unittest.TestCase):
    """Safe game metadata fields are preserved in wire payload."""

    def test_game_metadata_preserved(self):
        request = _valid_game_request()
        translator = ContractTranslator()

        result = translator.translate(request)

        self.assertTrue(result.success)
        wire_meta = result.wire_payload["metadata"]
        self.assertEqual(wire_meta["turn"], 1)
        self.assertEqual(wire_meta["agent_position"], "A1")
        self.assertEqual(wire_meta["strategy"], "adaptive")
        self.assertEqual(wire_meta["grid_width"], 5)
        self.assertEqual(wire_meta["grid_height"], 5)
        self.assertEqual(wire_meta["known_rewards"], 2)
        self.assertEqual(wire_meta["known_hazards"], 1)
        self.assertEqual(wire_meta["known_enemies"], 0)
        self.assertEqual(wire_meta["goal"], "E5")
        self.assertEqual(wire_meta["source"], "SPATHODEA_GAME")
        self.assertEqual(wire_meta["task_intent"], "game_navigation")

    def test_unsafe_metadata_not_forwarded(self):
        """Extra metadata fields not in safe list should not appear in wire."""
        metadata = {
            "source": "SPATHODEA_GAME",
            "task_intent": "game_navigation",
            "turn": 1,
            "agent_position": "A1",
            "strategy": "adaptive",
            "grid_width": 5,
            "grid_height": 5,
            "known_rewards": 0,
            "known_hazards": 0,
            "known_enemies": 0,
            "goal": "E5",
            "_secret_key": "should_not_appear",
            "internal_debug": True,
            "api_key": "sk-fake-123",
        }
        request = _valid_game_request(metadata=metadata)
        translator = ContractTranslator()

        result = translator.translate(request)

        self.assertTrue(result.success)
        wire_meta = result.wire_payload["metadata"]
        self.assertNotIn("_secret_key", wire_meta)
        self.assertNotIn("internal_debug", wire_meta)
        self.assertNotIn("api_key", wire_meta)


# =============================================================================
# Test 14: Source/target contract namespace
# =============================================================================

class TestContractNamespace(unittest.TestCase):
    """Translation result and wire metadata carry correct contract namespaces."""

    def test_result_namespaces(self):
        request = _valid_game_request()
        translator = ContractTranslator()

        result = translator.translate(request)

        self.assertEqual(result.source_contract, "FASTLAB-0.2.0")
        self.assertEqual(result.target_contract, "ATAN-BUZZ-0.2.0")

    def test_wire_metadata_namespaces(self):
        request = _valid_game_request()
        translator = ContractTranslator()

        result = translator.translate(request)

        self.assertTrue(result.success)
        wire_meta = result.wire_payload["metadata"]
        self.assertEqual(wire_meta["source_contract"], "FASTLAB-0.2.0")
        self.assertEqual(wire_meta["target_contract"], "ATAN-BUZZ-0.2.0")

    def test_constants_match(self):
        self.assertEqual(SOURCE_CONTRACT, "FASTLAB-0.2.0")
        self.assertEqual(TARGET_CONTRACT, "ATAN-BUZZ-0.2.0")


# =============================================================================
# Test 15: contract_version remains 0.2.0
# =============================================================================

class TestContractVersion(unittest.TestCase):
    """Wire payload contract_version is 0.2.0."""

    def test_wire_contract_version(self):
        request = _valid_game_request()
        translator = ContractTranslator()

        result = translator.translate(request)

        self.assertTrue(result.success)
        self.assertEqual(result.wire_payload["contract_version"], "0.2.0")

    def test_wire_version_constant(self):
        self.assertEqual(WIRE_CONTRACT_VERSION, "0.2.0")

    def test_fastlab_contract_version_unchanged(self):
        self.assertEqual(CONTRACT_VERSION, "0.2.0")


# =============================================================================
# Test 16: No mutation of original ProviderRequest
# =============================================================================

class TestNoMutation(unittest.TestCase):
    """Translation does NOT mutate the original ProviderRequest."""

    def test_original_unchanged(self):
        request = _valid_game_request()
        original_dict = request.to_dict()

        translator = ContractTranslator(config=TranslatorConfig(
            wire_execution_mode="consensus",
            wire_provider="openai",
            wire_reviewer="gemini",
        ))
        result = translator.translate(request)

        self.assertTrue(result.success)
        # Original request should be completely unchanged
        after_dict = request.to_dict()
        self.assertEqual(original_dict, after_dict)

    def test_metadata_not_mutated(self):
        request = _valid_game_request()
        original_meta = copy.deepcopy(request.metadata)

        translator = ContractTranslator()
        translator.translate(request)

        self.assertEqual(request.metadata, original_meta)


# =============================================================================
# Test 17: Deterministic translation
# =============================================================================

class TestDeterministic(unittest.TestCase):
    """Same input always produces same output."""

    def test_repeated_translation_identical(self):
        request = _valid_game_request()
        translator = ContractTranslator(config=TranslatorConfig(
            wire_execution_mode="single",
            wire_provider="openai",
            wire_reviewer="none",
        ))

        result1 = translator.translate(request)
        result2 = translator.translate(request)

        self.assertEqual(result1.wire_payload, result2.wire_payload)
        self.assertEqual(result1.success, result2.success)
        self.assertEqual(result1.errors, result2.errors)

    def test_different_translators_same_config(self):
        request = _valid_game_request()
        config = TranslatorConfig(
            wire_execution_mode="fallback",
            wire_provider="auto",
            wire_reviewer="none",
        )
        t1 = ContractTranslator(config=config)
        t2 = ContractTranslator(config=TranslatorConfig(
            wire_execution_mode="fallback",
            wire_provider="auto",
            wire_reviewer="none",
        ))

        r1 = t1.translate(request)
        r2 = t2.translate(request)

        self.assertEqual(r1.wire_payload, r2.wire_payload)


# =============================================================================
# Test 18: No secret-like metadata added
# =============================================================================

class TestNoSecrets(unittest.TestCase):
    """Wire payload does not contain secret-like fields."""

    def test_no_api_key_in_wire(self):
        request = _valid_game_request()
        translator = ContractTranslator()
        result = translator.translate(request)

        self.assertTrue(result.success)
        payload_str = str(result.wire_payload).lower()
        self.assertNotIn("api_key", payload_str)
        self.assertNotIn("secret", payload_str)
        self.assertNotIn("password", payload_str)
        self.assertNotIn("auth_token", payload_str)

    def test_wire_metadata_only_safe_fields(self):
        request = _valid_game_request()
        translator = ContractTranslator()
        result = translator.translate(request)

        wire_meta = result.wire_payload["metadata"]
        # All keys should be from the known safe set + translator context
        allowed_keys = {
            "turn", "agent_position", "strategy",
            "grid_width", "grid_height",
            "known_rewards", "known_hazards", "known_enemies",
            "goal", "source", "task_intent",
            "source_contract", "target_contract",
        }
        for key in wire_meta:
            self.assertIn(key, allowed_keys, f"Unexpected metadata key: {key}")


# =============================================================================
# Test: Invalid wire execution mode
# =============================================================================

class TestInvalidWireExecutionMode(unittest.TestCase):
    """Invalid wire execution mode is rejected."""

    def test_sync_not_valid_wire_mode(self):
        request = _valid_game_request()
        translator = ContractTranslator(config=TranslatorConfig(
            wire_execution_mode="sync",
        ))
        result = translator.translate(request)

        self.assertFalse(result.success)
        self.assertTrue(any("execution mode" in e.lower() for e in result.errors))

    def test_batch_not_valid_wire_mode(self):
        request = _valid_game_request()
        translator = ContractTranslator(config=TranslatorConfig(
            wire_execution_mode="batch",
        ))
        result = translator.translate(request)

        self.assertFalse(result.success)


# =============================================================================
# Runner
# =============================================================================

def run_translator_tests() -> dict:
    """Run all translator tests and return structured results."""
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
        "success": len(result.failures) == 0 and len(result.errors) == 0,
    }


if __name__ == "__main__":
    unittest.main(verbosity=2)

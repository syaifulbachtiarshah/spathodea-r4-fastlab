"""
SPATHODEA R4 FASTLAB — LIVE-20 Validator Tests
Offline tests for evaluation/live20_validator.py

Covers:
- valid JSON
- invalid JSON
- required keys present / missing
- forbidden terms
- clarification request (NOT_AUTOMATED)
- traceback detection
- code block detection
- length bounds (min/max)
- unsupported/non-automatable rule
- contract version mismatch
- request_id mismatch
- language detection
- must_contain_any / must_contain_all
- full record validation

No network calls. No API keys.

Run: python tests/test_live20_validator.py
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.live20_validator import (
    check_non_empty,
    check_json_valid,
    check_required_keys,
    check_forbidden_terms,
    check_required_language,
    check_contains_code_block,
    check_must_ask_clarification,
    check_must_not_contain_traceback,
    check_minimum_length,
    check_maximum_length,
    check_must_contain_any,
    check_must_contain_all,
    check_response_type,
    validate_content_rules,
    validate_response_envelope,
    validate_record_response,
    summarize_validations,
)


# =============================================================================
# Test: non_empty
# =============================================================================

class TestNonEmpty(unittest.TestCase):
    def test_pass(self):
        r = check_non_empty("Hello world")
        self.assertEqual(r["status"], "PASS")

    def test_fail_empty(self):
        r = check_non_empty("")
        self.assertEqual(r["status"], "FAIL")

    def test_fail_whitespace(self):
        r = check_non_empty("   \n\t  ")
        self.assertEqual(r["status"], "FAIL")


# =============================================================================
# Test: json_valid
# =============================================================================

class TestJsonValid(unittest.TestCase):
    def test_valid_json_object(self):
        r = check_json_valid('{"name": "test", "value": 42}')
        self.assertEqual(r["status"], "PASS")

    def test_valid_json_array(self):
        r = check_json_valid('[1, 2, 3]')
        self.assertEqual(r["status"], "PASS")

    def test_valid_json_in_code_fence(self):
        content = '```json\n{"key": "value"}\n```'
        r = check_json_valid(content)
        self.assertEqual(r["status"], "PASS")

    def test_invalid_json(self):
        r = check_json_valid("This is not JSON at all")
        self.assertEqual(r["status"], "FAIL")

    def test_malformed_json(self):
        r = check_json_valid('{"key": "value",}')
        self.assertEqual(r["status"], "FAIL")


# =============================================================================
# Test: required_keys
# =============================================================================

class TestRequiredKeys(unittest.TestCase):
    def test_all_present(self):
        content = '{"name": "Ali", "age": 30, "city": "KL"}'
        r = check_required_keys(content, rule_value=["name", "age", "city"])
        self.assertEqual(r["status"], "PASS")

    def test_missing_keys(self):
        content = '{"name": "Ali"}'
        r = check_required_keys(content, rule_value=["name", "age", "city"])
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("age", r["message"])

    def test_not_json(self):
        r = check_required_keys("plain text", rule_value=["key"])
        self.assertEqual(r["status"], "FAIL")

    def test_json_array_not_object(self):
        r = check_required_keys("[1, 2, 3]", rule_value=["key"])
        self.assertEqual(r["status"], "FAIL")


# =============================================================================
# Test: forbidden_terms
# =============================================================================

class TestForbiddenTerms(unittest.TestCase):
    def test_pass_no_forbidden(self):
        r = check_forbidden_terms("The sky is blue", rule_value=["red", "green"])
        self.assertEqual(r["status"], "PASS")

    def test_fail_contains_forbidden(self):
        r = check_forbidden_terms("I don't know the answer", rule_value=["I don't know"])
        self.assertEqual(r["status"], "FAIL")

    def test_case_insensitive(self):
        r = check_forbidden_terms("Here is the TRACEBACK", rule_value=["traceback"])
        self.assertEqual(r["status"], "FAIL")


# =============================================================================
# Test: must_ask_clarification (NOT_AUTOMATED)
# =============================================================================

class TestMustAskClarification(unittest.TestCase):
    def test_always_not_automated(self):
        r = check_must_ask_clarification("Could you clarify what you mean?")
        self.assertEqual(r["status"], "NOT_AUTOMATED")

    def test_even_obvious_case(self):
        r = check_must_ask_clarification("Done! I changed your password.")
        self.assertEqual(r["status"], "NOT_AUTOMATED")


# =============================================================================
# Test: must_not_contain_traceback
# =============================================================================

class TestTraceback(unittest.TestCase):
    def test_pass_clean(self):
        r = check_must_not_contain_traceback("Here is your answer: use the app.")
        self.assertEqual(r["status"], "PASS")

    def test_fail_traceback(self):
        content = 'Traceback (most recent call last):\n  File "main.py", line 1\nNameError'
        r = check_must_not_contain_traceback(content)
        self.assertEqual(r["status"], "FAIL")

    def test_fail_partial_traceback(self):
        r = check_must_not_contain_traceback('An error occurred: File "x.py" caused issue')
        self.assertEqual(r["status"], "FAIL")


# =============================================================================
# Test: contains_code_block
# =============================================================================

class TestCodeBlock(unittest.TestCase):
    def test_pass_fenced(self):
        content = "Here is code:\n```python\ndef hello():\n    pass\n```"
        r = check_contains_code_block(content)
        self.assertEqual(r["status"], "PASS")

    def test_pass_def_keyword(self):
        content = "def validate_ic(s):\n    return True"
        r = check_contains_code_block(content)
        self.assertEqual(r["status"], "PASS")

    def test_fail_no_code(self):
        r = check_contains_code_block("Just a normal paragraph about programming.")
        self.assertEqual(r["status"], "FAIL")


# =============================================================================
# Test: length bounds
# =============================================================================

class TestLengthBounds(unittest.TestCase):
    def test_min_pass(self):
        r = check_minimum_length("a" * 100, rule_value=50)
        self.assertEqual(r["status"], "PASS")

    def test_min_fail(self):
        r = check_minimum_length("short", rule_value=50)
        self.assertEqual(r["status"], "FAIL")

    def test_max_pass(self):
        r = check_maximum_length("a" * 50, rule_value=100)
        self.assertEqual(r["status"], "PASS")

    def test_max_fail(self):
        r = check_maximum_length("a" * 200, rule_value=100)
        self.assertEqual(r["status"], "FAIL")

    def test_exact_boundary_min(self):
        r = check_minimum_length("a" * 50, rule_value=50)
        self.assertEqual(r["status"], "PASS")

    def test_exact_boundary_max(self):
        r = check_maximum_length("a" * 100, rule_value=100)
        self.assertEqual(r["status"], "PASS")


# =============================================================================
# Test: response_type (semantic = NOT_AUTOMATED)
# =============================================================================

class TestResponseType(unittest.TestCase):
    def test_json_type_valid(self):
        r = check_response_type('{"key": "value"}', rule_value="json")
        self.assertEqual(r["status"], "PASS")

    def test_json_type_invalid(self):
        r = check_response_type("not json", rule_value="json")
        self.assertEqual(r["status"], "FAIL")

    def test_code_type_valid(self):
        r = check_response_type("```python\nprint('hi')\n```", rule_value="code")
        self.assertEqual(r["status"], "PASS")

    def test_semantic_type_not_automated(self):
        r = check_response_type("any content", rule_value="instructional")
        self.assertEqual(r["status"], "NOT_AUTOMATED")

    def test_advisory_type_not_automated(self):
        r = check_response_type("any content", rule_value="advisory")
        self.assertEqual(r["status"], "NOT_AUTOMATED")


# =============================================================================
# Test: must_contain_any / must_contain_all
# =============================================================================

class TestMustContain(unittest.TestCase):
    def test_contain_any_pass(self):
        r = check_must_contain_any("The balance is RM500", rule_value=["balance", "credit"])
        self.assertEqual(r["status"], "PASS")

    def test_contain_any_fail(self):
        r = check_must_contain_any("Hello world", rule_value=["balance", "credit"])
        self.assertEqual(r["status"], "FAIL")

    def test_contain_all_pass(self):
        r = check_must_contain_all("SSM registration and LHDN tax", rule_value=["SSM", "LHDN"])
        self.assertEqual(r["status"], "PASS")

    def test_contain_all_fail(self):
        r = check_must_contain_all("SSM only here", rule_value=["SSM", "LHDN"])
        self.assertEqual(r["status"], "FAIL")


# =============================================================================
# Test: required_language
# =============================================================================

class TestRequiredLanguage(unittest.TestCase):
    def test_english_detected(self):
        r = check_required_language(
            "The system will process your request and you should receive confirmation.",
            rule_value="en"
        )
        self.assertEqual(r["status"], "PASS")

    def test_malay_detected(self):
        r = check_required_language(
            "Untuk membantu anda dengan perkara ini sila ikuti langkah yang berikut.",
            rule_value="ms"
        )
        self.assertEqual(r["status"], "PASS")

    def test_mixed_detected(self):
        r = check_required_language(
            "Okay so basically anda perlu pergi ke settings and tukar the password.",
            rule_value="mixed"
        )
        self.assertEqual(r["status"], "PASS")

    def test_wrong_language(self):
        r = check_required_language(
            "The system will process your request automatically.",
            rule_value="ms"
        )
        self.assertEqual(r["status"], "FAIL")


# =============================================================================
# Test: Response Envelope Validation
# =============================================================================

class TestEnvelopeValidation(unittest.TestCase):
    def _good_response(self):
        return {
            "content": "Test content",
            "model": "gpt-4o-mini",
            "request_id": "test-001",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            "latency_ms": 123.45,
            "provider": "openai",
            "error": None,
            "contract_version": "0.2.0",
        }

    def test_valid_envelope(self):
        results = validate_response_envelope(self._good_response(), "test-001")
        statuses = [r["status"] for r in results]
        self.assertTrue(all(s == "PASS" for s in statuses))

    def test_contract_version_mismatch(self):
        resp = self._good_response()
        resp["contract_version"] = "0.1.0"
        results = validate_response_envelope(resp, "test-001")
        cv_result = next(r for r in results if r["rule"] == "envelope.contract_version")
        self.assertEqual(cv_result["status"], "FAIL")

    def test_request_id_mismatch(self):
        resp = self._good_response()
        resp["request_id"] = "wrong-id"
        results = validate_response_envelope(resp, "test-001")
        rid_result = next(r for r in results if r["rule"] == "envelope.request_id")
        self.assertEqual(rid_result["status"], "FAIL")

    def test_missing_usage_keys(self):
        resp = self._good_response()
        resp["usage"] = {"prompt_tokens": 10}
        results = validate_response_envelope(resp, "test-001")
        usage_result = next(r for r in results if r["rule"] == "envelope.usage")
        self.assertEqual(usage_result["status"], "FAIL")

    def test_negative_latency(self):
        resp = self._good_response()
        resp["latency_ms"] = -5.0
        results = validate_response_envelope(resp, "test-001")
        lat_result = next(r for r in results if r["rule"] == "envelope.latency_ms")
        self.assertEqual(lat_result["status"], "FAIL")


# =============================================================================
# Test: Full Record Validation
# =============================================================================

class TestFullRecordValidation(unittest.TestCase):
    def test_full_pass(self):
        record = {
            "record_id": "test-rec-001",
            "validation_rules": {
                "non_empty": True,
                "minimum_length": 10,
            },
        }
        response = {
            "content": "This is a perfectly valid response with enough length.",
            "model": "gpt-4o-mini",
            "request_id": "test-rec-001",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
            "latency_ms": 50.0,
            "provider": "openai",
            "error": None,
            "contract_version": "0.2.0",
        }
        result = validate_record_response(record, response)
        self.assertEqual(result["validation"]["overall_status"], "PASS")
        self.assertTrue(result["passed"])
        self.assertEqual(result["validation"]["automated_fail"], 0)

    def test_partial_with_non_automated(self):
        record = {
            "record_id": "test-rec-002",
            "validation_rules": {
                "non_empty": True,
                "response_type": "instructional",
            },
        }
        response = {
            "content": "Here is the answer with instructions.",
            "model": "gpt-4o-mini",
            "request_id": "test-rec-002",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 5, "completion_tokens": 8, "total_tokens": 13},
            "latency_ms": 30.0,
            "provider": "openai",
            "error": None,
            "contract_version": "0.2.0",
        }
        result = validate_record_response(record, response)
        self.assertEqual(result["validation"]["overall_status"], "PARTIAL")
        self.assertTrue(result["passed"])  # passed=true because automated_fail==0
        self.assertGreater(result["validation"]["not_automated"], 0)

    def test_fail_on_content_rule(self):
        record = {
            "record_id": "test-rec-003",
            "validation_rules": {
                "minimum_length": 500,
            },
        }
        response = {
            "content": "Short.",
            "model": "gpt-4o-mini",
            "request_id": "test-rec-003",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            "latency_ms": 10.0,
            "provider": "openai",
            "error": None,
            "contract_version": "0.2.0",
        }
        result = validate_record_response(record, response)
        self.assertEqual(result["validation"]["overall_status"], "FAIL")
        self.assertFalse(result["passed"])

    def test_error_response_skips_content(self):
        record = {
            "record_id": "test-rec-004",
            "validation_rules": {
                "non_empty": True,
                "minimum_length": 100,
            },
        }
        response = {
            "content": "",
            "model": "",
            "request_id": "test-rec-004",
            "finish_reason": "error",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "latency_ms": 5.0,
            "provider": "openai",
            "error": "Connection timeout",
            "contract_version": "0.2.0",
        }
        result = validate_record_response(record, response)
        # Content rules should be SKIPPED, not FAIL
        content_rules = [
            r for r in result["validation"]["rules"]
            if r["rule"] in ("non_empty", "minimum_length")
        ]
        for cr in content_rules:
            self.assertEqual(cr["status"], "SKIPPED")


# =============================================================================
# Test: Summary
# =============================================================================

class TestSummary(unittest.TestCase):
    def test_summary_structure(self):
        records = [
            {"record_id": "r1", "language": "en", "difficulty": "easy", "primary_provider": "openai"},
            {"record_id": "r2", "language": "ms", "difficulty": "hard", "primary_provider": "gemini"},
        ]
        results = [
            {"record_id": "r1", "validation": {"overall_status": "PASS", "automated_pass": 5, "automated_fail": 0, "not_automated": 1, "skipped": 0}},
            {"record_id": "r2", "validation": {"overall_status": "FAIL", "automated_pass": 3, "automated_fail": 2, "not_automated": 0, "skipped": 0}},
        ]
        summary = summarize_validations(results, records)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["passed"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["automated_rule_passes"], 8)
        self.assertEqual(summary["automated_rule_failures"], 2)
        self.assertEqual(summary["not_automated_rules"], 1)
        self.assertIn("language_breakdown", summary)
        self.assertIn("difficulty_breakdown", summary)
        self.assertIn("provider_breakdown", summary)


# =============================================================================
# Runner
# =============================================================================

def run_validator_tests() -> dict:
    """Run all validator tests and return structured results."""
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
        "failure_details": [{"test": str(t), "msg": m.split("\n")[-2] if m else ""} for t, m in result.failures],
        "error_details": [{"test": str(t), "msg": m.split("\n")[-2] if m else ""} for t, m in result.errors],
    }


if __name__ == "__main__":
    unittest.main(verbosity=2)

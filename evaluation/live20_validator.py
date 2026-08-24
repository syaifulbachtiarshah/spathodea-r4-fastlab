"""
SPATHODEA R4 FASTLAB — Deterministic LIVE-20 Validator
Evaluates BUZZ ProviderResponse content against validation_rules from live20.jsonl.

Uses deterministic checks only. No LLM judge. No network calls.
Non-automatable rules return status=NOT_AUTOMATED (never PASS, never FAIL).

Contract: BUZZ v0.2.0
"""

import json
import re
from typing import Optional

# Expected contract version
EXPECTED_CONTRACT_VERSION = "0.2.0"

# Rules that cannot be evaluated deterministically without LLM
NON_AUTOMATABLE_RULES = {
    "must_ask_clarification",
    "response_type",
}

# Additional response_type values that require semantic judgment
SEMANTIC_RESPONSE_TYPES = {
    "instructional", "comparison", "advisory", "explanatory",
    "corrective", "analytical", "empathetic_structured",
    "clarification_request", "refusal", "multi_part",
    "multi_part_structured", "summary", "classification",
    "email", "paraphrase", "rating_with_justification",
    "score_with_justification",
}


# =============================================================================
# Rule Validators
# =============================================================================

def check_non_empty(content: str, **_) -> dict:
    """Rule: non_empty — content must not be empty or whitespace-only."""
    if content and content.strip():
        return {"rule": "non_empty", "status": "PASS", "message": "Content is non-empty"}
    return {"rule": "non_empty", "status": "FAIL", "message": "Content is empty or whitespace-only"}


def check_json_valid(content: str, **_) -> dict:
    """Rule: json_valid — content must be valid parseable JSON."""
    # Strip markdown code fences if present
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        json.loads(text)
        return {"rule": "json_valid", "status": "PASS", "message": "Valid JSON"}
    except (json.JSONDecodeError, ValueError) as e:
        return {"rule": "json_valid", "status": "FAIL", "message": f"Invalid JSON: {e}"}


def check_required_keys(content: str, rule_value: list, **_) -> dict:
    """Rule: required_keys — parsed JSON must contain all specified keys."""
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {"rule": "required_keys", "status": "FAIL", "message": "Cannot parse JSON to check keys"}

    if not isinstance(obj, dict):
        return {"rule": "required_keys", "status": "FAIL", "message": "JSON root is not an object"}

    missing = [k for k in rule_value if k not in obj]
    if missing:
        return {"rule": "required_keys", "status": "FAIL", "message": f"Missing keys: {missing}"}
    return {"rule": "required_keys", "status": "PASS", "message": f"All {len(rule_value)} required keys present"}


def check_forbidden_terms(content: str, rule_value: list, **_) -> dict:
    """Rule: forbidden_terms — content must NOT contain any of the listed terms."""
    content_lower = content.lower()
    found = [term for term in rule_value if term.lower() in content_lower]
    if found:
        return {"rule": "forbidden_terms", "status": "FAIL", "message": f"Forbidden terms found: {found}"}
    return {"rule": "forbidden_terms", "status": "PASS", "message": "No forbidden terms found"}


def check_required_language(content: str, rule_value: str, **_) -> dict:
    """Rule: required_language — heuristic language detection.

    Checks presence of common language markers:
    - ms: Malay markers (yang, dan, untuk, dengan, ini, itu, saya, anda, adalah, telah)
    - en: English markers (the, is, are, was, were, have, this, that, will, can)
    - mixed: must contain markers from both
    """
    ms_markers = {"yang", "dan", "untuk", "dengan", "ini", "itu", "saya", "anda", "adalah",
                  "telah", "tidak", "boleh", "perlu", "dalam", "akan", "jika", "atau",
                  "sila", "kami", "mereka"}
    en_markers = {"the", "is", "are", "was", "were", "have", "has", "this", "that", "will",
                  "can", "your", "you", "would", "should", "which", "from", "been", "with"}

    words = set(re.findall(r'\b\w+\b', content.lower()))
    ms_count = len(words & ms_markers)
    en_count = len(words & en_markers)

    if rule_value == "ms":
        if ms_count >= 3 and ms_count > en_count:
            return {"rule": "required_language", "status": "PASS", "message": f"Malay detected (ms={ms_count}, en={en_count})"}
        elif ms_count >= 2:
            return {"rule": "required_language", "status": "PASS", "message": f"Malay likely (ms={ms_count}, en={en_count})"}
        return {"rule": "required_language", "status": "FAIL", "message": f"Expected Malay but got ms={ms_count}, en={en_count}"}
    elif rule_value == "en":
        if en_count >= 3 and en_count > ms_count:
            return {"rule": "required_language", "status": "PASS", "message": f"English detected (en={en_count}, ms={ms_count})"}
        elif en_count >= 2:
            return {"rule": "required_language", "status": "PASS", "message": f"English likely (en={en_count}, ms={ms_count})"}
        return {"rule": "required_language", "status": "FAIL", "message": f"Expected English but got en={en_count}, ms={ms_count}"}
    elif rule_value == "mixed":
        if ms_count >= 1 and en_count >= 1:
            return {"rule": "required_language", "status": "PASS", "message": f"Mixed detected (en={en_count}, ms={ms_count})"}
        return {"rule": "required_language", "status": "FAIL", "message": f"Expected mixed but got en={en_count}, ms={ms_count}"}

    return {"rule": "required_language", "status": "SKIPPED", "message": f"Unknown language target: {rule_value}"}


def check_contains_code_block(content: str, **_) -> dict:
    """Rule: contains_code_block — content must contain a fenced code block or def/class keyword."""
    if "```" in content:
        return {"rule": "contains_code_block", "status": "PASS", "message": "Fenced code block found"}
    if re.search(r'\bdef\s+\w+\s*\(', content):
        return {"rule": "contains_code_block", "status": "PASS", "message": "Python function definition found"}
    if re.search(r'\bclass\s+\w+', content):
        return {"rule": "contains_code_block", "status": "PASS", "message": "Class definition found"}
    return {"rule": "contains_code_block", "status": "FAIL", "message": "No code block or function/class definition found"}


def check_must_not_contain_traceback(content: str, **_) -> dict:
    """Rule: must_not_contain_traceback — content must not contain Python traceback."""
    traceback_markers = ["Traceback (most recent call last)", "File \"", "raise ", "Error:"]
    for marker in traceback_markers:
        if marker in content:
            return {"rule": "must_not_contain_traceback", "status": "FAIL", "message": f"Traceback marker found: '{marker}'"}
    return {"rule": "must_not_contain_traceback", "status": "PASS", "message": "No traceback detected"}


def check_minimum_length(content: str, rule_value: int, **_) -> dict:
    """Rule: minimum_length — content must be at least N characters."""
    actual = len(content)
    if actual >= rule_value:
        return {"rule": "minimum_length", "status": "PASS", "message": f"Length {actual} >= {rule_value}"}
    return {"rule": "minimum_length", "status": "FAIL", "message": f"Length {actual} < {rule_value} required"}


def check_maximum_length(content: str, rule_value: int, **_) -> dict:
    """Rule: maximum_length — content must be at most N characters."""
    actual = len(content)
    if actual <= rule_value:
        return {"rule": "maximum_length", "status": "PASS", "message": f"Length {actual} <= {rule_value}"}
    return {"rule": "maximum_length", "status": "FAIL", "message": f"Length {actual} > {rule_value} limit"}


def check_must_contain_any(content: str, rule_value: list, **_) -> dict:
    """Rule: must_contain_any — content must contain at least one of the listed terms."""
    content_lower = content.lower()
    found = [term for term in rule_value if term.lower() in content_lower]
    if found:
        return {"rule": "must_contain_any", "status": "PASS", "message": f"Found: {found[:3]}"}
    return {"rule": "must_contain_any", "status": "FAIL", "message": f"None of {rule_value} found in content"}


def check_must_contain_all(content: str, rule_value: list, **_) -> dict:
    """Rule: must_contain_all — content must contain ALL listed terms."""
    content_lower = content.lower()
    missing = [term for term in rule_value if term.lower() not in content_lower]
    if not missing:
        return {"rule": "must_contain_all", "status": "PASS", "message": f"All {len(rule_value)} terms found"}
    return {"rule": "must_contain_all", "status": "FAIL", "message": f"Missing: {missing}"}


def check_must_ask_clarification(content: str, **_) -> dict:
    """Rule: must_ask_clarification — requires semantic judgment."""
    return {"rule": "must_ask_clarification", "status": "NOT_AUTOMATED", "message": "Requires semantic judgment (LLM judge needed)"}


def check_response_type(content: str, rule_value: str, **_) -> dict:
    """Rule: response_type — most types require semantic judgment."""
    # Only json type can be checked deterministically
    if rule_value == "json":
        result = check_json_valid(content)
        result["rule"] = "response_type"
        return result
    elif rule_value == "code":
        result = check_contains_code_block(content)
        result["rule"] = "response_type"
        return result
    # All other response_type values are semantic
    return {"rule": "response_type", "status": "NOT_AUTOMATED", "message": f"response_type='{rule_value}' requires semantic judgment"}


# =============================================================================
# Rule Dispatcher
# =============================================================================

RULE_HANDLERS = {
    "non_empty": check_non_empty,
    "json_valid": check_json_valid,
    "required_keys": check_required_keys,
    "forbidden_terms": check_forbidden_terms,
    "required_language": check_required_language,
    "contains_code_block": check_contains_code_block,
    "contains_code_block_or_math": check_contains_code_block,  # alias
    "must_ask_clarification": check_must_ask_clarification,
    "must_not_contain_traceback": check_must_not_contain_traceback,
    "minimum_length": check_minimum_length,
    "maximum_length": check_maximum_length,
    "must_contain_any": check_must_contain_any,
    "must_contain_all": check_must_contain_all,
    "response_type": check_response_type,
}

# Rules to skip entirely (informational, not checkable)
SKIP_RULES = {"dedup_pair", "maximum_extra_keys"}


def validate_content_rules(content: str, validation_rules: dict) -> list[dict]:
    """Apply all validation_rules to the content.

    Args:
        content: The response content string from ProviderResponse
        validation_rules: The validation_rules dict from the live20 record

    Returns:
        List of rule result dicts: [{rule, status, message}, ...]
    """
    results = []
    for rule_name, rule_value in validation_rules.items():
        if rule_name in SKIP_RULES:
            results.append({"rule": rule_name, "status": "SKIPPED", "message": "Informational rule, not validated"})
            continue

        handler = RULE_HANDLERS.get(rule_name)
        if handler is None:
            results.append({"rule": rule_name, "status": "NOT_AUTOMATED", "message": f"No handler for rule '{rule_name}'"})
            continue

        # Call handler with content and rule_value
        if rule_value is True or rule_value is False:
            # Boolean rules (non_empty=true, etc.)
            if rule_value:
                result = handler(content)
            else:
                results.append({"rule": rule_name, "status": "SKIPPED", "message": "Rule disabled (value=false)"})
                continue
        else:
            result = handler(content, rule_value=rule_value)

        results.append(result)
    return results


# =============================================================================
# Response Envelope Validation
# =============================================================================

def validate_response_envelope(response: dict, expected_request_id: str) -> list[dict]:
    """Validate the BUZZ ProviderResponse envelope structure.

    Checks:
    - contract_version == 0.2.0
    - request_id matches expected
    - provider is present
    - model is present
    - finish_reason is present
    - usage object exists with required keys
    - latency_ms exists and >= 0
    - error format (null on success, string on failure)

    Args:
        response: ProviderResponse as dict
        expected_request_id: The request_id we sent

    Returns:
        List of rule result dicts
    """
    results = []

    # contract_version
    cv = response.get("contract_version")
    if cv == EXPECTED_CONTRACT_VERSION:
        results.append({"rule": "envelope.contract_version", "status": "PASS", "message": f"v{cv}"})
    elif cv is None:
        results.append({"rule": "envelope.contract_version", "status": "PASS", "message": "Not present (backward-compatible v0.1.0 response)"})
    else:
        results.append({"rule": "envelope.contract_version", "status": "FAIL", "message": f"Expected {EXPECTED_CONTRACT_VERSION}, got {cv}"})

    # request_id
    rid = response.get("request_id")
    if rid == expected_request_id:
        results.append({"rule": "envelope.request_id", "status": "PASS", "message": f"Matches: {rid}"})
    else:
        results.append({"rule": "envelope.request_id", "status": "FAIL", "message": f"Expected '{expected_request_id}', got '{rid}'"})

    # provider
    provider = response.get("provider")
    if provider and isinstance(provider, str) and provider.strip():
        results.append({"rule": "envelope.provider", "status": "PASS", "message": f"Provider: {provider}"})
    else:
        results.append({"rule": "envelope.provider", "status": "FAIL", "message": "Provider field missing or empty"})

    # model
    model = response.get("model")
    if model is not None and isinstance(model, str):
        results.append({"rule": "envelope.model", "status": "PASS", "message": f"Model: {model}"})
    else:
        results.append({"rule": "envelope.model", "status": "FAIL", "message": "Model field missing"})

    # finish_reason
    fr = response.get("finish_reason")
    if fr and isinstance(fr, str) and fr.strip():
        results.append({"rule": "envelope.finish_reason", "status": "PASS", "message": f"Finish reason: {fr}"})
    else:
        results.append({"rule": "envelope.finish_reason", "status": "FAIL", "message": "finish_reason missing or empty"})

    # usage
    usage = response.get("usage")
    if isinstance(usage, dict):
        required_usage_keys = {"prompt_tokens", "completion_tokens", "total_tokens"}
        missing = required_usage_keys - set(usage.keys())
        if not missing:
            results.append({"rule": "envelope.usage", "status": "PASS", "message": "All usage keys present"})
        else:
            results.append({"rule": "envelope.usage", "status": "FAIL", "message": f"Missing usage keys: {missing}"})
    else:
        results.append({"rule": "envelope.usage", "status": "FAIL", "message": "Usage object missing or not a dict"})

    # latency_ms
    latency = response.get("latency_ms")
    if isinstance(latency, (int, float)) and latency >= 0:
        results.append({"rule": "envelope.latency_ms", "status": "PASS", "message": f"{latency:.2f} ms"})
    elif latency is None:
        results.append({"rule": "envelope.latency_ms", "status": "FAIL", "message": "latency_ms missing"})
    else:
        results.append({"rule": "envelope.latency_ms", "status": "FAIL", "message": f"Invalid latency: {latency}"})

    # error format
    error = response.get("error")
    fr = response.get("finish_reason", "")
    if error is None and fr != "error":
        results.append({"rule": "envelope.error_format", "status": "PASS", "message": "No error (success)"})
    elif isinstance(error, str) and error and fr == "error":
        results.append({"rule": "envelope.error_format", "status": "PASS", "message": "Error properly formatted"})
    elif error is None and fr == "error":
        results.append({"rule": "envelope.error_format", "status": "FAIL", "message": "finish_reason=error but error field is null"})
    else:
        results.append({"rule": "envelope.error_format", "status": "PASS", "message": "Error/finish_reason consistent"})

    return results


# =============================================================================
# Full Record Validation
# =============================================================================

def validate_record_response(record: dict, response: dict) -> dict:
    """Validate a complete response against its record's rules.

    Args:
        record: Original live20 record (with validation_rules)
        response: BUZZ ProviderResponse dict

    Returns:
        Validation result dict with rules, counts, and overall_status
    """
    all_rules = []

    # 1. Envelope validation
    envelope_results = validate_response_envelope(response, record["record_id"])
    all_rules.extend(envelope_results)

    # 2. Content validation (only if response is successful)
    content = response.get("content", "")
    error = response.get("error")
    if error is None and content:
        content_results = validate_content_rules(content, record.get("validation_rules", {}))
        all_rules.extend(content_results)
    elif error:
        # If response is an error, skip content rules
        for rule_name in record.get("validation_rules", {}):
            all_rules.append({"rule": rule_name, "status": "SKIPPED", "message": "Skipped due to error response"})

    # Count statuses
    automated_pass = sum(1 for r in all_rules if r["status"] == "PASS")
    automated_fail = sum(1 for r in all_rules if r["status"] == "FAIL")
    not_automated = sum(1 for r in all_rules if r["status"] == "NOT_AUTOMATED")
    skipped = sum(1 for r in all_rules if r["status"] == "SKIPPED")

    # Determine overall status
    if automated_fail > 0:
        overall_status = "FAIL"
    elif not_automated > 0:
        overall_status = "PARTIAL"
    else:
        overall_status = "PASS"

    # passed = true only when automated_fail == 0
    passed = automated_fail == 0

    return {
        "record_id": record["record_id"],
        "validation": {
            "rules": all_rules,
            "automated_pass": automated_pass,
            "automated_fail": automated_fail,
            "not_automated": not_automated,
            "skipped": skipped,
            "overall_status": overall_status,
        },
        "passed": passed,
    }


# =============================================================================
# Batch Validation Summary
# =============================================================================

def summarize_validations(results: list[dict], records: list[dict]) -> dict:
    """Produce aggregate summary from a batch of validation results.

    Args:
        results: List of validate_record_response() outputs
        records: Original live20 records (for metadata)

    Returns:
        Summary dict suitable for live20_summary.json
    """
    total = len(results)
    passed = sum(1 for r in results if r["validation"]["overall_status"] == "PASS")
    failed = sum(1 for r in results if r["validation"]["overall_status"] == "FAIL")
    partial = sum(1 for r in results if r["validation"]["overall_status"] == "PARTIAL")

    all_rule_pass = sum(r["validation"]["automated_pass"] for r in results)
    all_rule_fail = sum(r["validation"]["automated_fail"] for r in results)
    all_not_auto = sum(r["validation"]["not_automated"] for r in results)

    # Breakdowns
    from collections import Counter
    lang_status = Counter()
    diff_status = Counter()
    prov_status = Counter()

    record_map = {r["record_id"]: r for r in records}
    for result in results:
        rec = record_map.get(result["record_id"], {})
        lang = rec.get("language", "unknown")
        diff = rec.get("difficulty", "unknown")
        prov = rec.get("primary_provider", "unknown")
        status = result["validation"]["overall_status"]

        lang_status[f"{lang}_{status}"] += 1
        diff_status[f"{diff}_{status}"] += 1
        prov_status[f"{prov}_{status}"] += 1

    def _breakdown(counter, categories):
        breakdown = {}
        for cat in categories:
            breakdown[cat] = {
                "pass": counter.get(f"{cat}_PASS", 0),
                "fail": counter.get(f"{cat}_FAIL", 0),
                "partial": counter.get(f"{cat}_PARTIAL", 0),
            }
        return breakdown

    languages = sorted(set(r.get("language", "unknown") for r in records))
    difficulties = sorted(set(r.get("difficulty", "unknown") for r in records))
    providers = sorted(set(r.get("primary_provider", "unknown") for r in records))

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "partial": partial,
        "automated_rule_passes": all_rule_pass,
        "automated_rule_failures": all_rule_fail,
        "not_automated_rules": all_not_auto,
        "language_breakdown": _breakdown(lang_status, languages),
        "difficulty_breakdown": _breakdown(diff_status, difficulties),
        "provider_breakdown": _breakdown(prov_status, providers),
    }

#!/usr/bin/env python3
"""
SPATHODEA R4 FASTLAB — LIVE-20 Offline Validator
Validates live20.jsonl without calling external services.

Checks:
- Exactly 20 JSONL records
- All record_id values unique
- Every required field exists and is non-empty
- Provider names are valid
- No duplicate prompts
- JSONL parses successfully
- task_type and difficulty values are valid

Run: python evaluation/validate_live20.py
"""

import json
import sys
import os
from pathlib import Path

# Constants
VALID_PROVIDERS = {"openai", "gemini", "ollama", "mock"}
VALID_DIFFICULTIES = {"easy", "medium", "hard"}
VALID_TASK_TYPES = {"generate", "adversarial", "review", "score", "paraphrase"}
VALID_LANGUAGES = {"en", "ms", "mixed"}
REQUIRED_FIELDS = [
    "record_id", "task_type", "language", "difficulty",
    "prompt", "expected_behavior", "validation_rules",
    "primary_provider", "reviewer_provider", "tags",
]
EXPECTED_COUNT = 20


def validate_live20(filepath: str = None) -> dict:
    """Validate live20.jsonl and return structured results."""
    if filepath is None:
        filepath = str(Path(__file__).parent / "live20.jsonl")

    results = {
        "file": filepath,
        "total_records": 0,
        "valid": True,
        "errors": [],
        "warnings": [],
        "stats": {},
    }

    path = Path(filepath)
    if not path.exists():
        results["valid"] = False
        results["errors"].append(f"File not found: {filepath}")
        return results

    # Parse all records
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                records.append((line_num, record))
            except json.JSONDecodeError as e:
                results["valid"] = False
                results["errors"].append(f"Line {line_num}: Invalid JSON — {e}")

    results["total_records"] = len(records)

    # Check exact count
    if len(records) != EXPECTED_COUNT:
        results["valid"] = False
        results["errors"].append(
            f"Expected exactly {EXPECTED_COUNT} records, got {len(records)}"
        )

    # Check required fields and uniqueness
    record_ids = []
    prompts = []
    languages = []
    difficulties = []
    primary_providers = []
    reviewer_providers = []

    for line_num, record in records:
        rid = record.get("record_id", f"<line {line_num}>")

        # Required fields
        for field in REQUIRED_FIELDS:
            if field not in record:
                results["valid"] = False
                results["errors"].append(f"{rid}: Missing required field '{field}'")
            elif record[field] is None or (isinstance(record[field], str) and not record[field].strip()):
                results["valid"] = False
                results["errors"].append(f"{rid}: Field '{field}' is empty/null")

        # Record ID uniqueness
        record_ids.append(record.get("record_id"))

        # Provider validation
        pp = record.get("primary_provider", "")
        rp = record.get("reviewer_provider", "")
        if pp not in VALID_PROVIDERS:
            results["valid"] = False
            results["errors"].append(f"{rid}: Invalid primary_provider '{pp}'")
        if rp not in VALID_PROVIDERS:
            results["valid"] = False
            results["errors"].append(f"{rid}: Invalid reviewer_provider '{rp}'")

        # Difficulty validation
        diff = record.get("difficulty", "")
        if diff not in VALID_DIFFICULTIES:
            results["valid"] = False
            results["errors"].append(f"{rid}: Invalid difficulty '{diff}'")

        # Task type validation
        tt = record.get("task_type", "")
        if tt not in VALID_TASK_TYPES:
            results["valid"] = False
            results["errors"].append(f"{rid}: Invalid task_type '{tt}'")

        # Language validation
        lang = record.get("language", "")
        if lang not in VALID_LANGUAGES:
            results["valid"] = False
            results["errors"].append(f"{rid}: Invalid language '{lang}'")

        # Collect stats
        prompts.append(record.get("prompt", ""))
        languages.append(lang)
        difficulties.append(diff)
        primary_providers.append(pp)
        reviewer_providers.append(rp)

    # Unique record_ids
    id_dupes = [rid for rid in record_ids if record_ids.count(rid) > 1]
    if id_dupes:
        results["valid"] = False
        results["errors"].append(f"Duplicate record_ids: {set(id_dupes)}")

    # No duplicate prompts
    prompt_dupes = [p[:50] for p in prompts if prompts.count(p) > 1]
    if prompt_dupes:
        results["valid"] = False
        results["errors"].append(f"Duplicate prompts found: {set(prompt_dupes)}")

    # Stats
    from collections import Counter
    results["stats"] = {
        "language_distribution": dict(Counter(languages)),
        "difficulty_distribution": dict(Counter(difficulties)),
        "primary_provider_distribution": dict(Counter(primary_providers)),
        "reviewer_provider_distribution": dict(Counter(reviewer_providers)),
    }

    return results


def main():
    """Run validation and print report."""
    results = validate_live20()

    print()
    print("=" * 60)
    print("  🧪 LIVE-20 Qualification Set — Validation Report")
    print("=" * 60)
    print()
    print(f"  File: {results['file']}")
    print(f"  Records: {results['total_records']}")
    print(f"  Status: {'✅ VALID' if results['valid'] else '❌ INVALID'}")
    print()

    if results["errors"]:
        print(f"  Errors ({len(results['errors'])}):")
        for err in results["errors"]:
            print(f"    ✗ {err}")
        print()

    if results["warnings"]:
        print(f"  Warnings ({len(results['warnings'])}):")
        for warn in results["warnings"]:
            print(f"    ⚠ {warn}")
        print()

    stats = results.get("stats", {})
    if stats:
        print("  Language distribution:")
        for k, v in sorted(stats.get("language_distribution", {}).items()):
            print(f"    {k}: {v}")
        print()
        print("  Difficulty distribution:")
        for k, v in sorted(stats.get("difficulty_distribution", {}).items()):
            print(f"    {k}: {v}")
        print()
        print("  Primary provider distribution:")
        for k, v in sorted(stats.get("primary_provider_distribution", {}).items()):
            print(f"    {k}: {v}")
        print()
        print("  Reviewer provider distribution:")
        for k, v in sorted(stats.get("reviewer_provider_distribution", {}).items()):
            print(f"    {k}: {v}")
        print()

    print("=" * 60)
    print()

    return 0 if results["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())

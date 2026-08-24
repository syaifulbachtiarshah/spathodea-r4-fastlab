"""
SPATHODEA R4 FASTLAB — Deterministic Record Validator
Validates internal master records against the schema and business rules.
"""

import json
import re
import uuid
from pathlib import Path
from typing import Optional


# UUID v4 pattern with r4- prefix
ID_PATTERN = re.compile(
    r"^r4-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

VALID_DIFFICULTIES = {"easy", "medium", "hard", "adversarial", "noisy"}
VALID_LANGUAGES = {"en", "ms", "mixed"}


class ValidationError:
    """Represents a single validation failure."""

    def __init__(self, field: str, rule: str, message: str):
        self.field = field
        self.rule = rule
        self.message = message

    def to_dict(self) -> dict:
        return {"field": self.field, "rule": self.rule, "message": self.message}

    def __repr__(self) -> str:
        return f"<ValidationError {self.field}: {self.message}>"


class ValidationResult:
    """Result of validating a single record."""

    def __init__(self, record_id: Optional[str] = None):
        self.record_id = record_id
        self.errors: list[ValidationError] = []

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, field: str, rule: str, message: str):
        self.errors.append(ValidationError(field, rule, message))

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "is_valid": self.is_valid,
            "error_count": len(self.errors),
            "errors": [e.to_dict() for e in self.errors],
        }


class Validator:
    """Deterministic schema and business-rule validator for internal records.
    
    All validation is rule-based and deterministic — no randomness,
    no LLM calls, same input always produces same result.
    """

    def __init__(self, config: Optional[dict] = None):
        cfg = config or {}
        self.max_input_length = cfg.get("max_input_length", 4096)
        self.max_output_length = cfg.get("max_output_length", 8192)
        self.min_input_length = cfg.get("min_input_length", 5)
        self.min_output_length = cfg.get("min_output_length", 10)

    def validate_record(self, record: dict) -> ValidationResult:
        """Validate a single internal master record.
        
        Checks (in order):
        1. Required fields present
        2. ID format (r4-{uuid4})
        3. Input constraints
        4. Output constraints
        5. Metadata required fields
        6. Metadata enum values
        7. No control characters
        
        Returns:
            ValidationResult with all errors found
        """
        result = ValidationResult(record.get("id"))

        # --- Check required top-level fields ---
        for field in ("id", "input", "output", "metadata"):
            if field not in record:
                result.add_error(field, "required", f"Missing required field: {field}")

        # If critical fields missing, return early
        if not result.is_valid:
            return result

        # --- Validate ID ---
        rec_id = record["id"]
        if not isinstance(rec_id, str):
            result.add_error("id", "type", "ID must be a string")
        elif not ID_PATTERN.match(rec_id):
            result.add_error("id", "format", f"ID must match r4-{{uuid4}} pattern, got: {rec_id[:50]}")

        # --- Validate input ---
        inp = record["input"]
        if not isinstance(inp, str):
            result.add_error("input", "type", "Input must be a string")
        elif len(inp.strip()) == 0:
            result.add_error("input", "empty", "Input must not be empty/whitespace-only")
        elif len(inp) < self.min_input_length:
            result.add_error("input", "min_length", f"Input too short ({len(inp)} < {self.min_input_length})")
        elif len(inp) > self.max_input_length:
            result.add_error("input", "max_length", f"Input too long ({len(inp)} > {self.max_input_length})")
        elif self._has_control_chars(inp):
            result.add_error("input", "control_chars", "Input contains invalid control characters")

        # --- Validate output ---
        out = record["output"]
        if not isinstance(out, str):
            result.add_error("output", "type", "Output must be a string")
        elif len(out.strip()) == 0:
            result.add_error("output", "empty", "Output must not be empty/whitespace-only")
        elif len(out) < self.min_output_length:
            result.add_error("output", "min_length", f"Output too short ({len(out)} < {self.min_output_length})")
        elif len(out) > self.max_output_length:
            result.add_error("output", "max_length", f"Output too long ({len(out)} > {self.max_output_length})")
        elif self._has_control_chars(out):
            result.add_error("output", "control_chars", "Output contains invalid control characters")

        # --- Validate system_prompt (optional) ---
        if "system_prompt" in record and record["system_prompt"] is not None:
            sp = record["system_prompt"]
            if not isinstance(sp, str):
                result.add_error("system_prompt", "type", "system_prompt must be string or null")
            elif len(sp) > 2048:
                result.add_error("system_prompt", "max_length", "system_prompt exceeds 2048 chars")

        # --- Validate metadata ---
        meta = record["metadata"]
        if not isinstance(meta, dict):
            result.add_error("metadata", "type", "Metadata must be an object")
            return result

        # Required metadata fields
        for mfield in ("intent", "difficulty", "language", "generator"):
            if mfield not in meta:
                result.add_error(f"metadata.{mfield}", "required", f"Missing required metadata field: {mfield}")
            elif not isinstance(meta[mfield], str) or len(meta[mfield].strip()) == 0:
                result.add_error(f"metadata.{mfield}", "empty", f"metadata.{mfield} must be non-empty string")

        # Enum validation
        if "difficulty" in meta and isinstance(meta["difficulty"], str):
            if meta["difficulty"] not in VALID_DIFFICULTIES:
                result.add_error(
                    "metadata.difficulty", "enum",
                    f"Invalid difficulty: '{meta['difficulty']}'. Valid: {sorted(VALID_DIFFICULTIES)}"
                )

        if "language" in meta and isinstance(meta["language"], str):
            if meta["language"] not in VALID_LANGUAGES:
                result.add_error(
                    "metadata.language", "enum",
                    f"Invalid language: '{meta['language']}'. Valid: {sorted(VALID_LANGUAGES)}"
                )

        # Quality score bounds
        if "quality_score" in meta and meta["quality_score"] is not None:
            qs = meta["quality_score"]
            if not isinstance(qs, (int, float)):
                result.add_error("metadata.quality_score", "type", "quality_score must be a number or null")
            elif qs < 0.0 or qs > 1.0:
                result.add_error("metadata.quality_score", "range", "quality_score must be between 0.0 and 1.0")

        return result

    def validate_file(self, filepath: str) -> dict:
        """Validate all records in a JSONL file.
        
        Returns:
            Dict with: {total, valid, invalid, errors: [...]}
        """
        path = Path(filepath)
        if not path.exists():
            return {"total": 0, "valid": 0, "invalid": 0, "errors": [f"File not found: {filepath}"]}

        total = 0
        valid = 0
        invalid = 0
        all_errors = []

        with open(path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                total += 1

                try:
                    record = json.loads(line)
                except json.JSONDecodeError as e:
                    invalid += 1
                    all_errors.append({
                        "line": line_num,
                        "error": f"Invalid JSON: {e}",
                    })
                    continue

                result = self.validate_record(record)
                if result.is_valid:
                    valid += 1
                else:
                    invalid += 1
                    all_errors.append({
                        "line": line_num,
                        "record_id": result.record_id,
                        "errors": [e.to_dict() for e in result.errors],
                    })

        return {
            "total": total,
            "valid": valid,
            "invalid": invalid,
            "errors": all_errors,
        }

    def _has_control_chars(self, text: str) -> bool:
        """Check for invalid control characters (allow newline, tab, carriage return)."""
        for ch in text:
            code = ord(ch)
            if code < 32 and code not in (9, 10, 13):  # Allow \t, \n, \r
                return True
        return False

    @staticmethod
    def generate_id() -> str:
        """Generate a new valid record ID."""
        return f"r4-{uuid.uuid4()}"

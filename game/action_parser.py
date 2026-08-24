"""
SPATHODEA R4 FASTLAB — Action Parser (Phase 2F Part 2)
Parses provider/LLM output into a validated Action.

Accepted formats:
    - Plain text: "UP", "DOWN", "LEFT", "RIGHT", "WAIT"
    - JSON object: {"action": "UP"}
    - Fenced JSON: ```json\n{"action": "UP"}\n```
    - Case-insensitive matching

Rejected:
    - Invalid/unknown action words
    - Multiple conflicting actions in output
    - Empty output
    - HTML content
    - Python tracebacks
    - Malformed JSON (when JSON-like input detected)

Future reserved actions (recognized but not executed):
    - INTERACT, PICKUP, ATTACK
"""

import json
import re
from dataclasses import dataclass
from typing import Optional

from .action_schema import Action, FutureAction


# =============================================================================
# Parse Result
# =============================================================================

@dataclass
class ActionParseResult:
    """Result of parsing a provider response into an Action.

    Attributes:
        action: Parsed action (None if parsing failed)
        success: Whether parsing succeeded
        raw_input: Original input string (truncated for logging)
        method: How the action was extracted (plain/json/fenced_json)
        error: Error message if parsing failed
        is_future_action: True if a reserved future action was detected
    """
    action: Optional[Action] = None
    success: bool = False
    raw_input: str = ""
    method: str = ""
    error: str = ""
    is_future_action: bool = False

    def to_dict(self) -> dict:
        return {
            "action": self.action.value if self.action else None,
            "success": self.success,
            "raw_input": self.raw_input[:100],
            "method": self.method,
            "error": self.error,
            "is_future_action": self.is_future_action,
        }


# =============================================================================
# Constants
# =============================================================================

_VALID_ACTION_NAMES = {a.value for a in Action}
_FUTURE_ACTION_NAMES = {a.value for a in FutureAction}
_ALL_KNOWN_ACTIONS = _VALID_ACTION_NAMES | _FUTURE_ACTION_NAMES

# Patterns for rejection
_HTML_PATTERN = re.compile(r'<\s*(html|body|div|span|p|script|head)\b', re.IGNORECASE)
_TRACEBACK_PATTERN = re.compile(r'Traceback \(most recent call last\)|File ".*", line \d+')
_JSON_FENCE_PATTERN = re.compile(r'```(?:json)?\s*\n?(.*?)\n?\s*```', re.DOTALL)
_JSON_OBJECT_PATTERN = re.compile(r'\{[^{}]*\}')


# =============================================================================
# Action Parser
# =============================================================================

class ActionParser:
    """Parses provider output into validated Action enum values.

    Stateless parser — each call is independent.
    Never executes invalid or future-reserved actions.
    """

    def parse(self, raw_output: str) -> ActionParseResult:
        """Parse provider output into a valid Action.

        Tries multiple extraction methods in order:
        1. Reject obviously invalid content (HTML, traceback, empty)
        2. Try fenced JSON extraction
        3. Try plain JSON object extraction
        4. Try plain text action word extraction

        Args:
            raw_output: Raw string from provider response content

        Returns:
            ActionParseResult with parsed action or error details
        """
        # Truncate for logging safety
        raw_summary = raw_output[:200] if raw_output else ""

        # 1. Empty check
        if not raw_output or not raw_output.strip():
            return ActionParseResult(
                success=False,
                raw_input=raw_summary,
                error="Empty output from provider",
            )

        stripped = raw_output.strip()

        # 2. HTML rejection
        if _HTML_PATTERN.search(stripped):
            return ActionParseResult(
                success=False,
                raw_input=raw_summary,
                error="HTML content detected — rejected",
            )

        # 3. Traceback rejection
        if _TRACEBACK_PATTERN.search(stripped):
            return ActionParseResult(
                success=False,
                raw_input=raw_summary,
                error="Python traceback detected — rejected",
            )

        # 4. Try fenced JSON (```json ... ```)
        result = self._try_fenced_json(stripped, raw_summary)
        if result:
            return result

        # 5. Try plain JSON object
        result = self._try_json_object(stripped, raw_summary)
        if result:
            return result

        # 6. Try plain text extraction
        result = self._try_plain_text(stripped, raw_summary)
        if result:
            return result

        # 7. Nothing matched
        return ActionParseResult(
            success=False,
            raw_input=raw_summary,
            error=f"Could not extract valid action from output: '{stripped[:60]}'",
        )

    def _try_fenced_json(self, text: str, raw_summary: str) -> Optional[ActionParseResult]:
        """Try extracting action from fenced JSON code block."""
        match = _JSON_FENCE_PATTERN.search(text)
        if not match:
            return None

        json_str = match.group(1).strip()
        return self._parse_json_action(json_str, raw_summary, method="fenced_json")

    def _try_json_object(self, text: str, raw_summary: str) -> Optional[ActionParseResult]:
        """Try extracting action from a JSON object in the text."""
        # Only try if it looks like JSON
        if '{' not in text:
            return None

        match = _JSON_OBJECT_PATTERN.search(text)
        if not match:
            # Has braces but malformed
            return ActionParseResult(
                success=False,
                raw_input=raw_summary,
                error="Malformed JSON detected (contains braces but not parseable)",
            )

        json_str = match.group(0)
        result = self._parse_json_action(json_str, raw_summary, method="json")
        if result:
            return result

        # JSON parsed but no action field
        return ActionParseResult(
            success=False,
            raw_input=raw_summary,
            error="JSON object found but no 'action' field present",
        )

    def _try_plain_text(self, text: str, raw_summary: str) -> Optional[ActionParseResult]:
        """Try extracting action from plain text."""
        # Tokenize and look for action words
        words = re.findall(r'\b[A-Za-z_]+\b', text.upper())

        found_actions = []
        found_future = []

        for word in words:
            if word in _VALID_ACTION_NAMES:
                if word not in [a for a in found_actions]:
                    found_actions.append(word)
            elif word in _FUTURE_ACTION_NAMES:
                if word not in [a for a in found_future]:
                    found_future.append(word)

        # Multiple conflicting valid actions
        if len(found_actions) > 1:
            return ActionParseResult(
                success=False,
                raw_input=raw_summary,
                error=f"Multiple conflicting actions found: {found_actions}",
            )

        # Single valid action
        if len(found_actions) == 1:
            action = Action(found_actions[0])
            return ActionParseResult(
                action=action,
                success=True,
                raw_input=raw_summary,
                method="plain_text",
            )

        # Future action detected (but not executable)
        if found_future:
            return ActionParseResult(
                success=False,
                raw_input=raw_summary,
                error=f"Future reserved action detected (not executable): {found_future[0]}",
                is_future_action=True,
            )

        # No action words found at all
        return None

    def _parse_json_action(
        self, json_str: str, raw_summary: str, method: str
    ) -> Optional[ActionParseResult]:
        """Parse a JSON string and extract the action field."""
        try:
            obj = json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            return ActionParseResult(
                success=False,
                raw_input=raw_summary,
                error=f"Malformed JSON: '{json_str[:80]}'",
            )

        if not isinstance(obj, dict):
            return ActionParseResult(
                success=False,
                raw_input=raw_summary,
                error="JSON root is not an object",
            )

        # Look for "action" key (case-insensitive keys)
        action_value = None
        for key, value in obj.items():
            if key.lower() == "action":
                action_value = value
                break

        if action_value is None:
            return None  # No action key — let other parsers try

        if not isinstance(action_value, str):
            return ActionParseResult(
                success=False,
                raw_input=raw_summary,
                error=f"Action field is not a string: {type(action_value).__name__}",
            )

        action_upper = action_value.strip().upper()

        if action_upper in _VALID_ACTION_NAMES:
            return ActionParseResult(
                action=Action(action_upper),
                success=True,
                raw_input=raw_summary,
                method=method,
            )
        elif action_upper in _FUTURE_ACTION_NAMES:
            return ActionParseResult(
                success=False,
                raw_input=raw_summary,
                error=f"Future reserved action in JSON: {action_upper}",
                is_future_action=True,
            )
        else:
            return ActionParseResult(
                success=False,
                raw_input=raw_summary,
                error=f"Invalid action value in JSON: '{action_value}'",
            )

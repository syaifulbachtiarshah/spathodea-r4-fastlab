"""
SPATHODEA R4 FASTLAB — Contract Translator (Phase 2F Part 3A)
Translates FASTLAB internal ProviderRequest v0.2.0 into ATAN BUZZ wire payload.

Source contract: FASTLAB-0.2.0
Target contract: ATAN-BUZZ-0.2.0

Both share contract_version "0.2.0" but their execution/task semantics differ:

    FASTLAB internal:
        execution_mode: sync | async | batch
        task_type: generate | review | score | adversarial | paraphrase
        Game intent: metadata.task_intent = "game_navigation"

    ATAN BUZZ wire:
        execution_mode: single | fallback | consensus
        task_type: game_navigation (or other BUZZ runtime task strings)

These are NOT equivalent dimensions. Translation is explicit, not mechanical.

NOTE: The future live-BUZZ transport layer may translate FASTLAB internal
semantics into the local BUZZ wire vocabulary. This module implements
that translation offline for validation and testing purposes.
The wire translation is NOT sent to a live endpoint yet.
"""

import copy
from dataclasses import dataclass, field
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.provider_request import ProviderRequest, CONTRACT_VERSION


# =============================================================================
# Contract Namespaces
# =============================================================================

SOURCE_CONTRACT = "FASTLAB-0.2.0"
TARGET_CONTRACT = "ATAN-BUZZ-0.2.0"

# Wire contract version (shared semantic version, different vocabulary)
WIRE_CONTRACT_VERSION = "0.2.0"


# =============================================================================
# Wire Enumerations (ATAN BUZZ)
# =============================================================================

WIRE_EXECUTION_MODES = ("single", "fallback", "consensus")

WIRE_TASK_TYPES = ("game_navigation",)  # Extensible for future wire tasks

WIRE_PROVIDERS = ("auto", "mock", "ollama", "openai", "gemini")

WIRE_REVIEWERS = ("none", "auto", "openai", "gemini")


# =============================================================================
# Translator Configuration
# =============================================================================

@dataclass
class TranslatorConfig:
    """Configuration for the contract translator.

    Attributes:
        wire_execution_mode: Target ATAN BUZZ execution mode (single|fallback|consensus)
        wire_provider: Wire provider preference (auto|mock|ollama|openai|gemini)
        wire_reviewer: Wire reviewer preference (none|auto|openai|gemini)
    """
    wire_execution_mode: str = "single"
    wire_provider: Optional[str] = "auto"
    wire_reviewer: Optional[str] = "none"

    def to_dict(self) -> dict:
        return {
            "wire_execution_mode": self.wire_execution_mode,
            "wire_provider": self.wire_provider,
            "wire_reviewer": self.wire_reviewer,
        }


# =============================================================================
# Translation Result
# =============================================================================

@dataclass
class TranslationResult:
    """Result of translating a FASTLAB request into ATAN BUZZ wire payload.

    Attributes:
        success: Whether translation succeeded
        wire_payload: The translated wire payload dict (None on failure)
        errors: List of validation/translation errors
        source_contract: Source contract namespace
        target_contract: Target contract namespace
    """
    success: bool = False
    wire_payload: Optional[dict] = None
    errors: list = field(default_factory=list)
    source_contract: str = SOURCE_CONTRACT
    target_contract: str = TARGET_CONTRACT

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "wire_payload": self.wire_payload,
            "errors": self.errors,
            "source_contract": self.source_contract,
            "target_contract": self.target_contract,
        }


# =============================================================================
# Contract Translator
# =============================================================================

class ContractTranslator:
    """Translates FASTLAB ProviderRequest v0.2.0 into ATAN BUZZ wire payload.

    Translation is explicit and configurable — NOT a mechanical mapping.
    FASTLAB execution_mode is NOT blindly mapped to wire execution_mode.

    Usage:
        translator = ContractTranslator(config=TranslatorConfig(
            wire_execution_mode="single",
            wire_provider="openai",
            wire_reviewer="none",
        ))
        result = translator.translate(fastlab_request)
        if result.success:
            wire_dict = result.wire_payload
    """

    def __init__(self, config: Optional[TranslatorConfig] = None):
        """Initialize the translator.

        Args:
            config: Translator configuration (wire execution mode, provider, reviewer)
        """
        self._config = config or TranslatorConfig()

    @property
    def config(self) -> TranslatorConfig:
        return self._config

    @property
    def source_contract(self) -> str:
        return SOURCE_CONTRACT

    @property
    def target_contract(self) -> str:
        return TARGET_CONTRACT

    # =========================================================================
    # Main Translation
    # =========================================================================

    def translate(self, request: ProviderRequest) -> TranslationResult:
        """Translate a FASTLAB ProviderRequest into an ATAN BUZZ wire payload.

        Validates both the source request and the translator configuration
        before producing the wire payload. Does NOT mutate the original request.

        Args:
            request: FASTLAB ProviderRequest v0.2.0

        Returns:
            TranslationResult with wire_payload on success or errors on failure
        """
        result = TranslationResult()

        # 1. Validate FASTLAB request first (never bypass)
        fastlab_errors = request.validate()
        if fastlab_errors:
            result.errors = [f"FASTLAB validation: {e}" for e in fastlab_errors]
            return result

        # 2. Validate game task intent
        task_intent = request.metadata.get("task_intent")
        if task_intent != "game_navigation":
            result.errors.append(
                f"Missing or invalid game task intent: metadata.task_intent must be "
                f"'game_navigation', got '{task_intent}'"
            )
            return result

        # 3. Validate translator configuration
        config_errors = self._validate_config()
        if config_errors:
            result.errors = config_errors
            return result

        # 4. Validate provider/reviewer combination for execution mode
        combo_errors = self._validate_execution_combination()
        if combo_errors:
            result.errors = combo_errors
            return result

        # 5. Build wire payload
        wire_payload = self._build_wire_payload(request)
        result.success = True
        result.wire_payload = wire_payload
        return result

    # =========================================================================
    # Configuration Validation
    # =========================================================================

    def _validate_config(self) -> list[str]:
        """Validate translator configuration."""
        errors = []

        if self._config.wire_execution_mode not in WIRE_EXECUTION_MODES:
            errors.append(
                f"Invalid wire execution mode: '{self._config.wire_execution_mode}'. "
                f"Must be one of {WIRE_EXECUTION_MODES}"
            )

        if self._config.wire_provider is not None and self._config.wire_provider not in WIRE_PROVIDERS:
            errors.append(
                f"Unsupported wire provider: '{self._config.wire_provider}'. "
                f"Must be one of {WIRE_PROVIDERS}"
            )

        if self._config.wire_reviewer and self._config.wire_reviewer not in WIRE_REVIEWERS:
            errors.append(
                f"Unsupported wire reviewer: '{self._config.wire_reviewer}'. "
                f"Must be one of {WIRE_REVIEWERS}"
            )

        return errors

    def _validate_execution_combination(self) -> list[str]:
        """Validate provider/reviewer combination for execution mode."""
        errors = []
        mode = self._config.wire_execution_mode

        if mode == "consensus":
            # Consensus requires a reviewer
            if not self._config.wire_reviewer or self._config.wire_reviewer == "none":
                errors.append(
                    "Consensus execution mode requires a configured reviewer "
                    "(wire_reviewer must not be 'none')"
                )

        return errors

    # =========================================================================
    # Wire Payload Construction
    # =========================================================================

    def _build_wire_payload(self, request: ProviderRequest) -> dict:
        """Build the ATAN BUZZ wire payload from a validated FASTLAB request.

        Does NOT mutate the original request.
        """
        # Extract safe game metadata
        wire_metadata = self._build_wire_metadata(request.metadata)

        # Build wire payload
        payload = {
            "contract_version": WIRE_CONTRACT_VERSION,
            "prompt": request.prompt,
            "system_prompt": request.system_prompt,
            "model": request.model,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p,
            "stop_sequences": request.stop_sequences,
            "request_id": request.request_id,
            # Wire-translated fields
            "task_type": "game_navigation",
            "execution_mode": self._config.wire_execution_mode,
            "provider_preference": self._config.wire_provider,
            "reviewer_preference": self._config.wire_reviewer,
            # Wire metadata
            "metadata": wire_metadata,
        }

        return payload

    def _build_wire_metadata(self, source_metadata: dict) -> dict:
        """Build wire metadata from FASTLAB metadata.

        Preserves safe game fields. Adds translator context.
        Does NOT include secrets or hidden evaluator data.
        """
        # Safe game metadata fields to preserve
        SAFE_FIELDS = (
            "turn", "agent_position", "strategy",
            "grid_width", "grid_height",
            "known_rewards", "known_hazards", "known_enemies",
            "goal", "source", "task_intent",
        )

        wire_meta = {}

        # Copy safe fields
        for key in SAFE_FIELDS:
            if key in source_metadata:
                wire_meta[key] = source_metadata[key]

        # Add translator context
        wire_meta["source_contract"] = SOURCE_CONTRACT
        wire_meta["target_contract"] = TARGET_CONTRACT

        return wire_meta

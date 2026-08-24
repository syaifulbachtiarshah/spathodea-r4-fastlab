"""
SPATHODEA R4 FASTLAB — Provider Request Model
Standardized request format for all LLM provider interactions via BUZZ gateway.

Contract version: 0.2.0 (Phase 2C — backward-compatible extension)
"""

from dataclasses import dataclass, field
from typing import Optional

# Contract version
CONTRACT_VERSION = "0.2.0"

# Valid enumerations for Phase 2C fields
VALID_EXECUTION_MODES = ("sync", "async", "batch")
VALID_TASK_TYPES = ("generate", "review", "score", "adversarial", "paraphrase")


@dataclass
class ProviderRequest:
    """Immutable request object sent to any LLM provider through the BUZZ gateway.

    This is the canonical outbound contract. All generation requests — regardless
    of backend mode (mock, local_http, local_cli) — are first serialized into
    this structure before dispatch.

    Contract v0.2.0 adds: provider_preference, reviewer_preference,
    execution_mode, task_type (all optional, backward-compatible).

    Attributes:
        prompt: The user-facing input text to send to the model.
        system_prompt: Optional system-level instruction context.
        model: Target model identifier (e.g. "gpt-4o-mini", "llama3.2:3b").
        temperature: Sampling temperature (0.0 = deterministic).
        max_tokens: Maximum tokens to generate in the response.
        top_p: Nucleus sampling probability mass.
        stop_sequences: Optional list of stop strings.
        request_id: Unique identifier for tracing/logging this request.
        metadata: Arbitrary key-value pairs for pipeline context.
        provider_preference: Preferred provider for generation (v0.2.0).
        reviewer_preference: Preferred provider for review/scoring (v0.2.0).
        execution_mode: Execution strategy: sync|async|batch (v0.2.0).
        task_type: Task classification: generate|review|score|adversarial|paraphrase (v0.2.0).
    """

    prompt: str
    system_prompt: Optional[str] = None
    model: str = "mock-model"
    temperature: float = 0.8
    max_tokens: int = 2048
    top_p: float = 0.95
    stop_sequences: Optional[list[str]] = None
    request_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    # --- Phase 2C additions (optional, backward-compatible) ---
    provider_preference: Optional[str] = None
    reviewer_preference: Optional[str] = None
    execution_mode: str = "sync"
    task_type: str = "generate"

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary for transport / logging."""
        d = {
            "prompt": self.prompt,
            "system_prompt": self.system_prompt,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "stop_sequences": self.stop_sequences,
            "request_id": self.request_id,
            "metadata": self.metadata,
            # v0.2.0 fields
            "provider_preference": self.provider_preference,
            "reviewer_preference": self.reviewer_preference,
            "execution_mode": self.execution_mode,
            "task_type": self.task_type,
            "contract_version": CONTRACT_VERSION,
        }
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ProviderRequest":
        """Deserialize from a plain dictionary. Backward-compatible with v0.1.0 payloads."""
        return cls(
            prompt=data["prompt"],
            system_prompt=data.get("system_prompt"),
            model=data.get("model", "mock-model"),
            temperature=data.get("temperature", 0.8),
            max_tokens=data.get("max_tokens", 2048),
            top_p=data.get("top_p", 0.95),
            stop_sequences=data.get("stop_sequences"),
            request_id=data.get("request_id"),
            metadata=data.get("metadata", {}),
            provider_preference=data.get("provider_preference"),
            reviewer_preference=data.get("reviewer_preference"),
            execution_mode=data.get("execution_mode", "sync"),
            task_type=data.get("task_type", "generate"),
        )

    def validate(self) -> list[str]:
        """Return a list of validation errors (empty if valid)."""
        errors: list[str] = []
        if not self.prompt or not self.prompt.strip():
            errors.append("prompt must be a non-empty string")
        if self.temperature < 0.0 or self.temperature > 2.0:
            errors.append(f"temperature must be 0.0–2.0, got {self.temperature}")
        if self.max_tokens < 1:
            errors.append(f"max_tokens must be >= 1, got {self.max_tokens}")
        if self.top_p < 0.0 or self.top_p > 1.0:
            errors.append(f"top_p must be 0.0–1.0, got {self.top_p}")
        # v0.2.0 field validation
        if self.execution_mode not in VALID_EXECUTION_MODES:
            errors.append(
                f"execution_mode must be one of {VALID_EXECUTION_MODES}, got '{self.execution_mode}'"
            )
        if self.task_type not in VALID_TASK_TYPES:
            errors.append(
                f"task_type must be one of {VALID_TASK_TYPES}, got '{self.task_type}'"
            )
        return errors

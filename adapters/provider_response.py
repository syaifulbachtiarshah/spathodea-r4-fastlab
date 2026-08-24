"""
SPATHODEA R4 FASTLAB — Provider Response Model
Standardized response format returned by all LLM provider interactions via BUZZ gateway.

Contract version: 0.2.0 (Phase 2C — backward-compatible extension)
"""

from dataclasses import dataclass, field
from typing import Optional

CONTRACT_VERSION = "0.2.0"


@dataclass
class ProviderResponse:
    """Immutable response object returned from any LLM provider through the BUZZ gateway.

    This is the canonical inbound contract. Regardless of backend mode
    (mock, local_http, local_cli), all responses are normalized into this
    structure before being consumed by the pipeline.

    Attributes:
        content: The generated text content from the model.
        model: Model identifier that produced this response.
        request_id: Matches the corresponding ProviderRequest.request_id.
        finish_reason: Why generation stopped ("stop", "length", "error", "mock").
        usage: Token usage statistics (prompt_tokens, completion_tokens, total_tokens).
        latency_ms: Response latency in milliseconds.
        provider: Backend provider name (e.g. "mock", "openai", "ollama").
        error: Error message if the request failed (None on success).
        metadata: Arbitrary key-value pairs for pipeline context.
    """

    content: str
    model: str = "mock-model"
    request_id: Optional[str] = None
    finish_reason: str = "stop"
    usage: dict = field(default_factory=lambda: {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    })
    latency_ms: float = 0.0
    provider: str = "mock"
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        """True if the response completed without error."""
        return self.error is None and self.finish_reason != "error"

    @property
    def is_error(self) -> bool:
        """True if the response represents a failure."""
        return not self.is_success

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary for transport / logging."""
        return {
            "content": self.content,
            "model": self.model,
            "request_id": self.request_id,
            "finish_reason": self.finish_reason,
            "usage": self.usage,
            "latency_ms": self.latency_ms,
            "provider": self.provider,
            "error": self.error,
            "metadata": self.metadata,
            "contract_version": CONTRACT_VERSION,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProviderResponse":
        """Deserialize from a plain dictionary."""
        return cls(
            content=data.get("content", ""),
            model=data.get("model", "mock-model"),
            request_id=data.get("request_id"),
            finish_reason=data.get("finish_reason", "stop"),
            usage=data.get("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
            latency_ms=data.get("latency_ms", 0.0),
            provider=data.get("provider", "unknown"),
            error=data.get("error"),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def error_response(
        cls,
        error_message: str,
        request_id: Optional[str] = None,
        provider: str = "unknown",
    ) -> "ProviderResponse":
        """Factory for creating an error response."""
        return cls(
            content="",
            model="",
            request_id=request_id,
            finish_reason="error",
            provider=provider,
            error=error_message,
        )

    def validate(self) -> list[str]:
        """Return a list of validation errors (empty if valid response structure)."""
        errors: list[str] = []
        if self.is_success and not self.content:
            errors.append("successful response must have non-empty content")
        if not self.finish_reason:
            errors.append("finish_reason must be set")
        if self.latency_ms < 0:
            errors.append(f"latency_ms cannot be negative, got {self.latency_ms}")
        return errors

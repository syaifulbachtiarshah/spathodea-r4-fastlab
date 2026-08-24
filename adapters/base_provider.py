"""
SPATHODEA R4 FASTLAB — Base Provider Adapter
Abstract base class for all LLM provider adapters.
"""

import os
from abc import ABC, abstractmethod
from typing import Optional


class BaseProvider(ABC):
    """Abstract base class for LLM provider adapters.
    
    All providers must implement:
    - is_configured(): Check if API key / connection is available
    - generate(): Send a prompt and get a completion
    - name: Human-readable provider name
    """

    def __init__(self, config: dict):
        self._config = config
        self._name = config.get("name", "Unknown Provider")
        self._env_key = config.get("env_key")
        self._enabled = config.get("enabled", False)

    @property
    def name(self) -> str:
        return self._name

    @property
    def enabled(self) -> bool:
        return self._enabled

    def is_configured(self) -> bool:
        """Check if the provider has valid credentials configured.
        
        Returns True if:
        - Provider is enabled in config
        - Required environment variable is set and non-empty
        
        SECURITY: Never prints, logs, or returns the actual API key.
        """
        if not self._enabled:
            return False
        if self._env_key is None:
            # Some providers (like local) don't need a key
            return True
        key = os.environ.get(self._env_key, "").strip()
        return len(key) > 0

    def get_status(self) -> str:
        """Return human-readable configuration status."""
        if not self._enabled:
            return "DISABLED"
        if self.is_configured():
            return "CONFIGURED"
        return "NOT CONFIGURED"

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.8,
        max_tokens: int = 2048,
    ) -> str:
        """Generate a completion from the provider.
        
        Args:
            prompt: The user prompt/instruction
            system_prompt: Optional system-level instruction
            temperature: Sampling temperature (0.0 = deterministic)
            max_tokens: Maximum tokens to generate
            
        Returns:
            Generated text string
            
        Raises:
            NotImplementedError: If provider is not configured
            ConnectionError: If API call fails
        """
        pass

    @abstractmethod
    def generate_batch(
        self,
        prompts: list[str],
        system_prompt: Optional[str] = None,
        temperature: float = 0.8,
        max_tokens: int = 2048,
    ) -> list[str]:
        """Generate completions for multiple prompts.
        
        Args:
            prompts: List of user prompts
            system_prompt: Optional shared system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens per generation
            
        Returns:
            List of generated text strings (same order as input)
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self._name} status={self.get_status()}>"

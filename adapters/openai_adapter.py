"""
SPATHODEA R4 FASTLAB — OpenAI Provider Adapter
Wraps OpenAI API for synthetic data generation and evaluation.
"""

import os
from typing import Optional

from .base_provider import BaseProvider


class OpenAIAdapter(BaseProvider):
    """Adapter for OpenAI API (GPT-4o, GPT-4o-mini, etc.)
    
    Requires OPENAI_API_KEY environment variable.
    SECURITY: Never hardcodes, prints, or logs API keys.
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self._base_url = config.get("base_url")
        self._models = config.get("models", {})
        self._rate_limits = config.get("rate_limits", {})
        self._timeout = config.get("timeout", 60)

    @property
    def generator_model(self) -> str:
        return self._models.get("generator", "gpt-4o-mini")

    @property
    def reviewer_model(self) -> str:
        return self._models.get("reviewer", "gpt-4o")

    @property
    def judge_model(self) -> str:
        return self._models.get("judge", "gpt-4o")

    def _get_client(self):
        """Lazily initialize OpenAI client.
        
        Raises ImportError if openai package not installed.
        Raises RuntimeError if API key not configured.
        """
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "openai package not installed. Run: pip install openai"
            )

        key = os.environ.get(self._env_key, "").strip()
        if not key:
            raise RuntimeError(
                f"OpenAI API key not configured. Set {self._env_key} in .env"
            )

        kwargs = {"api_key": key, "timeout": self._timeout}
        if self._base_url:
            kwargs["base_url"] = self._base_url

        return OpenAI(**kwargs)

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.8,
        max_tokens: int = 2048,
        model: Optional[str] = None,
    ) -> str:
        """Generate a single completion via OpenAI API.
        
        This method is NOT called in Phase 1 (no API calls).
        Included for architecture completeness.
        """
        client = self._get_client()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=model or self.generator_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content

    def generate_batch(
        self,
        prompts: list[str],
        system_prompt: Optional[str] = None,
        temperature: float = 0.8,
        max_tokens: int = 2048,
        model: Optional[str] = None,
    ) -> list[str]:
        """Generate completions for multiple prompts sequentially.
        
        Note: For production, implement async batching with rate limiting.
        """
        results = []
        for prompt in prompts:
            result = self.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                model=model,
            )
            results.append(result)
        return results

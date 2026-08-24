"""
SPATHODEA R4 FASTLAB — Google Gemini Provider Adapter
Wraps Google Gemini API for synthetic data generation and evaluation.
"""

import os
from typing import Optional

from .base_provider import BaseProvider


class GeminiAdapter(BaseProvider):
    """Adapter for Google Gemini API (gemini-2.0-flash, etc.)
    
    Requires GEMINI_API_KEY environment variable.
    SECURITY: Never hardcodes, prints, or logs API keys.
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self._models = config.get("models", {})
        self._rate_limits = config.get("rate_limits", {})
        self._timeout = config.get("timeout", 60)

    @property
    def generator_model(self) -> str:
        return self._models.get("generator", "gemini-2.0-flash")

    @property
    def reviewer_model(self) -> str:
        return self._models.get("reviewer", "gemini-2.0-flash")

    @property
    def judge_model(self) -> str:
        return self._models.get("judge", "gemini-2.0-flash")

    def _get_client(self):
        """Lazily initialize Gemini client.
        
        Raises ImportError if google-generativeai package not installed.
        Raises RuntimeError if API key not configured.
        """
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError(
                "google-generativeai package not installed. "
                "Run: pip install google-generativeai"
            )

        key = os.environ.get(self._env_key, "").strip()
        if not key:
            raise RuntimeError(
                f"Gemini API key not configured. Set {self._env_key} in .env"
            )

        genai.configure(api_key=key)
        return genai

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.8,
        max_tokens: int = 2048,
        model: Optional[str] = None,
    ) -> str:
        """Generate a single completion via Gemini API.
        
        This method is NOT called in Phase 1 (no API calls).
        Included for architecture completeness.
        """
        genai = self._get_client()
        model_name = model or self.generator_model

        generation_config = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }

        model_instance = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_prompt,
            generation_config=generation_config,
        )

        response = model_instance.generate_content(prompt)
        return response.text

    def generate_batch(
        self,
        prompts: list[str],
        system_prompt: Optional[str] = None,
        temperature: float = 0.8,
        max_tokens: int = 2048,
        model: Optional[str] = None,
    ) -> list[str]:
        """Generate completions for multiple prompts sequentially."""
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

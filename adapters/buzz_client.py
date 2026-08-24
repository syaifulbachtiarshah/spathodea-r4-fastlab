"""
SPATHODEA R4 FASTLAB — BUZZ Gateway Client
Unified LLM provider gateway supporting mock, local_http, and local_cli modes.

Contract version: 0.2.0 (Phase 2C)
- Endpoint: 127.0.0.1:8765
- POST /v1/generate
- GET /health
- provider_preference / reviewer_preference routing
- execution_mode / task_type classification
- total max attempts = 3
- localhost-only security

SECURITY: No API keys. No external network calls. Mock responses only.
"""

import hashlib
import random
import time
import uuid
from pathlib import Path
from typing import Optional

from .provider_request import ProviderRequest, CONTRACT_VERSION
from .provider_response import ProviderResponse


# =============================================================================
# Mock Response Templates
# =============================================================================

_MOCK_RESPONSES_EN = [
    "To assist you with this, please follow these steps: First, navigate to your account settings. "
    "Then select the relevant option from the menu. Finally, confirm your changes and you should "
    "see the update reflected within a few minutes.",

    "Based on the information provided, here is my recommendation: The most suitable option for "
    "your needs would be the standard package, which includes all essential features at a "
    "competitive price point. Let me know if you need more details.",

    "I understand your concern. Let me explain how this works: The system processes your request "
    "automatically once submitted. You will receive a confirmation notification within 24 hours. "
    "If you do not receive it, please contact our support team for assistance.",

    "Here is a detailed breakdown of the available options:\n"
    "1. Basic Plan — Suitable for light usage with essential features\n"
    "2. Standard Plan — Best value for regular users with moderate needs\n"
    "3. Premium Plan — Full-featured option for power users\n"
    "Each plan can be customized further based on your specific requirements.",

    "Thank you for your question. The process involves several key steps that I will outline "
    "clearly. First, you need to verify your identity. Second, submit the required documentation. "
    "Third, wait for the verification period to complete. The entire process typically takes "
    "3-5 business days.",
]

_MOCK_RESPONSES_MS = [
    "Untuk membantu anda dengan perkara ini, sila ikuti langkah berikut: Pertama, pergi ke "
    "tetapan akaun anda. Kemudian pilih pilihan yang berkaitan dari menu. Akhir sekali, "
    "sahkan perubahan anda dan ia akan dikemas kini dalam beberapa minit.",

    "Berdasarkan maklumat yang diberikan, berikut adalah cadangan saya: Pilihan paling sesuai "
    "untuk keperluan anda ialah pakej standard yang merangkumi semua ciri penting pada harga "
    "yang kompetitif. Beritahu saya jika anda memerlukan maklumat lanjut.",

    "Saya faham kebimbangan anda. Izinkan saya menerangkan cara ini berfungsi: Sistem akan "
    "memproses permintaan anda secara automatik setelah dihantar. Anda akan menerima "
    "pemberitahuan pengesahan dalam masa 24 jam. Jika tidak menerimanya, sila hubungi "
    "pasukan sokongan kami.",

    "Berikut ialah pecahan terperinci pilihan yang tersedia:\n"
    "1. Pelan Asas — Sesuai untuk pengguna ringan dengan ciri-ciri penting\n"
    "2. Pelan Standard — Nilai terbaik untuk pengguna biasa\n"
    "3. Pelan Premium — Pilihan penuh untuk pengguna aktif\n"
    "Setiap pelan boleh disesuaikan mengikut keperluan anda.",

    "Terima kasih atas soalan anda. Proses ini melibatkan beberapa langkah penting yang akan "
    "saya terangkan dengan jelas. Pertama, anda perlu mengesahkan identiti anda. Kedua, "
    "hantar dokumen yang diperlukan. Ketiga, tunggu tempoh pengesahan selesai. Keseluruhan "
    "proses biasanya mengambil masa 3-5 hari bekerja.",
]

_MOCK_RESPONSES_MIXED = [
    "Okay, jadi basically ada beberapa options yang you boleh consider. First option is the "
    "basic plan yang paling affordable. Second option pulak lebih comprehensive dengan extra "
    "features. I suggest you go with option dua sebab ia lebih value for money in the long run.",

    "Boleh je! So here's what you need to do: Step pertama, log in ke account anda. Then pergi "
    "ke settings section. After that, cari option yang you nak tukar. Click confirm dan done! "
    "Senang je sebenarnya, kalau ada masalah lagi just let me know.",

    "Based on your situation, saya rasa the best approach would be to start dengan plan yang "
    "basic dulu. Lepas tu kalau you rasa perlu more features, boleh upgrade anytime. No "
    "commitment punya, so you tak rugi apa-apa untuk try dulu.",
]


# =============================================================================
# BUZZ Client
# =============================================================================

class BuzzClient:
    """Unified BUZZ gateway client for LLM provider interactions.

    Supports three operational modes:
    - mock: Deterministic synthetic responses (default, no network)
    - local_http: HTTP calls to local inference server (Phase 2B)
    - local_cli: Subprocess calls to local CLI binary (Phase 2B)

    Phase 2A implements mock mode only.
    """

    SUPPORTED_MODES = ("mock", "local_http", "local_cli")

    # v0.2.0 defaults
    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 8765
    DEFAULT_GENERATE_PATH = "/v1/generate"
    DEFAULT_HEALTH_PATH = "/health"
    MAX_ATTEMPTS = 3  # total max attempts (1 initial + 2 retries)

    def __init__(self, config: Optional[dict] = None):
        """Initialize BUZZ client from configuration.

        Args:
            config: Parsed buzz.yaml configuration dict (the 'buzz' key contents).
                    If None, defaults to mock mode with standard settings.
        """
        cfg = config or {}
        self._mode = cfg.get("mode", "mock")
        self._mock_cfg = cfg.get("mock", {})
        self._http_cfg = cfg.get("local_http", {})
        self._cli_cfg = cfg.get("local_cli", {})
        self._defaults = cfg.get("generation_defaults", {})
        self._retry_cfg = cfg.get("retry", {})
        self._log_cfg = cfg.get("logging", {})

        # v0.2.0: endpoint configuration
        endpoint_cfg = cfg.get("endpoint", {})
        self._host = endpoint_cfg.get("host", self.DEFAULT_HOST)
        self._port = endpoint_cfg.get("port", self.DEFAULT_PORT)
        self._generate_path = endpoint_cfg.get("generate_path", self.DEFAULT_GENERATE_PATH)
        self._health_path = endpoint_cfg.get("health_path", self.DEFAULT_HEALTH_PATH)

        # v0.2.0: preferences
        self._provider_preference = cfg.get("provider_preference")
        self._reviewer_preference = cfg.get("reviewer_preference")
        self._execution_mode = cfg.get("execution_mode", "sync")

        # v0.2.0: retry with total max attempts
        self._max_attempts = self._retry_cfg.get("max_attempts", self.MAX_ATTEMPTS)

        # Security: enforce localhost-only
        if self._host not in ("127.0.0.1", "localhost", "::1"):
            self._host = "127.0.0.1"  # Force localhost

        # Mock state
        self._mock_seed = self._mock_cfg.get("seed", 42)
        self._mock_rng = random.Random(self._mock_seed)
        self._mock_deterministic = self._mock_cfg.get("deterministic", True)
        self._mock_latency = self._mock_cfg.get("latency_ms", 50)
        self._mock_error_rate = self._mock_cfg.get("error_rate", 0.0)
        self._mock_style = self._mock_cfg.get("response_style", "helpful")
        self._mock_model = self._mock_cfg.get("model_name", "buzz-mock-v1")

        # Request counter
        self._request_count = 0

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def mode(self) -> str:
        """Current operational mode."""
        return self._mode

    @property
    def is_mock(self) -> bool:
        """True if running in mock mode."""
        return self._mode == "mock"

    @property
    def request_count(self) -> int:
        """Total requests processed in this session."""
        return self._request_count

    @property
    def endpoint_url(self) -> str:
        """Full generation endpoint URL (v0.2.0)."""
        return f"http://{self._host}:{self._port}{self._generate_path}"

    @property
    def health_url(self) -> str:
        """Full health check endpoint URL (v0.2.0)."""
        return f"http://{self._host}:{self._port}{self._health_path}"

    @property
    def contract_version(self) -> str:
        """Current contract version."""
        return CONTRACT_VERSION

    @property
    def max_attempts(self) -> int:
        """Total max attempts (initial + retries)."""
        return self._max_attempts

    # =========================================================================
    # Health & Status
    # =========================================================================

    def health_check(self) -> dict:
        """Run a health check on the current mode.

        Returns:
            Dict with status, mode, model, endpoint (v0.2.0), and diagnostics.
        """
        base = {
            "contract_version": CONTRACT_VERSION,
            "endpoint": self.endpoint_url,
            "health_endpoint": self.health_url,
            "max_attempts": self._max_attempts,
            "host": self._host,
            "port": self._port,
            "provider_preference": self._provider_preference,
            "reviewer_preference": self._reviewer_preference,
            "execution_mode": self._execution_mode,
        }

        if self._mode == "mock":
            return {
                **base,
                "status": "healthy",
                "mode": "mock",
                "model": self._mock_model,
                "deterministic": self._mock_deterministic,
                "seed": self._mock_seed,
                "error_rate": self._mock_error_rate,
                "response_templates": {
                    "en": len(_MOCK_RESPONSES_EN),
                    "ms": len(_MOCK_RESPONSES_MS),
                    "mixed": len(_MOCK_RESPONSES_MIXED),
                },
                "requests_processed": self._request_count,
            }
        elif self._mode == "local_http":
            return {
                **base,
                "status": "not_implemented",
                "mode": "local_http",
                "base_url": self._http_cfg.get("base_url", "not configured"),
                "message": "local_http mode is stubbed for Phase 2B",
            }
        elif self._mode == "local_cli":
            return {
                **base,
                "status": "not_implemented",
                "mode": "local_cli",
                "binary": self._cli_cfg.get("binary", "not configured"),
                "message": "local_cli mode is stubbed for Phase 2B",
            }
        else:
            return {
                **base,
                "status": "error",
                "mode": self._mode,
                "message": f"Unknown mode: {self._mode}",
            }

    def get_status(self) -> str:
        """Return a single-word status string for doctor checks."""
        health = self.health_check()
        status = health.get("status", "error")
        if status == "healthy":
            return "PASS"
        elif status == "not_implemented":
            return "STUB"
        else:
            return "FAIL"

    # =========================================================================
    # Core: Send Request
    # =========================================================================

    def send(self, request: ProviderRequest) -> ProviderResponse:
        """Send a request through the BUZZ gateway with retry logic.

        Dispatches to the active mode handler. Retries up to max_attempts (default 3)
        on transient errors. Respects provider_preference and task_type routing.

        Args:
            request: A validated ProviderRequest instance.

        Returns:
            A ProviderResponse instance (always, even on simulated error).
        """
        # Validate request
        errors = request.validate()
        if errors:
            return ProviderResponse.error_response(
                error_message=f"Request validation failed: {'; '.join(errors)}",
                request_id=request.request_id,
                provider=self._mode,
            )

        self._request_count += 1

        # Retry loop (total max attempts = self._max_attempts)
        last_response = None
        for attempt in range(self._max_attempts):
            resp = self._dispatch(request)
            if resp.is_success:
                return resp
            last_response = resp
            # Don't retry validation errors
            if resp.error and "validation failed" in resp.error.lower():
                return resp
            # Backoff before retry (skip on last attempt)
            if attempt < self._max_attempts - 1:
                backoff = min(
                    self._retry_cfg.get("backoff_base_seconds", 1.0) * (2 ** attempt),
                    self._retry_cfg.get("backoff_max_seconds", 30.0),
                )
                time.sleep(min(backoff, 0.001))  # Cap for tests

        return last_response  # Return last error after all attempts exhausted

    def _dispatch(self, request: ProviderRequest) -> ProviderResponse:
        """Route request to the appropriate mode handler."""
        if self._mode == "mock":
            return self._handle_mock(request)
        elif self._mode == "local_http":
            return self._handle_local_http(request)
        elif self._mode == "local_cli":
            return self._handle_local_cli(request)
        else:
            return ProviderResponse.error_response(
                error_message=f"Unsupported mode: {self._mode}",
                request_id=request.request_id,
                provider=self._mode,
            )

    def send_batch(self, requests: list[ProviderRequest]) -> list[ProviderResponse]:
        """Send multiple requests sequentially.

        Args:
            requests: List of ProviderRequest instances.

        Returns:
            List of ProviderResponse instances (same order as input).
        """
        return [self.send(req) for req in requests]

    # =========================================================================
    # Mock Mode Handler
    # =========================================================================

    def _handle_mock(self, request: ProviderRequest) -> ProviderResponse:
        """Generate a deterministic mock response.

        If deterministic=True, the same prompt always produces the same response
        (uses SHA-256 hash of prompt as seed).
        """
        start_time = time.time()

        # Simulate error rate
        if self._mock_error_rate > 0:
            roll = self._mock_rng.random()
            if roll < self._mock_error_rate:
                return ProviderResponse.error_response(
                    error_message="Simulated mock error (error_rate triggered)",
                    request_id=request.request_id,
                    provider="mock",
                )

        # Select language from request metadata or default to English
        language = request.metadata.get("language", "en")

        # Pick response pool
        if language == "ms":
            pool = _MOCK_RESPONSES_MS
        elif language == "mixed":
            pool = _MOCK_RESPONSES_MIXED
        else:
            pool = _MOCK_RESPONSES_EN

        # Deterministic selection based on prompt hash
        if self._mock_deterministic:
            prompt_hash = hashlib.sha256(request.prompt.encode("utf-8")).hexdigest()
            index = int(prompt_hash[:8], 16) % len(pool)
        else:
            index = self._mock_rng.randint(0, len(pool) - 1)

        content = pool[index]

        # Simulate latency
        simulated_latency = self._mock_latency / 1000.0
        time.sleep(min(simulated_latency, 0.01))  # Cap actual sleep for tests

        elapsed_ms = (time.time() - start_time) * 1000.0

        # Estimate token usage
        prompt_tokens = len(request.prompt.split())
        completion_tokens = len(content.split())

        return ProviderResponse(
            content=content,
            model=self._mock_model,
            request_id=request.request_id or f"mock-{uuid.uuid4().hex[:12]}",
            finish_reason="mock",
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            latency_ms=round(elapsed_ms, 2),
            provider="mock",
            error=None,
            metadata={
                "language": language,
                "response_index": index,
                "deterministic": self._mock_deterministic,
            },
        )

    # =========================================================================
    # Stub: local_http (Phase 2B)
    # =========================================================================

    def _handle_local_http(self, request: ProviderRequest) -> ProviderResponse:
        """Stub for local HTTP inference server.

        NOT IMPLEMENTED in Phase 2A. Returns a descriptive error response.
        No network calls are made.
        """
        return ProviderResponse.error_response(
            error_message=(
                "local_http mode is not implemented in Phase 2A. "
                f"Would connect to: {self._http_cfg.get('base_url', 'not configured')}"
            ),
            request_id=request.request_id,
            provider="local_http",
        )

    # =========================================================================
    # Stub: local_cli (Phase 2B)
    # =========================================================================

    def _handle_local_cli(self, request: ProviderRequest) -> ProviderResponse:
        """Stub for local CLI binary invocation.

        NOT IMPLEMENTED in Phase 2A. Returns a descriptive error response.
        No subprocess calls are made.
        """
        return ProviderResponse.error_response(
            error_message=(
                "local_cli mode is not implemented in Phase 2A. "
                f"Would invoke: {self._cli_cfg.get('binary', 'not configured')}"
            ),
            request_id=request.request_id,
            provider="local_cli",
        )

    # =========================================================================
    # Utilities
    # =========================================================================

    def reset(self):
        """Reset internal state (request counter, RNG seed)."""
        self._request_count = 0
        self._mock_rng = random.Random(self._mock_seed)

    def __repr__(self) -> str:
        return (
            f"<BuzzClient v{CONTRACT_VERSION} mode={self._mode} "
            f"endpoint={self.endpoint_url} requests={self._request_count}>"
        )

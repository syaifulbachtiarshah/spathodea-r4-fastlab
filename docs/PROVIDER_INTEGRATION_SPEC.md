# 🔌 Provider Integration Specification

> **SPATHODEA R4 FASTLAB — Phase 2E-A**
> Contract Version: 0.2.0 (unchanged)
> Status: Specification only — no live API calls
> Date: 2026-08-24

---

## 1. Provider Identity Mapping

| Canonical Name | Runtime Description | Auth Source | Locality |
|----------------|---------------------|-------------|----------|
| `openai` | OpenAI API runtime (ChatGPT family) | `OPENAI_API_KEY` env var | Remote HTTPS |
| `gemini` | Personal Gemini API configured through Google AI Studio | `GEMINI_API_KEY` env var | Remote HTTPS |
| `ollama` | Local laptop provider (Ollama daemon) | None | Local `127.0.0.1:11434` |
| `mock` | Built-in testing provider | None | In-process |

### 1.1 Identity Clarifications

- **openai** = the OpenAI API runtime. Any model served through `api.openai.com`.
- **gemini** = the user's personal Gemini API environment. Configured through Google AI Studio, which is the dashboard/portal for obtaining keys and managing quotas. **Google AI Studio is NOT a separate runtime provider** — it is only the admin interface.
- **ollama** = a local laptop provider. The Ollama daemon runs on the user's machine, serves models locally at `http://127.0.0.1:11434`.
- **mock** = the testing provider already implemented in Phase 2A. Returns deterministic canned responses. No network, no keys.

---

## 2. ProviderRequest v0.2.0 — Full Field Map

Every request flowing through the BUZZ gateway uses this canonical structure:

| Field | Type | Required | Default | Constraint |
|-------|------|----------|---------|------------|
| `prompt` | string | **YES** | — | Non-empty after strip |
| `system_prompt` | string \| null | No | `null` | Max 2048 chars |
| `model` | string | No | `"mock-model"` | Provider-specific model ID |
| `temperature` | float | No | `0.8` | `0.0 ≤ x ≤ 2.0` |
| `max_tokens` | int | No | `2048` | `≥ 1` |
| `top_p` | float | No | `0.95` | `0.0 ≤ x ≤ 1.0` |
| `stop_sequences` | list[string] \| null | No | `null` | Optional stop strings |
| `request_id` | string \| null | No | `null` | Unique trace ID (echoed in response) |
| `metadata` | dict | No | `{}` | Arbitrary k/v context |
| `provider_preference` | string \| null | No | `null` | Preferred generation provider |
| `reviewer_preference` | string \| null | No | `null` | Preferred review/scoring provider |
| `execution_mode` | string | No | `"sync"` | `sync` \| `async` \| `batch` |
| `task_type` | string | No | `"generate"` | `generate` \| `review` \| `score` \| `adversarial` \| `paraphrase` |

### 2.1 Per-Provider Request Field Mapping

| BUZZ Field | openai | gemini | ollama | mock |
|-----------|--------|--------|--------|------|
| `prompt` | `messages[user].content` | `contents` (user role) | `prompt` | Directly used |
| `system_prompt` | `messages[system].content` | `system_instruction` | `system` | Ignored (pool selection) |
| `model` | `model` | model name arg | `model` | `"buzz-mock-v1"` |
| `temperature` | `temperature` | `generation_config.temperature` | `options.temperature` | N/A |
| `max_tokens` | `max_tokens` | `generation_config.max_output_tokens` | `options.num_predict` | N/A |
| `top_p` | `top_p` | `generation_config.top_p` | `options.top_p` | N/A |
| `stop_sequences` | `stop` | `generation_config.stop_sequences` | `options.stop` | N/A |

---

## 3. ProviderResponse v0.2.0 — Full Field Map

| Field | Type | Always Present | Success Condition |
|-------|------|----------------|-------------------|
| `content` | string | YES | Non-empty on success; `""` on error |
| `model` | string | YES | Model that produced the response |
| `request_id` | string \| null | YES | Echoes request `request_id` |
| `finish_reason` | string | YES | `"stop"` \| `"length"` \| `"mock"` \| `"error"` |
| `usage` | dict | YES | `{prompt_tokens, completion_tokens, total_tokens}` |
| `latency_ms` | float | YES | `≥ 0` milliseconds |
| `provider` | string | YES | Canonical provider name |
| `error` | string \| null | YES | `null` on success; message on error |
| `metadata` | dict | YES | Arbitrary context |

### 3.1 Success Detection

```
is_success = (error is None) AND (finish_reason != "error")
```

### 3.2 Per-Provider Response Field Mapping

| BUZZ Field | openai source | gemini source | ollama source | mock source |
|-----------|---------------|---------------|---------------|-------------|
| `content` | `choices[0].message.content` | `candidates[0].content.parts[0].text` | `response` | Template pool |
| `model` | `model` | Model name | `model` | `"buzz-mock-v1"` |
| `finish_reason` | `choices[0].finish_reason` | `candidates[0].finish_reason` | `done_reason` | `"mock"` |
| `usage.prompt_tokens` | `usage.prompt_tokens` | `usage_metadata.prompt_token_count` | `prompt_eval_count` | `len(prompt.split())` |
| `usage.completion_tokens` | `usage.completion_tokens` | `usage_metadata.candidates_token_count` | `eval_count` | `len(content.split())` |
| `latency_ms` | Wall-clock measurement | Wall-clock measurement | `total_duration` (ns→ms) | Simulated |
| `provider` | `"openai"` | `"gemini"` | `"ollama"` | `"mock"` |

---

## 4. Token Usage Normalization

All providers report token counts differently. The BUZZ gateway normalizes to:

```json
{
  "prompt_tokens": <int>,
  "completion_tokens": <int>,
  "total_tokens": <int>
}
```

### 4.1 Rules

1. `total_tokens` MUST equal `prompt_tokens + completion_tokens`.
2. If a provider does not return token counts, estimate using `len(text.split())`.
3. When estimation is used, set `metadata.token_estimation = "word_count"`.
4. All three keys MUST always be present (never omit, never null).
5. Values MUST be non-negative integers.

---

## 5. Latency Reporting

| Rule | Specification |
|------|---------------|
| Unit | Floating-point milliseconds |
| Measurement | Wall-clock end-to-end (includes network RTT) |
| Minimum | `≥ 0.0` |
| On retry | Report latency of the **successful** attempt only, not cumulative |
| On error | Report latency up to the point of failure |
| Precision | At least 2 decimal places |

### 5.1 Measurement Method

```python
start = time.time()
# ... provider call ...
latency_ms = (time.time() - start) * 1000.0
```

For `ollama`, prefer `total_duration` field (nanoseconds) when available:
```python
latency_ms = response["total_duration"] / 1_000_000.0
```

---

## 6. Provider Health States

### 6.1 State Definitions

| State | Meaning | BuzzClient.get_status() |
|-------|---------|------------------------|
| `healthy` | Provider responding normally | `"PASS"` |
| `degraded` | Responding but slow or partial failures | `"WARN"` |
| `unavailable` | Not responding or auth failed | `"FAIL"` |
| `not_configured` | API key missing or provider disabled | `"NOT CONFIGURED"` |
| `not_implemented` | Stub mode (Phase 2A stubs) | `"STUB"` |

### 6.2 Health Check Methods

| Provider | Health Probe |
|----------|-------------|
| `openai` | Minimal chat completion: model=`gpt-4o-mini`, max_tokens=1 |
| `gemini` | Minimal generate: model=`gemini-2.0-flash`, max_output_tokens=1 |
| `ollama` | `GET http://127.0.0.1:11434/api/tags` |
| `mock` | Always `healthy` (in-process, no I/O) |

### 6.3 State Transitions

```
NOT_CONFIGURED ──(key added)──► HEALTHY
HEALTHY ──(slow/partial)──► DEGRADED
HEALTHY ──(timeout/refuse)──► UNAVAILABLE
DEGRADED ──(recovered)──► HEALTHY
UNAVAILABLE ──(retry success)──► HEALTHY
```

---

## 7. Retryable vs Non-Retryable Errors

### 7.1 Retry Policy

| Parameter | Value |
|-----------|-------|
| **max_attempts** | **3** (1 initial + 2 retries) |
| Backoff formula | `min(1.0 * 2^attempt, 30.0)` seconds |
| Retry on success | Stop immediately |
| Retry on non-retryable | Stop immediately (return error) |
| Retry on retryable | Continue to next attempt |

### 7.2 Classification Table

| Error Type | Retryable | Applies To |
|-----------|-----------|------------|
| HTTP 429 (rate limit) | ✅ YES | openai, gemini |
| HTTP 500 (internal) | ✅ YES | openai, gemini |
| HTTP 502/503/504 (gateway) | ✅ YES | openai, gemini |
| Connection timeout | ✅ YES | all |
| Connection refused | ✅ YES | ollama |
| DNS resolution failure | ✅ YES | openai, gemini |
| HTTP 401 (unauthorized) | ❌ NO | openai, gemini |
| HTTP 403 (forbidden/quota) | ❌ NO | gemini |
| HTTP 400 (bad request) | ❌ NO | all |
| Invalid model name | ❌ NO | all |
| Safety/content filter block | ❌ NO | gemini, openai |
| Request validation failure | ❌ NO | all (pre-dispatch) |
| Provider not configured | ❌ NO | all |

### 7.3 Error Response Format

All errors are returned as valid `ProviderResponse` objects:

```json
{
  "content": "",
  "model": "",
  "request_id": "<echoed from request>",
  "finish_reason": "error",
  "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
  "latency_ms": <time_until_failure>,
  "provider": "<canonical_name>",
  "error": "<provider>: <human-readable message>",
  "metadata": {}
}
```

Error message format: `"<provider>: <description>"` (e.g. `"openai: rate limit exceeded"`).

---

## 8. Localhost / Security Requirements

| Requirement | Enforcement |
|-------------|-------------|
| API keys in `.env` only | `.env` in `.gitignore`; read via `os.environ.get()` |
| Keys never logged/printed/serialized | Code-level discipline |
| Keys never in request/response payloads | Contract guarantee |
| No OS credential scanning | No keychain/config-dir access |
| Ollama: localhost only (127.0.0.1) | BuzzClient rejects non-loopback hosts |
| BUZZ endpoint: 127.0.0.1:8765 | Enforced in config validation |
| No `0.0.0.0` binding | Never listen on all interfaces |
| OpenAI/Gemini: HTTPS only | SDK default (TLS enforced) |
| Prompt content optionally redacted | `logging.redact_content` config flag |

---

## 9. Consensus & Fallback Patterns

### 9.1 Single Provider

```
Request → provider_primary → Response
```

No reviewer. Used for bulk generation.

### 9.2 Fallback

```
Request → provider_primary (fails all attempts)
        → provider_fallback → Response
```

If `provider_preference` is unavailable, fall back to next available provider.
Fallback order: `openai → gemini → ollama → mock`.

### 9.3 Consensus (Generator + Reviewer)

```
Request → provider_primary → generated_content
        → provider_reviewer → quality_score/review
        → consensus_metadata attached to final response
```

Consensus metadata:
```json
{
  "consensus": {
    "generator_provider": "openai",
    "reviewer_provider": "gemini",
    "generator_model": "gpt-4o-mini",
    "reviewer_model": "gemini-2.0-flash",
    "agreement": true,
    "confidence": 0.85,
    "review_latency_ms": 423.5,
    "total_pipeline_ms": 1247.8
  }
}
```

---

## 10. BUZZ v0.2.0 Compatibility

This spec does NOT modify the BUZZ contract. All additions are:
- Documentation of mapping rules
- Test vectors for offline validation
- Health state definitions

The `ProviderRequest` and `ProviderResponse` dataclass schemas remain identical to Phase 2C.

---

*Document version: 2E-A/1.0*
*Created: 2026-08-24*
*Status: Specification only — awaiting provider credentials for live testing*

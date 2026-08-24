# 🤖 ATAN Phase 2E Handoff

> **SPATHODEA R4 FASTLAB**
> From: FASTLAB Pipeline (Kiro)
> To: ATAN (Local Agent)
> Date: 2026-08-24
> Baseline: Phase 2E-A Part 3B verified
> Contract: BUZZ v0.2.0

---

## 1. Verified Baseline State

| Suite | Result | Notes |
|-------|--------|-------|
| FASTLAB core regression | 85/85 PASS | Phase 2A (48) + Phase 2C (37) |
| LIVE-20 validator | 52/52 PASS | `tests/test_live20_validator.py` |
| Combined automated tests | **137/137 PASS** | All green, zero failures |
| BUZZ Phase 2D handshake | 27/27 PASS | Gateway contract tests |
| BUZZ Phase 2D legacy | 11/11 PASS | Backward compatibility |
| BUZZ Phase 2D migration | 28/28 PASS | v0.1.0 → v0.2.0 migration |
| BUZZ contract version | **0.2.0** | Unchanged — do NOT modify |
| FASTLAB doctor | 8/8 PASS | All components healthy |

---

## 2. Provider Identity Mapping

| Canonical Name | Runtime | Auth | Notes |
|----------------|---------|------|-------|
| `openai` | OpenAI API | `OPENAI_API_KEY` env var | ChatGPT family models |
| `gemini` | Personal Gemini API | `GEMINI_API_KEY` env var | Configured via Google AI Studio |
| `ollama` | Local laptop provider | None | `http://127.0.0.1:11434` |
| `mock` | Testing provider | None | In-process deterministic |

### Identity Rules (non-negotiable)

- **Google AI Studio is NOT a separate runtime provider.** It is only the admin portal for obtaining Gemini API keys and managing quotas. The runtime is `gemini`.
- **ollama** runs on the user's local machine only. Never expose to network.
- **mock** is the Phase 2A testing provider. It remains active for CI/regression.

---

## 3. Provider Integration Order

ATAN MUST integrate providers in this exact sequence:

```
Stage 1: ollama     (local, no API key, fastest feedback loop)
Stage 2: openai     (remote, requires OPENAI_API_KEY)
Stage 3: gemini     (remote, requires GEMINI_API_KEY)
Stage 4: consensus  (openai primary + gemini reviewer)
```

### 3.1 Stage 1 — Ollama

| Item | Value |
|------|-------|
| Endpoint | `POST http://127.0.0.1:11434/api/generate` |
| Health | `GET http://127.0.0.1:11434/api/tags` |
| Model (smoke-test) | `qwen2.5:7b` (preferred first) |
| Model (secondary) | `llama3.2:3b` (comparison) |
| Model selection | **Runtime detection** — query `/api/tags` for locally available models |
| Auth | None |
| Timeout | 120 seconds |
| Retry | Yes (connection refused = retryable) |

**Important:** Do NOT hard-code any model name. ATAN must detect locally available models at runtime via the `/api/tags` endpoint and select from what is pulled. The preferred smoke-test order is `qwen2.5:7b` first, `llama3.2:3b` second, then any available model.

**Exit criteria:** Single request/response works. Health check passes. Model auto-detection works. LIVE-20 dry-run validates requests for ollama provider.

### 3.2 Stage 2 — OpenAI

| Item | Value |
|------|-------|
| API Architecture | **OpenAI Responses API** |
| Auth | `Authorization: Bearer $OPENAI_API_KEY` |
| Model | Configured via `OPENAI_MODEL` env var or config (do NOT hard-code) |
| Current preferred | Configurable (set in `.env` or `config/providers.yaml`) |
| Timeout | 120 seconds |
| Retry | Yes (429, 5xx, timeout) |
| Non-retryable | 401, 400, safety block |

**Important:** Do NOT hard-code `gpt-4o-mini`, `gpt-4o`, or any specific model name. The model MUST be read from `OPENAI_MODEL` environment variable or config. Do NOT assume Chat Completions API is the required integration path — the current preferred API architecture is the **OpenAI Responses API**.

**Exit criteria:** Single generation works. Token usage reported. Latency measured. Model configurable at runtime.

### 3.3 Stage 3 — Gemini

| Item | Value |
|------|-------|
| SDK | `google-genai` Python package |
| Usage | `from google import genai` / `client = genai.Client()` |
| Auth | `GEMINI_API_KEY` env var (configured via Google AI Studio) |
| Model | Configured via `GEMINI_MODEL` env var or config (do NOT hard-code) |
| Current intended | `gemini-3.7-flash` (configurable, not fixed) |
| Timeout | 120 seconds |
| Retry | Yes (RESOURCE_EXHAUSTED, 5xx, timeout) |
| Non-retryable | PERMISSION_DENIED, INVALID_ARGUMENT, safety block |

**Important:** Do NOT use the deprecated `google-generativeai` package. Use `google-genai` with the new client pattern:

```python
from google import genai
client = genai.Client()
response = client.models.generate_content(
    model=GEMINI_MODEL,
    contents=prompt,
)
```

Do NOT hard-code `gemini-2.0-flash` or any specific model. The model MUST be read from `GEMINI_MODEL` environment variable or config. The current intended model is `gemini-3.7-flash` but runtime must remain configurable.

**Exit criteria:** Single generation works. Token usage normalized. Latency measured. Model configurable at runtime.

### 3.4 Stage 4 — Consensus (OpenAI + Gemini)

| Item | Value |
|------|-------|
| Primary | openai (generates content) |
| Reviewer | gemini (scores/reviews content) |
| Pattern | Generate → Review → Attach consensus metadata |
| Consensus metadata | `response.metadata.consensus = {...}` |

**Exit criteria:** Full consensus pipeline works. Both providers invoked. Agreement/disagreement recorded.

---

## 4. Critical Runtime Warning

### ⚠️ Current Phase 2D Runtime Interface

```python
# CURRENT behavior (Phase 2D):
provider.complete(prompt) -> str          # Returns raw string
router._invoke(provider, prompt) -> str   # Consumes raw string
```

**`ProviderResult` exists as a class but is NOT the active runtime interface.**

The router and providers currently return plain strings. `ProviderResult` is defined but unused in the live dispatch path.

### Migration Rule

If `ProviderResult` is later introduced as the active interface:

1. It MUST be a **complete, tested migration** across all providers + the router simultaneously.
2. It MUST NOT be a partial migration (some providers returning `ProviderResult`, others returning `str`).
3. All existing tests MUST be updated atomically in the same commit.
4. The migration commit MUST pass all test suites before merge.

**Do not mix return types in a single runtime state.**

---

## 5. BUZZ Gateway Contract

### 5.1 Endpoint (unchanged)

| Path | Method | Purpose |
|------|--------|---------|
| `/v1/generate` | POST | Send generation request |
| `/health` | GET | Health check |

**Binding:** `127.0.0.1:8765` — localhost only.

### 5.2 Request/Response (unchanged)

All provider interactions go through BUZZ `ProviderRequest` → `ProviderResponse`. The BUZZ client handles:
- Validation (pre-dispatch)
- Retry (max_attempts=3, exponential backoff)
- Localhost enforcement
- Provider routing via `provider_preference`
- Reviewer routing via `reviewer_preference`

### 5.3 Do NOT change:
- Contract version (stays 0.2.0)
- ProviderRequest schema
- ProviderResponse schema
- Retry logic (max_attempts=3)
- Endpoint paths

---

## 6. Security Requirements

| Rule | Enforcement |
|------|-------------|
| BUZZ endpoint: `127.0.0.1:8765` only | Config + code enforcement |
| No public exposure | Never bind `0.0.0.0` |
| No tunnels (ngrok, cloudflare, etc.) | Prohibited |
| No secrets in source code | `.gitignore` excludes `.env`, `credentials/`, `secrets/` |
| No secrets in logs | `logging.redact_content` available |
| No secrets in results | Strip keys from all output |
| API keys from `os.environ.get()` only | Never hardcode |
| Keys never printed/logged/serialized | Code discipline |
| Ollama: localhost only | Reject non-`127.0.0.1` |

---

## 7. Mandatory Test Execution After Each Stage

After completing **each** provider stage (1–4), ATAN MUST run:

```bash
# 1. Legacy tests (Phase 2A)
python tests/test_buzz_contract.py

# 2. FASTLAB-BUZZ handshake (Phase 2C)
python tests/test_phase2c_contract.py

# 3. Migration tests (LIVE-20 validator)
python tests/test_live20_validator.py

# 4. FASTLAB doctor
python fastlab.py doctor

# 5. BUZZ doctor
python fastlab.py buzz-doctor

# 6. LIVE-20 dry-run
python evaluation/run_live20.py --dry-run
```

**All must pass before proceeding to the next stage.**

Expected results per stage:

| Check | Expected |
|-------|----------|
| `test_buzz_contract.py` | 48/48 PASS |
| `test_phase2c_contract.py` | 37/37 PASS |
| `test_live20_validator.py` | 52/52 PASS |
| `fastlab.py doctor` | 8/8 PASS |
| `fastlab.py buzz-doctor` | HEALTHY |
| `run_live20.py --dry-run` | 20/20 valid, 0 network calls |

---

## 8. LIVE-20 Execution (after all stages pass)

Once all 4 provider stages are integrated and verified:

```bash
# Single provider (ollama)
python evaluation/run_live20.py --provider ollama --execution-mode single

# Single provider (openai)
python evaluation/run_live20.py --provider openai --execution-mode single

# Consensus (openai + gemini)
python evaluation/run_live20.py --provider openai --reviewer gemini --execution-mode consensus
```

Results are written to:
- `reports/live20/live20_results.jsonl`
- `reports/live20/live20_summary.json`

Validation is applied via `evaluation/live20_validator.py`.

---

## 9. File Map (what ATAN needs)

| File | Purpose |
|------|---------|
| `docs/PROVIDER_INTEGRATION_SPEC.md` | Full provider API mapping |
| `docs/BUZZ_INTEGRATION_CONTRACT.md` | BUZZ v0.2.0 contract |
| `docs/LIVE_20_RECORD_PROTOCOL.md` | 20-record evaluation protocol |
| `evaluation/live20.jsonl` | The 20 test records |
| `evaluation/run_live20.py` | Runner (dry-run + live) |
| `evaluation/live20_validator.py` | Deterministic response validator |
| `tests/provider_contract_vectors.json` | 35 offline test vectors |
| `tests/test_buzz_contract.py` | Phase 2A contract tests |
| `tests/test_phase2c_contract.py` | Phase 2C contract tests |
| `tests/test_live20_validator.py` | Validator unit tests |
| `adapters/buzz_client.py` | BUZZ gateway client |
| `adapters/provider_request.py` | ProviderRequest v0.2.0 |
| `adapters/provider_response.py` | ProviderResponse v0.2.0 |
| `config/buzz.yaml` | BUZZ configuration |

---

## 10. Prohibited Actions

ATAN MUST NOT:

1. Modify the BUZZ contract version
2. Change ProviderRequest or ProviderResponse schemas
3. Skip test execution between stages
4. Partially migrate to ProviderResult
5. Expose any endpoint publicly
6. Store API keys in source, logs, or results
7. Create tunnels or reverse proxies
8. Push directly to main without passing all tests
9. Generate the full production dataset (that is Phase 3)
10. Connect to AWS SageMaker (that is Phase 4)

---

## 11. Success Criteria

The handoff is considered **complete** when:

- [ ] Ollama provider sends and receives successfully
- [ ] OpenAI provider sends and receives successfully
- [ ] Gemini provider sends and receives successfully
- [ ] Consensus (openai→gemini) pipeline works end-to-end
- [ ] All 137 regression tests pass after each stage
- [ ] LIVE-20 runs with at least one real provider
- [ ] Validation results show ≥16/20 automated PASS
- [ ] No secrets leaked in any file or log
- [ ] Commit pushed with all tests green

---

*Document version: 1.0*
*Created: 2026-08-24*
*Status: Handoff ready — ATAN may begin Stage 1 (ollama)*

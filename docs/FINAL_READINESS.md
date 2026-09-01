# POLYCC AI Agentic Final Readiness

Final date: **14 September 2026**

This gate verifies the reproducible, local-first portion of SPATHODEA without
AWS credentials, provider API keys, or a live BUZZ/Ollama service.

## One-command verification

```bash
python -m pip install -r requirements-dev.txt
python scripts/final_readiness.py
```

Expected baseline:

- FASTLAB doctor: 8/8 checks pass
- Dataset validation: 20/20 records valid
- Offline regression suite: 382 tests pass
- No API key or public endpoint is required

## Final demo sequence

1. Run `python scripts/final_readiness.py` before opening the presentation.
2. Start the local BUZZ/Ollama services using the existing handoff procedure.
3. Demonstrate one successful navigation episode with `llama3.2:3b`.
4. Show a safe fallback or invalid-action rejection.
5. End with the benchmark evidence and state clearly that it is an internal
   readiness score, not an official POLYCC score.

## Demo fallback

If the live provider is unavailable, use the deterministic offline path and
show the checked-in benchmark artifact. Do not improvise credentials, expose a
local service publicly, or claim a live result when replaying stored evidence.

## Pre-stage checklist

- Pull the latest `main` branch and confirm the GitHub quality gate is green.
- Confirm Ollama contains the selected model (`llama3.2:3b`).
- Keep one terminal ready for health/status and one for the demo command.
- Disable unrelated notifications and close windows containing secrets.
- Keep the offline demo path rehearsed and immediately accessible.


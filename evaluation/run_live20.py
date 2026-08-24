#!/usr/bin/env python3
"""
SPATHODEA R4 FASTLAB — LIVE-20 Runner
Executes the 20-record qualification set against a BUZZ gateway endpoint.

Modes:
  --dry-run     Validate records and show request construction (ZERO network calls)
  (live)        Send requests to BUZZ endpoint at --base-url (future)

Provider routing:
  All requests go through BUZZ gateway (POST /v1/generate).
  Never calls provider APIs directly.

Security:
  Never stores or prints credentials.
  Never connects to external services in dry-run mode.

Usage:
  python evaluation/run_live20.py --dry-run
  python evaluation/run_live20.py --dry-run --limit 5
  python evaluation/run_live20.py --dry-run --record-id live20-011
  python evaluation/run_live20.py --base-url http://127.0.0.1:8765 --provider openai --reviewer gemini

Contract: BUZZ v0.2.0
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from adapters.provider_request import ProviderRequest, CONTRACT_VERSION

# =============================================================================
# Constants
# =============================================================================

LIVE20_FILE = Path(__file__).parent / "live20.jsonl"
RESULTS_DIR = PROJECT_ROOT / "reports" / "live20"
RESULTS_FILE = RESULTS_DIR / "live20_results.jsonl"
SUMMARY_FILE = RESULTS_DIR / "live20_summary.json"

VALID_PROVIDERS = ("mock", "openai", "gemini", "ollama", "auto")
VALID_REVIEWERS = ("none", "openai", "gemini", "auto")
VALID_EXECUTION_MODES = ("single", "fallback", "consensus")

BUZZ_HEALTH_PATH = "/health"
BUZZ_GENERATE_PATH = "/v1/generate"

DEFAULT_BASE_URL = "http://127.0.0.1:8765"


# =============================================================================
# Record Loader
# =============================================================================

def load_live20_records(filepath: Path = LIVE20_FILE) -> list[dict]:
    """Load and parse live20.jsonl records."""
    if not filepath.exists():
        print(f"  ❌ File not found: {filepath}")
        sys.exit(1)

    records = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  ❌ Line {line_num}: Invalid JSON — {e}")
                sys.exit(1)
    return records


# =============================================================================
# Request Builder
# =============================================================================

def build_provider_request(
    record: dict,
    provider: str,
    reviewer: str,
    execution_mode: str,
) -> ProviderRequest:
    """Build a BUZZ ProviderRequest from a LIVE-20 record.

    Constructs the request using only pipeline-relevant fields.
    Does NOT include expected_behavior or validation_rules in the prompt.

    Args:
        record: Parsed live20.jsonl record dict
        provider: Resolved primary provider name
        reviewer: Resolved reviewer provider name (or None)
        execution_mode: Execution strategy (single/fallback/consensus)

    Returns:
        ProviderRequest instance ready for BUZZ gateway dispatch
    """
    # Resolve provider from record if "auto"
    resolved_provider = provider
    if provider == "auto":
        resolved_provider = record.get("primary_provider", "mock")

    resolved_reviewer = reviewer
    if reviewer == "auto":
        resolved_reviewer = record.get("reviewer_provider", "none")
    if reviewer == "none" or resolved_reviewer == "none":
        resolved_reviewer = None

    # Map execution_mode string to BUZZ contract values
    buzz_execution_mode = "sync"  # default for single and consensus
    if execution_mode == "single":
        buzz_execution_mode = "sync"
    elif execution_mode == "fallback":
        buzz_execution_mode = "sync"
    elif execution_mode == "consensus":
        buzz_execution_mode = "sync"

    # Build metadata — pipeline context only
    metadata = {
        "record_id": record["record_id"],
        "language": record["language"],
        "difficulty": record["difficulty"],
        "tags": record.get("tags", []),
        "source": "FASTLAB_LIVE20",
    }

    return ProviderRequest(
        prompt=record["prompt"],
        system_prompt=None,  # System prompt handled by BUZZ/provider
        model="auto",  # Let BUZZ resolve model based on provider
        temperature=0.8,
        max_tokens=2048,
        top_p=0.95,
        stop_sequences=None,
        request_id=record["record_id"],
        metadata=metadata,
        provider_preference=resolved_provider,
        reviewer_preference=resolved_reviewer,
        execution_mode=buzz_execution_mode,
        task_type=record.get("task_type", "generate"),
    )


# =============================================================================
# Health Check (live mode only)
# =============================================================================

def check_buzz_health(base_url: str) -> dict:
    """Check BUZZ gateway health via GET /health.

    Expected response:
        {"service": "buzz", "contract_version": "0.2.0", ...}

    Returns:
        Health check result dict
    """
    import urllib.request
    import urllib.error

    url = f"{base_url}{BUZZ_HEALTH_PATH}"
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "status": "healthy",
                "url": url,
                "service": data.get("service"),
                "contract_version": data.get("contract_version"),
                "raw": data,
            }
    except urllib.error.URLError as e:
        return {"status": "unavailable", "url": url, "error": str(e)}
    except Exception as e:
        return {"status": "error", "url": url, "error": str(e)}


# =============================================================================
# Live Sender (future — NOT used in dry-run)
# =============================================================================

def send_to_buzz(base_url: str, request: ProviderRequest) -> dict:
    """Send a ProviderRequest to BUZZ gateway via POST /v1/generate.

    NOT called in --dry-run mode.
    In live mode, sends JSON body and parses JSON response.

    Args:
        base_url: BUZZ gateway base URL
        request: ProviderRequest to send

    Returns:
        Raw response dict from BUZZ
    """
    import urllib.request
    import urllib.error

    url = f"{base_url}{BUZZ_GENERATE_PATH}"
    payload = json.dumps(request.to_dict()).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")

        start = time.time()
        with urllib.request.urlopen(req, timeout=120) as resp:
            latency_ms = (time.time() - start) * 1000.0
            data = json.loads(resp.read().decode("utf-8"))
            data["_measured_latency_ms"] = latency_ms
            return data
    except urllib.error.URLError as e:
        return {
            "content": "",
            "finish_reason": "error",
            "error": f"BUZZ connection failed: {e}",
            "provider": "buzz",
            "request_id": request.request_id,
        }
    except Exception as e:
        return {
            "content": "",
            "finish_reason": "error",
            "error": f"Unexpected error: {e}",
            "provider": "buzz",
            "request_id": request.request_id,
        }


# =============================================================================
# Dry-Run Mode
# =============================================================================

def run_dry(
    records: list[dict],
    provider: str,
    reviewer: str,
    execution_mode: str,
    limit: int = None,
    record_id: str = None,
) -> dict:
    """Dry-run: validate all records, show request construction, ZERO network calls.

    Args:
        records: Loaded live20 records
        provider: Provider selection
        reviewer: Reviewer selection
        execution_mode: Execution mode
        limit: Max records to process (None = all)
        record_id: Specific record to process (None = all)

    Returns:
        Dry-run summary dict
    """
    # Filter records
    if record_id:
        records = [r for r in records if r["record_id"] == record_id]
        if not records:
            print(f"  ❌ Record not found: {record_id}")
            return {"status": "error", "message": f"Record not found: {record_id}"}
    if limit and limit > 0:
        records = records[:limit]

    print()
    print("=" * 70)
    print("  🧪 LIVE-20 Runner — DRY RUN (zero network calls)")
    print("=" * 70)
    print()
    print(f"  Mode:           dry-run")
    print(f"  Provider:       {provider}")
    print(f"  Reviewer:       {reviewer}")
    print(f"  Execution:      {execution_mode}")
    print(f"  Records:        {len(records)}")
    print(f"  Contract:       v{CONTRACT_VERSION}")
    print(f"  Target:         {DEFAULT_BASE_URL}")
    print(f"  Generate path:  POST {BUZZ_GENERATE_PATH}")
    print(f"  Health path:    GET {BUZZ_HEALTH_PATH}")
    print()
    print("-" * 70)

    results = []
    valid_requests = 0
    invalid_requests = 0

    for i, record in enumerate(records, 1):
        rid = record["record_id"]
        req = build_provider_request(record, provider, reviewer, execution_mode)

        # Validate the built request
        errors = req.validate()

        status = "✅ VALID" if not errors else "❌ INVALID"
        if errors:
            invalid_requests += 1
        else:
            valid_requests += 1

        print()
        print(f"  [{i:02d}/{len(records):02d}] {rid}")
        print(f"    Task:        {req.task_type}")
        print(f"    Language:    {record['language']}")
        print(f"    Difficulty:  {record['difficulty']}")
        print(f"    Provider:    {req.provider_preference}")
        print(f"    Reviewer:    {req.reviewer_preference or 'none'}")
        print(f"    Exec mode:   {req.execution_mode}")
        print(f"    Request ID:  {req.request_id}")
        print(f"    Prompt:      {req.prompt[:70]}{'...' if len(req.prompt) > 70 else ''}")
        print(f"    Validation:  {status}")
        if errors:
            for err in errors:
                print(f"      ⚠ {err}")

        results.append({
            "record_id": rid,
            "request_valid": not errors,
            "provider_preference": req.provider_preference,
            "reviewer_preference": req.reviewer_preference,
            "task_type": req.task_type,
            "execution_mode": req.execution_mode,
            "prompt_length": len(req.prompt),
            "metadata": req.metadata,
            "validation_errors": errors,
        })

    print()
    print("-" * 70)
    print()
    print(f"  Summary:")
    print(f"    Total records:     {len(records)}")
    print(f"    Valid requests:    {valid_requests} ✅")
    print(f"    Invalid requests:  {invalid_requests} ❌")
    print(f"    Network calls:     0 (dry-run)")
    print()
    print(f"  ⚠️  DRY RUN — no requests were sent to BUZZ gateway.")
    print()

    # Save dry-run results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    summary = {
        "mode": "dry-run",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "contract_version": CONTRACT_VERSION,
        "base_url": DEFAULT_BASE_URL,
        "provider": provider,
        "reviewer": reviewer,
        "execution_mode": execution_mode,
        "total_records": len(records),
        "valid_requests": valid_requests,
        "invalid_requests": invalid_requests,
        "network_calls": 0,
        "results": results,
    }

    # Write results JSONL
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Write summary JSON
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"  Results:  {RESULTS_FILE}")
    print(f"  Summary:  {SUMMARY_FILE}")
    print()
    print("=" * 70)
    print()

    return summary


# =============================================================================
# Live Mode (future)
# =============================================================================

def run_live(
    records: list[dict],
    base_url: str,
    provider: str,
    reviewer: str,
    execution_mode: str,
    limit: int = None,
    record_id: str = None,
) -> dict:
    """Live mode: send requests to BUZZ gateway.

    NOT AVAILABLE in Phase 2E-A. Requires BUZZ server running at base_url.
    """
    print()
    print("  ❌ Live mode requires a running BUZZ server.")
    print(f"     Expected at: {base_url}")
    print(f"     Health check: GET {base_url}{BUZZ_HEALTH_PATH}")
    print()
    print("  To run in dry-run mode (no network):")
    print("     python evaluation/run_live20.py --dry-run")
    print()
    sys.exit(1)


# =============================================================================
# CLI
# =============================================================================

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="SPATHODEA LIVE-20 Runner — qualification set evaluator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python evaluation/run_live20.py --dry-run
  python evaluation/run_live20.py --dry-run --limit 5
  python evaluation/run_live20.py --dry-run --record-id live20-011
  python evaluation/run_live20.py --dry-run --provider gemini --reviewer openai
  python evaluation/run_live20.py --base-url http://127.0.0.1:8765 --provider openai
        """,
    )

    parser.add_argument(
        "--base-url",
        type=str,
        default=DEFAULT_BASE_URL,
        help=f"BUZZ gateway base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--provider",
        type=str,
        choices=VALID_PROVIDERS,
        default="auto",
        help="Primary provider: mock|openai|gemini|ollama|auto (default: auto)",
    )
    parser.add_argument(
        "--reviewer",
        type=str,
        choices=VALID_REVIEWERS,
        default="none",
        help="Reviewer provider: none|openai|gemini|auto (default: none)",
    )
    parser.add_argument(
        "--execution-mode",
        type=str,
        choices=VALID_EXECUTION_MODES,
        default="single",
        help="Execution mode: single|fallback|consensus (default: single)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max records to process (default: all 20)",
    )
    parser.add_argument(
        "--record-id",
        type=str,
        default=None,
        help="Process only this specific record_id",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Validate and show requests without network calls",
    )

    return parser.parse_args()


# =============================================================================
# Main
# =============================================================================

def main():
    """Main entry point."""
    args = parse_args()

    # Load records
    records = load_live20_records()

    if args.dry_run:
        summary = run_dry(
            records=records,
            provider=args.provider,
            reviewer=args.reviewer,
            execution_mode=args.execution_mode,
            limit=args.limit,
            record_id=args.record_id,
        )
        success = summary.get("invalid_requests", 0) == 0
        sys.exit(0 if success else 1)
    else:
        run_live(
            records=records,
            base_url=args.base_url,
            provider=args.provider,
            reviewer=args.reviewer,
            execution_mode=args.execution_mode,
            limit=args.limit,
            record_id=args.record_id,
        )


if __name__ == "__main__":
    main()

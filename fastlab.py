#!/usr/bin/env python3
"""
SPATHODEA R4 FASTLAB — CLI Entry Point
Competition-ready local-first AI experimentation environment.

Commands:
    doctor    - Check system health and component status
    validate  - Validate records against internal schema
    stats     - Show dataset statistics and distribution analysis
    split     - Split dataset into train/validation/test
    export    - Export to AWS SageMaker format
    benchmark - Run dataset benchmark evaluation
"""

import json
import os
import sys
from pathlib import Path

# Ensure project root is on the path
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# YAML loading — use ruamel.yaml (available) or pyyaml as fallback
try:
    import yaml
except ImportError:
    try:
        from ruamel.yaml import YAML as _RuamelYAML

        class _YamlCompat:
            """Minimal compatibility shim for ruamel.yaml → yaml.safe_load()."""
            @staticmethod
            def safe_load(stream):
                y = _RuamelYAML()
                y.preserve_quotes = True
                return y.load(stream)

        yaml = _YamlCompat()
    except ImportError:
        class _NoYaml:
            @staticmethod
            def safe_load(stream):
                return {}
        yaml = _NoYaml()

from pipeline.validator import Validator
from pipeline.deduplicator import Deduplicator
from pipeline.splitter import Splitter
from pipeline.generator import Generator
from pipeline.scorer import Scorer
from pipeline.balancer import Balancer
from adapters.aws_format_adapter import AWSFormatAdapter
from adapters.openai_adapter import OpenAIAdapter
from adapters.gemini_adapter import GeminiAdapter
from adapters.buzz_client import BuzzClient
from adapters.provider_request import ProviderRequest
from adapters.provider_response import ProviderResponse
from evaluation.benchmark import Benchmark
from evaluation.judge import Judge
from evaluation.error_analysis import ErrorAnalyzer


# ============================================================================
# Configuration Loader
# ============================================================================

def load_config(name: str) -> dict:
    """Load a YAML config file from config/ directory."""
    path = PROJECT_ROOT / "config" / f"{name}.yaml"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_all_configs() -> dict:
    """Load all configuration files."""
    return {
        "dataset": load_config("dataset"),
        "providers": load_config("providers"),
        "models": load_config("models"),
        "evaluation": load_config("evaluation"),
        "buzz": load_config("buzz"),
    }


# ============================================================================
# Utility: Find dataset files
# ============================================================================

def find_dataset_files() -> list[Path]:
    """Find all JSONL files in generated/accepted/ and seeds/."""
    files = []
    for directory in ["generated/accepted", "seeds"]:
        dir_path = PROJECT_ROOT / directory
        if dir_path.exists():
            files.extend(sorted(dir_path.glob("*.jsonl")))
    return files


def load_all_records() -> list[dict]:
    """Load all records from dataset files."""
    records = []
    for filepath in find_dataset_files():
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return records


# ============================================================================
# CLI Commands
# ============================================================================

def cmd_doctor():
    """Run system health check."""
    configs = load_all_configs()
    provider_cfg = configs["providers"].get("providers", {})

    print()
    print("=" * 60)
    print("  🌺 SPATHODEA R4 FASTLAB")
    print("=" * 60)
    print()

    checks = []

    # --- Core Pipeline ---
    try:
        v = Validator()
        d = Deduplicator()
        s = Splitter()
        g = Generator()
        sc = Scorer()
        b = Balancer()
        checks.append(("Core Pipeline", "PASS"))
    except Exception as e:
        checks.append(("Core Pipeline", f"FAIL ({e})"))

    # --- Schema Validator ---
    try:
        v = Validator()
        test_record = {
            "id": "r4-00000000-0000-4000-8000-000000000000",
            "input": "Test input query",
            "output": "Test output response that is long enough",
            "system_prompt": None,
            "metadata": {
                "intent": "test",
                "difficulty": "easy",
                "language": "en",
                "generator": "doctor_check",
            },
        }
        result = v.validate_record(test_record)
        if result.is_valid:
            checks.append(("Schema Validator", "PASS"))
        else:
            checks.append(("Schema Validator", f"FAIL ({len(result.errors)} errors)"))
    except Exception as e:
        checks.append(("Schema Validator", f"FAIL ({e})"))

    # --- Deduplicator ---
    try:
        d = Deduplicator()
        d.reset()
        is_dup, _ = d.is_duplicate({"id": "test-1", "input": "hello", "output": "world"})
        is_dup2, _ = d.is_duplicate({"id": "test-2", "input": "hello", "output": "world"})
        if not is_dup and is_dup2:
            checks.append(("Deduplicator", "PASS"))
        else:
            checks.append(("Deduplicator", "FAIL (logic error)"))
    except Exception as e:
        checks.append(("Deduplicator", f"FAIL ({e})"))

    # --- Dataset Splitter ---
    try:
        s = Splitter({"train_ratio": 0.8, "validation_ratio": 0.1, "test_ratio": 0.1, "seed": 42})
        test_records = [
            {"id": f"r4-test-{i}", "metadata": {"language": "en", "difficulty": "easy"}}
            for i in range(10)
        ]
        result = s.split_records(test_records)
        if result["stats"]["total"] == 10:
            checks.append(("Dataset Splitter", "PASS"))
        else:
            checks.append(("Dataset Splitter", "FAIL (count mismatch)"))
    except Exception as e:
        checks.append(("Dataset Splitter", f"FAIL ({e})"))

    # --- Evaluation Engine ---
    try:
        bm = Benchmark()
        j = Judge()
        ea = ErrorAnalyzer()
        checks.append(("Evaluation Engine", "PASS"))
    except Exception as e:
        checks.append(("Evaluation Engine", f"FAIL ({e})"))

    # --- OpenAI Adapter ---
    try:
        openai_cfg = provider_cfg.get("openai", {})
        adapter = OpenAIAdapter(openai_cfg)
        status = adapter.get_status()
        checks.append(("OpenAI Adapter", status))
    except Exception as e:
        checks.append(("OpenAI Adapter", f"FAIL ({e})"))

    # --- Gemini Adapter ---
    try:
        gemini_cfg = provider_cfg.get("gemini", {})
        adapter = GeminiAdapter(gemini_cfg)
        status = adapter.get_status()
        checks.append(("Gemini Adapter", status))
    except Exception as e:
        checks.append(("Gemini Adapter", f"FAIL ({e})"))

    # --- AWS Exporter ---
    try:
        aws = AWSFormatAdapter()
        test_rec = {"input": "test", "output": "response", "system_prompt": None}
        pc = aws.to_prompt_completion(test_rec)
        msgs = aws.to_messages(test_rec)
        if "prompt" in pc and "messages" in msgs:
            checks.append(("AWS Exporter", "PASS"))
        else:
            checks.append(("AWS Exporter", "FAIL (format error)"))
    except Exception as e:
        checks.append(("AWS Exporter", f"FAIL ({e})"))

    # --- Print Results ---
    max_name_len = max(len(name) for name, _ in checks)
    for name, status in checks:
        dots = "." * (max_name_len - len(name) + 8)
        print(f"  {name} {dots} {status}")

    print()

    # --- Summary ---
    passes = sum(1 for _, s in checks if s in ("PASS", "CONFIGURED", "DISABLED", "NOT CONFIGURED"))
    total = len(checks)
    failures = sum(1 for _, s in checks if s.startswith("FAIL"))
    print(f"  Results: {passes}/{total} checks passed ({failures} failures)")
    print()

    # --- Dataset Info ---
    files = find_dataset_files()
    records = load_all_records()
    print(f"  Dataset files found: {len(files)}")
    print(f"  Total records loaded: {len(records)}")
    print()
    print("=" * 60)
    print()

    return failures == 0


def cmd_validate(filepath: str = None):
    """Validate records against internal schema."""
    configs = load_all_configs()
    dataset_cfg = configs["dataset"].get("dataset", {}).get("validation", {})
    validator = Validator(dataset_cfg)

    print()
    print("🔍 Validating records...")
    print()

    if filepath:
        # Validate specific file
        result = validator.validate_file(filepath)
    else:
        # Validate all dataset files
        files = find_dataset_files()
        if not files:
            print("  No dataset files found in generated/accepted/ or seeds/")
            print("  Create records first.")
            return
        
        total = 0
        valid = 0
        invalid = 0
        all_errors = []

        for f in files:
            r = validator.validate_file(str(f))
            total += r["total"]
            valid += r["valid"]
            invalid += r["invalid"]
            all_errors.extend(r["errors"])
            print(f"  {f.name}: {r['valid']}/{r['total']} valid")

        result = {"total": total, "valid": valid, "invalid": invalid, "errors": all_errors}

    print()
    print(f"  Total:   {result['total']}")
    print(f"  Valid:   {result['valid']} ✅")
    print(f"  Invalid: {result['invalid']} ❌")

    if result["errors"]:
        print()
        print("  Errors (first 10):")
        for err in result["errors"][:10]:
            if "errors" in err:
                for e in err["errors"]:
                    print(f"    Line {err.get('line', '?')}: [{e['field']}] {e['message']}")
            else:
                print(f"    Line {err.get('line', '?')}: {err.get('error', 'unknown')}")
    print()


def cmd_stats():
    """Show dataset statistics."""
    records = load_all_records()

    print()
    print("📊 Dataset Statistics")
    print()

    if not records:
        print("  No records found. Generate or add data first.")
        print()
        return

    # Run benchmark for stats
    bm = Benchmark()
    report = bm.run_dataset_benchmark(records)

    print(f"  Total Records: {report['total_records']}")
    print()

    # Coverage
    cov = report["coverage"]
    print("  Languages:")
    for lang, count in sorted(cov["languages"].items()):
        pct = count / report["total_records"] * 100
        print(f"    {lang}: {count} ({pct:.1f}%)")
    print()

    print("  Difficulties:")
    for diff, count in sorted(cov["difficulties"].items()):
        pct = count / report["total_records"] * 100
        print(f"    {diff}: {count} ({pct:.1f}%)")
    print()

    print(f"  Unique Intents: {cov['unique_intents']}")
    print(f"  With System Prompt: {cov['has_system_prompt']}")
    print(f"  With Quality Score: {cov['has_quality_score']}")
    print()

    # Lengths
    lens = report["lengths"]
    if lens.get("input"):
        print(f"  Input Length:  min={lens['input']['min']}, "
              f"mean={lens['input']['mean']:.0f}, max={lens['input']['max']}")
    if lens.get("output"):
        print(f"  Output Length: min={lens['output']['min']}, "
              f"mean={lens['output']['mean']:.0f}, max={lens['output']['max']}")
    print()

    # Balance analysis
    balancer = Balancer()
    recommendations = balancer.get_recommendations(records)
    print("  Balance Analysis:")
    for rec in recommendations:
        print(f"    • {rec}")
    print()


def cmd_split():
    """Split dataset into train/validation/test."""
    configs = load_all_configs()
    split_cfg = configs["dataset"].get("dataset", {}).get("splitting", {})
    splitter = Splitter(split_cfg)

    records = load_all_records()

    print()
    print("✂️  Splitting dataset...")
    print()

    if not records:
        print("  No records found. Generate or add data first.")
        print()
        return

    output_dir = str(PROJECT_ROOT / "datasets")
    result = splitter.split_and_save(records, output_dir)
    stats = result["stats"]

    print(f"  Total Records: {stats['total']}")
    print(f"  Train:         {stats['train']} ({stats['train']/max(stats['total'],1)*100:.1f}%)")
    print(f"  Validation:    {stats['validation']} ({stats['validation']/max(stats['total'],1)*100:.1f}%)")
    print(f"  Test:          {stats['test']} ({stats['test']/max(stats['total'],1)*100:.1f}%)")
    print(f"  Strata:        {stats['strata_count']}")
    print()
    print("  Output files:")
    for split_name, path in result["paths"].items():
        print(f"    {split_name}: {path}")
    print()


def cmd_export(fmt: str):
    """Export dataset to AWS SageMaker format."""
    adapter = AWSFormatAdapter()

    if fmt not in adapter.SUPPORTED_FORMATS:
        print(f"\n  ❌ Unsupported format: '{fmt}'")
        print(f"  Supported: {adapter.SUPPORTED_FORMATS}\n")
        return

    records = load_all_records()

    print()
    print(f"📦 Exporting to AWS format: {fmt}")
    print()

    if not records:
        print("  No records found. Generate or add data first.")
        print()
        return

    # Export from each split if available, otherwise from all records
    splits_dir = PROJECT_ROOT / "datasets"
    exported_any = False

    for split_name in ("train", "validation", "test"):
        split_file = splits_dir / split_name / "data.jsonl"
        if split_file.exists():
            # Load split records
            split_records = []
            with open(split_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            split_records.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass

            if split_records:
                output_name = f"{split_name}_{fmt.replace('-', '_')}.jsonl"
                output_path = str(splits_dir / split_name / output_name)
                result = adapter.export_jsonl(split_records, output_path, fmt)
                print(f"  {split_name}: {result['exported']} records → {output_path}")
                exported_any = True

    if not exported_any:
        # Export all records as a single file
        output_path = str(PROJECT_ROOT / "generated" / "accepted" / f"export_{fmt.replace('-', '_')}.jsonl")
        result = adapter.export_jsonl(records, output_path, fmt)
        print(f"  Exported {result['exported']} records → {output_path}")
        if result["errors"] > 0:
            print(f"  ⚠️  {result['errors']} records had export errors")

    print()


def cmd_benchmark():
    """Run dataset benchmark."""
    configs = load_all_configs()
    eval_cfg = configs["evaluation"].get("evaluation", {}).get("benchmark", {})

    bm = Benchmark(eval_cfg)

    print()
    print("🏆 Running Benchmark")
    print()

    # Try test split first, fall back to all records
    test_dir = PROJECT_ROOT / "datasets" / "test"
    if test_dir.exists() and any(test_dir.glob("*.jsonl")):
        report = bm.run_benchmark(str(test_dir))
        source = "datasets/test/"
    else:
        records = load_all_records()
        if not records:
            print("  No records found. Generate data and run 'split' first.")
            print()
            return
        report = bm.run_dataset_benchmark(records)
        source = "all records"

    print(f"  Source: {source}")
    print(f"  Records: {report.get('total_records', 0)}")
    print()

    if report.get("coverage"):
        cov = report["coverage"]
        print(f"  Languages: {cov['languages']}")
        print(f"  Difficulties: {cov['difficulties']}")
        print(f"  Unique Intents: {cov['unique_intents']}")
        print()

    if report.get("quality") and report["quality"]:
        q = report["quality"]
        print(f"  Quality Scores:")
        print(f"    Scored: {q['count']}/{report['total_records']}")
        print(f"    Mean:   {q['mean']:.4f}")
        print(f"    Min:    {q['min']:.4f}")
        print(f"    Max:    {q['max']:.4f}")
        print(f"    Above 0.70: {q['above_threshold']}")
    else:
        print("  Quality Scores: Not yet computed (run scorer first)")
    print()

    # Save report
    report_path = bm.save_report(report)
    print(f"  Report saved: {report_path}")
    print()


# ============================================================================
# BUZZ Gateway Commands (Phase 2A)
# ============================================================================

def _get_buzz_client() -> BuzzClient:
    """Load BUZZ config and instantiate client."""
    configs = load_all_configs()
    buzz_cfg = configs["buzz"].get("buzz", {})
    return BuzzClient(config=buzz_cfg)


def cmd_buzz_doctor():
    """Run BUZZ gateway health check."""
    client = _get_buzz_client()
    health = client.health_check()

    print()
    print("=" * 60)
    print("  🐝 BUZZ Gateway — Health Check")
    print("=" * 60)
    print()
    print(f"  Mode .............. {health.get('mode', 'unknown')}")
    print(f"  Status ............ {health.get('status', 'unknown').upper()}")
    print(f"  Model ............. {health.get('model', 'n/a')}")

    if health.get("mode") == "mock":
        print(f"  Deterministic ..... {health.get('deterministic', False)}")
        print(f"  Seed .............. {health.get('seed', 'n/a')}")
        print(f"  Error Rate ........ {health.get('error_rate', 0.0)}")
        templates = health.get("response_templates", {})
        print(f"  Templates (EN) .... {templates.get('en', 0)}")
        print(f"  Templates (MS) .... {templates.get('ms', 0)}")
        print(f"  Templates (Mixed) . {templates.get('mixed', 0)}")
        print(f"  Requests Done ..... {health.get('requests_processed', 0)}")
    elif health.get("mode") == "local_http":
        print(f"  Base URL .......... {health.get('base_url', 'n/a')}")
        print(f"  Message ........... {health.get('message', '')}")
    elif health.get("mode") == "local_cli":
        print(f"  Binary ............ {health.get('binary', 'n/a')}")
        print(f"  Message ........... {health.get('message', '')}")

    # Quick send test
    print()
    print("  Quick send test:")
    req = ProviderRequest(
        prompt="BUZZ doctor test ping",
        request_id="buzz-doctor-ping",
        metadata={"language": "en"},
    )
    resp = client.send(req)
    if resp.is_success:
        print(f"    Status .......... PASS ✅")
        print(f"    Finish Reason ... {resp.finish_reason}")
        print(f"    Content (first 80) {resp.content[:80]}...")
        print(f"    Latency ......... {resp.latency_ms:.2f} ms")
    else:
        print(f"    Status .......... FAIL ❌")
        print(f"    Error ........... {resp.error}")

    print()
    print("=" * 60)
    print()

    return health.get("status") == "healthy"


def cmd_buzz_test():
    """Run BUZZ contract test suite."""
    print()
    print("🧪 BUZZ Contract Tests")
    print()

    # Import and run tests
    from tests.test_buzz_contract import run_tests_with_report

    results = run_tests_with_report()

    print(f"  Total:   {results['total']}")
    print(f"  Passed:  {results['passed']} ✅")
    print(f"  Failed:  {results['failed']} ❌")
    print(f"  Errors:  {results['errors']} 💥")
    print()

    if results["failure_details"]:
        print("  Failures:")
        for f in results["failure_details"][:10]:
            test_name = f["test"].split()[-1] if f["test"] else "unknown"
            # Extract just the assertion line
            msg_lines = f["message"].strip().split("\n")
            short_msg = msg_lines[-1] if msg_lines else ""
            print(f"    ✗ {test_name}")
            print(f"      {short_msg[:100]}")
        print()

    if results["error_details"]:
        print("  Errors:")
        for e in results["error_details"][:10]:
            test_name = e["test"].split()[-1] if e["test"] else "unknown"
            msg_lines = e["message"].strip().split("\n")
            short_msg = msg_lines[-1] if msg_lines else ""
            print(f"    ✗ {test_name}")
            print(f"      {short_msg[:100]}")
        print()

    verdict = "ALL PASSED ✅" if results["success"] else "FAILURES DETECTED ❌"
    print(f"  Verdict: {verdict}")
    print()

    return results["success"]


def cmd_generate_dry_run(count: int):
    """Generate records using BUZZ mock gateway (dry-run, no persistence).

    Creates `count` mock records using the BUZZ gateway, validates each one,
    and reports statistics — but does NOT save them to disk.
    """
    import uuid
    from datetime import datetime, timezone

    client = _get_buzz_client()
    validator = Validator()

    print()
    print(f"🧬 Dry-Run Generation ({count} records via BUZZ {client.mode} mode)")
    print()

    languages = ["en", "ms", "mixed"]
    difficulties = ["easy", "medium", "hard", "adversarial", "noisy"]
    intents = [
        "account_management", "product_inquiry", "billing",
        "technical_support", "complaints", "general_knowledge",
    ]
    prompts = [
        "How do I reset my password?",
        "What data plans do you offer?",
        "Macam mana nak bayar bil?",
        "Explain the difference between 4G and 5G",
        "I want to file a complaint about my service",
        "Boleh recommend plan untuk student?",
        "Help me set up parental controls",
        "Kenapa internet saya lambat?",
        "Tell me about roaming packages",
        "I need to cancel my subscription",
        "Apa beza prepaid dan postpaid?",
        "How to activate eSIM?",
        "Saya nak upgrade plan saya",
        "What is your coverage in Sabah?",
        "Tolong check baki data saya",
        "I forgot my account PIN",
        "Boleh transfer credit tak?",
        "How much is international call to Singapore?",
        "Nak tukar nombor telefon",
        "My phone was stolen, help!",
    ]

    # Use a seeded RNG for reproducible dry-run
    rng = __import__("random").Random(42)

    generated = []
    valid_count = 0
    invalid_count = 0
    buzz_errors = 0

    for i in range(count):
        prompt = prompts[i % len(prompts)]
        language = languages[i % len(languages)]
        difficulty = difficulties[i % len(difficulties)]
        intent = intents[i % len(intents)]

        # Send to BUZZ gateway
        req = ProviderRequest(
            prompt=prompt,
            system_prompt="You are a helpful bilingual customer service assistant.",
            model=client._mock_model if client.is_mock else "unknown",
            request_id=f"dryrun-{i:04d}",
            metadata={"language": language},
        )
        resp = client.send(req)

        if resp.is_error:
            buzz_errors += 1
            continue

        # Assemble internal record
        record = {
            "id": f"r4-{uuid.uuid4()}",
            "input": prompt,
            "output": resp.content,
            "system_prompt": req.system_prompt,
            "metadata": {
                "intent": intent,
                "difficulty": difficulty,
                "language": language,
                "persona": "general_user",
                "noise_type": None,
                "generator": f"buzz-{client.mode}",
                "generation_batch": "dryrun-001",
                "seed_id": None,
                "quality_score": None,
                "quality_dimensions": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "tags": ["dry_run"],
            },
        }

        # Validate
        result = validator.validate_record(record)
        if result.is_valid:
            valid_count += 1
        else:
            invalid_count += 1

        generated.append(record)

    # Report
    print(f"  BUZZ requests sent: {count}")
    print(f"  BUZZ errors:        {buzz_errors}")
    print(f"  Records assembled:  {len(generated)}")
    print(f"  Valid:              {valid_count} ✅")
    print(f"  Invalid:            {invalid_count} ❌")
    print()

    # Show sample
    if generated:
        sample = generated[0]
        print("  Sample record (first):")
        print(f"    ID:         {sample['id']}")
        print(f"    Input:      {sample['input'][:60]}...")
        print(f"    Output:     {sample['output'][:60]}...")
        print(f"    Language:   {sample['metadata']['language']}")
        print(f"    Difficulty: {sample['metadata']['difficulty']}")
        print(f"    Generator:  {sample['metadata']['generator']}")
    print()

    print(f"  ⚠️  DRY RUN — no records were saved to disk.")
    print()

    return buzz_errors == 0 and invalid_count == 0


# ============================================================================
# Main Entry Point
# ============================================================================

def print_usage():
    """Print usage information."""
    print()
    print("🌺 SPATHODEA R4 FASTLAB")
    print()
    print("Usage: python fastlab.py <command> [options]")
    print()
    print("Commands:")
    print("  doctor                        Check system health")
    print("  validate [file]               Validate records against schema")
    print("  stats                         Show dataset statistics")
    print("  split                         Split into train/validation/test")
    print("  export --format <fmt>         Export to AWS format")
    print("  benchmark                     Run dataset benchmark")
    print()
    print("BUZZ Gateway (Phase 2A):")
    print("  buzz-doctor                   BUZZ gateway health check")
    print("  buzz-test                     Run BUZZ contract tests")
    print("  generate --dry-run --count N  Mock-generate N records (no save)")
    print()
    print("Export formats:")
    print("  prompt-completion             AWS Standard format")
    print("  messages                      AWS Conversational format")
    print()


def main():
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(0)

    command = sys.argv[1].lower()

    if command == "doctor":
        success = cmd_doctor()
        sys.exit(0 if success else 1)

    elif command == "validate":
        filepath = sys.argv[2] if len(sys.argv) > 2 else None
        cmd_validate(filepath)

    elif command == "stats":
        cmd_stats()

    elif command == "split":
        cmd_split()

    elif command == "export":
        fmt = None
        for i, arg in enumerate(sys.argv):
            if arg == "--format" and i + 1 < len(sys.argv):
                fmt = sys.argv[i + 1]
        if not fmt:
            print("\n  ❌ Missing --format argument")
            print("  Usage: python fastlab.py export --format <prompt-completion|messages>\n")
            sys.exit(1)
        cmd_export(fmt)

    elif command == "benchmark":
        cmd_benchmark()

    elif command == "buzz-doctor":
        success = cmd_buzz_doctor()
        sys.exit(0 if success else 1)

    elif command == "buzz-test":
        success = cmd_buzz_test()
        sys.exit(0 if success else 1)

    elif command == "generate":
        # Parse --dry-run and --count N
        dry_run = "--dry-run" in sys.argv
        count = 20  # default
        for i, arg in enumerate(sys.argv):
            if arg == "--count" and i + 1 < len(sys.argv):
                try:
                    count = int(sys.argv[i + 1])
                except ValueError:
                    print(f"\n  ❌ Invalid count: '{sys.argv[i + 1]}'\n")
                    sys.exit(1)
        if not dry_run:
            print("\n  ❌ Only --dry-run mode is supported in Phase 2A.")
            print("  Usage: python fastlab.py generate --dry-run --count N\n")
            sys.exit(1)
        success = cmd_generate_dry_run(count)
        sys.exit(0 if success else 1)

    elif command in ("--help", "-h", "help"):
        print_usage()

    else:
        print(f"\n  ❌ Unknown command: '{command}'")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()

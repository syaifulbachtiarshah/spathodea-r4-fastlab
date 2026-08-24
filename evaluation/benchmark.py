"""
SPATHODEA R4 FASTLAB — Benchmark Engine
Evaluates dataset quality and model performance using deterministic metrics.

Phase 1: Dataset-level statistics and quality metrics.
Phase 2: Model inference + scoring against test set.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Optional


class Benchmark:
    """Dataset benchmarking and quality evaluation.
    
    Phase 1 metrics (no model required):
    - Dataset completeness
    - Schema compliance rate
    - Distribution coverage
    - Quality score distribution
    - Duplicate rate
    
    Phase 2 metrics (requires model endpoint):
    - Exact match accuracy
    - BLEU / ROUGE-L scores
    - Semantic similarity
    """

    def __init__(self, config: Optional[dict] = None):
        self._config = config or {}
        self._report_dir = self._config.get("output_dir", "reports")

    def run_dataset_benchmark(self, records: list[dict]) -> dict:
        """Run Phase 1 dataset-level benchmark (no model required).
        
        Args:
            records: List of internal master records
            
        Returns:
            Comprehensive benchmark report dict
        """
        if not records:
            return {"status": "empty", "total_records": 0}

        n = len(records)

        # --- Coverage Metrics ---
        lang_counts = Counter()
        diff_counts = Counter()
        intent_counts = Counter()
        has_system_prompt = 0
        has_quality_score = 0
        input_lengths = []
        output_lengths = []

        for record in records:
            meta = record.get("metadata", {})
            lang_counts[meta.get("language", "unknown")] += 1
            diff_counts[meta.get("difficulty", "unknown")] += 1
            intent_counts[meta.get("intent", "unknown")] += 1

            if record.get("system_prompt"):
                has_system_prompt += 1
            if meta.get("quality_score") is not None:
                has_quality_score += 1

            input_lengths.append(len(record.get("input", "")))
            output_lengths.append(len(record.get("output", "")))

        # --- Quality Score Stats ---
        quality_scores = [
            r.get("metadata", {}).get("quality_score")
            for r in records
            if r.get("metadata", {}).get("quality_score") is not None
        ]

        quality_stats = {}
        if quality_scores:
            quality_stats = {
                "count": len(quality_scores),
                "mean": sum(quality_scores) / len(quality_scores),
                "min": min(quality_scores),
                "max": max(quality_scores),
                "above_threshold": sum(1 for s in quality_scores if s >= 0.70),
            }

        # --- Length Stats ---
        def _length_stats(lengths):
            if not lengths:
                return {}
            return {
                "mean": sum(lengths) / len(lengths),
                "min": min(lengths),
                "max": max(lengths),
                "median": sorted(lengths)[len(lengths) // 2],
            }

        return {
            "status": "complete",
            "total_records": n,
            "coverage": {
                "languages": dict(lang_counts),
                "difficulties": dict(diff_counts),
                "intents": dict(intent_counts),
                "unique_intents": len(intent_counts),
                "has_system_prompt": has_system_prompt,
                "has_quality_score": has_quality_score,
            },
            "lengths": {
                "input": _length_stats(input_lengths),
                "output": _length_stats(output_lengths),
            },
            "quality": quality_stats,
            "distributions": {
                "language_pct": {k: v / n for k, v in lang_counts.items()},
                "difficulty_pct": {k: v / n for k, v in diff_counts.items()},
            },
        }

    def run_benchmark(self, dataset_dir: str = "datasets/test") -> dict:
        """Run benchmark on the test dataset.
        
        Args:
            dataset_dir: Path to test dataset directory
            
        Returns:
            Benchmark report dict
        """
        path = Path(dataset_dir)
        records = []

        # Load all JSONL files in the directory
        if path.is_dir():
            for jsonl_file in sorted(path.glob("*.jsonl")):
                with open(jsonl_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                records.append(json.loads(line))
                            except json.JSONDecodeError:
                                pass
        elif path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass

        report = self.run_dataset_benchmark(records)
        report["source"] = str(path)
        return report

    def save_report(self, report: dict, filename: str = "benchmark_report.json") -> str:
        """Save benchmark report to file.
        
        Returns:
            Path to saved report
        """
        output_dir = Path(self._report_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / filename

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        return str(output_path)

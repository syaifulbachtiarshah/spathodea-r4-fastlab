"""
SPATHODEA R4 FASTLAB — Error Analysis
Categorizes and analyzes validation/quality failures for targeted improvement.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional


class ErrorAnalyzer:
    """Analyzes validation failures and quality issues to guide dataset improvement.
    
    Identifies patterns in:
    - Which categories have highest rejection rates
    - Which languages have most issues
    - Which difficulty levels fail most
    - Common validation error types
    """

    def __init__(self, config: Optional[dict] = None):
        self._config = config or {}
        self._output_dir = self._config.get("output_dir", "reports/errors")

    def analyze_validation_errors(self, validation_results: dict) -> dict:
        """Analyze validation error patterns.
        
        Args:
            validation_results: Output from Validator.validate_file()
            
        Returns:
            Error analysis report
        """
        errors = validation_results.get("errors", [])
        if not errors:
            return {
                "status": "clean",
                "message": "No validation errors found",
                "total_errors": 0,
            }

        # Count error types
        error_rules = Counter()
        error_fields = Counter()

        for entry in errors:
            if isinstance(entry, dict) and "errors" in entry:
                for err in entry["errors"]:
                    error_rules[err.get("rule", "unknown")] += 1
                    error_fields[err.get("field", "unknown")] += 1
            elif isinstance(entry, dict) and "error" in entry:
                error_rules["json_parse"] += 1
                error_fields["line_level"] += 1

        return {
            "status": "errors_found",
            "total_invalid_records": validation_results.get("invalid", 0),
            "total_error_instances": sum(error_rules.values()),
            "by_rule": dict(error_rules.most_common()),
            "by_field": dict(error_fields.most_common()),
            "top_issues": [
                f"{rule}: {count} occurrences"
                for rule, count in error_rules.most_common(5)
            ],
        }

    def analyze_rejected_records(self, rejected_dir: str = "generated/rejected") -> dict:
        """Analyze rejected records for patterns.
        
        Args:
            rejected_dir: Path to directory containing rejected JSONL files
            
        Returns:
            Analysis of rejection patterns
        """
        path = Path(rejected_dir)
        if not path.exists() or not any(path.glob("*.jsonl")):
            return {
                "status": "no_data",
                "message": "No rejected records found",
            }

        records = []
        for jsonl_file in path.glob("*.jsonl"):
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass

        if not records:
            return {"status": "no_data", "message": "No valid rejected records"}

        # Analyze by dimension
        by_language = Counter()
        by_difficulty = Counter()
        by_intent = Counter()

        for record in records:
            meta = record.get("metadata", {})
            by_language[meta.get("language", "unknown")] += 1
            by_difficulty[meta.get("difficulty", "unknown")] += 1
            by_intent[meta.get("intent", "unknown")] += 1

        return {
            "status": "analyzed",
            "total_rejected": len(records),
            "by_language": dict(by_language.most_common()),
            "by_difficulty": dict(by_difficulty.most_common()),
            "by_intent": dict(by_intent.most_common(10)),
            "recommendations": self._generate_recommendations(
                by_language, by_difficulty, by_intent, len(records)
            ),
        }

    def _generate_recommendations(
        self,
        by_language: Counter,
        by_difficulty: Counter,
        by_intent: Counter,
        total: int,
    ) -> list[str]:
        """Generate actionable recommendations from error patterns."""
        recommendations = []

        # High rejection rate in specific language
        for lang, count in by_language.most_common(3):
            rate = count / max(total, 1)
            if rate > 0.4:
                recommendations.append(
                    f"High rejection rate for language='{lang}' ({rate:.0%}). "
                    f"Review generation prompts for this language."
                )

        # High rejection rate for specific difficulty
        for diff, count in by_difficulty.most_common(3):
            rate = count / max(total, 1)
            if rate > 0.3:
                recommendations.append(
                    f"High rejection rate for difficulty='{diff}' ({rate:.0%}). "
                    f"Adjust difficulty-specific templates."
                )

        if not recommendations:
            recommendations.append("No dominant rejection patterns detected.")

        return recommendations

    def full_analysis(
        self,
        validation_results: Optional[dict] = None,
        rejected_dir: str = "generated/rejected",
    ) -> dict:
        """Run complete error analysis.
        
        Args:
            validation_results: Output from validator (optional)
            rejected_dir: Path to rejected records
            
        Returns:
            Combined error analysis report
        """
        report = {
            "validation_errors": None,
            "rejection_patterns": None,
        }

        if validation_results:
            report["validation_errors"] = self.analyze_validation_errors(validation_results)

        report["rejection_patterns"] = self.analyze_rejected_records(rejected_dir)

        return report

    def save_report(self, report: dict, filename: str = "error_analysis.json") -> str:
        """Save error analysis report to file."""
        output_dir = Path(self._output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / filename

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        return str(output_path)

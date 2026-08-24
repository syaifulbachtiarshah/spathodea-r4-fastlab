"""
SPATHODEA R4 FASTLAB — Dataset Balancer
Enforces target distributions across categories, languages, and difficulty.

Phase 1: Reports distribution imbalances.
Phase 2: Will actively rebalance via over/undersampling.
"""

from collections import Counter
from typing import Optional


class Balancer:
    """Dataset distribution balancer.
    
    Checks and enforces target distributions for:
    - Language (en/ms/mixed)
    - Difficulty (easy/medium/hard/adversarial/noisy)
    - Intent categories
    """

    def __init__(self, config: Optional[dict] = None):
        cfg = config or {}
        self.language_targets = cfg.get("language_targets", {
            "en": 0.50, "ms": 0.40, "mixed": 0.10,
        })
        self.difficulty_targets = cfg.get("difficulty_targets", {
            "easy": 0.20, "medium": 0.35, "hard": 0.25,
            "adversarial": 0.15, "noisy": 0.05,
        })
        self.tolerance = cfg.get("tolerance", 0.05)

    def analyze_distribution(self, records: list[dict]) -> dict:
        """Analyze the distribution of records across all dimensions.
        
        Returns:
            Dict with language, difficulty, and intent distributions + imbalance flags
        """
        if not records:
            return {"total": 0, "language": {}, "difficulty": {}, "intent": {}, "balanced": False}

        n = len(records)
        lang_counts = Counter()
        diff_counts = Counter()
        intent_counts = Counter()

        for record in records:
            meta = record.get("metadata", {})
            lang_counts[meta.get("language", "unknown")] += 1
            diff_counts[meta.get("difficulty", "unknown")] += 1
            intent_counts[meta.get("intent", "unknown")] += 1

        # Compute ratios
        lang_dist = {k: v / n for k, v in lang_counts.items()}
        diff_dist = {k: v / n for k, v in diff_counts.items()}
        intent_dist = {k: v / n for k, v in intent_counts.items()}

        # Check balance
        lang_balanced = self._check_balance(lang_dist, self.language_targets)
        diff_balanced = self._check_balance(diff_dist, self.difficulty_targets)

        return {
            "total": n,
            "language": {
                "counts": dict(lang_counts),
                "distribution": lang_dist,
                "targets": self.language_targets,
                "balanced": lang_balanced,
            },
            "difficulty": {
                "counts": dict(diff_counts),
                "distribution": diff_dist,
                "targets": self.difficulty_targets,
                "balanced": diff_balanced,
            },
            "intent": {
                "counts": dict(intent_counts),
                "distribution": intent_dist,
                "unique_intents": len(intent_counts),
            },
            "balanced": lang_balanced and diff_balanced,
        }

    def _check_balance(self, actual: dict, targets: dict) -> bool:
        """Check if actual distribution is within tolerance of targets."""
        for key, target in targets.items():
            actual_val = actual.get(key, 0.0)
            if abs(actual_val - target) > self.tolerance:
                return False
        return True

    def get_recommendations(self, records: list[dict]) -> list[str]:
        """Get recommendations for rebalancing.
        
        Returns:
            List of human-readable recommendation strings
        """
        analysis = self.analyze_distribution(records)
        recommendations = []

        if analysis["total"] == 0:
            return ["No records to analyze. Generate data first."]

        # Language recommendations
        lang = analysis["language"]
        if not lang["balanced"]:
            for key, target in self.language_targets.items():
                actual = lang["distribution"].get(key, 0.0)
                diff = actual - target
                if abs(diff) > self.tolerance:
                    if diff < 0:
                        recommendations.append(
                            f"UNDER-REPRESENTED: language='{key}' "
                            f"(have {actual:.1%}, need {target:.1%}, deficit {abs(diff):.1%})"
                        )
                    else:
                        recommendations.append(
                            f"OVER-REPRESENTED: language='{key}' "
                            f"(have {actual:.1%}, target {target:.1%}, excess {diff:.1%})"
                        )

        # Difficulty recommendations
        diff_data = analysis["difficulty"]
        if not diff_data["balanced"]:
            for key, target in self.difficulty_targets.items():
                actual = diff_data["distribution"].get(key, 0.0)
                delta = actual - target
                if abs(delta) > self.tolerance:
                    if delta < 0:
                        recommendations.append(
                            f"UNDER-REPRESENTED: difficulty='{key}' "
                            f"(have {actual:.1%}, need {target:.1%})"
                        )
                    else:
                        recommendations.append(
                            f"OVER-REPRESENTED: difficulty='{key}' "
                            f"(have {actual:.1%}, target {target:.1%})"
                        )

        if not recommendations:
            recommendations.append("Dataset is balanced within tolerance.")

        return recommendations

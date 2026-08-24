"""
SPATHODEA R4 FASTLAB — Quality Scorer
Rule-based quality scoring for internal records.

Phase 1: Simple heuristic scoring.
Phase 2: Will add LLM-as-judge scoring.
"""

from typing import Optional


class Scorer:
    """Rule-based quality scorer for training records.
    
    Scores each record on multiple dimensions (0.0 to 1.0):
    - completeness: Are all expected parts present and well-formed?
    - coherence: Does the output logically relate to the input?
    - relevance: Is the content on-topic for the stated intent?
    - naturalness: Does it read like natural language?
    - difficulty_alignment: Does complexity match stated difficulty?
    
    Phase 1 uses simple heuristics. Phase 2 adds LLM-based scoring.
    """

    def __init__(self, config: Optional[dict] = None):
        cfg = config or {}
        self.min_acceptable = cfg.get("min_acceptable_score", 0.70)
        self.weights = cfg.get("dimensions", {
            "completeness": 0.25,
            "coherence": 0.30,
            "relevance": 0.20,
            "naturalness": 0.15,
            "difficulty_alignment": 0.10,
        })

    def score_completeness(self, record: dict) -> float:
        """Score based on structural completeness."""
        score = 0.0
        # Has non-trivial input
        inp = record.get("input", "")
        if len(inp) >= 10:
            score += 0.3
        elif len(inp) >= 5:
            score += 0.15

        # Has non-trivial output
        out = record.get("output", "")
        if len(out) >= 50:
            score += 0.4
        elif len(out) >= 20:
            score += 0.25
        elif len(out) >= 10:
            score += 0.1

        # Has metadata
        meta = record.get("metadata", {})
        if meta.get("intent"):
            score += 0.15
        if meta.get("language"):
            score += 0.15

        return min(score, 1.0)

    def score_coherence(self, record: dict) -> float:
        """Score based on input-output coherence (heuristic).
        
        Simple heuristic: checks that output is substantively longer
        than input and doesn't just repeat the input.
        """
        inp = record.get("input", "")
        out = record.get("output", "")

        if not inp or not out:
            return 0.0

        score = 0.5  # Base score for having both fields

        # Output should be longer than input (for instructional data)
        if len(out) > len(inp):
            score += 0.2

        # Output shouldn't just be a copy of input
        if out.strip().lower() != inp.strip().lower():
            score += 0.2

        # Output has some structural content (sentences, not just a word)
        if "." in out or "。" in out or len(out.split()) >= 5:
            score += 0.1

        return min(score, 1.0)

    def score_relevance(self, record: dict) -> float:
        """Score based on metadata consistency (heuristic).
        
        Checks that intent/category is present and non-generic.
        """
        meta = record.get("metadata", {})
        score = 0.5  # Base

        intent = meta.get("intent", "")
        if intent and intent != "unknown" and intent != "general":
            score += 0.3
        if meta.get("difficulty"):
            score += 0.1
        if meta.get("language"):
            score += 0.1

        return min(score, 1.0)

    def score_naturalness(self, record: dict) -> float:
        """Score based on language naturalness (heuristic).
        
        Checks for overly repetitive patterns, adequate word diversity.
        """
        out = record.get("output", "")
        if not out:
            return 0.0

        words = out.split()
        if len(words) < 3:
            return 0.3

        score = 0.5  # Base

        # Word diversity (unique/total ratio)
        unique_ratio = len(set(w.lower() for w in words)) / len(words)
        if unique_ratio > 0.5:
            score += 0.3
        elif unique_ratio > 0.3:
            score += 0.15

        # Not excessively short
        if len(words) >= 10:
            score += 0.2

        return min(score, 1.0)

    def score_difficulty_alignment(self, record: dict) -> float:
        """Score based on difficulty label alignment (heuristic).
        
        Simple check: harder difficulty should correlate with longer/more complex output.
        """
        meta = record.get("metadata", {})
        difficulty = meta.get("difficulty", "medium")
        out = record.get("output", "")
        word_count = len(out.split())

        # Expected complexity ranges
        expectations = {
            "easy": (10, 80),
            "medium": (20, 200),
            "hard": (40, 500),
            "adversarial": (20, 500),
            "noisy": (5, 200),
        }

        expected = expectations.get(difficulty, (10, 200))
        if expected[0] <= word_count <= expected[1]:
            return 0.9
        elif word_count < expected[0]:
            return 0.5
        else:
            return 0.7  # Longer is usually fine

    def score_record(self, record: dict) -> dict:
        """Score a record on all dimensions.
        
        Returns:
            Dict with dimension scores and composite score
        """
        dimensions = {
            "completeness": self.score_completeness(record),
            "coherence": self.score_coherence(record),
            "relevance": self.score_relevance(record),
            "naturalness": self.score_naturalness(record),
            "difficulty_alignment": self.score_difficulty_alignment(record),
        }

        # Weighted composite
        composite = sum(
            dimensions[dim] * self.weights.get(dim, 0.0)
            for dim in dimensions
        )

        return {
            "dimensions": dimensions,
            "composite": round(composite, 4),
            "acceptable": composite >= self.min_acceptable,
        }

    def score_records(self, records: list[dict]) -> dict:
        """Score multiple records and return statistics.
        
        Returns:
            Dict with per-record scores and aggregate stats
        """
        results = []
        scores = []

        for record in records:
            score_result = self.score_record(record)
            results.append({
                "record_id": record.get("id"),
                **score_result,
            })
            scores.append(score_result["composite"])

        acceptable = sum(1 for r in results if r["acceptable"])

        stats = {
            "total": len(records),
            "acceptable": acceptable,
            "rejected": len(records) - acceptable,
            "mean_score": sum(scores) / max(len(scores), 1),
            "min_score": min(scores) if scores else 0.0,
            "max_score": max(scores) if scores else 0.0,
        }

        return {"results": results, "stats": stats}

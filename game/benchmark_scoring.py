"""
SPATHODEA R4 FASTLAB — Benchmark Scoring (Phase 2F Part 3D)
Internal scoring metrics for competition readiness benchmark.

NOT POLYCC OFFICIAL SCORE. Internal readiness assessment only.
"""

from dataclasses import dataclass, field
from typing import Optional


# =============================================================================
# Stage A: One-Turn Metrics
# =============================================================================

@dataclass
class OneTurnMetrics:
    """Metrics for a single one-turn scenario evaluation."""
    scenario_name: str = ""
    model: str = ""
    raw_response: str = ""
    parsed_action: Optional[str] = None
    parse_success: bool = False
    legal_action: bool = False
    unsafe_accepted: bool = False
    fallback_used: bool = False
    fallback_reason: str = ""
    goal_progress: str = "neutral"  # progress / neutral / regress
    provider_latency_ms: float = 0.0
    bridge_processing_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario_name,
            "model": self.model,
            "raw_response": self.raw_response[:80],
            "parsed_action": self.parsed_action,
            "parse_success": self.parse_success,
            "legal_action": self.legal_action,
            "unsafe_accepted": self.unsafe_accepted,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "goal_progress": self.goal_progress,
            "provider_latency_ms": round(self.provider_latency_ms, 1),
            "bridge_processing_ms": round(self.bridge_processing_ms, 1),
        }


@dataclass
class ModelOneTurnAgg:
    """Aggregated one-turn metrics for a model."""
    model: str = ""
    total_scenarios: int = 0
    parse_success_count: int = 0
    legal_action_count: int = 0
    unsafe_count: int = 0
    fallback_count: int = 0
    goal_progress_count: int = 0
    latencies: list = field(default_factory=list)

    @property
    def parse_success_rate(self) -> float:
        return self.parse_success_count / self.total_scenarios if self.total_scenarios else 0.0

    @property
    def legal_action_rate(self) -> float:
        return self.legal_action_count / self.total_scenarios if self.total_scenarios else 0.0

    @property
    def unsafe_rate(self) -> float:
        return self.unsafe_count / self.total_scenarios if self.total_scenarios else 0.0

    @property
    def fallback_rate(self) -> float:
        return self.fallback_count / self.total_scenarios if self.total_scenarios else 0.0

    @property
    def goal_progress_rate(self) -> float:
        return self.goal_progress_count / self.total_scenarios if self.total_scenarios else 0.0

    @property
    def avg_latency_ms(self) -> float:
        return sum(self.latencies) / len(self.latencies) if self.latencies else 0.0

    @property
    def p50_latency_ms(self) -> float:
        if not self.latencies:
            return 0.0
        s = sorted(self.latencies)
        return s[len(s) // 2]

    @property
    def max_latency_ms(self) -> float:
        return max(self.latencies) if self.latencies else 0.0

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "total_scenarios": self.total_scenarios,
            "parse_success_rate": round(self.parse_success_rate, 3),
            "legal_action_rate": round(self.legal_action_rate, 3),
            "unsafe_count": self.unsafe_count,
            "fallback_count": self.fallback_count,
            "fallback_rate": round(self.fallback_rate, 3),
            "goal_progress_rate": round(self.goal_progress_rate, 3),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "p50_latency_ms": round(self.p50_latency_ms, 1),
            "max_latency_ms": round(self.max_latency_ms, 1),
        }


# =============================================================================
# Stage B: Multi-Turn Metrics
# =============================================================================

@dataclass
class MultiTurnMetrics:
    """Metrics for a multi-turn episode evaluation."""
    episode_name: str = ""
    model: str = ""
    total_turns: int = 0
    goal_reached: bool = False
    final_position: str = ""
    turns_to_goal: int = 0
    optimal_path_length: int = 0
    path_efficiency: float = 0.0
    fallback_count: int = 0
    oscillation_events: int = 0
    repeated_loops: int = 0
    unsafe_accepted_actions: int = 0
    avg_provider_latency: float = 0.0

    @property
    def path_efficiency_ratio(self) -> float:
        if self.optimal_path_length == 0 or self.turns_to_goal == 0:
            return 0.0
        return self.optimal_path_length / self.turns_to_goal

    def to_dict(self) -> dict:
        return {
            "episode": self.episode_name,
            "model": self.model,
            "total_turns": self.total_turns,
            "goal_reached": self.goal_reached,
            "final_position": self.final_position,
            "turns_to_goal": self.turns_to_goal,
            "optimal_path_length": self.optimal_path_length,
            "path_efficiency": round(self.path_efficiency_ratio, 3),
            "fallback_count": self.fallback_count,
            "oscillation_events": self.oscillation_events,
            "repeated_loops": self.repeated_loops,
            "unsafe_accepted_actions": self.unsafe_accepted_actions,
            "avg_provider_latency_ms": round(self.avg_provider_latency, 1),
        }


@dataclass
class ModelMultiTurnAgg:
    """Aggregated multi-turn metrics for a model."""
    model: str = ""
    total_episodes: int = 0
    goals_reached: int = 0
    total_turns: int = 0
    total_optimal: int = 0
    total_fallback: int = 0
    total_oscillation: int = 0
    total_repeated_loops: int = 0
    total_unsafe: int = 0
    latencies: list = field(default_factory=list)

    @property
    def goal_completion_rate(self) -> float:
        return self.goals_reached / self.total_episodes if self.total_episodes else 0.0

    @property
    def avg_path_efficiency(self) -> float:
        if self.total_turns == 0 or self.total_optimal == 0:
            return 0.0
        return self.total_optimal / self.total_turns

    @property
    def fallback_rate(self) -> float:
        return self.total_fallback / self.total_turns if self.total_turns else 0.0

    @property
    def avg_latency_ms(self) -> float:
        return sum(self.latencies) / len(self.latencies) if self.latencies else 0.0

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "total_episodes": self.total_episodes,
            "goals_reached": self.goals_reached,
            "goal_completion_rate": round(self.goal_completion_rate, 3),
            "total_turns": self.total_turns,
            "avg_path_efficiency": round(self.avg_path_efficiency, 3),
            "fallback_rate": round(self.fallback_rate, 3),
            "total_oscillation": self.total_oscillation,
            "total_repeated_loops": self.total_repeated_loops,
            "total_unsafe": self.total_unsafe,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
        }


# =============================================================================
# Stage C: Strategy Metrics
# =============================================================================

@dataclass
class StrategyMetrics:
    """Metrics for a strategy evaluation on a single scenario."""
    strategy: str = ""
    scenario_name: str = ""
    goal_reached: bool = False
    score: int = 0
    rewards_collected: int = 0
    health_remaining: int = 100
    turns: int = 0
    path_efficiency: float = 0.0
    unsafe_actions: int = 0
    fallback_count: int = 0
    oscillation_events: int = 0

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "scenario": self.scenario_name,
            "goal_reached": self.goal_reached,
            "score": self.score,
            "rewards_collected": self.rewards_collected,
            "health_remaining": self.health_remaining,
            "turns": self.turns,
            "path_efficiency": round(self.path_efficiency, 3),
            "unsafe_actions": self.unsafe_actions,
            "fallback_count": self.fallback_count,
            "oscillation_events": self.oscillation_events,
        }


# =============================================================================
# Stage D: Latency Classification
# =============================================================================

def classify_latency(latency_ms: float) -> str:
    """Classify latency into performance buckets.

    FAST: < 2s
    ACCEPTABLE: 2-5s
    SLOW: 5-10s
    VERY_SLOW: > 10s
    """
    if latency_ms < 2000:
        return "FAST"
    elif latency_ms < 5000:
        return "ACCEPTABLE"
    elif latency_ms < 10000:
        return "SLOW"
    else:
        return "VERY_SLOW"


@dataclass
class LatencyDistribution:
    """Latency distribution for a model."""
    model: str = ""
    latencies: list = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.latencies)

    @property
    def avg_ms(self) -> float:
        return sum(self.latencies) / len(self.latencies) if self.latencies else 0.0

    @property
    def p50_ms(self) -> float:
        if not self.latencies:
            return 0.0
        s = sorted(self.latencies)
        return s[len(s) // 2]

    @property
    def p90_ms(self) -> float:
        if not self.latencies:
            return 0.0
        s = sorted(self.latencies)
        idx = int(len(s) * 0.9)
        return s[min(idx, len(s) - 1)]

    @property
    def max_ms(self) -> float:
        return max(self.latencies) if self.latencies else 0.0

    @property
    def min_ms(self) -> float:
        return min(self.latencies) if self.latencies else 0.0

    def classify(self) -> dict[str, int]:
        """Count latencies in each classification bucket."""
        counts = {"FAST": 0, "ACCEPTABLE": 0, "SLOW": 0, "VERY_SLOW": 0}
        for lat in self.latencies:
            counts[classify_latency(lat)] += 1
        return counts

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "count": self.count,
            "avg_ms": round(self.avg_ms, 1),
            "p50_ms": round(self.p50_ms, 1),
            "p90_ms": round(self.p90_ms, 1),
            "max_ms": round(self.max_ms, 1),
            "min_ms": round(self.min_ms, 1),
            "classification": self.classify(),
        }


# =============================================================================
# Stage E: Internal Readiness Score
# =============================================================================

@dataclass
class ReadinessScore:
    """SPATHODEA_INTERNAL_READINESS_SCORE for a model.

    NOT POLYCC OFFICIAL SCORE.
    """
    model: str = ""

    # Component scores (0.0 - 1.0)
    safety_score: float = 0.0
    goal_score: float = 0.0
    efficiency_score: float = 0.0
    fallback_score: float = 0.0
    oscillation_score: float = 0.0
    latency_score: float = 0.0

    # Weights
    SAFETY_WEIGHT: float = 0.30
    GOAL_WEIGHT: float = 0.25
    EFFICIENCY_WEIGHT: float = 0.15
    FALLBACK_WEIGHT: float = 0.10
    OSCILLATION_WEIGHT: float = 0.10
    LATENCY_WEIGHT: float = 0.10

    @property
    def total_score(self) -> float:
        """Weighted total readiness score."""
        return (
            self.safety_score * self.SAFETY_WEIGHT +
            self.goal_score * self.GOAL_WEIGHT +
            self.efficiency_score * self.EFFICIENCY_WEIGHT +
            self.fallback_score * self.FALLBACK_WEIGHT +
            self.oscillation_score * self.OSCILLATION_WEIGHT +
            self.latency_score * self.LATENCY_WEIGHT
        )

    @property
    def grade(self) -> str:
        """Letter grade based on total score."""
        s = self.total_score
        if s >= 0.9:
            return "A"
        elif s >= 0.8:
            return "B"
        elif s >= 0.7:
            return "C"
        elif s >= 0.6:
            return "D"
        else:
            return "F"

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "component_scores": {
                "safety_legal_correctness": round(self.safety_score, 3),
                "goal_completion_progress": round(self.goal_score, 3),
                "path_efficiency": round(self.efficiency_score, 3),
                "fallback_independence": round(self.fallback_score, 3),
                "oscillation_control": round(self.oscillation_score, 3),
                "latency": round(self.latency_score, 3),
            },
            "weights": {
                "safety": self.SAFETY_WEIGHT,
                "goal": self.GOAL_WEIGHT,
                "efficiency": self.EFFICIENCY_WEIGHT,
                "fallback": self.FALLBACK_WEIGHT,
                "oscillation": self.OSCILLATION_WEIGHT,
                "latency": self.LATENCY_WEIGHT,
            },
            "SPATHODEA_INTERNAL_READINESS_SCORE": round(self.total_score, 3),
            "grade": self.grade,
        }

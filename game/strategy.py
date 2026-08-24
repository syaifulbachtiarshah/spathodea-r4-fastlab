"""
SPATHODEA R4 FASTLAB — Strategy Profiles (Phase 2F)
Strategy profiles controlling pathfinding and decision-making behavior.

Profiles:
    safe        — Minimize hazard/enemy exposure
    speedrun    — Shortest valid path to objective
    reward_max  — Maximize reward while still reaching objective
    adaptive    — Balance reward, risk, and distance
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


# =============================================================================
# Strategy Profile Enum
# =============================================================================

class StrategyProfile(str, Enum):
    """Available strategy profiles for the game agent."""
    SAFE = "safe"
    SPEEDRUN = "speedrun"
    REWARD_MAX = "reward_max"
    ADAPTIVE = "adaptive"


VALID_STRATEGIES = tuple(StrategyProfile)


# =============================================================================
# Strategy Configuration
# =============================================================================

@dataclass
class Strategy:
    """Strategy configuration controlling agent behavior.

    Attributes:
        profile: Active strategy profile
        hazard_weight: Cost multiplier for hazard cells (higher = more avoidance)
        enemy_weight: Cost multiplier for enemy-adjacent cells
        reward_weight: Negative cost (incentive) for reward cells
        door_weight: Cost for locked doors (discourages unless key held)
        movement_cost: Base cost per step
        max_detour_ratio: Max allowed path length vs shortest (for reward collection)
        enemy_proximity_radius: Radius for enemy-adjacent penalty
        risk_tolerance: 0.0 = risk-averse, 1.0 = risk-neutral
        collect_keys: Whether to pursue keys actively
        collect_rewards: Whether to pursue coins actively
    """
    profile: StrategyProfile
    hazard_weight: float = 10.0
    enemy_weight: float = 8.0
    reward_weight: float = -2.0
    door_weight: float = 50.0
    movement_cost: float = 1.0
    max_detour_ratio: float = 2.0
    enemy_proximity_radius: int = 2
    risk_tolerance: float = 0.5
    collect_keys: bool = True
    collect_rewards: bool = False

    @classmethod
    def from_profile(cls, profile: StrategyProfile) -> "Strategy":
        """Create a Strategy with preset values for the given profile."""
        if profile == StrategyProfile.SAFE:
            return cls(
                profile=profile,
                hazard_weight=50.0,
                enemy_weight=40.0,
                reward_weight=0.0,
                door_weight=100.0,
                movement_cost=1.0,
                max_detour_ratio=3.0,
                enemy_proximity_radius=3,
                risk_tolerance=0.0,
                collect_keys=True,
                collect_rewards=False,
            )
        elif profile == StrategyProfile.SPEEDRUN:
            return cls(
                profile=profile,
                hazard_weight=1.0,
                enemy_weight=1.0,
                reward_weight=0.0,
                door_weight=5.0,
                movement_cost=1.0,
                max_detour_ratio=1.0,
                enemy_proximity_radius=0,
                risk_tolerance=1.0,
                collect_keys=True,
                collect_rewards=False,
            )
        elif profile == StrategyProfile.REWARD_MAX:
            return cls(
                profile=profile,
                hazard_weight=15.0,
                enemy_weight=12.0,
                reward_weight=-5.0,
                door_weight=20.0,
                movement_cost=1.0,
                max_detour_ratio=3.0,
                enemy_proximity_radius=2,
                risk_tolerance=0.4,
                collect_keys=True,
                collect_rewards=True,
            )
        elif profile == StrategyProfile.ADAPTIVE:
            return cls(
                profile=profile,
                hazard_weight=10.0,
                enemy_weight=8.0,
                reward_weight=-2.0,
                door_weight=30.0,
                movement_cost=1.0,
                max_detour_ratio=2.0,
                enemy_proximity_radius=2,
                risk_tolerance=0.5,
                collect_keys=True,
                collect_rewards=True,
            )
        else:
            raise ValueError(f"Unknown strategy profile: {profile}")

    def should_collect_reward(self, detour_steps: int, shortest_path: int) -> bool:
        """Decide if a detour to collect a reward is acceptable.

        Args:
            detour_steps: Additional steps required for the reward
            shortest_path: Length of the shortest path to goal

        Returns:
            True if the detour is within acceptable ratio
        """
        if shortest_path == 0:
            return detour_steps <= 2
        total = shortest_path + detour_steps
        return total <= shortest_path * self.max_detour_ratio

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "profile": self.profile.value,
            "hazard_weight": self.hazard_weight,
            "enemy_weight": self.enemy_weight,
            "reward_weight": self.reward_weight,
            "door_weight": self.door_weight,
            "movement_cost": self.movement_cost,
            "max_detour_ratio": self.max_detour_ratio,
            "enemy_proximity_radius": self.enemy_proximity_radius,
            "risk_tolerance": self.risk_tolerance,
            "collect_keys": self.collect_keys,
            "collect_rewards": self.collect_rewards,
        }

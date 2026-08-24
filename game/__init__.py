"""
SPATHODEA R4 FASTLAB — Game Agent Package (Phase 2F)
Offline adapter layer for POLYCC grid-navigation competition game.

Modules:
    game_state       — Grid game state representation
    action_schema    — Normalized action definitions
    strategy         — Strategy profiles (safe, speedrun, reward_max, adaptive)
    pathfinder       — Deterministic local pathfinding (BFS, A*, weighted A*)
    game_agent_adapter — Adapter converting game state + strategy into actions
"""

from .game_state import GameState, Position
from .action_schema import Action, ActionResult, VALID_ACTIONS, FUTURE_ACTIONS
from .strategy import Strategy, StrategyProfile, VALID_STRATEGIES
from .pathfinder import Pathfinder, PathResult, CostConfig
from .game_agent_adapter import GameAgentAdapter, PlanningContext, CombatLogEntry

__all__ = [
    "GameState", "Position",
    "Action", "ActionResult", "VALID_ACTIONS", "FUTURE_ACTIONS",
    "Strategy", "StrategyProfile", "VALID_STRATEGIES",
    "Pathfinder", "PathResult", "CostConfig",
    "GameAgentAdapter", "PlanningContext", "CombatLogEntry",
]

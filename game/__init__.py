"""
SPATHODEA R4 FASTLAB — Game Agent Package (Phase 2F)
Offline adapter layer for POLYCC grid-navigation competition game.

Modules:
    game_state          — Grid game state representation
    action_schema       — Normalized action definitions
    strategy            — Strategy profiles (safe, speedrun, reward_max, adaptive)
    pathfinder          — Deterministic local pathfinding (BFS, A*, weighted A*)
    game_agent_adapter  — Adapter converting game state + strategy into actions
    action_parser       — Parses provider output into validated Action (Phase 2F Part 2)
    buzz_game_bridge    — Bridge between GameAgentAdapter and BUZZ (Phase 2F Part 2)
    game_simulator      — Deterministic offline game simulator (Phase 2F Part 2)
    turn_controller     — Full turn pipeline orchestrator (Phase 2F Part 2)
    navigation_context  — Deterministic navigation context builder (Phase 2F Part 3C)
    navigation_prompt   — Grounded navigation prompt builder (Phase 2F Part 3C)
"""

from .game_state import GameState, Position
from .action_schema import Action, ActionResult, VALID_ACTIONS, FUTURE_ACTIONS
from .strategy import Strategy, StrategyProfile, VALID_STRATEGIES
from .pathfinder import Pathfinder, PathResult, CostConfig
from .game_agent_adapter import GameAgentAdapter, PlanningContext, CombatLogEntry
from .action_parser import ActionParser, ActionParseResult
from .buzz_game_bridge import BuzzGameBridge, BridgeConfig, BridgeResult, SimulatedProvider
from .game_simulator import GameSimulator, SimulationMetrics, SimConfig
from .turn_controller import TurnController, TurnLogEntry, ControllerConfig, EpisodeResult
from .navigation_context import NavigationContext, NavigationContextBuilder
from .navigation_prompt import build_baseline_prompt, build_grounded_nav_prompt, build_prompt

__all__ = [
    # Part 1
    "GameState", "Position",
    "Action", "ActionResult", "VALID_ACTIONS", "FUTURE_ACTIONS",
    "Strategy", "StrategyProfile", "VALID_STRATEGIES",
    "Pathfinder", "PathResult", "CostConfig",
    "GameAgentAdapter", "PlanningContext", "CombatLogEntry",
    # Part 2
    "ActionParser", "ActionParseResult",
    "BuzzGameBridge", "BridgeConfig", "BridgeResult", "SimulatedProvider",
    "GameSimulator", "SimulationMetrics", "SimConfig",
    "TurnController", "TurnLogEntry", "ControllerConfig", "EpisodeResult",
    # Part 3C
    "NavigationContext", "NavigationContextBuilder",
    "build_baseline_prompt", "build_grounded_nav_prompt", "build_prompt",
]

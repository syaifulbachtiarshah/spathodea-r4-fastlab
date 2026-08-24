"""
SPATHODEA R4 FASTLAB — Turn Controller (Phase 2F Part 2)
Orchestrates the full turn pipeline:

    state → planning context → simulated BUZZ request → provider response
    → action parser → safety gate → apply action → combat log

Configurable: max_turns, strategy, provider, reviewer, execution_mode.
Tracks performance metrics separately: pathfinder_ms, bridge_processing_ms, turn_processing_ms.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

from .game_state import GameState, Position
from .action_schema import Action
from .strategy import Strategy, StrategyProfile
from .pathfinder import Pathfinder, CostConfig
from .game_agent_adapter import GameAgentAdapter, PlanningContext
from .buzz_game_bridge import BuzzGameBridge, BridgeConfig, BridgeResult, SimulatedProvider
from .game_simulator import GameSimulator, SimulationMetrics, SimConfig


# =============================================================================
# Turn Log Entry (Extended Combat Log)
# =============================================================================

@dataclass
class TurnLogEntry:
    """Extended combat log entry for one turn cycle.

    Never logs full sensitive prompts.

    Attributes:
        turn: Turn number
        position_before: Agent position before action
        provider_requested: Provider preference sent
        provider_used: Provider that responded
        raw_action_summary: Truncated raw provider output
        parsed_action: Action extracted from provider output (or None)
        final_action: Action actually applied after safety gate
        fallback_used: Whether fallback was triggered
        fallback_reason: Why fallback was needed
        position_after: Agent position after action
        score: Score after this turn
        health: Health after this turn
        status: Turn outcome
        pathfinder_ms: Time in pathfinder logic
        bridge_processing_ms: Time in bridge processing
        turn_processing_ms: Total turn processing time
    """
    turn: int = 0
    position_before: str = ""
    provider_requested: Optional[str] = None
    provider_used: Optional[str] = None
    raw_action_summary: str = ""
    parsed_action: Optional[str] = None
    final_action: str = ""
    fallback_used: bool = False
    fallback_reason: str = ""
    position_after: str = ""
    score: int = 0
    health: int = 100
    status: str = "ok"
    pathfinder_ms: float = 0.0
    bridge_processing_ms: float = 0.0
    turn_processing_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "turn": self.turn,
            "position_before": self.position_before,
            "provider_requested": self.provider_requested,
            "provider_used": self.provider_used,
            "raw_action_summary": self.raw_action_summary,
            "parsed_action": self.parsed_action,
            "final_action": self.final_action,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "position_after": self.position_after,
            "score": self.score,
            "health": self.health,
            "status": self.status,
            "pathfinder_ms": round(self.pathfinder_ms, 3),
            "bridge_processing_ms": round(self.bridge_processing_ms, 3),
            "turn_processing_ms": round(self.turn_processing_ms, 3),
        }


# =============================================================================
# Controller Configuration
# =============================================================================

@dataclass
class ControllerConfig:
    """Configuration for the turn controller.

    Attributes:
        max_turns: Maximum turns before forced termination
        strategy: Strategy profile name
        provider: Provider preference for BUZZ
        reviewer: Reviewer preference for BUZZ
        execution_mode: Execution mode for BUZZ
        sim_config: Game simulator configuration
        bridge_config: BUZZ bridge configuration
    """
    max_turns: int = 100
    strategy: str = "adaptive"
    provider: Optional[str] = "mock"
    reviewer: Optional[str] = None
    execution_mode: str = "sync"
    sim_config: Optional[SimConfig] = None
    bridge_config: Optional[BridgeConfig] = None

    def to_dict(self) -> dict:
        return {
            "max_turns": self.max_turns,
            "strategy": self.strategy,
            "provider": self.provider,
            "reviewer": self.reviewer,
            "execution_mode": self.execution_mode,
            "sim_config": self.sim_config.to_dict() if self.sim_config else None,
            "bridge_config": self.bridge_config.to_dict() if self.bridge_config else None,
        }


# =============================================================================
# Episode Result
# =============================================================================

@dataclass
class EpisodeResult:
    """Result of a full game episode.

    Attributes:
        metrics: Simulation metrics
        turn_log: List of per-turn log entries
        config: Controller configuration used
        termination_reason: Why episode ended
        total_pathfinder_ms: Cumulative pathfinder time
        total_bridge_ms: Cumulative bridge processing time
        total_turn_ms: Cumulative turn processing time
    """
    metrics: Optional[SimulationMetrics] = None
    turn_log: list = field(default_factory=list)
    config: Optional[ControllerConfig] = None
    termination_reason: str = ""
    total_pathfinder_ms: float = 0.0
    total_bridge_ms: float = 0.0
    total_turn_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "metrics": self.metrics.to_dict() if self.metrics else None,
            "turn_log": [t.to_dict() for t in self.turn_log],
            "config": self.config.to_dict() if self.config else None,
            "termination_reason": self.termination_reason,
            "total_pathfinder_ms": round(self.total_pathfinder_ms, 3),
            "total_bridge_ms": round(self.total_bridge_ms, 3),
            "total_turn_ms": round(self.total_turn_ms, 3),
        }


# =============================================================================
# Turn Controller
# =============================================================================

class TurnController:
    """Orchestrates the full game turn pipeline.

    Pipeline per turn:
        1. Build planning context (GameAgentAdapter)
        2. Send to BUZZ bridge (simulated)
        3. Parse provider response
        4. Apply safety gate
        5. Apply action to simulator
        6. Record turn log

    Usage:
        controller = TurnController(state, config)
        result = controller.run_episode()
    """

    def __init__(
        self,
        initial_state: GameState,
        config: Optional[ControllerConfig] = None,
        provider: Optional[SimulatedProvider] = None,
    ):
        """Initialize the turn controller.

        Args:
            initial_state: Starting game state
            config: Controller configuration
            provider: Simulated provider (for testing specific behaviors)
        """
        self._config = config or ControllerConfig()

        # Build bridge config
        bridge_cfg = self._config.bridge_config or BridgeConfig(
            provider_preference=self._config.provider,
            reviewer_preference=self._config.reviewer,
            execution_mode=self._config.execution_mode,
        )

        # Initialize components
        self._adapter = GameAgentAdapter(strategy_profile=self._config.strategy)
        self._bridge = BuzzGameBridge(config=bridge_cfg, provider=provider or SimulatedProvider())
        self._simulator = GameSimulator(
            initial_state,
            config=self._config.sim_config or SimConfig(),
        )
        self._turn_log: list[TurnLogEntry] = []

    @property
    def simulator(self) -> GameSimulator:
        return self._simulator

    @property
    def bridge(self) -> BuzzGameBridge:
        return self._bridge

    @property
    def adapter(self) -> GameAgentAdapter:
        return self._adapter

    @property
    def turn_log(self) -> list[TurnLogEntry]:
        return self._turn_log

    # =========================================================================
    # Single Turn
    # =========================================================================

    def execute_turn(self) -> TurnLogEntry:
        """Execute a single turn of the game pipeline.

        Returns:
            TurnLogEntry for this turn
        """
        turn_start = time.perf_counter() * 1000.0
        state = self._simulator.state
        entry = TurnLogEntry(
            turn=state.turn,
            position_before=state.agent_pos.to_label(),
        )

        # 1. Planning context (includes pathfinder)
        pathfinder_start = time.perf_counter() * 1000.0
        context = self._adapter.plan(state)
        entry.pathfinder_ms = time.perf_counter() * 1000.0 - pathfinder_start

        # 2. Bridge request cycle
        bridge_result = self._bridge.request_action(state, context)
        entry.bridge_processing_ms = bridge_result.bridge_processing_ms
        entry.provider_requested = bridge_result.provider_requested
        entry.provider_used = bridge_result.provider_used
        entry.raw_action_summary = bridge_result.raw_action_summary
        entry.parsed_action = (
            bridge_result.parse_result.action.value
            if bridge_result.parse_result and bridge_result.parse_result.action
            else None
        )
        entry.final_action = bridge_result.action.value
        entry.fallback_used = bridge_result.fallback_used
        entry.fallback_reason = bridge_result.fallback_reason

        # 3. Apply action to simulator
        action_result = self._simulator.apply_action(
            bridge_result.action,
            fallback_used=bridge_result.fallback_used,
        )

        # 4. Record outcomes
        entry.position_after = state.agent_pos.to_label()
        entry.score = state.score
        entry.health = state.health

        # Determine status
        if self._simulator.is_finished and self._simulator.metrics.goal_reached:
            entry.status = "goal_reached"
        elif self._simulator.is_finished and state.health <= 0:
            entry.status = "dead"
        elif not action_result.success:
            entry.status = "blocked"
        elif action_result.damage_taken > 0:
            entry.status = "damaged"
        elif action_result.items_collected:
            entry.status = "collected"
        elif bridge_result.fallback_used:
            entry.status = "fallback"
        else:
            entry.status = "ok"

        entry.turn_processing_ms = time.perf_counter() * 1000.0 - turn_start
        self._turn_log.append(entry)
        return entry

    # =========================================================================
    # Full Episode
    # =========================================================================

    def run_episode(self) -> EpisodeResult:
        """Run a complete game episode until termination.

        Termination conditions:
        - Goal reached
        - Agent dead (health <= 0)
        - Max turns exceeded
        - Game already finished

        Returns:
            EpisodeResult with full metrics and turn log
        """
        self._turn_log = []

        while not self._simulator.is_finished:
            if self._simulator.state.turn >= self._config.max_turns:
                break
            self.execute_turn()

        # Determine termination reason
        if self._simulator.metrics.goal_reached:
            reason = "goal_reached"
        elif self._simulator.state.health <= 0:
            reason = "agent_dead"
        elif self._simulator.state.turn >= self._config.max_turns:
            reason = "max_turns_exceeded"
        else:
            reason = "unknown"

        # Compute totals
        total_pathfinder = sum(t.pathfinder_ms for t in self._turn_log)
        total_bridge = sum(t.bridge_processing_ms for t in self._turn_log)
        total_turn = sum(t.turn_processing_ms for t in self._turn_log)

        return EpisodeResult(
            metrics=self._simulator.get_metrics(),
            turn_log=self._turn_log,
            config=self._config,
            termination_reason=reason,
            total_pathfinder_ms=total_pathfinder,
            total_bridge_ms=total_bridge,
            total_turn_ms=total_turn,
        )

"""
SPATHODEA R4 FASTLAB — Game Agent Adapter (Phase 2F)
Converts game state + navigation prompt + strategy into structured planning
context and a recommended next action.

Future topology:
    GAME → GameAgentAdapter → BUZZ → provider → normalized action → GAME

Current (Phase 2F Part 1):
    GAME → GameAgentAdapter → deterministic pathfinding → recommended action
    (No BUZZ connection yet)
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone

from .game_state import GameState, Position
from .action_schema import Action, ActionResult
from .strategy import Strategy, StrategyProfile
from .pathfinder import Pathfinder, PathResult, CostConfig


# =============================================================================
# Planning Context
# =============================================================================

@dataclass
class PlanningContext:
    """Structured planning context built from game state + strategy.

    This is the intermediate representation that would be sent to BUZZ
    in future phases. Currently used for local deterministic planning.

    Attributes:
        game_state_summary: Compact text summary of current state
        objective: What the agent is trying to achieve
        strategy_profile: Active strategy name
        path_to_goal: Planned path result
        available_rewards: Reachable uncollected rewards
        threats: Known dangerous positions
        recommended_action: The action to take
        reasoning: Human-readable explanation of the decision
        navigation_prompt: Optional external guidance (untrusted)
        confidence: 0.0–1.0 confidence in recommended action
    """
    game_state_summary: str = ""
    objective: str = ""
    strategy_profile: str = ""
    path_to_goal: Optional[PathResult] = None
    available_rewards: list = field(default_factory=list)
    threats: list = field(default_factory=list)
    recommended_action: Optional[Action] = None
    reasoning: str = ""
    navigation_prompt: Optional[str] = None
    confidence: float = 1.0

    def to_dict(self) -> dict:
        """Serialize to dict for logging/transport."""
        return {
            "game_state_summary": self.game_state_summary,
            "objective": self.objective,
            "strategy_profile": self.strategy_profile,
            "path_to_goal": self.path_to_goal.to_dict() if self.path_to_goal else None,
            "available_rewards": self.available_rewards,
            "threats": self.threats,
            "recommended_action": self.recommended_action.value if self.recommended_action else None,
            "reasoning": self.reasoning,
            "navigation_prompt": self.navigation_prompt,
            "confidence": self.confidence,
        }


# =============================================================================
# Combat Log Entry
# =============================================================================

@dataclass
class CombatLogEntry:
    """Structured log entry for a single turn decision.

    No secrets or prompts stored — only observable game facts.

    Attributes:
        turn: Turn number
        agent_position: Position label at decision time
        chosen_action: Action taken
        strategy: Strategy profile used
        reason: Why this action was chosen
        known_rewards: Number of visible uncollected rewards
        known_hazards: Number of visible hazards/enemies
        path_length: Remaining steps to goal (or -1 if unreachable)
        status: Turn outcome (ok, damaged, collected, blocked, goal_reached)
    """
    turn: int
    agent_position: str
    chosen_action: str
    strategy: str
    reason: str
    known_rewards: int
    known_hazards: int
    path_length: int
    status: str

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "turn": self.turn,
            "agent_position": self.agent_position,
            "chosen_action": self.chosen_action,
            "strategy": self.strategy,
            "reason": self.reason,
            "known_rewards": self.known_rewards,
            "known_hazards": self.known_hazards,
            "path_length": self.path_length,
            "status": self.status,
        }


# =============================================================================
# Game Agent Adapter
# =============================================================================

class GameAgentAdapter:
    """Adapter that converts game state + strategy into recommended actions.

    Currently operates in fully deterministic offline mode.
    Future integration will route through BUZZ for LLM-assisted decisions.

    Usage:
        adapter = GameAgentAdapter(strategy_profile="adaptive")
        context = adapter.plan(game_state)
        action = context.recommended_action
    """

    def __init__(
        self,
        strategy_profile: str = "adaptive",
        navigation_prompt: Optional[str] = None,
    ):
        """Initialize the game agent adapter.

        Args:
            strategy_profile: Strategy profile name (safe/speedrun/reward_max/adaptive)
            navigation_prompt: Optional external navigation guidance (untrusted)
        """
        self._strategy = Strategy.from_profile(StrategyProfile(strategy_profile))
        self._navigation_prompt = navigation_prompt
        self._pathfinder = Pathfinder(CostConfig.from_strategy(self._strategy))
        self._combat_log: list[CombatLogEntry] = []

    @property
    def strategy(self) -> Strategy:
        return self._strategy

    @property
    def combat_log(self) -> list[CombatLogEntry]:
        return self._combat_log

    def set_strategy(self, profile: str):
        """Change strategy profile."""
        self._strategy = Strategy.from_profile(StrategyProfile(profile))
        self._pathfinder.cost_config = CostConfig.from_strategy(self._strategy)

    def set_navigation_prompt(self, prompt: Optional[str]):
        """Set external navigation prompt (untrusted guidance)."""
        self._navigation_prompt = prompt

    # =========================================================================
    # Main Planning Method
    # =========================================================================

    def plan(self, state: GameState) -> PlanningContext:
        """Produce a planning context with recommended action.

        This is the primary entry point. Analyzes the game state,
        applies strategy-based pathfinding, and recommends the next action.

        The navigation_prompt is treated as advisory context only.
        Game state always overrides contradictory prompt claims.

        Args:
            state: Current game state

        Returns:
            PlanningContext with recommended_action set
        """
        ctx = PlanningContext()
        ctx.navigation_prompt = self._navigation_prompt
        ctx.strategy_profile = self._strategy.profile.value

        # Build state summary
        ctx.game_state_summary = self._summarize_state(state)

        # Identify threats
        ctx.threats = [p.to_label() for p in (state.enemies | state.hazards)]

        # Identify available rewards
        ctx.available_rewards = [p.to_label() for p in state.get_available_rewards()]

        # Determine objective and path
        objective, path, action, reasoning, confidence = self._decide(state)
        ctx.objective = objective
        ctx.path_to_goal = path
        ctx.recommended_action = action
        ctx.reasoning = reasoning
        ctx.confidence = confidence

        # Log the decision
        self._log_decision(state, action, reasoning)

        return ctx

    # =========================================================================
    # Decision Logic
    # =========================================================================

    def _decide(self, state: GameState) -> tuple[str, Optional[PathResult], Action, str, float]:
        """Core decision logic: determine objective, path, and action.

        Returns:
            (objective, path_result, action, reasoning, confidence)
        """
        # If no goal defined, WAIT
        if state.goal is None:
            return ("No goal defined", None, Action.WAIT, "No goal position set; waiting", 0.5)

        # If already at goal
        if state.agent_pos == state.goal:
            return ("Goal reached", None, Action.WAIT, "Already at goal position", 1.0)

        # Check if goal is reachable at all (basic BFS reachability)
        # For doors: check if we need to get keys first
        path_to_goal = self._pathfinder.find_path(state, state.agent_pos, state.goal, self._strategy)

        # Strategy-specific behavior
        if self._strategy.profile == StrategyProfile.SPEEDRUN:
            return self._decide_speedrun(state, path_to_goal)
        elif self._strategy.profile == StrategyProfile.SAFE:
            return self._decide_safe(state, path_to_goal)
        elif self._strategy.profile == StrategyProfile.REWARD_MAX:
            return self._decide_reward_max(state, path_to_goal)
        else:  # ADAPTIVE
            return self._decide_adaptive(state, path_to_goal)

    def _decide_speedrun(self, state: GameState, path_to_goal: PathResult):
        """Speedrun: shortest path to goal, ignore rewards/hazards cost."""
        if not path_to_goal.found:
            # Try to find a key if doors block the way
            return self._handle_blocked_path(state, "speedrun to goal")

        action = self._next_action_on_path(state, path_to_goal)
        return (
            "Reach goal via shortest path",
            path_to_goal,
            action,
            f"Speedrun: following shortest path ({path_to_goal.length} steps)",
            1.0,
        )

    def _decide_safe(self, state: GameState, path_to_goal: PathResult):
        """Safe: minimize hazard/enemy exposure."""
        if not path_to_goal.found:
            return self._handle_blocked_path(state, "safe route to goal")

        # Check if next step is dangerous
        action = self._next_action_on_path(state, path_to_goal)
        next_pos = action.apply(state.agent_pos)

        if state.is_dangerous(next_pos):
            # Try to find alternative
            alt_action = self._find_safe_alternative(state, path_to_goal)
            if alt_action:
                return (
                    "Reach goal avoiding dangers",
                    path_to_goal,
                    alt_action,
                    "Safe: avoiding dangerous cell on planned path",
                    0.8,
                )

        return (
            "Reach goal avoiding dangers",
            path_to_goal,
            action,
            f"Safe: following weighted-safe path ({path_to_goal.length} steps)",
            0.9,
        )

    def _decide_reward_max(self, state: GameState, path_to_goal: PathResult):
        """Reward max: collect as many rewards as possible while still reaching goal."""
        if not path_to_goal.found:
            return self._handle_blocked_path(state, "reward collection")

        # Check if there are uncollected rewards worth detouring for
        available = state.get_available_rewards()
        if available and self._strategy.collect_rewards:
            best_reward = self._find_best_reward_detour(state, available, path_to_goal)
            if best_reward:
                reward_path, reward_pos = best_reward
                action = self._next_action_on_path(state, reward_path)
                return (
                    f"Collect reward at {reward_pos.to_label()} then reach goal",
                    reward_path,
                    action,
                    f"Reward-max: detouring to collect reward at {reward_pos.to_label()}",
                    0.85,
                )

        # No worthwhile detours, go to goal
        action = self._next_action_on_path(state, path_to_goal)
        return (
            "Reach goal (no worthwhile rewards nearby)",
            path_to_goal,
            action,
            f"Reward-max: proceeding to goal ({path_to_goal.length} steps remaining)",
            0.9,
        )

    def _decide_adaptive(self, state: GameState, path_to_goal: PathResult):
        """Adaptive: balance reward, risk, and distance."""
        if not path_to_goal.found:
            return self._handle_blocked_path(state, "adaptive navigation")

        available_rewards = state.get_available_rewards()

        # If low health, switch to safe behavior
        if state.health <= 30:
            action = self._next_action_on_path(state, path_to_goal)
            return (
                "Reach goal (low health — conservative)",
                path_to_goal,
                action,
                f"Adaptive: low health ({state.health}), prioritizing goal",
                0.9,
            )

        # If rewards available and health is good, consider detour
        if available_rewards and state.health > 50:
            best_reward = self._find_best_reward_detour(state, available_rewards, path_to_goal)
            if best_reward:
                reward_path, reward_pos = best_reward
                action = self._next_action_on_path(state, reward_path)
                return (
                    f"Collect reward at {reward_pos.to_label()} (adaptive balance)",
                    reward_path,
                    action,
                    f"Adaptive: balanced detour to {reward_pos.to_label()} (health={state.health})",
                    0.8,
                )

        # Default: follow weighted path to goal
        action = self._next_action_on_path(state, path_to_goal)
        return (
            "Reach goal (balanced approach)",
            path_to_goal,
            action,
            f"Adaptive: following balanced path ({path_to_goal.length} steps)",
            0.85,
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _handle_blocked_path(self, state: GameState, context: str):
        """Handle when no path to goal exists."""
        # Check if we need a key
        available_keys = state.get_available_keys()
        if available_keys:
            for key_pos in available_keys:
                key_path = self._pathfinder.find_path(state, state.agent_pos, key_pos, self._strategy)
                if key_path.found:
                    action = self._next_action_on_path(state, key_path)
                    return (
                        f"Collect key at {key_pos.to_label()} to unlock path",
                        key_path,
                        action,
                        f"Path blocked: seeking key at {key_pos.to_label()}",
                        0.7,
                    )

        # Truly unreachable
        return (
            "Goal unreachable",
            None,
            Action.WAIT,
            f"No path to goal found ({context}); no keys available",
            0.1,
        )

    def _next_action_on_path(self, state: GameState, path: PathResult) -> Action:
        """Get the next action to take based on a path.

        Returns the action that moves from current position toward next waypoint.
        """
        if not path.found or path.length == 0:
            return Action.WAIT

        # Find agent's position in path and get next step
        agent_pos = state.agent_pos
        for i, pos in enumerate(path.path):
            if pos == agent_pos and i + 1 < len(path.path):
                next_pos = path.path[i + 1]
                action = Action.from_positions(agent_pos, next_pos)
                return action if action else Action.WAIT

        # Agent not on path — use first step
        if len(path.path) >= 2:
            next_pos = path.path[1]
            action = Action.from_positions(agent_pos, next_pos)
            return action if action else Action.WAIT

        return Action.WAIT

    def _find_safe_alternative(self, state: GameState, path: PathResult) -> Optional[Action]:
        """Find a non-dangerous alternative to the next step on path."""
        agent_pos = state.agent_pos
        walkable = state.get_walkable_neighbors(agent_pos)
        safe_neighbors = [n for n in walkable if not state.is_dangerous(n)]

        if not safe_neighbors:
            return None

        # Pick the safe neighbor closest to goal
        if state.goal:
            safe_neighbors.sort(key=lambda n: n.manhattan_distance(state.goal))
            best = safe_neighbors[0]
            return Action.from_positions(agent_pos, best)

        return None

    def _find_best_reward_detour(
        self,
        state: GameState,
        rewards: set,
        direct_path: PathResult,
    ) -> Optional[tuple[PathResult, Position]]:
        """Find the best reward to detour for.

        Returns (path_to_reward, reward_position) or None if no worthwhile detour.
        """
        best = None
        best_score = float('-inf')

        for reward_pos in rewards:
            # Path to reward
            path_to_reward = self._pathfinder.find_path(
                state, state.agent_pos, reward_pos, self._strategy
            )
            if not path_to_reward.found:
                continue

            # Path from reward to goal
            path_reward_to_goal = self._pathfinder.find_path(
                state, reward_pos, state.goal, self._strategy
            )
            if not path_reward_to_goal.found:
                continue

            total_detour = path_to_reward.length + path_reward_to_goal.length
            extra_steps = total_detour - direct_path.length

            # Check if detour is acceptable
            if not self._strategy.should_collect_reward(extra_steps, direct_path.length):
                continue

            # Score: prefer closer rewards with less detour
            score = -extra_steps  # Lower detour = higher score
            if score > best_score:
                best_score = score
                best = (path_to_reward, reward_pos)

        return best

    def _summarize_state(self, state: GameState) -> str:
        """Build compact text summary of game state."""
        parts = [
            f"Grid: {state.width}x{state.height}",
            f"Agent: {state.agent_pos.to_label()}",
            f"Goal: {state.goal.to_label() if state.goal else 'None'}",
            f"Turn: {state.turn}",
            f"Health: {state.health}",
            f"Score: {state.score}",
            f"Keys held: {len(state.collected_keys)}",
            f"Coins: {len(state.collected_coins)}/{len(state.coins)}",
            f"Threats: {len(state.enemies)} enemies, {len(state.hazards)} hazards",
            f"Walls: {len(state.walls)}",
        ]
        return " | ".join(parts)

    def _log_decision(self, state: GameState, action: Action, reason: str):
        """Record decision in combat log."""
        path_to_goal = None
        path_length = -1
        if state.goal:
            result = self._pathfinder.bfs(state, state.agent_pos, state.goal)
            path_length = result.length if result.found else -1

        entry = CombatLogEntry(
            turn=state.turn,
            agent_position=state.agent_pos.to_label(),
            chosen_action=action.value,
            strategy=self._strategy.profile.value,
            reason=reason,
            known_rewards=len(state.get_available_rewards()),
            known_hazards=len(state.enemies) + len(state.hazards),
            path_length=path_length,
            status="ok",
        )
        self._combat_log.append(entry)

    # =========================================================================
    # BUZZ Integration Stub (future)
    # =========================================================================

    def plan_with_buzz(self, state: GameState) -> PlanningContext:
        """Future: Route planning through BUZZ gateway for LLM-assisted decisions.

        NOT IMPLEMENTED in Phase 2F Part 1.
        Will send PlanningContext to BUZZ and receive enhanced action recommendation.

        Raises:
            NotImplementedError: Always (Phase 2F Part 1)
        """
        raise NotImplementedError(
            "BUZZ integration not available in Phase 2F Part 1. "
            "Use plan() for deterministic offline planning."
        )

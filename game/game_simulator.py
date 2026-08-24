"""
SPATHODEA R4 FASTLAB — Game Simulator (Phase 2F Part 2)
Deterministic offline simulator for POLYCC grid-navigation game.

Simulates game episodes by applying actions to game state,
tracking scores, collection, hazard contacts, and goal completion.

No network calls. No LLM. Fully deterministic given same inputs.
"""

import copy
from dataclasses import dataclass, field
from typing import Optional

from .game_state import GameState, Position
from .action_schema import Action, ActionResult


# =============================================================================
# Simulation Metrics
# =============================================================================

@dataclass
class SimulationMetrics:
    """Aggregate metrics for a simulated game episode.

    Attributes:
        total_turns: Number of turns executed
        goal_reached: Whether the agent reached the goal
        final_position: Agent position at end of episode
        coins_collected: Number of coins collected
        keys_collected: Number of keys collected
        hazard_contacts: Number of times agent stepped on hazard
        enemy_contacts: Number of times agent stepped on enemy
        invalid_actions: Number of actions that were blocked by safety gate
        fallback_count: Number of times fallback was used
        final_score: Score at end of episode
        final_health: Health at end of episode
        doors_opened: Number of doors opened
        turns_waited: Number of WAIT actions taken
    """
    total_turns: int = 0
    goal_reached: bool = False
    final_position: str = ""
    coins_collected: int = 0
    keys_collected: int = 0
    hazard_contacts: int = 0
    enemy_contacts: int = 0
    invalid_actions: int = 0
    fallback_count: int = 0
    final_score: int = 0
    final_health: int = 100
    doors_opened: int = 0
    turns_waited: int = 0

    def to_dict(self) -> dict:
        return {
            "total_turns": self.total_turns,
            "goal_reached": self.goal_reached,
            "final_position": self.final_position,
            "coins_collected": self.coins_collected,
            "keys_collected": self.keys_collected,
            "hazard_contacts": self.hazard_contacts,
            "enemy_contacts": self.enemy_contacts,
            "invalid_actions": self.invalid_actions,
            "fallback_count": self.fallback_count,
            "final_score": self.final_score,
            "final_health": self.final_health,
            "doors_opened": self.doors_opened,
            "turns_waited": self.turns_waited,
        }


# =============================================================================
# Simulation Configuration
# =============================================================================

@dataclass
class SimConfig:
    """Configuration for the game simulator.

    Attributes:
        coin_reward: Score gained per coin collected
        key_reward: Score gained per key collected
        goal_reward: Score gained for reaching goal
        hazard_damage: Health lost per hazard contact
        enemy_damage: Health lost per enemy contact
        turn_penalty: Score penalty per turn (encourages speed)
        step_reward: Score per step taken (0 = no step reward)
    """
    coin_reward: int = 10
    key_reward: int = 5
    goal_reward: int = 100
    hazard_damage: int = 20
    enemy_damage: int = 30
    turn_penalty: int = 0
    step_reward: int = 0

    def to_dict(self) -> dict:
        return {
            "coin_reward": self.coin_reward,
            "key_reward": self.key_reward,
            "goal_reward": self.goal_reward,
            "hazard_damage": self.hazard_damage,
            "enemy_damage": self.enemy_damage,
            "turn_penalty": self.turn_penalty,
            "step_reward": self.step_reward,
        }


# =============================================================================
# Game Simulator
# =============================================================================

class GameSimulator:
    """Deterministic offline game simulator.

    Applies actions to game state and tracks outcomes.
    Does NOT decide actions — that's the adapter/bridge/controller's job.

    Usage:
        sim = GameSimulator(initial_state)
        result = sim.apply_action(Action.RIGHT)
        metrics = sim.get_metrics()
    """

    def __init__(self, initial_state: GameState, config: Optional[SimConfig] = None):
        """Initialize simulator with a starting game state.

        Args:
            initial_state: Starting game state (deep-copied internally)
            config: Simulation configuration
        """
        self._state = copy.deepcopy(initial_state)
        self._config = config or SimConfig()
        self._metrics = SimulationMetrics(
            final_position=self._state.agent_pos.to_label(),
            final_health=self._state.health,
            final_score=self._state.score,
        )
        self._history: list[ActionResult] = []
        self._finished = False

    @property
    def state(self) -> GameState:
        """Current game state (live reference)."""
        return self._state

    @property
    def metrics(self) -> SimulationMetrics:
        """Current simulation metrics."""
        return self._metrics

    @property
    def history(self) -> list[ActionResult]:
        """Action history (all results)."""
        return self._history

    @property
    def is_finished(self) -> bool:
        """Whether the simulation is complete (goal reached or agent dead)."""
        return self._finished

    def apply_action(self, action: Action, fallback_used: bool = False) -> ActionResult:
        """Apply an action to the current game state.

        Handles:
        - Movement validation
        - Coin collection
        - Key collection
        - Door opening
        - Hazard damage
        - Enemy damage
        - Goal detection
        - Turn advancement

        Args:
            action: Action to apply
            fallback_used: Whether this was a fallback action (for metrics)

        Returns:
            ActionResult describing what happened
        """
        if self._finished:
            return ActionResult(
                action=action,
                success=False,
                new_position=self._state.agent_pos,
                reason="Game already finished",
            )

        # Track fallback
        if fallback_used:
            self._metrics.fallback_count += 1

        # Track WAIT
        if action == Action.WAIT:
            self._metrics.turns_waited += 1
            self._state.turn += 1
            self._metrics.total_turns += 1
            self._apply_turn_penalty()
            result = ActionResult(
                action=action,
                success=True,
                new_position=self._state.agent_pos,
                reason="Agent waited",
            )
            self._history.append(result)
            self._update_final_metrics()
            return result

        # Compute target
        target = action.apply(self._state.agent_pos)

        # Validate movement
        if not self._state.is_valid_position(target):
            self._metrics.invalid_actions += 1
            self._state.turn += 1
            self._metrics.total_turns += 1
            result = ActionResult(
                action=action,
                success=False,
                new_position=self._state.agent_pos,
                reason=f"Out of bounds: {target.to_label()}",
            )
            self._history.append(result)
            self._update_final_metrics()
            return result

        if target in self._state.walls:
            self._metrics.invalid_actions += 1
            self._state.turn += 1
            self._metrics.total_turns += 1
            result = ActionResult(
                action=action,
                success=False,
                new_position=self._state.agent_pos,
                reason=f"Wall collision at {target.to_label()}",
            )
            self._history.append(result)
            self._update_final_metrics()
            return result

        if target in self._state.doors and not self._state._can_open_door(target):
            self._metrics.invalid_actions += 1
            self._state.turn += 1
            self._metrics.total_turns += 1
            result = ActionResult(
                action=action,
                success=False,
                new_position=self._state.agent_pos,
                reason=f"Locked door at {target.to_label()}",
            )
            self._history.append(result)
            self._update_final_metrics()
            return result

        # Move agent
        self._state.agent_pos = target
        reward = 0
        damage = 0
        items = []
        door_opened = None
        status_parts = []

        # Door opening
        if target in self._state.doors:
            self._metrics.doors_opened += 1
            door_opened = target
            status_parts.append(f"opened door at {target.to_label()}")

        # Key collection
        if target in self._state.keys and target not in self._state.collected_keys:
            self._state.collected_keys.add(target)
            self._metrics.keys_collected += 1
            reward += self._config.key_reward
            items.append(f"key@{target.to_label()}")
            status_parts.append(f"collected key")

        # Coin collection
        if target in self._state.coins and target not in self._state.collected_coins:
            self._state.collected_coins.add(target)
            self._metrics.coins_collected += 1
            reward += self._config.coin_reward
            items.append(f"coin@{target.to_label()}")
            status_parts.append(f"collected coin (+{self._config.coin_reward})")

        # Hazard contact
        if target in self._state.hazards:
            self._metrics.hazard_contacts += 1
            damage += self._config.hazard_damage
            status_parts.append(f"hazard damage (-{self._config.hazard_damage}hp)")

        # Enemy contact
        if target in self._state.enemies:
            self._metrics.enemy_contacts += 1
            damage += self._config.enemy_damage
            status_parts.append(f"enemy damage (-{self._config.enemy_damage}hp)")

        # Step reward
        reward += self._config.step_reward

        # Apply score and health changes
        self._state.score += reward
        self._state.health = max(0, self._state.health - damage)

        # Check goal
        if target == self._state.goal:
            self._state.score += self._config.goal_reward
            self._finished = True
            self._metrics.goal_reached = True
            status_parts.append("GOAL REACHED!")

        # Check death
        if self._state.health <= 0:
            self._finished = True
            status_parts.append("AGENT DIED")

        # Advance turn
        self._state.turn += 1
        self._metrics.total_turns += 1
        self._apply_turn_penalty()

        reason = "; ".join(status_parts) if status_parts else f"Moved to {target.to_label()}"

        result = ActionResult(
            action=action,
            success=True,
            new_position=target,
            reason=reason,
            reward_gained=reward,
            damage_taken=damage,
            items_collected=items,
            door_opened=door_opened,
        )
        self._history.append(result)
        self._update_final_metrics()
        return result

    def _apply_turn_penalty(self):
        """Apply per-turn score penalty."""
        if self._config.turn_penalty > 0:
            self._state.score -= self._config.turn_penalty

    def _update_final_metrics(self):
        """Update final metrics snapshot."""
        self._metrics.final_position = self._state.agent_pos.to_label()
        self._metrics.final_score = self._state.score
        self._metrics.final_health = self._state.health

    def get_metrics(self) -> SimulationMetrics:
        """Get current simulation metrics."""
        return self._metrics

    def reset(self, new_state: Optional[GameState] = None):
        """Reset simulation with optional new state."""
        if new_state:
            self._state = copy.deepcopy(new_state)
        self._metrics = SimulationMetrics(
            final_position=self._state.agent_pos.to_label(),
            final_health=self._state.health,
            final_score=self._state.score,
        )
        self._history = []
        self._finished = False

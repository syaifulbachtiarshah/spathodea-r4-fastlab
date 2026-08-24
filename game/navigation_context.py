"""
SPATHODEA R4 FASTLAB — Navigation Context Builder (Phase 2F Part 3C)
Builds deterministic navigation context from GameState.

Provides:
- Legal/blocked action computation
- Goal direction analysis
- Oscillation tracking
- Reward/hazard/enemy awareness
"""

from dataclasses import dataclass, field
from typing import Optional

from .game_state import GameState, Position
from .action_schema import Action
from .strategy import Strategy, StrategyProfile


# =============================================================================
# Navigation Context
# =============================================================================

@dataclass
class NavigationContext:
    """Deterministic navigation context for grounded prompt construction.

    All fields are computed from observable GameState only.
    No hidden information. No secrets.
    """
    current_position: str
    goal: Optional[str]
    grid_width: int
    grid_height: int
    health: int
    turn: int
    strategy: str

    legal_actions: list[str]
    blocked_actions: dict[str, str]  # action -> reason

    goal_direction_horizontal: str  # LEFT / RIGHT / SAME
    goal_direction_vertical: str    # UP / DOWN / SAME

    known_rewards: list[str]
    known_hazards: list[str]
    known_enemies: list[str]

    recent_positions: list[str]
    recent_actions: list[str]

    def to_dict(self) -> dict:
        return {
            "current_position": self.current_position,
            "goal": self.goal,
            "grid_width": self.grid_width,
            "grid_height": self.grid_height,
            "health": self.health,
            "turn": self.turn,
            "strategy": self.strategy,
            "legal_actions": self.legal_actions,
            "blocked_actions": self.blocked_actions,
            "goal_direction_horizontal": self.goal_direction_horizontal,
            "goal_direction_vertical": self.goal_direction_vertical,
            "known_rewards": self.known_rewards,
            "known_hazards": self.known_hazards,
            "known_enemies": self.known_enemies,
            "recent_positions": self.recent_positions,
            "recent_actions": self.recent_actions,
        }


# =============================================================================
# Navigation Context Builder
# =============================================================================

class NavigationContextBuilder:
    """Builds NavigationContext from GameState.

    Usage:
        builder = NavigationContextBuilder()
        context = builder.build(state, strategy, recent_positions, recent_actions)
    """

    def __init__(self, max_history: int = 3):
        self._max_history = max_history

    def build(
        self,
        state: GameState,
        strategy: str = "exploration",
        recent_positions: Optional[list[str]] = None,
        recent_actions: Optional[list[str]] = None,
    ) -> NavigationContext:
        """Build navigation context from current game state.

        Args:
            state: Current game state
            strategy: Current strategy profile name
            recent_positions: Previous positions (most recent last)
            recent_actions: Previous actions (most recent last)

        Returns:
            NavigationContext with all computed fields
        """
        pos = state.agent_pos
        goal = state.goal

        legal, blocked = self._compute_actions(state)
        h_dir, v_dir = self._goal_direction(pos, goal)

        recent_pos = (recent_positions or [])[-self._max_history:]
        recent_act = (recent_actions or [])[-self._max_history:]

        return NavigationContext(
            current_position=pos.to_label(),
            goal=goal.to_label() if goal else None,
            grid_width=state.width,
            grid_height=state.height,
            health=state.health,
            turn=state.turn,
            strategy=strategy,
            legal_actions=legal,
            blocked_actions=blocked,
            goal_direction_horizontal=h_dir,
            goal_direction_vertical=v_dir,
            known_rewards=sorted(p.to_label() for p in state.get_available_rewards()),
            known_hazards=sorted(p.to_label() for p in state.hazards),
            known_enemies=sorted(p.to_label() for p in state.enemies),
            recent_positions=recent_pos,
            recent_actions=recent_act,
        )

    def _compute_actions(self, state: GameState) -> tuple[list[str], dict[str, str]]:
        """Compute legal and blocked actions from state."""
        legal = []
        blocked = {}
        pos = state.agent_pos

        for action in Action:
            if action == Action.WAIT:
                legal.append(action.value)
                continue

            target = action.apply(pos)

            if not state.is_valid_position(target):
                blocked[action.value] = "OUT_OF_BOUNDS"
            elif target in state.walls:
                blocked[action.value] = "WALL"
            elif target in state.doors and not state._can_open_door(target):
                blocked[action.value] = "LOCKED_DOOR"
            else:
                legal.append(action.value)

        return legal, blocked

    def _goal_direction(
        self, pos: Position, goal: Optional[Position]
    ) -> tuple[str, str]:
        """Compute horizontal and vertical direction to goal."""
        if goal is None:
            return ("UNKNOWN", "UNKNOWN")

        dc = goal.col - pos.col
        dr = goal.row - pos.row

        if dc > 0:
            h = "RIGHT"
        elif dc < 0:
            h = "LEFT"
        else:
            h = "SAME"

        if dr > 0:
            v = "DOWN"
        elif dr < 0:
            v = "UP"
        else:
            v = "SAME"

        return (h, v)

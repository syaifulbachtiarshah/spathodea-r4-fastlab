"""
SPATHODEA R4 FASTLAB — Action Schema (Phase 2F)
Normalized action definitions for POLYCC grid-navigation game.

Actions are adapter-based: the schema defines canonical actions
that get translated to the real competition API format when connected.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .game_state import Position


# =============================================================================
# Action Enum
# =============================================================================

class Action(str, Enum):
    """Normalized movement actions for grid navigation."""
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    WAIT = "WAIT"

    def delta(self) -> tuple[int, int]:
        """Return (dcol, drow) for this action. WAIT returns (0, 0)."""
        return _ACTION_DELTAS[self]

    def apply(self, pos: Position) -> Position:
        """Apply this action to a position, returning the new position."""
        dc, dr = self.delta()
        return Position(pos.col + dc, pos.row + dr)

    @classmethod
    def from_positions(cls, current: Position, target: Position) -> Optional["Action"]:
        """Determine which single action moves from current to target.

        Returns None if target is not a direct neighbor or is same position.
        """
        dc = target.col - current.col
        dr = target.row - current.row
        for action, (adc, adr) in _ACTION_DELTAS.items():
            if dc == adc and dr == adr and action != cls.WAIT:
                return action
        return None


# Action-to-delta mapping
_ACTION_DELTAS = {
    Action.UP: (0, -1),
    Action.DOWN: (0, 1),
    Action.LEFT: (-1, 0),
    Action.RIGHT: (1, 0),
    Action.WAIT: (0, 0),
}

# Valid core actions
VALID_ACTIONS = tuple(Action)


# =============================================================================
# Future Actions (not yet active)
# =============================================================================

class FutureAction(str, Enum):
    """Future action extensions — not active until competition API is confirmed."""
    INTERACT = "INTERACT"
    PICKUP = "PICKUP"
    ATTACK = "ATTACK"


FUTURE_ACTIONS = tuple(FutureAction)


# =============================================================================
# Action Result
# =============================================================================

@dataclass
class ActionResult:
    """Result of executing an action in the game.

    Attributes:
        action: The action that was executed
        success: Whether the action was valid and executed
        new_position: Agent position after action
        reason: Human-readable explanation
        reward_gained: Points gained this turn
        damage_taken: Health lost this turn
        items_collected: Labels of items collected (keys, coins)
        door_opened: Door position opened (if any)
    """
    action: Action
    success: bool
    new_position: Position
    reason: str = ""
    reward_gained: int = 0
    damage_taken: int = 0
    items_collected: list = field(default_factory=list)
    door_opened: Optional[Position] = None

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "action": self.action.value,
            "success": self.success,
            "new_position": self.new_position.to_label(),
            "reason": self.reason,
            "reward_gained": self.reward_gained,
            "damage_taken": self.damage_taken,
            "items_collected": self.items_collected,
            "door_opened": self.door_opened.to_label() if self.door_opened else None,
        }

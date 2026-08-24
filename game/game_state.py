"""
SPATHODEA R4 FASTLAB — Game State Representation (Phase 2F)
Grid game state for POLYCC navigation competition.

Coordinate system:
    Column = letter (A-Z), Row = number (1-based)
    Examples: A1, B3, J10

Internal representation:
    (col: int, row: int) — 0-indexed tuple
    A1 = (0, 0), B3 = (1, 2), J10 = (9, 9)
"""

from dataclasses import dataclass, field
from typing import Optional
import re


# =============================================================================
# Position
# =============================================================================

@dataclass(frozen=True)
class Position:
    """Immutable 2D grid position.

    Attributes:
        col: Column index (0-based, maps to letters A=0, B=1, ...)
        row: Row index (0-based, maps to numbers 1-based in display)
    """
    col: int
    row: int

    def to_label(self) -> str:
        """Convert to human-readable label like A1, B3, J10."""
        if self.col < 26:
            letter = chr(ord('A') + self.col)
        else:
            # Extended: AA, AB, etc. (unlikely for typical grids)
            letter = chr(ord('A') + self.col // 26 - 1) + chr(ord('A') + self.col % 26)
        return f"{letter}{self.row + 1}"

    @classmethod
    def from_label(cls, label: str) -> "Position":
        """Parse a label like A1, B3, J10 into a Position.

        Raises:
            ValueError: If the label format is invalid.
        """
        label = label.strip().upper()
        match = re.match(r'^([A-Z]{1,2})(\d+)$', label)
        if not match:
            raise ValueError(f"Invalid position label: '{label}'. Expected format: A1, B3, J10")
        letters, number = match.groups()
        if len(letters) == 1:
            col = ord(letters) - ord('A')
        else:
            col = (ord(letters[0]) - ord('A') + 1) * 26 + (ord(letters[1]) - ord('A'))
        row = int(number) - 1
        if row < 0:
            raise ValueError(f"Row number must be >= 1, got {number}")
        return cls(col=col, row=row)

    def manhattan_distance(self, other: "Position") -> int:
        """Calculate Manhattan distance to another position."""
        return abs(self.col - other.col) + abs(self.row - other.row)

    def neighbors(self) -> list["Position"]:
        """Return 4-directional neighbors (may include invalid positions)."""
        return [
            Position(self.col, self.row - 1),  # UP
            Position(self.col, self.row + 1),  # DOWN
            Position(self.col - 1, self.row),  # LEFT
            Position(self.col + 1, self.row),  # RIGHT
        ]

    def __repr__(self) -> str:
        return f"Position({self.to_label()})"


# =============================================================================
# Cell Types
# =============================================================================

class CellType:
    """Cell type constants for the grid."""
    EMPTY = "empty"
    WALL = "wall"
    KEY = "key"
    DOOR = "door"
    COIN = "coin"
    ENEMY = "enemy"
    HAZARD = "hazard"
    GOAL = "goal"
    UNKNOWN = "unknown"
    AGENT = "agent"


# =============================================================================
# Game State
# =============================================================================

@dataclass
class GameState:
    """Complete grid game state for POLYCC navigation.

    The grid is width x height. Positions are 0-indexed internally.
    Cell (0,0) is top-left corner (A1 in label notation).

    Attributes:
        width: Grid width (number of columns)
        height: Grid height (number of rows)
        agent_pos: Current agent position
        walls: Set of wall positions (impassable)
        keys: Set of key positions (collectible, unlock doors)
        doors: Dict mapping door position -> required key position (or None if any key)
        coins: Set of coin/reward positions (collectible)
        enemies: Set of enemy positions (dangerous)
        hazards: Set of hazard/trap positions (dangerous)
        goal: Goal/exit position (objective)
        unknown: Set of unexplored/fog positions
        collected_keys: Set of key positions already collected
        collected_coins: Set of coin positions already collected
        turn: Current turn number
        score: Current accumulated score
        health: Agent health points (100 = full)
    """

    width: int
    height: int
    agent_pos: Position
    walls: set = field(default_factory=set)
    keys: set = field(default_factory=set)
    doors: dict = field(default_factory=dict)
    coins: set = field(default_factory=set)
    enemies: set = field(default_factory=set)
    hazards: set = field(default_factory=set)
    goal: Optional[Position] = None
    unknown: set = field(default_factory=set)
    collected_keys: set = field(default_factory=set)
    collected_coins: set = field(default_factory=set)
    turn: int = 0
    score: int = 0
    health: int = 100

    def is_valid_position(self, pos: Position) -> bool:
        """Check if position is within grid bounds."""
        return 0 <= pos.col < self.width and 0 <= pos.row < self.height

    def is_walkable(self, pos: Position) -> bool:
        """Check if position can be moved to (within bounds, not a wall, not a locked door)."""
        if not self.is_valid_position(pos):
            return False
        if pos in self.walls:
            return False
        if pos in self.doors and not self._can_open_door(pos):
            return False
        return True

    def _can_open_door(self, door_pos: Position) -> bool:
        """Check if agent has a key to open the door at door_pos."""
        required_key = self.doors.get(door_pos)
        if required_key is None:
            # Door requires any key
            return len(self.collected_keys) > 0
        return required_key in self.collected_keys

    def is_dangerous(self, pos: Position) -> bool:
        """Check if position contains an enemy or hazard."""
        return pos in self.enemies or pos in self.hazards

    def is_reward(self, pos: Position) -> bool:
        """Check if position contains uncollected coin/reward."""
        return pos in self.coins and pos not in self.collected_coins

    def is_key(self, pos: Position) -> bool:
        """Check if position contains uncollected key."""
        return pos in self.keys and pos not in self.collected_keys

    def get_cell_type(self, pos: Position) -> str:
        """Get the primary cell type at a position."""
        if not self.is_valid_position(pos):
            return CellType.UNKNOWN
        if pos in self.unknown:
            return CellType.UNKNOWN
        if pos == self.agent_pos:
            return CellType.AGENT
        if pos in self.walls:
            return CellType.WALL
        if pos in self.doors:
            return CellType.DOOR
        if pos in self.enemies:
            return CellType.ENEMY
        if pos in self.hazards:
            return CellType.HAZARD
        if pos == self.goal:
            return CellType.GOAL
        if pos in self.keys and pos not in self.collected_keys:
            return CellType.KEY
        if pos in self.coins and pos not in self.collected_coins:
            return CellType.COIN
        return CellType.EMPTY

    def get_walkable_neighbors(self, pos: Position) -> list[Position]:
        """Get all walkable neighbors of a position."""
        return [n for n in pos.neighbors() if self.is_walkable(n)]

    def get_available_rewards(self) -> set:
        """Get positions of uncollected coins."""
        return self.coins - self.collected_coins

    def get_available_keys(self) -> set:
        """Get positions of uncollected keys."""
        return self.keys - self.collected_keys

    def get_locked_doors(self) -> set:
        """Get positions of doors that cannot currently be opened."""
        return {pos for pos in self.doors if not self._can_open_door(pos)}

    def validate(self) -> list[str]:
        """Return a list of validation errors (empty if valid state)."""
        errors = []
        if self.width < 1:
            errors.append(f"width must be >= 1, got {self.width}")
        if self.height < 1:
            errors.append(f"height must be >= 1, got {self.height}")
        if not self.is_valid_position(self.agent_pos):
            errors.append(f"agent_pos {self.agent_pos} is outside grid bounds")
        if self.agent_pos in self.walls:
            errors.append(f"agent_pos {self.agent_pos} is inside a wall")
        if self.goal and not self.is_valid_position(self.goal):
            errors.append(f"goal {self.goal} is outside grid bounds")
        if self.health < 0:
            errors.append(f"health cannot be negative, got {self.health}")
        return errors

    def to_dict(self) -> dict:
        """Serialize game state to dict for transport/logging."""
        return {
            "width": self.width,
            "height": self.height,
            "agent_pos": self.agent_pos.to_label(),
            "walls": sorted(p.to_label() for p in self.walls),
            "keys": sorted(p.to_label() for p in self.keys),
            "doors": {p.to_label(): (v.to_label() if v else None) for p, v in self.doors.items()},
            "coins": sorted(p.to_label() for p in self.coins),
            "enemies": sorted(p.to_label() for p in self.enemies),
            "hazards": sorted(p.to_label() for p in self.hazards),
            "goal": self.goal.to_label() if self.goal else None,
            "unknown": sorted(p.to_label() for p in self.unknown),
            "collected_keys": sorted(p.to_label() for p in self.collected_keys),
            "collected_coins": sorted(p.to_label() for p in self.collected_coins),
            "turn": self.turn,
            "score": self.score,
            "health": self.health,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameState":
        """Deserialize from dict."""
        def _pos_set(labels: list) -> set:
            return {Position.from_label(l) for l in (labels or [])}

        doors = {}
        for k, v in (data.get("doors") or {}).items():
            doors[Position.from_label(k)] = Position.from_label(v) if v else None

        return cls(
            width=data["width"],
            height=data["height"],
            agent_pos=Position.from_label(data["agent_pos"]),
            walls=_pos_set(data.get("walls")),
            keys=_pos_set(data.get("keys")),
            doors=doors,
            coins=_pos_set(data.get("coins")),
            enemies=_pos_set(data.get("enemies")),
            hazards=_pos_set(data.get("hazards")),
            goal=Position.from_label(data["goal"]) if data.get("goal") else None,
            unknown=_pos_set(data.get("unknown")),
            collected_keys=_pos_set(data.get("collected_keys")),
            collected_coins=_pos_set(data.get("collected_coins")),
            turn=data.get("turn", 0),
            score=data.get("score", 0),
            health=data.get("health", 100),
        )

    def __repr__(self) -> str:
        return (
            f"GameState({self.width}x{self.height}, agent={self.agent_pos.to_label()}, "
            f"goal={self.goal.to_label() if self.goal else 'None'}, turn={self.turn})"
        )

"""
SPATHODEA R4 FASTLAB — Pathfinder (Phase 2F)
Deterministic local pathfinding for POLYCC grid navigation.

Algorithms:
    BFS             — Unweighted shortest path
    A*              — Heuristic shortest path (Manhattan distance)
    Weighted A*     — Cost-aware path with configurable cell costs

No LLM required. Fully deterministic given the same inputs.
"""

import heapq
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from .game_state import GameState, Position
from .strategy import Strategy


# =============================================================================
# Cost Configuration
# =============================================================================

@dataclass
class CostConfig:
    """Configurable costs for weighted pathfinding.

    Attributes:
        movement: Base cost per step
        hazard: Cost for stepping on a hazard cell
        enemy: Cost for stepping on an enemy cell
        enemy_adjacent: Cost for cells adjacent to an enemy
        locked_door: Cost for a locked door (impassable adds this)
        reward: Cost adjustment for reward cells (negative = incentive)
        unknown: Cost for unknown/fog cells
    """
    movement: float = 1.0
    hazard: float = 10.0
    enemy: float = 50.0
    enemy_adjacent: float = 3.0
    locked_door: float = 100.0
    reward: float = 0.0
    unknown: float = 2.0

    @classmethod
    def from_strategy(cls, strategy: Strategy) -> "CostConfig":
        """Derive cost config from a Strategy."""
        return cls(
            movement=strategy.movement_cost,
            hazard=strategy.hazard_weight,
            enemy=strategy.enemy_weight * 5.0,  # enemies are very dangerous
            enemy_adjacent=strategy.enemy_weight,
            locked_door=strategy.door_weight,
            reward=strategy.reward_weight,
            unknown=2.0,
        )


# =============================================================================
# Path Result
# =============================================================================

@dataclass
class PathResult:
    """Result of a pathfinding operation.

    Attributes:
        path: Ordered list of positions from start to goal (inclusive)
        found: Whether a valid path was found
        cost: Total weighted cost of the path
        explored_count: Number of nodes explored during search
        algorithm: Algorithm used (bfs, astar, weighted_astar)
    """
    path: list = field(default_factory=list)
    found: bool = False
    cost: float = 0.0
    explored_count: int = 0
    algorithm: str = ""

    @property
    def length(self) -> int:
        """Number of steps in the path (positions - 1, or 0 if no path)."""
        return max(0, len(self.path) - 1)

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "path": [p.to_label() for p in self.path],
            "found": self.found,
            "cost": round(self.cost, 2),
            "length": self.length,
            "explored_count": self.explored_count,
            "algorithm": self.algorithm,
        }


# =============================================================================
# Pathfinder
# =============================================================================

class Pathfinder:
    """Deterministic pathfinder for grid-based navigation.

    Supports BFS (unweighted), A* (heuristic), and Weighted A* (cost-aware).
    All methods are stateless — they operate on the provided GameState.
    """

    def __init__(self, cost_config: Optional[CostConfig] = None):
        """Initialize pathfinder with optional cost configuration.

        Args:
            cost_config: Cost configuration for weighted searches.
                         If None, uses default costs.
        """
        self._cost_config = cost_config or CostConfig()

    @property
    def cost_config(self) -> CostConfig:
        return self._cost_config

    @cost_config.setter
    def cost_config(self, config: CostConfig):
        self._cost_config = config

    # =========================================================================
    # BFS — Unweighted Shortest Path
    # =========================================================================

    def bfs(self, state: GameState, start: Position, goal: Position) -> PathResult:
        """Find shortest unweighted path using Breadth-First Search.

        Only considers walkability (walls, locked doors).
        Does not account for hazards or enemies as costs.

        Args:
            state: Current game state
            start: Starting position
            goal: Target position

        Returns:
            PathResult with shortest path or empty if unreachable
        """
        if start == goal:
            return PathResult(path=[start], found=True, cost=0.0, explored_count=1, algorithm="bfs")

        if not state.is_valid_position(start) or not state.is_valid_position(goal):
            return PathResult(found=False, algorithm="bfs")

        queue = deque([(start, [start])])
        visited = {start}
        explored = 0

        while queue:
            current, path = queue.popleft()
            explored += 1

            for neighbor in current.neighbors():
                if neighbor in visited:
                    continue
                if not state.is_walkable(neighbor):
                    continue

                new_path = path + [neighbor]
                if neighbor == goal:
                    return PathResult(
                        path=new_path,
                        found=True,
                        cost=float(len(new_path) - 1),
                        explored_count=explored,
                        algorithm="bfs",
                    )

                visited.add(neighbor)
                queue.append((neighbor, new_path))

        return PathResult(found=False, explored_count=explored, algorithm="bfs")

    # =========================================================================
    # A* — Heuristic Shortest Path
    # =========================================================================

    def astar(self, state: GameState, start: Position, goal: Position) -> PathResult:
        """Find shortest path using A* with Manhattan distance heuristic.

        Only considers walkability. Uniform movement cost.

        Args:
            state: Current game state
            start: Starting position
            goal: Target position

        Returns:
            PathResult with optimal path or empty if unreachable
        """
        if start == goal:
            return PathResult(path=[start], found=True, cost=0.0, explored_count=1, algorithm="astar")

        if not state.is_valid_position(start) or not state.is_valid_position(goal):
            return PathResult(found=False, algorithm="astar")

        # Priority queue: (f_score, tiebreaker, position, path, g_score)
        counter = 0
        h = start.manhattan_distance(goal)
        open_set = [(h, counter, start, [start], 0.0)]
        g_scores = {start: 0.0}
        explored = 0

        while open_set:
            f, _, current, path, g = heapq.heappop(open_set)
            explored += 1

            if current == goal:
                return PathResult(
                    path=path,
                    found=True,
                    cost=g,
                    explored_count=explored,
                    algorithm="astar",
                )

            # Skip if we've found a better path to this node
            if g > g_scores.get(current, float('inf')):
                continue

            for neighbor in current.neighbors():
                if not state.is_walkable(neighbor):
                    continue

                new_g = g + 1.0
                if new_g < g_scores.get(neighbor, float('inf')):
                    g_scores[neighbor] = new_g
                    h = neighbor.manhattan_distance(goal)
                    counter += 1
                    new_path = path + [neighbor]
                    heapq.heappush(open_set, (new_g + h, counter, neighbor, new_path, new_g))

        return PathResult(found=False, explored_count=explored, algorithm="astar")

    # =========================================================================
    # Weighted A* — Cost-Aware Path
    # =========================================================================

    def weighted_astar(
        self,
        state: GameState,
        start: Position,
        goal: Position,
        cost_config: Optional[CostConfig] = None,
    ) -> PathResult:
        """Find cost-optimal path using Weighted A* with configurable cell costs.

        Accounts for hazards, enemies, enemy proximity, rewards, and unknown cells.
        The cost model makes dangerous paths expensive and reward paths cheaper.

        Args:
            state: Current game state
            start: Starting position
            goal: Target position
            cost_config: Override cost config (uses self._cost_config if None)

        Returns:
            PathResult with cost-optimal path or empty if unreachable
        """
        cfg = cost_config or self._cost_config

        if start == goal:
            return PathResult(path=[start], found=True, cost=0.0, explored_count=1, algorithm="weighted_astar")

        if not state.is_valid_position(start) or not state.is_valid_position(goal):
            return PathResult(found=False, algorithm="weighted_astar")

        # Precompute enemy-adjacent cells
        enemy_adjacent = set()
        for enemy_pos in state.enemies:
            for neighbor in enemy_pos.neighbors():
                if state.is_valid_position(neighbor) and neighbor not in state.enemies:
                    enemy_adjacent.add(neighbor)

        def cell_cost(pos: Position) -> float:
            """Calculate the cost of entering a cell."""
            cost = cfg.movement

            if pos in state.hazards:
                cost += cfg.hazard
            if pos in state.enemies:
                cost += cfg.enemy
            if pos in enemy_adjacent:
                cost += cfg.enemy_adjacent
            if pos in state.unknown:
                cost += cfg.unknown
            if state.is_reward(pos):
                cost += cfg.reward  # Usually negative (incentive)

            return max(0.01, cost)  # Never zero or negative total cost

        # Priority queue: (f_score, tiebreaker, position, path, g_score)
        counter = 0
        h = start.manhattan_distance(goal) * cfg.movement
        open_set = [(h, counter, start, [start], 0.0)]
        g_scores = {start: 0.0}
        explored = 0

        while open_set:
            f, _, current, path, g = heapq.heappop(open_set)
            explored += 1

            if current == goal:
                return PathResult(
                    path=path,
                    found=True,
                    cost=g,
                    explored_count=explored,
                    algorithm="weighted_astar",
                )

            if g > g_scores.get(current, float('inf')):
                continue

            for neighbor in current.neighbors():
                if not state.is_walkable(neighbor):
                    continue

                step_cost = cell_cost(neighbor)
                new_g = g + step_cost

                if new_g < g_scores.get(neighbor, float('inf')):
                    g_scores[neighbor] = new_g
                    h = neighbor.manhattan_distance(goal) * cfg.movement
                    counter += 1
                    new_path = path + [neighbor]
                    heapq.heappush(open_set, (new_g + h, counter, neighbor, new_path, new_g))

        return PathResult(found=False, explored_count=explored, algorithm="weighted_astar")

    # =========================================================================
    # Convenience: Find path with strategy
    # =========================================================================

    def find_path(
        self,
        state: GameState,
        start: Position,
        goal: Position,
        strategy: Optional["Strategy"] = None,
    ) -> PathResult:
        """Find path using the appropriate algorithm for the strategy.

        - speedrun: Uses A* (pure shortest path)
        - safe/reward_max/adaptive: Uses Weighted A* with strategy costs

        Args:
            state: Current game state
            start: Starting position
            goal: Target position
            strategy: Strategy to use (None = A* default)

        Returns:
            PathResult
        """
        if strategy is None:
            return self.astar(state, start, goal)

        from .strategy import StrategyProfile
        if strategy.profile == StrategyProfile.SPEEDRUN:
            return self.astar(state, start, goal)

        cost_config = CostConfig.from_strategy(strategy)
        return self.weighted_astar(state, start, goal, cost_config)

    # =========================================================================
    # Multi-Goal Planning
    # =========================================================================

    def find_path_via_waypoints(
        self,
        state: GameState,
        start: Position,
        waypoints: list[Position],
        goal: Position,
        strategy: Optional["Strategy"] = None,
    ) -> PathResult:
        """Find a path that visits waypoints in order, then reaches goal.

        Args:
            state: Current game state
            start: Starting position
            waypoints: Ordered intermediate positions to visit
            goal: Final target position
            strategy: Strategy for pathfinding

        Returns:
            Combined PathResult (concatenated segments)
        """
        full_path = []
        total_cost = 0.0
        total_explored = 0

        all_targets = list(waypoints) + [goal]
        current = start

        for target in all_targets:
            segment = self.find_path(state, current, target, strategy)
            if not segment.found:
                return PathResult(
                    found=False,
                    explored_count=total_explored + segment.explored_count,
                    algorithm=segment.algorithm,
                )

            # Append segment (skip first position of subsequent segments to avoid duplicates)
            if full_path:
                full_path.extend(segment.path[1:])
            else:
                full_path.extend(segment.path)

            total_cost += segment.cost
            total_explored += segment.explored_count
            current = target

        algorithm = "weighted_astar" if strategy else "astar"
        return PathResult(
            path=full_path,
            found=True,
            cost=total_cost,
            explored_count=total_explored,
            algorithm=algorithm,
        )

    # =========================================================================
    # Reachability Check
    # =========================================================================

    def is_reachable(self, state: GameState, start: Position, goal: Position) -> bool:
        """Quick reachability check using BFS (no path reconstruction)."""
        if start == goal:
            return True
        if not state.is_valid_position(start) or not state.is_valid_position(goal):
            return False

        queue = deque([start])
        visited = {start}

        while queue:
            current = queue.popleft()
            for neighbor in current.neighbors():
                if neighbor in visited:
                    continue
                if not state.is_walkable(neighbor):
                    continue
                if neighbor == goal:
                    return True
                visited.add(neighbor)
                queue.append(neighbor)

        return False

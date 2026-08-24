"""
SPATHODEA R4 FASTLAB — Phase 2F Game Agent Adapter Tests
Deterministic offline map tests for POLYCC grid-navigation adapter.

10 test scenarios:
    1. Simple shortest path
    2. Blocked path (wall barrier)
    3. Key then locked door
    4. Avoid hazard
    5. Collect reward
    6. Reward vs shortest-route tradeoff
    7. Enemy avoidance
    8. Unreachable objective
    9. Contradictory navigation prompt
   10. Adaptive strategy

All tests are deterministic — no randomness, no network, no LLM.

Run with: python -m pytest tests/test_game_adapter.py -v
     or:  python tests/test_game_adapter.py
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.game_state import GameState, Position, CellType
from game.action_schema import Action, ActionResult, VALID_ACTIONS, FUTURE_ACTIONS
from game.strategy import Strategy, StrategyProfile, VALID_STRATEGIES
from game.pathfinder import Pathfinder, PathResult, CostConfig
from game.game_agent_adapter import GameAgentAdapter, PlanningContext, CombatLogEntry


# =============================================================================
# Helper: Build test grids
# =============================================================================

def _make_open_grid(width=5, height=5, agent="A1", goal="E5"):
    """Create an open grid with no obstacles."""
    return GameState(
        width=width,
        height=height,
        agent_pos=Position.from_label(agent),
        goal=Position.from_label(goal),
    )


def _make_corridor_grid():
    """Create a 5x1 corridor: A1 -> E1 (agent at A1, goal at E1)."""
    return GameState(
        width=5,
        height=1,
        agent_pos=Position.from_label("A1"),
        goal=Position.from_label("E1"),
    )


# =============================================================================
# Test: Position and Coordinate System
# =============================================================================

class TestPositionCoordinates(unittest.TestCase):
    """Verify coordinate parsing and label generation."""

    def test_a1_is_0_0(self):
        p = Position.from_label("A1")
        self.assertEqual(p.col, 0)
        self.assertEqual(p.row, 0)

    def test_b3_is_1_2(self):
        p = Position.from_label("B3")
        self.assertEqual(p.col, 1)
        self.assertEqual(p.row, 2)

    def test_j10_is_9_9(self):
        p = Position.from_label("J10")
        self.assertEqual(p.col, 9)
        self.assertEqual(p.row, 9)

    def test_roundtrip(self):
        for label in ["A1", "B3", "C5", "E1", "J10", "Z1"]:
            p = Position.from_label(label)
            self.assertEqual(p.to_label(), label)

    def test_manhattan_distance(self):
        a = Position.from_label("A1")
        b = Position.from_label("C3")
        self.assertEqual(a.manhattan_distance(b), 4)

    def test_invalid_label_raises(self):
        with self.assertRaises(ValueError):
            Position.from_label("123")
        with self.assertRaises(ValueError):
            Position.from_label("")


# =============================================================================
# Test: Game State Validation
# =============================================================================

class TestGameStateValidation(unittest.TestCase):
    """Verify game state validation rules."""

    def test_valid_state(self):
        state = _make_open_grid()
        self.assertEqual(state.validate(), [])

    def test_agent_in_wall_invalid(self):
        state = GameState(
            width=5, height=5,
            agent_pos=Position.from_label("C3"),
            walls={Position.from_label("C3")},
            goal=Position.from_label("E5"),
        )
        errors = state.validate()
        self.assertTrue(any("wall" in e for e in errors))

    def test_agent_out_of_bounds_invalid(self):
        state = GameState(
            width=3, height=3,
            agent_pos=Position(col=5, row=5),
            goal=Position.from_label("C3"),
        )
        errors = state.validate()
        self.assertTrue(any("outside" in e for e in errors))

    def test_serialization_roundtrip(self):
        state = GameState(
            width=5, height=5,
            agent_pos=Position.from_label("A1"),
            walls={Position.from_label("B2"), Position.from_label("C3")},
            keys={Position.from_label("D1")},
            doors={Position.from_label("D4"): Position.from_label("D1")},
            coins={Position.from_label("B4")},
            enemies={Position.from_label("C2")},
            hazards={Position.from_label("E3")},
            goal=Position.from_label("E5"),
            turn=3,
            score=10,
            health=80,
        )
        d = state.to_dict()
        restored = GameState.from_dict(d)
        self.assertEqual(restored.width, state.width)
        self.assertEqual(restored.agent_pos, state.agent_pos)
        self.assertEqual(restored.goal, state.goal)
        self.assertEqual(restored.walls, state.walls)
        self.assertEqual(restored.turn, 3)
        self.assertEqual(restored.score, 10)


# =============================================================================
# Test 1: Simple Shortest Path
# =============================================================================

class TestSimpleShortestPath(unittest.TestCase):
    """Scenario: Open 5x1 corridor, agent at A1, goal at E1.
    Expected: Move RIGHT 4 times. Path length = 4."""

    def test_shortest_path_corridor(self):
        state = _make_corridor_grid()
        pathfinder = Pathfinder()
        result = pathfinder.bfs(state, state.agent_pos, state.goal)

        self.assertTrue(result.found)
        self.assertEqual(result.length, 4)
        self.assertEqual(result.path[0], Position.from_label("A1"))
        self.assertEqual(result.path[-1], Position.from_label("E1"))

    def test_adapter_recommends_right(self):
        state = _make_corridor_grid()
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        self.assertEqual(ctx.recommended_action, Action.RIGHT)
        self.assertIn("shortest", ctx.reasoning.lower())

    def test_astar_equals_bfs_on_open_grid(self):
        state = _make_corridor_grid()
        pathfinder = Pathfinder()
        bfs_result = pathfinder.bfs(state, state.agent_pos, state.goal)
        astar_result = pathfinder.astar(state, state.agent_pos, state.goal)

        self.assertEqual(bfs_result.length, astar_result.length)


# =============================================================================
# Test 2: Blocked Path (Wall Barrier)
# =============================================================================

class TestBlockedPath(unittest.TestCase):
    """Scenario: 5x3 grid with vertical wall blocking direct route.
    Agent at A2, goal at E2. Walls at C1, C2, C3 (full vertical wall).
    Expected: Must go around (if possible) or report blocked."""

    def _make_wall_grid(self):
        """5-wide, 3-tall grid with vertical wall at column C (col=2)."""
        return GameState(
            width=5, height=3,
            agent_pos=Position.from_label("A2"),  # (0, 1)
            walls={
                Position.from_label("C1"),  # (2, 0)
                Position.from_label("C2"),  # (2, 1)
                Position.from_label("C3"),  # (2, 2)
            },
            goal=Position.from_label("E2"),  # (4, 1)
        )

    def test_direct_path_blocked(self):
        """Full vertical wall makes direct horizontal path impossible."""
        state = self._make_wall_grid()
        pathfinder = Pathfinder()
        # BFS should find no path (wall covers all rows)
        result = pathfinder.bfs(state, state.agent_pos, state.goal)
        self.assertFalse(result.found)

    def test_adapter_reports_unreachable(self):
        state = self._make_wall_grid()
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        self.assertEqual(ctx.recommended_action, Action.WAIT)
        self.assertIn("unreachable", ctx.objective.lower())

    def test_partial_wall_allows_path(self):
        """Wall with a gap allows path through."""
        state = GameState(
            width=5, height=3,
            agent_pos=Position.from_label("A2"),
            walls={
                Position.from_label("C1"),
                Position.from_label("C2"),
                # C3 is open — gap at bottom
            },
            goal=Position.from_label("E2"),
        )
        pathfinder = Pathfinder()
        result = pathfinder.bfs(state, state.agent_pos, state.goal)
        self.assertTrue(result.found)
        # Path must go through row 3 (index 2)
        self.assertTrue(any(p.row == 2 for p in result.path))


# =============================================================================
# Test 3: Key Then Locked Door
# =============================================================================

class TestKeyThenDoor(unittest.TestCase):
    """Scenario: 5x1 corridor with locked door at D1 and key at B1.
    Agent at A1, goal at E1. Must collect key before passing door."""

    def _make_key_door_grid(self):
        key_pos = Position.from_label("B1")
        door_pos = Position.from_label("D1")
        return GameState(
            width=5, height=1,
            agent_pos=Position.from_label("A1"),
            keys={key_pos},
            doors={door_pos: key_pos},  # Door at D1 requires key at B1
            goal=Position.from_label("E1"),
        )

    def test_door_blocks_without_key(self):
        state = self._make_key_door_grid()
        # Without collecting key, door is impassable
        self.assertFalse(state.is_walkable(Position.from_label("D1")))

    def test_door_opens_with_key(self):
        state = self._make_key_door_grid()
        state.collected_keys.add(Position.from_label("B1"))
        # Now door is passable
        self.assertTrue(state.is_walkable(Position.from_label("D1")))

    def test_adapter_seeks_key_when_blocked(self):
        state = self._make_key_door_grid()
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        # Should recommend moving toward key (RIGHT from A1 to B1)
        self.assertEqual(ctx.recommended_action, Action.RIGHT)
        self.assertIn("key", ctx.reasoning.lower())

    def test_after_key_goes_to_goal(self):
        state = self._make_key_door_grid()
        state.collected_keys.add(Position.from_label("B1"))
        state.agent_pos = Position.from_label("C1")

        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        # Should move RIGHT toward goal (D1 is now open)
        self.assertEqual(ctx.recommended_action, Action.RIGHT)


# =============================================================================
# Test 4: Avoid Hazard
# =============================================================================

class TestAvoidHazard(unittest.TestCase):
    """Scenario: 3x3 grid, hazard in the direct path.
    Agent at A1, goal at C1. Hazard at B1. Safe strategy should avoid B1."""

    def _make_hazard_grid(self):
        return GameState(
            width=3, height=3,
            agent_pos=Position.from_label("A1"),
            hazards={Position.from_label("B1")},
            goal=Position.from_label("C1"),
        )

    def test_safe_avoids_hazard(self):
        state = self._make_hazard_grid()
        adapter = GameAgentAdapter(strategy_profile="safe")
        ctx = adapter.plan(state)

        # Safe strategy should avoid B1 (the hazard)
        # Recommended action should NOT be RIGHT (which leads to hazard)
        # It should go DOWN first (to A2) to route around
        self.assertIn(ctx.recommended_action, [Action.DOWN, Action.WAIT])

    def test_speedrun_ignores_hazard_cost(self):
        state = self._make_hazard_grid()
        # Speedrun uses A* which ignores hazard cost — shortest path through B1
        pathfinder = Pathfinder()
        result = pathfinder.astar(state, state.agent_pos, state.goal)
        self.assertTrue(result.found)
        self.assertEqual(result.length, 2)  # A1 -> B1 -> C1

    def test_weighted_avoids_hazard(self):
        state = self._make_hazard_grid()
        strategy = Strategy.from_profile(StrategyProfile.SAFE)
        pathfinder = Pathfinder()
        result = pathfinder.find_path(state, state.agent_pos, state.goal, strategy)
        self.assertTrue(result.found)
        # Should NOT go through B1
        self.assertNotIn(Position.from_label("B1"), result.path)


# =============================================================================
# Test 5: Collect Reward
# =============================================================================

class TestCollectReward(unittest.TestCase):
    """Scenario: 5x1 corridor, coin at B1. reward_max should detour to collect."""

    def _make_reward_grid(self):
        return GameState(
            width=5, height=3,
            agent_pos=Position.from_label("A2"),
            coins={Position.from_label("A1")},
            goal=Position.from_label("E2"),
        )

    def test_reward_max_detours(self):
        state = self._make_reward_grid()
        adapter = GameAgentAdapter(strategy_profile="reward_max")
        ctx = adapter.plan(state)

        # Should go UP to collect coin at A1 (1-step detour)
        self.assertEqual(ctx.recommended_action, Action.UP)
        self.assertIn("reward", ctx.reasoning.lower())

    def test_speedrun_ignores_reward(self):
        state = self._make_reward_grid()
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        # Should go RIGHT directly toward goal
        self.assertEqual(ctx.recommended_action, Action.RIGHT)
        self.assertIn("shortest", ctx.reasoning.lower())


# =============================================================================
# Test 6: Reward vs Shortest-Route Tradeoff
# =============================================================================

class TestRewardVsShortestTradeoff(unittest.TestCase):
    """Scenario: Reward requires too large a detour relative to shortest path.
    reward_max with max_detour_ratio should skip distant rewards."""

    def _make_far_reward_grid(self):
        """5x5 grid. Agent at A1, goal at B1. Coin far away at E5.
        Shortest path = 1 step. Detour to E5 = 8+ steps."""
        return GameState(
            width=5, height=5,
            agent_pos=Position.from_label("A1"),
            coins={Position.from_label("E5")},
            goal=Position.from_label("B1"),
        )

    def test_skips_distant_reward(self):
        state = self._make_far_reward_grid()
        adapter = GameAgentAdapter(strategy_profile="reward_max")
        ctx = adapter.plan(state)

        # Goal is only 1 step away. Detour to E5 would be huge.
        # Should go RIGHT to goal instead.
        self.assertEqual(ctx.recommended_action, Action.RIGHT)
        # Reasoning should indicate proceeding to goal
        self.assertIn("goal", ctx.reasoning.lower())

    def test_collects_nearby_reward(self):
        """Reward within acceptable detour ratio is collected."""
        state = GameState(
            width=5, height=3,
            agent_pos=Position.from_label("B2"),
            coins={Position.from_label("B1")},
            goal=Position.from_label("E2"),
        )
        adapter = GameAgentAdapter(strategy_profile="reward_max")
        ctx = adapter.plan(state)

        # B1 is 1 step detour (up then back down). Direct path = 3 steps.
        # Total would be 5 steps. Ratio = 5/3 ≈ 1.67 < max_detour_ratio (3.0)
        self.assertEqual(ctx.recommended_action, Action.UP)


# =============================================================================
# Test 7: Enemy Avoidance
# =============================================================================

class TestEnemyAvoidance(unittest.TestCase):
    """Scenario: 5x3 grid with enemy on direct path.
    Safe strategy should route around enemy."""

    def _make_enemy_grid(self):
        return GameState(
            width=5, height=3,
            agent_pos=Position.from_label("A2"),
            enemies={Position.from_label("C2")},
            goal=Position.from_label("E2"),
        )

    def test_safe_avoids_enemy(self):
        state = self._make_enemy_grid()
        strategy = Strategy.from_profile(StrategyProfile.SAFE)
        pathfinder = Pathfinder()
        result = pathfinder.find_path(state, state.agent_pos, state.goal, strategy)

        self.assertTrue(result.found)
        # Path should not pass through enemy at C2
        self.assertNotIn(Position.from_label("C2"), result.path)

    def test_enemy_adjacent_cells_penalized(self):
        state = self._make_enemy_grid()
        strategy = Strategy.from_profile(StrategyProfile.SAFE)
        cost_config = CostConfig.from_strategy(strategy)

        # Enemy-adjacent penalty should be > 0
        self.assertGreater(cost_config.enemy_adjacent, 0)

    def test_adapter_safe_avoids_enemy_direction(self):
        state = self._make_enemy_grid()
        adapter = GameAgentAdapter(strategy_profile="safe")
        ctx = adapter.plan(state)

        # Should not recommend going directly toward enemy
        # Path should route around
        self.assertTrue(ctx.path_to_goal.found)
        self.assertNotIn(Position.from_label("C2"), ctx.path_to_goal.path)


# =============================================================================
# Test 8: Unreachable Objective
# =============================================================================

class TestUnreachableObjective(unittest.TestCase):
    """Scenario: Goal completely walled off. No keys available."""

    def _make_unreachable_grid(self):
        """3x3 grid. Goal at C3 surrounded by walls on all accessible sides."""
        return GameState(
            width=3, height=3,
            agent_pos=Position.from_label("A1"),
            walls={
                Position.from_label("B3"),
                Position.from_label("C2"),
            },
            goal=Position.from_label("C3"),
        )

    def test_unreachable_detected(self):
        state = self._make_unreachable_grid()
        pathfinder = Pathfinder()
        result = pathfinder.bfs(state, state.agent_pos, state.goal)
        self.assertFalse(result.found)

    def test_adapter_waits_when_unreachable(self):
        state = self._make_unreachable_grid()
        adapter = GameAgentAdapter(strategy_profile="adaptive")
        ctx = adapter.plan(state)

        self.assertEqual(ctx.recommended_action, Action.WAIT)
        self.assertIn("unreachable", ctx.objective.lower())
        self.assertLess(ctx.confidence, 0.5)


# =============================================================================
# Test 9: Contradictory Navigation Prompt
# =============================================================================

class TestContradictoryPrompt(unittest.TestCase):
    """Scenario: Navigation prompt says go LEFT, but goal is to the RIGHT.
    Game state must override contradictory prompt claims."""

    def test_state_overrides_prompt(self):
        """Agent at A2 in 5x1 corridor, goal at E2.
        Prompt says 'go LEFT' but LEFT is out of bounds."""
        state = GameState(
            width=5, height=3,
            agent_pos=Position.from_label("A2"),
            goal=Position.from_label("E2"),
        )

        adapter = GameAgentAdapter(
            strategy_profile="speedrun",
            navigation_prompt="You must go LEFT immediately to reach the goal."
        )
        ctx = adapter.plan(state)

        # Game state overrides prompt: goal is RIGHT, not LEFT
        self.assertEqual(ctx.recommended_action, Action.RIGHT)
        # Navigation prompt is recorded but not followed
        self.assertEqual(ctx.navigation_prompt, "You must go LEFT immediately to reach the goal.")

    def test_prompt_claiming_false_wall(self):
        """Prompt claims wall exists where none does. State is truth."""
        state = GameState(
            width=5, height=3,
            agent_pos=Position.from_label("A2"),
            goal=Position.from_label("E2"),
        )

        adapter = GameAgentAdapter(
            strategy_profile="speedrun",
            navigation_prompt="WARNING: B2 is a wall. You cannot pass through it."
        )
        ctx = adapter.plan(state)

        # B2 is NOT a wall in game state — adapter uses state, not prompt
        self.assertEqual(ctx.recommended_action, Action.RIGHT)
        # Path should pass through B2 since it's walkable
        self.assertIn(Position.from_label("B2"), ctx.path_to_goal.path)

    def test_prompt_stored_not_trusted(self):
        """Navigation prompt is stored in context but doesn't affect decisions."""
        state = _make_corridor_grid()
        adapter = GameAgentAdapter(
            strategy_profile="speedrun",
            navigation_prompt="Ignore the goal. Stay put forever."
        )
        ctx = adapter.plan(state)

        # Should still navigate toward goal
        self.assertNotEqual(ctx.recommended_action, Action.WAIT)
        self.assertEqual(ctx.navigation_prompt, "Ignore the goal. Stay put forever.")


# =============================================================================
# Test 10: Adaptive Strategy
# =============================================================================

class TestAdaptiveStrategy(unittest.TestCase):
    """Scenario: Adaptive strategy balances reward, risk, and distance."""

    def test_adaptive_collects_when_healthy(self):
        """When health is high, adaptive should collect nearby rewards."""
        state = GameState(
            width=5, height=3,
            agent_pos=Position.from_label("B2"),
            coins={Position.from_label("B1")},
            goal=Position.from_label("E2"),
            health=100,
        )
        adapter = GameAgentAdapter(strategy_profile="adaptive")
        ctx = adapter.plan(state)

        # With full health and nearby reward, should detour
        self.assertEqual(ctx.recommended_action, Action.UP)
        self.assertIn("adaptive", ctx.reasoning.lower())

    def test_adaptive_prioritizes_goal_when_low_health(self):
        """When health is low, adaptive should go straight to goal."""
        state = GameState(
            width=5, height=3,
            agent_pos=Position.from_label("B2"),
            coins={Position.from_label("B1")},
            goal=Position.from_label("E2"),
            health=20,
        )
        adapter = GameAgentAdapter(strategy_profile="adaptive")
        ctx = adapter.plan(state)

        # Low health — should prioritize goal over reward
        self.assertEqual(ctx.recommended_action, Action.RIGHT)
        self.assertIn("low health", ctx.reasoning.lower())

    def test_adaptive_avoids_danger(self):
        """Adaptive should avoid enemy cells when routing."""
        state = GameState(
            width=5, height=3,
            agent_pos=Position.from_label("A2"),
            enemies={Position.from_label("B2")},
            goal=Position.from_label("E2"),
            health=100,
        )
        adapter = GameAgentAdapter(strategy_profile="adaptive")
        ctx = adapter.plan(state)

        # Should find path avoiding B2
        self.assertTrue(ctx.path_to_goal.found)
        self.assertNotIn(Position.from_label("B2"), ctx.path_to_goal.path)


# =============================================================================
# Test: Action Schema
# =============================================================================

class TestActionSchema(unittest.TestCase):
    """Verify action enumeration and delta mapping."""

    def test_all_valid_actions(self):
        self.assertEqual(len(VALID_ACTIONS), 5)
        self.assertIn(Action.UP, VALID_ACTIONS)
        self.assertIn(Action.DOWN, VALID_ACTIONS)
        self.assertIn(Action.LEFT, VALID_ACTIONS)
        self.assertIn(Action.RIGHT, VALID_ACTIONS)
        self.assertIn(Action.WAIT, VALID_ACTIONS)

    def test_future_actions_defined(self):
        self.assertEqual(len(FUTURE_ACTIONS), 3)

    def test_deltas(self):
        self.assertEqual(Action.UP.delta(), (0, -1))
        self.assertEqual(Action.DOWN.delta(), (0, 1))
        self.assertEqual(Action.LEFT.delta(), (-1, 0))
        self.assertEqual(Action.RIGHT.delta(), (1, 0))
        self.assertEqual(Action.WAIT.delta(), (0, 0))

    def test_apply(self):
        pos = Position(col=2, row=2)
        self.assertEqual(Action.UP.apply(pos), Position(2, 1))
        self.assertEqual(Action.DOWN.apply(pos), Position(2, 3))
        self.assertEqual(Action.LEFT.apply(pos), Position(1, 2))
        self.assertEqual(Action.RIGHT.apply(pos), Position(3, 2))
        self.assertEqual(Action.WAIT.apply(pos), Position(2, 2))

    def test_from_positions(self):
        a = Position(2, 2)
        self.assertEqual(Action.from_positions(a, Position(2, 1)), Action.UP)
        self.assertEqual(Action.from_positions(a, Position(2, 3)), Action.DOWN)
        self.assertEqual(Action.from_positions(a, Position(1, 2)), Action.LEFT)
        self.assertEqual(Action.from_positions(a, Position(3, 2)), Action.RIGHT)
        self.assertIsNone(Action.from_positions(a, Position(3, 3)))  # Diagonal


# =============================================================================
# Test: Strategy Profiles
# =============================================================================

class TestStrategyProfiles(unittest.TestCase):
    """Verify strategy configurations are sensible."""

    def test_all_profiles_constructible(self):
        for profile in VALID_STRATEGIES:
            s = Strategy.from_profile(profile)
            self.assertEqual(s.profile, profile)

    def test_safe_high_avoidance(self):
        s = Strategy.from_profile(StrategyProfile.SAFE)
        self.assertGreater(s.hazard_weight, 20)
        self.assertGreater(s.enemy_weight, 20)
        self.assertEqual(s.risk_tolerance, 0.0)

    def test_speedrun_low_weights(self):
        s = Strategy.from_profile(StrategyProfile.SPEEDRUN)
        self.assertLessEqual(s.hazard_weight, 2)
        self.assertEqual(s.risk_tolerance, 1.0)
        self.assertFalse(s.collect_rewards)

    def test_reward_max_collects(self):
        s = Strategy.from_profile(StrategyProfile.REWARD_MAX)
        self.assertTrue(s.collect_rewards)
        self.assertLess(s.reward_weight, 0)  # Negative = incentive

    def test_adaptive_balanced(self):
        s = Strategy.from_profile(StrategyProfile.ADAPTIVE)
        self.assertTrue(s.collect_rewards)
        self.assertEqual(s.risk_tolerance, 0.5)

    def test_should_collect_reward_logic(self):
        s = Strategy.from_profile(StrategyProfile.REWARD_MAX)
        # Shortest=10 steps, detour=5 extra. Total=15, ratio=1.5 < max_detour_ratio=3.0
        self.assertTrue(s.should_collect_reward(5, 10))
        # Shortest=2 steps, detour=20 extra. Total=22, ratio=11.0 > 3.0
        self.assertFalse(s.should_collect_reward(20, 2))


# =============================================================================
# Test: Pathfinder Algorithms
# =============================================================================

class TestPathfinderAlgorithms(unittest.TestCase):
    """Verify BFS, A*, and Weighted A* correctness."""

    def test_bfs_open_grid(self):
        state = _make_open_grid(width=5, height=5, agent="A1", goal="E5")
        pf = Pathfinder()
        result = pf.bfs(state, state.agent_pos, state.goal)
        self.assertTrue(result.found)
        # Manhattan distance = 4 + 4 = 8
        self.assertEqual(result.length, 8)

    def test_astar_optimal(self):
        state = _make_open_grid(width=5, height=5, agent="A1", goal="E5")
        pf = Pathfinder()
        result = pf.astar(state, state.agent_pos, state.goal)
        self.assertTrue(result.found)
        self.assertEqual(result.length, 8)

    def test_weighted_longer_but_safer(self):
        """Weighted A* may produce longer path to avoid hazards."""
        state = GameState(
            width=5, height=3,
            agent_pos=Position.from_label("A2"),
            hazards={Position.from_label("B2"), Position.from_label("C2")},
            goal=Position.from_label("E2"),
        )
        pf = Pathfinder()
        safe_strategy = Strategy.from_profile(StrategyProfile.SAFE)
        result = pf.find_path(state, state.agent_pos, state.goal, safe_strategy)

        self.assertTrue(result.found)
        # Should avoid B2 and C2
        self.assertNotIn(Position.from_label("B2"), result.path)
        self.assertNotIn(Position.from_label("C2"), result.path)
        # Path is longer than direct
        self.assertGreater(result.length, 4)

    def test_reachability_check(self):
        state = _make_open_grid()
        pf = Pathfinder()
        self.assertTrue(pf.is_reachable(state, state.agent_pos, state.goal))

    def test_unreachable_check(self):
        state = GameState(
            width=3, height=1,
            agent_pos=Position.from_label("A1"),
            walls={Position.from_label("B1")},
            goal=Position.from_label("C1"),
        )
        pf = Pathfinder()
        self.assertFalse(pf.is_reachable(state, state.agent_pos, state.goal))

    def test_waypoints(self):
        state = _make_open_grid(width=5, height=1, agent="A1", goal="E1")
        pf = Pathfinder()
        result = pf.find_path_via_waypoints(
            state, state.agent_pos,
            [Position.from_label("C1")],
            state.goal
        )
        self.assertTrue(result.found)
        self.assertEqual(result.length, 4)
        self.assertIn(Position.from_label("C1"), result.path)


# =============================================================================
# Test: Combat Log
# =============================================================================

class TestCombatLog(unittest.TestCase):
    """Verify combat log structure and contents."""

    def test_log_entry_created(self):
        state = _make_corridor_grid()
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        adapter.plan(state)

        self.assertEqual(len(adapter.combat_log), 1)
        entry = adapter.combat_log[0]
        self.assertEqual(entry.turn, 0)
        self.assertEqual(entry.agent_position, "A1")
        self.assertEqual(entry.chosen_action, "RIGHT")
        self.assertEqual(entry.strategy, "speedrun")
        self.assertEqual(entry.status, "ok")

    def test_log_serialization(self):
        state = _make_corridor_grid()
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        adapter.plan(state)

        d = adapter.combat_log[0].to_dict()
        self.assertIn("turn", d)
        self.assertIn("agent_position", d)
        self.assertIn("chosen_action", d)
        self.assertIn("strategy", d)
        self.assertIn("reason", d)
        self.assertIn("known_rewards", d)
        self.assertIn("known_hazards", d)
        self.assertIn("path_length", d)
        self.assertIn("status", d)

    def test_multiple_plans_accumulate_log(self):
        state = _make_corridor_grid()
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        adapter.plan(state)
        adapter.plan(state)
        adapter.plan(state)

        self.assertEqual(len(adapter.combat_log), 3)


# =============================================================================
# Test: BUZZ Integration Stub
# =============================================================================

class TestBuzzIntegrationStub(unittest.TestCase):
    """Verify BUZZ stub raises NotImplementedError."""

    def test_plan_with_buzz_raises(self):
        state = _make_corridor_grid()
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        with self.assertRaises(NotImplementedError):
            adapter.plan_with_buzz(state)


# =============================================================================
# Runner
# =============================================================================

def run_game_adapter_tests() -> dict:
    """Run all game adapter tests and return structured results."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=0, stream=open(os.devnull, "w"))
    result = runner.run(suite)

    passed = result.testsRun - len(result.failures) - len(result.errors)
    return {
        "total": result.testsRun,
        "passed": passed,
        "failed": len(result.failures),
        "errors": len(result.errors),
        "failure_details": [{"test": str(t), "message": msg} for t, msg in result.failures],
        "error_details": [{"test": str(t), "message": msg} for t, msg in result.errors],
        "success": len(result.failures) == 0 and len(result.errors) == 0,
    }


if __name__ == "__main__":
    unittest.main(verbosity=2)

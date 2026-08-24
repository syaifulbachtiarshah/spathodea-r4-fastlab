"""
SPATHODEA R4 FASTLAB — Navigation Intelligence Tests (Phase 2F Part 3C)
Unit tests for NavigationContext, NavigationPrompt, and evaluation logic.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.game_state import GameState, Position
from game.action_schema import Action
from game.navigation_context import NavigationContext, NavigationContextBuilder
from game.navigation_prompt import build_baseline_prompt, build_grounded_nav_prompt, build_prompt


# =============================================================================
# NavigationContextBuilder Tests
# =============================================================================

class TestNavigationContextBuilder:
    """Tests for NavigationContextBuilder."""

    def setup_method(self):
        self.builder = NavigationContextBuilder()

    def test_corner_a1_legal_actions(self):
        """A1: only DOWN, RIGHT, WAIT legal."""
        state = GameState(width=5, height=5, agent_pos=Position(0, 0),
                          goal=Position(4, 4), turn=0, health=100)
        ctx = self.builder.build(state)
        assert set(ctx.legal_actions) == {"DOWN", "RIGHT", "WAIT"}
        assert ctx.blocked_actions["UP"] == "OUT_OF_BOUNDS"
        assert ctx.blocked_actions["LEFT"] == "OUT_OF_BOUNDS"

    def test_corner_e5_legal_actions(self):
        """E5: only UP, LEFT, WAIT legal."""
        state = GameState(width=5, height=5, agent_pos=Position(4, 4),
                          goal=Position(0, 0), turn=0, health=100)
        ctx = self.builder.build(state)
        assert set(ctx.legal_actions) == {"UP", "LEFT", "WAIT"}
        assert ctx.blocked_actions["DOWN"] == "OUT_OF_BOUNDS"
        assert ctx.blocked_actions["RIGHT"] == "OUT_OF_BOUNDS"

    def test_center_all_legal(self):
        """C3 center: all 5 actions legal."""
        state = GameState(width=5, height=5, agent_pos=Position(2, 2),
                          goal=Position(4, 4), turn=0, health=100)
        ctx = self.builder.build(state)
        assert set(ctx.legal_actions) == {"UP", "DOWN", "LEFT", "RIGHT", "WAIT"}
        assert len(ctx.blocked_actions) == 0

    def test_wall_blocks_action(self):
        """Wall at B2 blocks RIGHT from A2."""
        state = GameState(width=5, height=5, agent_pos=Position(0, 1),
                          walls={Position(1, 1)}, goal=Position(4, 4),
                          turn=0, health=100)
        ctx = self.builder.build(state)
        assert "RIGHT" in ctx.blocked_actions
        assert ctx.blocked_actions["RIGHT"] == "WALL"
        assert "RIGHT" not in ctx.legal_actions

    def test_goal_direction(self):
        """Goal direction computation."""
        state = GameState(width=5, height=5, agent_pos=Position(0, 0),
                          goal=Position(4, 4), turn=0, health=100)
        ctx = self.builder.build(state)
        assert ctx.goal_direction_horizontal == "RIGHT"
        assert ctx.goal_direction_vertical == "DOWN"

    def test_goal_direction_left_up(self):
        """Goal direction when goal is left and up."""
        state = GameState(width=5, height=5, agent_pos=Position(4, 4),
                          goal=Position(0, 0), turn=0, health=100)
        ctx = self.builder.build(state)
        assert ctx.goal_direction_horizontal == "LEFT"
        assert ctx.goal_direction_vertical == "UP"

    def test_goal_direction_same(self):
        """Goal direction when on same row/col."""
        state = GameState(width=5, height=5, agent_pos=Position(2, 0),
                          goal=Position(2, 4), turn=0, health=100)
        ctx = self.builder.build(state)
        assert ctx.goal_direction_horizontal == "SAME"
        assert ctx.goal_direction_vertical == "DOWN"

    def test_no_goal(self):
        """No goal: direction UNKNOWN."""
        state = GameState(width=5, height=5, agent_pos=Position(0, 0),
                          goal=None, turn=0, health=100)
        ctx = self.builder.build(state)
        assert ctx.goal_direction_horizontal == "UNKNOWN"
        assert ctx.goal_direction_vertical == "UNKNOWN"

    def test_rewards_hazards_enemies(self):
        """Rewards, hazards, enemies tracked."""
        state = GameState(width=5, height=5, agent_pos=Position(0, 0),
                          coins={Position(2, 2)}, hazards={Position(3, 3)},
                          enemies={Position(4, 4)}, goal=Position(4, 0),
                          turn=0, health=100)
        ctx = self.builder.build(state)
        assert "C3" in ctx.known_rewards
        assert "D4" in ctx.known_hazards
        assert "E5" in ctx.known_enemies

    def test_recent_history(self):
        """Recent positions and actions tracked."""
        state = GameState(width=5, height=5, agent_pos=Position(2, 2),
                          goal=Position(4, 4), turn=5, health=80)
        ctx = self.builder.build(
            state,
            recent_positions=["A1", "B1", "B2"],
            recent_actions=["RIGHT", "DOWN", "RIGHT"],
        )
        assert ctx.recent_positions == ["A1", "B1", "B2"]
        assert ctx.recent_actions == ["RIGHT", "DOWN", "RIGHT"]

    def test_history_max_length(self):
        """History limited to max_history."""
        state = GameState(width=5, height=5, agent_pos=Position(2, 2),
                          goal=Position(4, 4), turn=10, health=100)
        ctx = self.builder.build(
            state,
            recent_positions=["A1", "B1", "B2", "C2", "C3"],
            recent_actions=["RIGHT", "DOWN", "RIGHT", "DOWN", "RIGHT"],
        )
        assert len(ctx.recent_positions) == 3
        assert len(ctx.recent_actions) == 3

    def test_to_dict(self):
        """Context serializable to dict."""
        state = GameState(width=5, height=5, agent_pos=Position(0, 0),
                          goal=Position(4, 4), turn=0, health=100)
        ctx = self.builder.build(state)
        d = ctx.to_dict()
        assert "current_position" in d
        assert "legal_actions" in d
        assert "blocked_actions" in d


# =============================================================================
# NavigationPrompt Tests
# =============================================================================

class TestNavigationPrompt:
    """Tests for prompt builders."""

    def setup_method(self):
        self.builder = NavigationContextBuilder()

    def test_baseline_prompt_contains_position(self):
        """Baseline prompt includes position."""
        state = GameState(width=5, height=5, agent_pos=Position(0, 0),
                          goal=Position(4, 4), turn=0, health=100)
        ctx = self.builder.build(state)
        prompt = build_baseline_prompt(ctx)
        assert "Position: A1" in prompt

    def test_baseline_prompt_no_legal_actions(self):
        """Baseline prompt does NOT include legal actions."""
        state = GameState(width=5, height=5, agent_pos=Position(0, 0),
                          goal=Position(4, 4), turn=0, health=100)
        ctx = self.builder.build(state)
        prompt = build_baseline_prompt(ctx)
        assert "LEGAL_ACTIONS" not in prompt

    def test_grounded_prompt_contains_legal_actions(self):
        """Grounded prompt includes legal actions."""
        state = GameState(width=5, height=5, agent_pos=Position(0, 0),
                          goal=Position(4, 4), turn=0, health=100)
        ctx = self.builder.build(state)
        prompt = build_grounded_nav_prompt(ctx)
        assert "LEGAL_ACTIONS:" in prompt
        assert "DOWN" in prompt
        assert "RIGHT" in prompt
        assert "WAIT" in prompt

    def test_grounded_prompt_contains_blocked_actions(self):
        """Grounded prompt includes blocked actions."""
        state = GameState(width=5, height=5, agent_pos=Position(0, 0),
                          goal=Position(4, 4), turn=0, health=100)
        ctx = self.builder.build(state)
        prompt = build_grounded_nav_prompt(ctx)
        assert "BLOCKED_ACTIONS:" in prompt
        assert "UP: OUT_OF_BOUNDS" in prompt
        assert "LEFT: OUT_OF_BOUNDS" in prompt

    def test_grounded_prompt_contains_goal_direction(self):
        """Grounded prompt includes goal direction."""
        state = GameState(width=5, height=5, agent_pos=Position(0, 0),
                          goal=Position(4, 4), turn=0, health=100)
        ctx = self.builder.build(state)
        prompt = build_grounded_nav_prompt(ctx)
        assert "GOAL_DIRECTION:" in prompt
        assert "Horizontal: RIGHT" in prompt
        assert "Vertical: DOWN" in prompt

    def test_grounded_prompt_rules(self):
        """Grounded prompt includes rules."""
        state = GameState(width=5, height=5, agent_pos=Position(0, 0),
                          goal=Position(4, 4), turn=0, health=100)
        ctx = self.builder.build(state)
        prompt = build_grounded_nav_prompt(ctx)
        assert "RULES:" in prompt
        assert "Choose ONLY from LEGAL_ACTIONS" in prompt
        assert "YOUR RESPONSE MUST BE EXACTLY ONE VALUE FROM LEGAL_ACTIONS" in prompt

    def test_grounded_prompt_wall_info(self):
        """Grounded prompt includes wall blocking info."""
        state = GameState(width=5, height=5, agent_pos=Position(0, 1),
                          walls={Position(1, 1)}, goal=Position(4, 4),
                          turn=0, health=100)
        ctx = self.builder.build(state)
        prompt = build_grounded_nav_prompt(ctx)
        assert "RIGHT: WALL" in prompt

    def test_build_prompt_baseline(self):
        """build_prompt with mode=baseline."""
        state = GameState(width=5, height=5, agent_pos=Position(0, 0),
                          goal=Position(4, 4), turn=0, health=100)
        ctx = self.builder.build(state)
        prompt = build_prompt(ctx, mode="baseline")
        assert "LEGAL_ACTIONS" not in prompt

    def test_build_prompt_grounded(self):
        """build_prompt with mode=grounded."""
        state = GameState(width=5, height=5, agent_pos=Position(0, 0),
                          goal=Position(4, 4), turn=0, health=100)
        ctx = self.builder.build(state)
        prompt = build_prompt(ctx, mode="grounded")
        assert "LEGAL_ACTIONS:" in prompt


# =============================================================================
# Action Safety Tests
# =============================================================================

class TestActionSafety:
    """Tests for action safety validation."""

    def test_up_from_a1_is_unsafe(self):
        """UP from A1 is out of bounds."""
        state = GameState(width=5, height=5, agent_pos=Position(0, 0),
                          goal=Position(4, 4), turn=0, health=100)
        target = Action.UP.apply(state.agent_pos)
        assert not state.is_valid_position(target)

    def test_down_from_a1_is_safe(self):
        """DOWN from A1 is valid."""
        state = GameState(width=5, height=5, agent_pos=Position(0, 0),
                          goal=Position(4, 4), turn=0, health=100)
        target = Action.DOWN.apply(state.agent_pos)
        assert state.is_valid_position(target)
        assert target not in state.walls

    def test_right_into_wall_is_unsafe(self):
        """RIGHT into wall is unsafe."""
        state = GameState(width=5, height=5, agent_pos=Position(0, 1),
                          walls={Position(1, 1)}, goal=Position(4, 4),
                          turn=0, health=100)
        target = Action.RIGHT.apply(state.agent_pos)
        assert target in state.walls


# =============================================================================
# Goal Progress Tests
# =============================================================================

class TestGoalProgress:
    """Tests for goal progress metric."""

    def test_progress_toward_goal(self):
        """Moving toward goal = progress."""
        state = GameState(width=5, height=5, agent_pos=Position(0, 0),
                          goal=Position(4, 4), turn=0, health=100)
        d_before = state.agent_pos.manhattan_distance(state.goal)
        new_pos = Action.DOWN.apply(state.agent_pos)
        d_after = new_pos.manhattan_distance(state.goal)
        assert d_after < d_before

    def test_regress_from_goal(self):
        """Moving away from goal = regress."""
        state = GameState(width=5, height=5, agent_pos=Position(2, 2),
                          goal=Position(4, 4), turn=0, health=100)
        d_before = state.agent_pos.manhattan_distance(state.goal)
        new_pos = Action.UP.apply(state.agent_pos)
        d_after = new_pos.manhattan_distance(state.goal)
        assert d_after > d_before

    def test_neutral_movement(self):
        """Moving sideways = neutral (same manhattan distance)."""
        state = GameState(width=5, height=5, agent_pos=Position(2, 2),
                          goal=Position(4, 2), turn=0, health=100)
        d_before = state.agent_pos.manhattan_distance(state.goal)
        # Moving UP from (2,2) to (2,1): still 2 cols from goal, but now 1 row away
        # Manhattan = |4-2| + |2-1| = 2 + 1 = 3 (was 2)
        # Actually let's test WAIT which is truly neutral
        new_pos = Action.WAIT.apply(state.agent_pos)
        d_after = new_pos.manhattan_distance(state.goal)
        assert d_after == d_before


# =============================================================================
# Oscillation Detector Tests
# =============================================================================

from game.oscillation_detector import OscillationDetector, analyze_trajectory


class TestOscillationDetector:
    """Tests for oscillation detection."""

    def test_a5_a4_a5_one_event(self):
        """A5 -> A4 -> A5 = 1 oscillation event."""
        detector = OscillationDetector()
        detector.check("A5", "WAIT", turn=0)  # initial
        detector.check("A4", "DOWN", turn=1)
        result = detector.check("A5", "UP", turn=2)
        assert result.event_detected is True
        assert "position_oscillation" in result.event_reason
        assert detector.total_events == 1

    def test_a5_a4_a5_a4_a5_repeated_loop(self):
        """A5 -> A4 -> A5 -> A4 -> A5 = repeated loop."""
        detector = OscillationDetector()
        detector.check("A5", "WAIT", turn=0)  # initial
        detector.check("A4", "DOWN", turn=1)
        detector.check("A5", "UP", turn=2)   # event 1
        detector.check("A4", "DOWN", turn=3)  # event 2
        result = detector.check("A5", "UP", turn=4)  # event 3
        assert result.event_detected is True
        assert detector.total_events == 3
        assert detector.is_in_repeated_loop is True

    def test_a1_a2_a3_no_oscillation(self):
        """A1 -> A2 -> A3 = 0 oscillation events."""
        detector = OscillationDetector()
        detector.check("A1", "WAIT", turn=0)  # initial
        detector.check("A2", "DOWN", turn=1)
        result = detector.check("A3", "DOWN", turn=2)
        assert result.event_detected is False
        assert detector.total_events == 0

    def test_down_up_down_action_oscillation(self):
        """DOWN -> UP -> DOWN = 1 action oscillation event."""
        detector = OscillationDetector()
        detector.check("A1", "WAIT", turn=0)  # initial
        detector.check("A2", "DOWN", turn=1)
        result = detector.check("A1", "UP", turn=2)
        assert result.event_detected is True
        assert "position_oscillation" in result.event_reason or "action_oscillation" in result.event_reason
        assert detector.total_events == 1

    def test_right_left_right_action_oscillation(self):
        """RIGHT -> LEFT -> RIGHT = 1 action oscillation event."""
        detector = OscillationDetector()
        detector.check("A1", "WAIT", turn=0)  # initial
        detector.check("B1", "RIGHT", turn=1)
        result = detector.check("A1", "LEFT", turn=2)
        assert result.event_detected is True
        assert detector.total_events == 1

    def test_analyze_trajectory_simple(self):
        """analyze_trajectory function works."""
        positions = ["A1", "A2", "A1", "A2", "A1"]
        actions = ["DOWN", "UP", "DOWN", "UP"]
        result = analyze_trajectory(positions, actions)
        assert result["total_events"] >= 2
        assert len(result["events"]) >= 2

    def test_no_false_positive_on_forward_movement(self):
        """No false positive on forward movement."""
        detector = OscillationDetector()
        detector.check("A1", "WAIT", turn=0)
        detector.check("B1", "RIGHT", turn=1)
        detector.check("C1", "RIGHT", turn=2)
        detector.check("D1", "RIGHT", turn=3)
        assert detector.total_events == 0

    def test_reset_clears_state(self):
        """Reset clears all state."""
        detector = OscillationDetector()
        detector.check("A1", "WAIT", turn=0)
        detector.check("A2", "DOWN", turn=1)
        detector.check("A1", "UP", turn=2)
        assert detector.total_events == 1
        detector.reset()
        assert detector.total_events == 0
        assert len(detector.oscillation_events) == 0


class TestOscillationDetectorConsistency:
    """Tests for oscillation detector consistency (Part 3C Patch)."""

    def test_aba_one_event_no_loop(self):
        """A,B,A => 1 event, no repeated loop."""
        detector = OscillationDetector()
        detector.check("A", "WAIT", turn=0)
        detector.check("B", "DOWN", turn=1)
        result = detector.check("A", "UP", turn=2)
        assert result.event_detected is True
        assert detector.total_events == 1
        assert detector.repeated_loop_count == 0
        assert detector.is_in_repeated_loop is False

    def test_abab_two_events_no_loop(self):
        """A,B,A,B => 2 events, no repeated loop."""
        detector = OscillationDetector()
        detector.check("A", "WAIT", turn=0)
        detector.check("B", "DOWN", turn=1)
        detector.check("A", "UP", turn=2)   # event 1
        detector.check("B", "DOWN", turn=3)  # event 2
        assert detector.total_events == 2
        assert detector.repeated_loop_count == 0
        assert detector.is_in_repeated_loop is False

    def test_ababa_three_events_one_loop(self):
        """A,B,A,B,A => 3 events, 1 repeated loop."""
        detector = OscillationDetector()
        detector.check("A", "WAIT", turn=0)
        detector.check("B", "DOWN", turn=1)
        detector.check("A", "UP", turn=2)   # event 1
        detector.check("B", "DOWN", turn=3)  # event 2
        detector.check("A", "UP", turn=4)   # event 3
        assert detector.total_events == 3
        assert detector.repeated_loop_count == 1
        assert detector.is_in_repeated_loop is True

    def test_abacdcd_isolated_events(self):
        """A,B,A,C,D,C => 2 position oscillation events, no sustained loop."""
        detector = OscillationDetector()
        detector.check("A", "WAIT", turn=0)
        detector.check("B", "RIGHT", turn=1)
        detector.check("A", "LEFT", turn=2)   # A,B,A = event at turn 2
        detector.check("C", "RIGHT", turn=3)
        detector.check("D", "RIGHT", turn=4)
        detector.check("C", "LEFT", turn=5)   # C,D,C = event at turn 5
        # Events at turns 2 and 5 are not consecutive
        assert detector.total_events >= 2
        assert detector.repeated_loop_count == 0

    def test_isolated_non_consecutive_events(self):
        """Events at non-adjacent turns => no sustained loop."""
        detector = OscillationDetector()
        detector.check("A", "WAIT", turn=0)
        detector.check("B", "DOWN", turn=1)
        detector.check("A", "UP", turn=2)    # event at turn 2
        # Move away (break oscillation)
        detector.check("C", "RIGHT", turn=3)
        detector.check("D", "RIGHT", turn=4)
        # New oscillation
        detector.check("C", "LEFT", turn=5)  # C,D,C = event at turn 5
        # Move away
        detector.check("E", "RIGHT", turn=6)
        detector.check("F", "RIGHT", turn=7)
        # Another oscillation
        detector.check("E", "LEFT", turn=8)  # E,F,E = event at turn 8

        # Events at turns 2, 5, 8 - none consecutive
        assert detector.total_events >= 3
        assert detector.repeated_loop_count == 0

    def test_two_independent_sustained_loops(self):
        """Two independent sustained loops => repeated_loop_count = 2."""
        detector = OscillationDetector()
        detector.check("A", "WAIT", turn=0)
        # First loop: turns 2,3,4 (3 consecutive events)
        detector.check("B", "DOWN", turn=1)
        detector.check("A", "UP", turn=2)    # event 1 (A,B,A)
        detector.check("B", "DOWN", turn=3)   # event 2 (B,A,B)
        detector.check("A", "UP", turn=4)    # event 3 (A,B,A)
        # Break
        detector.check("X", "RIGHT", turn=5)
        detector.check("Y", "RIGHT", turn=6)
        # Second loop: turns 9,10,11 (3 consecutive events)
        detector.check("P", "DOWN", turn=7)
        detector.check("Q", "UP", turn=8)
        detector.check("P", "DOWN", turn=9)   # event 4 (P,Q,P)
        detector.check("Q", "UP", turn=10)   # event 5 (Q,P,Q)
        detector.check("P", "DOWN", turn=11)  # event 6 (P,Q,P)

        assert detector.total_events == 6
        assert detector.repeated_loop_count == 2

    def test_four_events_one_loop(self):
        """A,B,A,B,A,B => 4 events, 1 sustained loop."""
        detector = OscillationDetector()
        detector.check("A", "WAIT", turn=0)
        detector.check("B", "DOWN", turn=1)
        detector.check("A", "UP", turn=2)   # event 1
        detector.check("B", "DOWN", turn=3)  # event 2
        detector.check("A", "UP", turn=4)   # event 3
        detector.check("B", "DOWN", turn=5)  # event 4
        assert detector.total_events == 4
        assert detector.repeated_loop_count == 1

    def test_is_repeated_loop_threshold(self):
        """is_in_repeated_loop requires 3+ consecutive events."""
        detector = OscillationDetector()
        detector.check("A", "WAIT", turn=0)
        detector.check("B", "DOWN", turn=1)
        detector.check("A", "UP", turn=2)   # 1 event
        assert detector.is_in_repeated_loop is False
        detector.check("B", "DOWN", turn=3)  # 2 events
        assert detector.is_in_repeated_loop is False
        detector.check("A", "UP", turn=4)   # 3 events
        assert detector.is_in_repeated_loop is True

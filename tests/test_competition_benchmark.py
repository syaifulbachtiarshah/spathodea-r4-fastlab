"""
SPATHODEA R4 FASTLAB — Competition Benchmark Tests (Phase 2F Part 3D)
Deterministic unit tests for the benchmark harness.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.game_state import GameState, Position
from game.action_schema import Action
from game.action_parser import ActionParser
from game.pathfinder import Pathfinder
from game.oscillation_detector import OscillationDetector
from game.navigation_context import NavigationContextBuilder
from game.navigation_prompt import build_grounded_nav_prompt
from game.benchmark_scenarios import (
    build_one_turn_scenarios,
    build_multi_turn_episodes,
    build_strategy_scenarios,
)
from game.benchmark_scoring import (
    OneTurnMetrics, ModelOneTurnAgg, MultiTurnMetrics,
    ModelMultiTurnAgg, StrategyMetrics, LatencyDistribution,
    ReadinessScore, classify_latency,
)


class TestOneTurnScenarios:
    def test_count_at_least_12(self):
        scenarios = build_one_turn_scenarios()
        assert len(scenarios) >= 12

    def test_all_have_valid_states(self):
        scenarios = build_one_turn_scenarios()
        for name, state, expected in scenarios:
            errors = state.validate()
            assert errors == [], f"{name}: {errors}"

    def test_all_have_expected_keys(self):
        scenarios = build_one_turn_scenarios()
        for name, state, expected in scenarios:
            assert "legal_actions" in expected
            assert "blocked_actions" in expected
            assert "goal_direction" in expected

    def test_corner_a1_blocked_actions(self):
        scenarios = build_one_turn_scenarios()
        for name, state, expected in scenarios:
            if name == "corner_A1":
                assert "UP" in expected["blocked_actions"]
                assert "LEFT" in expected["blocked_actions"]
                assert "DOWN" in expected["legal_actions"]
                assert "RIGHT" in expected["legal_actions"]
                break

    def test_wall_beside_has_wall(self):
        scenarios = build_one_turn_scenarios()
        for name, state, expected in scenarios:
            if name == "wall_beside":
                assert len(state.walls) == 1
                assert Position(1, 1) in state.walls
                break

    def test_low_health_scenario_exists(self):
        scenarios = build_one_turn_scenarios()
        names = [s[0] for s in scenarios]
        assert "low_health" in names


class TestMultiTurnEpisodes:
    def test_count_at_least_3(self):
        episodes = build_multi_turn_episodes()
        assert len(episodes) >= 3

    def test_all_have_optimal_path(self):
        episodes = build_multi_turn_episodes()
        for name, state, config in episodes:
            assert "optimal_path_length" in config
            assert config["optimal_path_length"] > 0

    def test_all_have_max_turns(self):
        episodes = build_multi_turn_episodes()
        for name, state, config in episodes:
            assert "max_turns" in config
            assert config["max_turns"] >= 5


class TestStrategyScenarios:
    def test_all_four_strategies_present(self):
        scenarios = build_strategy_scenarios()
        assert "safe" in scenarios
        assert "speedrun" in scenarios
        assert "reward_max" in scenarios
        assert "adaptive" in scenarios

    def test_each_strategy_has_at_least_one(self):
        scenarios = build_strategy_scenarios()
        for strat, episodes in scenarios.items():
            assert len(episodes) >= 1, f"{strat} has no scenarios"

    def test_safe_scenarios_have_hazards_or_enemies(self):
        scenarios = build_strategy_scenarios()
        for name, state, config in scenarios["safe"]:
            has_danger = len(state.hazards) > 0 or len(state.enemies) > 0
            assert has_danger, f"safe scenario {name} has no hazards/enemies"


class TestClassifyLatency:
    def test_fast(self):
        assert classify_latency(500) == "FAST"
        assert classify_latency(1999) == "FAST"

    def test_acceptable(self):
        assert classify_latency(2000) == "ACCEPTABLE"
        assert classify_latency(4999) == "ACCEPTABLE"

    def test_slow(self):
        assert classify_latency(5000) == "SLOW"
        assert classify_latency(9999) == "SLOW"

    def test_very_slow(self):
        assert classify_latency(10000) == "VERY_SLOW"
        assert classify_latency(50000) == "VERY_SLOW"


class TestLatencyDistribution:
    def test_empty(self):
        ld = LatencyDistribution(model="test")
        assert ld.count == 0
        assert ld.avg_ms == 0.0

    def test_single_value(self):
        ld = LatencyDistribution(model="test", latencies=[1500])
        assert ld.count == 1
        assert ld.avg_ms == 1500.0
        assert ld.p50_ms == 1500.0

    def test_classify(self):
        ld = LatencyDistribution(model="test", latencies=[500, 3000, 7000, 15000])
        cls = ld.classify()
        assert cls["FAST"] == 1
        assert cls["ACCEPTABLE"] == 1
        assert cls["SLOW"] == 1
        assert cls["VERY_SLOW"] == 1

    def test_to_dict(self):
        ld = LatencyDistribution(model="m1", latencies=[1000, 2000])
        d = ld.to_dict()
        assert d["model"] == "m1"
        assert d["count"] == 2
        assert "classification" in d


class TestModelOneTurnAgg:
    def test_rates(self):
        agg = ModelOneTurnAgg(model="test", total_scenarios=10,
            parse_success_count=8, legal_action_count=7,
            unsafe_count=1, fallback_count=2, goal_progress_count=5)
        assert agg.parse_success_rate == 0.8
        assert agg.legal_action_rate == 0.7
        assert agg.unsafe_rate == 0.1
        assert agg.fallback_rate == 0.2
        assert agg.goal_progress_rate == 0.5

    def test_latency_stats(self):
        agg = ModelOneTurnAgg(model="test", latencies=[100, 200, 300, 400])
        assert agg.avg_latency_ms == 250.0
        assert agg.p50_latency_ms == 300
        assert agg.max_latency_ms == 400


class TestModelMultiTurnAgg:
    def test_goal_rate(self):
        agg = ModelMultiTurnAgg(model="test", total_episodes=3, goals_reached=2)
        assert agg.goal_completion_rate == 2 / 3

    def test_empty(self):
        agg = ModelMultiTurnAgg(model="test")
        assert agg.goal_completion_rate == 0.0
        assert agg.avg_path_efficiency == 0.0


class TestReadinessScore:
    def test_total_score(self):
        rs = ReadinessScore(model="test", safety_score=0.9,
            goal_score=0.8, efficiency_score=0.7,
            fallback_score=0.9, oscillation_score=1.0, latency_score=0.5)
        total = rs.total_score
        assert 0.0 <= total <= 1.0

    def test_grade_a(self):
        rs = ReadinessScore(model="test", safety_score=1.0,
            goal_score=1.0, efficiency_score=1.0,
            fallback_score=1.0, oscillation_score=1.0, latency_score=1.0)
        assert rs.grade == "A"

    def test_grade_f(self):
        rs = ReadinessScore(model="test", safety_score=0.0,
            goal_score=0.0, efficiency_score=0.0,
            fallback_score=0.0, oscillation_score=0.0, latency_score=0.0)
        assert rs.grade == "F"

    def test_to_dict(self):
        rs = ReadinessScore(model="m1", safety_score=0.9, goal_score=0.8)
        d = rs.to_dict()
        assert d["model"] == "m1"
        assert "SPATHODEA_INTERNAL_READINESS_SCORE" in d
        assert "component_scores" in d
        assert "weights" in d


class TestOneTurnMetrics:
    def test_to_dict(self):
        m = OneTurnMetrics(scenario_name="test", model="m1", parse_success=True,
            legal_action=True, parsed_action="RIGHT")
        d = m.to_dict()
        assert d["scenario"] == "test"
        assert d["parse_success"] is True
        assert d["legal_action"] is True


class TestMultiTurnMetrics:
    def test_path_efficiency(self):
        m = MultiTurnMetrics(optimal_path_length=8, turns_to_goal=10)
        assert m.path_efficiency_ratio == 0.8

    def test_zero_turns(self):
        m = MultiTurnMetrics(optimal_path_length=8, turns_to_goal=0)
        assert m.path_efficiency_ratio == 0.0


class TestStrategyMetrics:
    def test_to_dict(self):
        m = StrategyMetrics(strategy="safe", scenario_name="test",
            goal_reached=True, score=100, turns=5)
        d = m.to_dict()
        assert d["strategy"] == "safe"
        assert d["goal_reached"] is True
        assert d["score"] == 100


class TestNavigationContextIntegration:
    def test_context_builds_for_scenarios(self):
        scenarios = build_one_turn_scenarios()
        builder = NavigationContextBuilder()
        for name, state, expected in scenarios:
            ctx = builder.build(state, strategy="exploration")
            assert ctx.current_position == state.agent_pos.to_label()
            assert len(ctx.legal_actions) > 0
            assert ctx.goal == (state.goal.to_label() if state.goal else None)

    def test_prompt_builds_for_scenarios(self):
        scenarios = build_one_turn_scenarios()
        builder = NavigationContextBuilder()
        for name, state, expected in scenarios:
            ctx = builder.build(state, strategy="exploration")
            prompt = build_grounded_nav_prompt(ctx)
            assert "LEGAL_ACTIONS" in prompt
            assert "GOAL_DIRECTION" in prompt
            assert state.agent_pos.to_label() in prompt


class TestOscillationDetectorIntegration:
    def test_detects_ababa(self):
        det = OscillationDetector()
        det.check("A", "WAIT", 0)
        det.check("B", "DOWN", 1)
        det.check("A", "UP", 2)
        det.check("B", "DOWN", 3)
        det.check("A", "UP", 4)
        assert det.total_events == 3
        assert det.repeated_loop_count == 1

    def test_no_false_positive(self):
        det = OscillationDetector()
        det.check("A", "WAIT", 0)
        det.check("B", "RIGHT", 1)
        det.check("C", "RIGHT", 2)
        det.check("D", "RIGHT", 3)
        assert det.total_events == 0


class TestPathfinderIntegration:
    def test_astar_finds_path(self):
        state = GameState(width=5, height=5, agent_pos=Position(0, 0),
            goal=Position(4, 4))
        pf = Pathfinder()
        result = pf.astar(state, Position(0, 0), Position(4, 4))
        assert result.found
        assert result.length == 8

    def test_wall_blocks_path(self):
        state = GameState(width=5, height=5, agent_pos=Position(0, 0),
            walls={Position(1, 0), Position(1, 1), Position(1, 2), Position(1, 3), Position(1, 4)},
            goal=Position(4, 0))
        pf = Pathfinder()
        result = pf.astar(state, Position(0, 0), Position(4, 0))
        assert not result.found

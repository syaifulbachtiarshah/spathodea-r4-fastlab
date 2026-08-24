"""
SPATHODEA R4 FASTLAB — Phase 2F Part 2 Game↔BUZZ Bridge Tests
Deterministic offline tests for the bridge between GameAgentAdapter and BUZZ.

20 test scenarios:
    1.  Valid UP action
    2.  Valid DOWN action
    3.  Valid LEFT action
    4.  Valid RIGHT action
    5.  JSON action output
    6.  Malformed JSON
    7.  Invalid action word
    8.  Conflicting actions
    9.  Wall collision safety gate
   10.  Out-of-bounds safety gate
   11.  Locked door safety gate
   12.  Provider timeout
   13.  Provider unavailable
   14.  Contract mismatch
   15.  Fallback to pathfinder
   16.  Fallback to WAIT
   17.  Goal reached
   18.  Coin collection
   19.  Key collection
   20.  Hazard contact
   21.  Max-turn termination
   22.  Strategy propagation
   23.  Full simulated game episode

All tests are deterministic — no randomness, no network, no LLM.

Run with: python -m unittest tests.test_game_buzz_bridge -v
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.game_state import GameState, Position
from game.action_schema import Action
from game.strategy import Strategy, StrategyProfile
from game.pathfinder import Pathfinder
from game.game_agent_adapter import GameAgentAdapter, PlanningContext
from game.action_parser import ActionParser, ActionParseResult
from game.buzz_game_bridge import (
    BuzzGameBridge, BridgeConfig, BridgeResult, SimulatedProvider,
)
from game.game_simulator import GameSimulator, SimulationMetrics, SimConfig
from game.turn_controller import (
    TurnController, TurnLogEntry, ControllerConfig, EpisodeResult,
)
from adapters.provider_request import ProviderRequest, CONTRACT_VERSION
from adapters.provider_response import ProviderResponse


# =============================================================================
# Helpers
# =============================================================================

def _corridor_state():
    """5x1 corridor: agent A1, goal E1."""
    return GameState(
        width=5, height=1,
        agent_pos=Position.from_label("A1"),
        goal=Position.from_label("E1"),
    )


def _grid_3x3_state():
    """3x3 open grid: agent A1, goal C3."""
    return GameState(
        width=3, height=3,
        agent_pos=Position.from_label("A1"),
        goal=Position.from_label("C3"),
    )


def _bridge_with_action(action_text: str) -> tuple:
    """Create bridge + provider pre-loaded with a specific action response."""
    provider = SimulatedProvider()
    provider.set_action_response(action_text)
    bridge = BuzzGameBridge(config=BridgeConfig(), provider=provider)
    return bridge, provider


# =============================================================================
# Test 1: Valid UP Action
# =============================================================================

class TestValidUP(unittest.TestCase):
    """Provider returns 'UP' — accepted and applied."""

    def test_up_parsed_and_applied(self):
        state = GameState(
            width=3, height=3,
            agent_pos=Position.from_label("B2"),
            goal=Position.from_label("B1"),
        )
        bridge, provider = _bridge_with_action("UP")
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        self.assertEqual(result.action, Action.UP)
        self.assertEqual(result.source, "provider")
        self.assertFalse(result.fallback_used)


# =============================================================================
# Test 2: Valid DOWN Action
# =============================================================================

class TestValidDOWN(unittest.TestCase):
    """Provider returns 'DOWN' — accepted and applied."""

    def test_down_parsed_and_applied(self):
        state = GameState(
            width=3, height=3,
            agent_pos=Position.from_label("B1"),
            goal=Position.from_label("B3"),
        )
        bridge, provider = _bridge_with_action("DOWN")
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        self.assertEqual(result.action, Action.DOWN)
        self.assertEqual(result.source, "provider")
        self.assertFalse(result.fallback_used)


# =============================================================================
# Test 3: Valid LEFT Action
# =============================================================================

class TestValidLEFT(unittest.TestCase):
    """Provider returns 'LEFT' — accepted and applied."""

    def test_left_parsed_and_applied(self):
        state = GameState(
            width=3, height=3,
            agent_pos=Position.from_label("B2"),
            goal=Position.from_label("A2"),
        )
        bridge, provider = _bridge_with_action("LEFT")
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        self.assertEqual(result.action, Action.LEFT)
        self.assertEqual(result.source, "provider")
        self.assertFalse(result.fallback_used)


# =============================================================================
# Test 4: Valid RIGHT Action
# =============================================================================

class TestValidRIGHT(unittest.TestCase):
    """Provider returns 'RIGHT' — accepted and applied."""

    def test_right_parsed_and_applied(self):
        state = _corridor_state()
        bridge, provider = _bridge_with_action("RIGHT")
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        self.assertEqual(result.action, Action.RIGHT)
        self.assertEqual(result.source, "provider")
        self.assertFalse(result.fallback_used)


# =============================================================================
# Test 5: JSON Action Output
# =============================================================================

class TestJSONAction(unittest.TestCase):
    """Provider returns JSON object with action field."""

    def test_json_object_parsed(self):
        state = _corridor_state()
        bridge, provider = _bridge_with_action('{"action": "RIGHT"}')
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        self.assertEqual(result.action, Action.RIGHT)
        self.assertEqual(result.source, "provider")
        self.assertEqual(result.parse_result.method, "json")

    def test_fenced_json_parsed(self):
        state = _corridor_state()
        bridge, provider = _bridge_with_action('```json\n{"action": "RIGHT"}\n```')
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        self.assertEqual(result.action, Action.RIGHT)
        self.assertEqual(result.parse_result.method, "fenced_json")

    def test_case_insensitive_json(self):
        state = _corridor_state()
        bridge, provider = _bridge_with_action('{"action": "right"}')
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        self.assertEqual(result.action, Action.RIGHT)


# =============================================================================
# Test 6: Malformed JSON
# =============================================================================

class TestMalformedJSON(unittest.TestCase):
    """Provider returns malformed JSON — triggers fallback."""

    def test_malformed_json_fallback(self):
        state = _corridor_state()
        bridge, provider = _bridge_with_action('{"action": "RIGHT"')  # Missing closing brace
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        self.assertTrue(result.fallback_used)
        self.assertIn("Malformed JSON", result.fallback_reason)

    def test_json_no_action_key(self):
        state = _corridor_state()
        bridge, provider = _bridge_with_action('{"move": "RIGHT"}')
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        # Has braces, parses as JSON, but no "action" key — tries plain text
        # "RIGHT" is in the text so plain_text parser finds it
        self.assertEqual(result.action, Action.RIGHT)


# =============================================================================
# Test 7: Invalid Action Word
# =============================================================================

class TestInvalidAction(unittest.TestCase):
    """Provider returns invalid action word — triggers fallback."""

    def test_unknown_action(self):
        state = _corridor_state()
        bridge, provider = _bridge_with_action("TELEPORT")
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        self.assertTrue(result.fallback_used)
        # Fallback should produce a valid action
        self.assertIn(result.action, list(Action))

    def test_empty_output(self):
        state = _corridor_state()
        bridge, provider = _bridge_with_action("")
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        self.assertTrue(result.fallback_used)
        self.assertIn("Empty", result.fallback_reason)

    def test_html_rejected(self):
        state = _corridor_state()
        bridge, provider = _bridge_with_action("<html><body>UP</body></html>")
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        self.assertTrue(result.fallback_used)
        self.assertIn("HTML", result.fallback_reason)

    def test_traceback_rejected(self):
        state = _corridor_state()
        bridge, provider = _bridge_with_action(
            'Traceback (most recent call last):\n  File "x.py", line 1\nError'
        )
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        self.assertTrue(result.fallback_used)
        self.assertIn("traceback", result.fallback_reason.lower())


# =============================================================================
# Test 8: Conflicting Actions
# =============================================================================

class TestConflictingActions(unittest.TestCase):
    """Provider returns multiple conflicting actions — triggers fallback."""

    def test_multiple_actions_rejected(self):
        state = _corridor_state()
        bridge, provider = _bridge_with_action("I recommend UP but maybe DOWN is better")
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        self.assertTrue(result.fallback_used)
        self.assertIn("conflicting", result.fallback_reason.lower())


# =============================================================================
# Test 9: Wall Collision Safety Gate
# =============================================================================

class TestWallCollision(unittest.TestCase):
    """Provider suggests action into a wall — safety gate redirects."""

    def test_wall_blocked(self):
        state = GameState(
            width=3, height=1,
            agent_pos=Position.from_label("A1"),
            walls={Position.from_label("B1")},
            goal=Position.from_label("C1"),
        )
        bridge, provider = _bridge_with_action("RIGHT")
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        # RIGHT leads to wall B1 — safety gate should block
        self.assertTrue(result.fallback_used)
        self.assertIn("wall", result.fallback_reason.lower())
        self.assertNotEqual(result.action, Action.RIGHT)


# =============================================================================
# Test 10: Out-of-Bounds Safety Gate
# =============================================================================

class TestOutOfBounds(unittest.TestCase):
    """Provider suggests action that goes off the grid."""

    def test_left_at_edge(self):
        state = GameState(
            width=3, height=1,
            agent_pos=Position.from_label("A1"),
            goal=Position.from_label("C1"),
        )
        bridge, provider = _bridge_with_action("LEFT")
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        self.assertTrue(result.fallback_used)
        self.assertIn("out of bounds", result.fallback_reason.lower())

    def test_up_at_top_edge(self):
        state = GameState(
            width=3, height=3,
            agent_pos=Position.from_label("B1"),
            goal=Position.from_label("B3"),
        )
        bridge, provider = _bridge_with_action("UP")
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        self.assertTrue(result.fallback_used)
        self.assertIn("out of bounds", result.fallback_reason.lower())


# =============================================================================
# Test 11: Locked Door Safety Gate
# =============================================================================

class TestLockedDoor(unittest.TestCase):
    """Provider suggests action into a locked door — safety gate blocks."""

    def test_locked_door_blocked(self):
        key_pos = Position.from_label("C1")
        door_pos = Position.from_label("B1")
        state = GameState(
            width=3, height=1,
            agent_pos=Position.from_label("A1"),
            keys={key_pos},
            doors={door_pos: key_pos},
            goal=Position.from_label("C1"),
        )
        bridge, provider = _bridge_with_action("RIGHT")
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        self.assertTrue(result.fallback_used)
        self.assertIn("locked door", result.fallback_reason.lower())


# =============================================================================
# Test 12: Provider Timeout
# =============================================================================

class TestProviderTimeout(unittest.TestCase):
    """Simulated provider timeout — fallback to pathfinder."""

    def test_timeout_triggers_fallback(self):
        state = _corridor_state()
        provider = SimulatedProvider()
        provider.set_timeout(True)
        bridge = BuzzGameBridge(config=BridgeConfig(), provider=provider)
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        self.assertTrue(result.fallback_used)
        self.assertIn("timeout", result.fallback_reason.lower())
        # Should still get a valid fallback action
        self.assertIn(result.action, list(Action))
        self.assertIn(result.source, ["fallback_pathfinder", "fallback_wait"])


# =============================================================================
# Test 13: Provider Unavailable
# =============================================================================

class TestProviderUnavailable(unittest.TestCase):
    """Simulated provider unavailability — fallback to pathfinder."""

    def test_unavailable_triggers_fallback(self):
        state = _corridor_state()
        provider = SimulatedProvider()
        provider.set_unavailable(True)
        bridge = BuzzGameBridge(config=BridgeConfig(), provider=provider)
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        self.assertTrue(result.fallback_used)
        self.assertIn("unavailable", result.fallback_reason.lower())
        self.assertIn(result.source, ["fallback_pathfinder", "fallback_wait"])


# =============================================================================
# Test 14: Contract Mismatch
# =============================================================================

class TestContractMismatch(unittest.TestCase):
    """Simulated contract version mismatch — do not trust provider output."""

    def test_mismatch_triggers_fallback(self):
        state = _corridor_state()
        provider = SimulatedProvider()
        provider.set_contract_mismatch(True)
        bridge = BuzzGameBridge(config=BridgeConfig(), provider=provider)
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        self.assertTrue(result.fallback_used)
        self.assertIn("contract mismatch", result.fallback_reason.lower())
        # Should use local pathfinder only
        self.assertIn(result.source, ["fallback_pathfinder", "fallback_wait"])


# =============================================================================
# Test 15: Fallback to Pathfinder
# =============================================================================

class TestFallbackPathfinder(unittest.TestCase):
    """When provider fails, fallback should use pathfinder toward goal."""

    def test_pathfinder_fallback_moves_toward_goal(self):
        state = _corridor_state()  # A1 → E1
        provider = SimulatedProvider()
        provider.set_timeout(True)
        bridge = BuzzGameBridge(config=BridgeConfig(), provider=provider)
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        # Pathfinder should recommend RIGHT (toward E1)
        self.assertEqual(result.action, Action.RIGHT)
        self.assertEqual(result.source, "fallback_pathfinder")


# =============================================================================
# Test 16: Fallback to WAIT
# =============================================================================

class TestFallbackWait(unittest.TestCase):
    """When pathfinder cannot find path, fallback to WAIT."""

    def test_wait_fallback_when_unreachable(self):
        state = GameState(
            width=3, height=1,
            agent_pos=Position.from_label("A1"),
            walls={Position.from_label("B1")},
            goal=Position.from_label("C1"),
        )
        provider = SimulatedProvider()
        provider.set_timeout(True)
        bridge = BuzzGameBridge(config=BridgeConfig(), provider=provider)
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        result = bridge.request_action(state, ctx)
        self.assertEqual(result.action, Action.WAIT)
        self.assertEqual(result.source, "fallback_wait")
        self.assertTrue(result.fallback_used)


# =============================================================================
# Test 17: Goal Reached
# =============================================================================

class TestGoalReached(unittest.TestCase):
    """Agent reaches goal through simulator."""

    def test_goal_reached_in_simulator(self):
        state = GameState(
            width=2, height=1,
            agent_pos=Position.from_label("A1"),
            goal=Position.from_label("B1"),
        )
        sim = GameSimulator(state)
        result = sim.apply_action(Action.RIGHT)

        self.assertTrue(result.success)
        self.assertTrue(sim.is_finished)
        self.assertTrue(sim.metrics.goal_reached)
        self.assertEqual(sim.metrics.final_score, 100)  # goal_reward default


# =============================================================================
# Test 18: Coin Collection
# =============================================================================

class TestCoinCollection(unittest.TestCase):
    """Agent collects a coin."""

    def test_coin_collected(self):
        state = GameState(
            width=3, height=1,
            agent_pos=Position.from_label("A1"),
            coins={Position.from_label("B1")},
            goal=Position.from_label("C1"),
        )
        sim = GameSimulator(state)
        result = sim.apply_action(Action.RIGHT)

        self.assertTrue(result.success)
        self.assertEqual(result.reward_gained, 10)
        self.assertEqual(sim.metrics.coins_collected, 1)
        self.assertIn("coin@B1", result.items_collected)

    def test_coin_not_double_collected(self):
        state = GameState(
            width=3, height=1,
            agent_pos=Position.from_label("A1"),
            coins={Position.from_label("B1")},
            goal=Position.from_label("C1"),
        )
        sim = GameSimulator(state)
        sim.apply_action(Action.RIGHT)   # collect coin at B1
        sim.apply_action(Action.LEFT)    # back to A1
        sim.apply_action(Action.RIGHT)   # revisit B1

        # Should only be collected once
        self.assertEqual(sim.metrics.coins_collected, 1)


# =============================================================================
# Test 19: Key Collection
# =============================================================================

class TestKeyCollection(unittest.TestCase):
    """Agent collects a key."""

    def test_key_collected(self):
        key_pos = Position.from_label("B1")
        door_pos = Position.from_label("C1")
        state = GameState(
            width=4, height=1,
            agent_pos=Position.from_label("A1"),
            keys={key_pos},
            doors={door_pos: key_pos},
            goal=Position.from_label("D1"),
        )
        sim = GameSimulator(state)
        result = sim.apply_action(Action.RIGHT)  # A1 → B1 (collect key)

        self.assertTrue(result.success)
        self.assertEqual(sim.metrics.keys_collected, 1)
        self.assertIn("key@B1", result.items_collected)
        # Now door should be openable
        self.assertTrue(sim.state.is_walkable(door_pos))


# =============================================================================
# Test 20: Hazard Contact
# =============================================================================

class TestHazardContact(unittest.TestCase):
    """Agent steps on hazard — takes damage."""

    def test_hazard_damage(self):
        state = GameState(
            width=3, height=1,
            agent_pos=Position.from_label("A1"),
            hazards={Position.from_label("B1")},
            goal=Position.from_label("C1"),
            health=100,
        )
        sim = GameSimulator(state)
        result = sim.apply_action(Action.RIGHT)  # step on hazard

        self.assertTrue(result.success)
        self.assertEqual(result.damage_taken, 20)
        self.assertEqual(sim.state.health, 80)
        self.assertEqual(sim.metrics.hazard_contacts, 1)

    def test_enemy_damage(self):
        state = GameState(
            width=3, height=1,
            agent_pos=Position.from_label("A1"),
            enemies={Position.from_label("B1")},
            goal=Position.from_label("C1"),
            health=100,
        )
        sim = GameSimulator(state)
        result = sim.apply_action(Action.RIGHT)  # step on enemy

        self.assertTrue(result.success)
        self.assertEqual(result.damage_taken, 30)
        self.assertEqual(sim.state.health, 70)
        self.assertEqual(sim.metrics.enemy_contacts, 1)


# =============================================================================
# Test 21: Max-Turn Termination
# =============================================================================

class TestMaxTurnTermination(unittest.TestCase):
    """Episode terminates when max_turns exceeded."""

    def test_max_turns_stops_episode(self):
        state = GameState(
            width=10, height=1,
            agent_pos=Position.from_label("A1"),
            goal=Position.from_label("J1"),
        )
        provider = SimulatedProvider()
        provider.set_action_response("RIGHT")
        config = ControllerConfig(max_turns=3, strategy="speedrun", provider="mock")
        controller = TurnController(state, config=config, provider=provider)

        result = controller.run_episode()
        self.assertEqual(result.termination_reason, "max_turns_exceeded")
        self.assertEqual(result.metrics.total_turns, 3)
        self.assertFalse(result.metrics.goal_reached)


# =============================================================================
# Test 22: Strategy Propagation
# =============================================================================

class TestStrategyPropagation(unittest.TestCase):
    """Strategy is correctly propagated through the pipeline."""

    def test_strategy_in_request_metadata(self):
        state = _corridor_state()
        bridge = BuzzGameBridge(config=BridgeConfig())
        adapter = GameAgentAdapter(strategy_profile="safe")
        ctx = adapter.plan(state)

        request = bridge.build_request(state, ctx)
        self.assertEqual(request.metadata["strategy"], "safe")
        self.assertEqual(request.metadata["source"], "SPATHODEA_GAME")
        self.assertEqual(request.metadata["task_intent"], "game_navigation")

    def test_strategy_in_turn_log(self):
        state = _corridor_state()
        provider = SimulatedProvider()
        provider.set_action_response("RIGHT")
        config = ControllerConfig(max_turns=1, strategy="reward_max")
        controller = TurnController(state, config=config, provider=provider)

        controller.execute_turn()
        # The adapter uses the configured strategy
        self.assertEqual(controller.adapter.strategy.profile, StrategyProfile.REWARD_MAX)


# =============================================================================
# Test 23: Full Simulated Game Episode
# =============================================================================

class TestFullEpisode(unittest.TestCase):
    """Complete game episode with provider responding correctly."""

    def test_full_episode_reaches_goal(self):
        """5x1 corridor, provider always says RIGHT, should reach goal in 4 turns."""
        state = _corridor_state()  # A1 → E1
        provider = SimulatedProvider()
        provider.set_action_response("RIGHT")
        config = ControllerConfig(max_turns=10, strategy="speedrun")
        controller = TurnController(state, config=config, provider=provider)

        result = controller.run_episode()

        self.assertEqual(result.termination_reason, "goal_reached")
        self.assertTrue(result.metrics.goal_reached)
        self.assertEqual(result.metrics.total_turns, 4)
        self.assertEqual(result.metrics.final_position, "E1")
        self.assertEqual(result.metrics.final_score, 100)  # goal_reward
        self.assertEqual(result.metrics.fallback_count, 0)
        self.assertEqual(len(result.turn_log), 4)

    def test_full_episode_with_coin(self):
        """Corridor with coin — collect coin then reach goal."""
        state = GameState(
            width=3, height=1,
            agent_pos=Position.from_label("A1"),
            coins={Position.from_label("B1")},
            goal=Position.from_label("C1"),
        )
        provider = SimulatedProvider()
        provider.set_action_response("RIGHT")
        config = ControllerConfig(max_turns=10, strategy="speedrun")
        controller = TurnController(state, config=config, provider=provider)

        result = controller.run_episode()

        self.assertTrue(result.metrics.goal_reached)
        self.assertEqual(result.metrics.coins_collected, 1)
        self.assertEqual(result.metrics.final_score, 110)  # 10 (coin) + 100 (goal)
        self.assertEqual(result.metrics.total_turns, 2)

    def test_episode_performance_metrics(self):
        """Performance metrics are separately tracked."""
        state = _corridor_state()
        provider = SimulatedProvider()
        provider.set_action_response("RIGHT")
        config = ControllerConfig(max_turns=10, strategy="speedrun")
        controller = TurnController(state, config=config, provider=provider)

        result = controller.run_episode()

        # All timing metrics should be non-negative
        self.assertGreaterEqual(result.total_pathfinder_ms, 0.0)
        self.assertGreaterEqual(result.total_bridge_ms, 0.0)
        self.assertGreaterEqual(result.total_turn_ms, 0.0)

        # Each turn should have timing
        for entry in result.turn_log:
            self.assertGreaterEqual(entry.pathfinder_ms, 0.0)
            self.assertGreaterEqual(entry.bridge_processing_ms, 0.0)
            self.assertGreaterEqual(entry.turn_processing_ms, 0.0)

    def test_episode_agent_death(self):
        """Agent dies from repeated hazard contact."""
        state = GameState(
            width=5, height=1,
            agent_pos=Position.from_label("A1"),
            hazards={
                Position.from_label("B1"),
                Position.from_label("C1"),
                Position.from_label("D1"),
            },
            goal=Position.from_label("E1"),
            health=50,
        )
        provider = SimulatedProvider()
        provider.set_action_response("RIGHT")
        config = ControllerConfig(max_turns=10, strategy="speedrun")
        sim_config = SimConfig(hazard_damage=20)
        config.sim_config = sim_config
        controller = TurnController(state, config=config, provider=provider)

        result = controller.run_episode()

        # 50 health, 20 damage per hazard: dies after 3 hazard contacts (at 50-20-20-20 = -10)
        self.assertEqual(result.termination_reason, "agent_dead")
        self.assertFalse(result.metrics.goal_reached)
        self.assertLessEqual(result.metrics.final_health, 0)


# =============================================================================
# Test: Action Parser Unit Tests
# =============================================================================

class TestActionParserUnit(unittest.TestCase):
    """Unit tests for ActionParser edge cases."""

    def setUp(self):
        self.parser = ActionParser()

    def test_plain_wait(self):
        r = self.parser.parse("WAIT")
        self.assertTrue(r.success)
        self.assertEqual(r.action, Action.WAIT)
        self.assertEqual(r.method, "plain_text")

    def test_case_insensitive(self):
        r = self.parser.parse("left")
        self.assertTrue(r.success)
        self.assertEqual(r.action, Action.LEFT)

    def test_json_with_extra_fields(self):
        r = self.parser.parse('{"action": "DOWN", "confidence": 0.9}')
        self.assertTrue(r.success)
        self.assertEqual(r.action, Action.DOWN)

    def test_future_action_rejected(self):
        r = self.parser.parse("ATTACK")
        self.assertFalse(r.success)
        self.assertTrue(r.is_future_action)

    def test_whitespace_only(self):
        r = self.parser.parse("   \n\t  ")
        self.assertFalse(r.success)
        self.assertIn("Empty", r.error)


# =============================================================================
# Test: Bridge Request Building
# =============================================================================

class TestBridgeRequestBuilding(unittest.TestCase):
    """Verify ProviderRequest is correctly built from game context."""

    def test_request_has_correct_metadata(self):
        state = GameState(
            width=5, height=5,
            agent_pos=Position.from_label("C3"),
            coins={Position.from_label("A1")},
            enemies={Position.from_label("D4")},
            hazards={Position.from_label("E5")},
            goal=Position.from_label("E5"),
            turn=7,
        )
        bridge = BuzzGameBridge(config=BridgeConfig(provider_preference="openai"))
        adapter = GameAgentAdapter(strategy_profile="adaptive")
        ctx = adapter.plan(state)

        request = bridge.build_request(state, ctx)

        self.assertEqual(request.metadata["source"], "SPATHODEA_GAME")
        self.assertEqual(request.metadata["task_intent"], "game_navigation")
        self.assertEqual(request.metadata["turn"], 7)
        self.assertEqual(request.metadata["agent_position"], "C3")
        self.assertEqual(request.metadata["strategy"], "adaptive")
        self.assertEqual(request.metadata["grid_width"], 5)
        self.assertEqual(request.metadata["grid_height"], 5)
        self.assertEqual(request.metadata["known_rewards"], 1)
        self.assertEqual(request.metadata["known_hazards"], 1)
        self.assertEqual(request.metadata["known_enemies"], 1)
        self.assertEqual(request.metadata["goal"], "E5")

    def test_request_uses_generate_task_type(self):
        """task_type must be 'generate' (v0.2.0 contract); game intent lives in metadata."""
        state = _corridor_state()
        bridge = BuzzGameBridge(config=BridgeConfig())
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        request = bridge.build_request(state, ctx)
        self.assertEqual(request.task_type, "generate")
        self.assertEqual(request.execution_mode, "sync")
        self.assertEqual(request.metadata["task_intent"], "game_navigation")

    def test_request_contract_compatible(self):
        """Built request must pass ProviderRequest.validate() with zero errors."""
        state = _corridor_state()
        bridge = BuzzGameBridge(config=BridgeConfig())
        adapter = GameAgentAdapter(strategy_profile="speedrun")
        ctx = adapter.plan(state)

        request = bridge.build_request(state, ctx)
        errors = request.validate()
        self.assertEqual(errors, [])
        # Verify canonical mapping
        self.assertEqual(request.task_type, "generate")
        self.assertEqual(request.execution_mode, "sync")
        self.assertEqual(request.metadata["task_intent"], "game_navigation")
        self.assertEqual(request.metadata["source"], "SPATHODEA_GAME")


# =============================================================================
# Test: Simulator Edge Cases
# =============================================================================

class TestSimulatorEdgeCases(unittest.TestCase):
    """Edge cases for the game simulator."""

    def test_action_after_finished(self):
        state = GameState(
            width=2, height=1,
            agent_pos=Position.from_label("A1"),
            goal=Position.from_label("B1"),
        )
        sim = GameSimulator(state)
        sim.apply_action(Action.RIGHT)  # reach goal

        result = sim.apply_action(Action.LEFT)  # try after finish
        self.assertFalse(result.success)
        self.assertIn("already finished", result.reason.lower())

    def test_wait_increments_turn(self):
        state = _corridor_state()
        sim = GameSimulator(state)
        sim.apply_action(Action.WAIT)

        self.assertEqual(sim.state.turn, 1)
        self.assertEqual(sim.metrics.turns_waited, 1)

    def test_wall_collision_invalid(self):
        state = GameState(
            width=3, height=1,
            agent_pos=Position.from_label("A1"),
            walls={Position.from_label("B1")},
            goal=Position.from_label("C1"),
        )
        sim = GameSimulator(state)
        result = sim.apply_action(Action.RIGHT)

        self.assertFalse(result.success)
        self.assertEqual(sim.metrics.invalid_actions, 1)
        # Agent should not have moved
        self.assertEqual(sim.state.agent_pos, Position.from_label("A1"))


# =============================================================================
# Test: Turn Controller Integration
# =============================================================================

class TestTurnControllerIntegration(unittest.TestCase):
    """Integration tests for the full turn pipeline."""

    def test_single_turn_execution(self):
        state = _corridor_state()
        provider = SimulatedProvider()
        provider.set_action_response("RIGHT")
        config = ControllerConfig(max_turns=10, strategy="speedrun")
        controller = TurnController(state, config=config, provider=provider)

        entry = controller.execute_turn()

        self.assertEqual(entry.position_before, "A1")
        self.assertEqual(entry.position_after, "B1")
        self.assertEqual(entry.final_action, "RIGHT")
        self.assertFalse(entry.fallback_used)
        self.assertEqual(entry.status, "ok")

    def test_turn_log_accumulates(self):
        state = _corridor_state()
        provider = SimulatedProvider()
        provider.set_action_response("RIGHT")
        config = ControllerConfig(max_turns=10, strategy="speedrun")
        controller = TurnController(state, config=config, provider=provider)

        controller.execute_turn()
        controller.execute_turn()

        self.assertEqual(len(controller.turn_log), 2)
        self.assertEqual(controller.turn_log[0].position_before, "A1")
        self.assertEqual(controller.turn_log[1].position_before, "B1")

    def test_serialization(self):
        state = _corridor_state()
        provider = SimulatedProvider()
        provider.set_action_response("RIGHT")
        config = ControllerConfig(max_turns=5, strategy="speedrun")
        controller = TurnController(state, config=config, provider=provider)

        result = controller.run_episode()
        d = result.to_dict()

        self.assertIn("metrics", d)
        self.assertIn("turn_log", d)
        self.assertIn("termination_reason", d)
        self.assertIn("total_pathfinder_ms", d)
        self.assertIn("total_bridge_ms", d)
        self.assertIn("total_turn_ms", d)


# =============================================================================
# Runner
# =============================================================================

def run_bridge_tests() -> dict:
    """Run all bridge tests and return structured results."""
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
        "success": len(result.failures) == 0 and len(result.errors) == 0,
    }


if __name__ == "__main__":
    unittest.main(verbosity=2)

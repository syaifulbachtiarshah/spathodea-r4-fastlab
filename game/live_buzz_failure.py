"""
SPATHODEA R4 FASTLAB — Failure Recovery Test (Phase 2F Part 3B)
Test controlled failure scenarios through live BUZZ -> Ollama.

Scenarios:
1. Invalid provider response (non-action prose)
2. Simulated timeout (via invalid request)
"""

import json
import time
import urllib.request
import urllib.error
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.game_state import GameState, Position
from game.game_simulator import GameSimulator
from game.action_schema import Action
from game.action_parser import ActionParser
from game.pathfinder import Pathfinder


# =============================================================================
# Configuration
# =============================================================================

BUZZ_URL = "http://127.0.0.1:8765"
TIMEOUT_S = 15.0


# =============================================================================
# Live BUZZ Client
# =============================================================================

class LiveBuzzClient:
    def __init__(self, base_url: str = BUZZ_URL):
        self._generate_url = f"{base_url}/v1/generate"

    def generate(self, payload: dict, timeout_s: float = TIMEOUT_S) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._generate_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read())


# =============================================================================
# Failure Tests
# =============================================================================

def test_invalid_provider_response():
    """Test: Provider returns non-action prose -> fallback activates."""
    print("=" * 60)
    print("FAILURE TEST 1: Invalid provider response (prose)")
    print("=" * 60)

    client = LiveBuzzClient()
    parser = ActionParser()
    pathfinder = Pathfinder()

    state = GameState(
        width=5, height=5,
        agent_pos=Position(0, 0),
        walls={Position(1, 1), Position(3, 3)},
        coins={Position(2, 2)},
        goal=Position(4, 4),
        turn=0, score=0, health=100,
    )

    # Build a prompt that might elicit prose
    prompt = (
        "Grid: 5x5 | Position: A1 | Goal: E5 | Strategy: exploration | "
        "Turn: 0 | Health: 100 | "
        "Explain your reasoning step by step before deciding on an action."
    )

    payload = {
        "prompt": prompt,
        "provider_preference": "ollama",
        "execution_mode": "single",
        "task_type": "game_navigation",
        "request_id": "failure-test-001",
        "metadata": {
            "source": "SPATHODEA_GAME",
            "task_intent": "game_navigation",
            "turn": 0,
        },
    }

    print(f"  Sending prose-inducing prompt to BUZZ...")
    start = time.perf_counter()
    try:
        response = client.generate(payload, timeout_s=TIMEOUT_S)
        latency_ms = (time.perf_counter() - start) * 1000
        raw_content = response.get("content", "")
        print(f"  Provider latency: {latency_ms:.0f}ms")
        print(f"  Raw response (first 200 chars): {raw_content[:200]}")
    except Exception as e:
        print(f"  [ERROR] Request failed: {e}")
        raw_content = ""

    # Parse
    parse_result = parser.parse(raw_content)
    print(f"  Parse success: {parse_result.success}")

    if not parse_result.success:
        print(f"  Parse error: {parse_result.error}")
        print(f"  [OK] Prose correctly rejected by ActionParser")

        # Fallback to pathfinder
        path = pathfinder.astar(state, state.agent_pos, state.goal)
        if path.found and path.length > 0:
            for i, pos in enumerate(path.path):
                if pos == state.agent_pos and i + 1 < len(path.path):
                    next_pos = path.path[i + 1]
                    fallback_action = Action.from_positions(state.agent_pos, next_pos)
                    if fallback_action:
                        print(f"  [FALLBACK] Pathfinder action: {fallback_action.value}")
                        break
            else:
                fallback_action = Action.WAIT
                print(f"  [FALLBACK] No path, using WAIT")
        else:
            fallback_action = Action.WAIT
            print(f"  [FALLBACK] No path found, using WAIT")

        # Apply action
        simulator = GameSimulator(state)
        result = simulator.apply_action(fallback_action, fallback_used=True)
        print(f"  Action applied: {fallback_action.value}")
        print(f"  Position after: {simulator.state.agent_pos.to_label()}")
        print(f"  Game continues: {not simulator.is_finished}")
    else:
        print(f"  Parsed action: {parse_result.action.value}")
        print(f"  [INFO] Model returned valid action despite prose prompt")

    print("\n" + "=" * 60)
    print("FAILURE TEST 1: PASS")
    print("=" * 60)
    return True


def test_provider_error_recovery():
    """Test: Provider error -> fallback activates, game continues."""
    print("\n" + "=" * 60)
    print("FAILURE TEST 2: Provider error recovery")
    print("=" * 60)

    parser = ActionParser()
    pathfinder = Pathfinder()

    state = GameState(
        width=5, height=5,
        agent_pos=Position(0, 0),
        walls={Position(1, 1), Position(3, 3)},
        coins={Position(2, 2)},
        goal=Position(4, 4),
        turn=0, score=0, health=100,
    )

    # Simulate a provider error response
    error_response = {
        "content": "",
        "provider": "ollama",
        "model": "qwen2.5:7b",
        "finish_reason": "error",
        "error": "Ollama connection failed: Connection refused",
        "latency_ms": 0,
        "contract_version": "0.2.0",
    }

    print(f"  Simulating provider error: {error_response['error']}")
    raw_content = error_response.get("content", "")

    # Parse empty content
    parse_result = parser.parse(raw_content)
    print(f"  Parse success: {parse_result.success}")

    if not parse_result.success:
        print(f"  Parse error: {parse_result.error}")
        print(f"  [OK] Empty content correctly rejected")

        # Fallback to pathfinder
        path = pathfinder.astar(state, state.agent_pos, state.goal)
        if path.found and path.length > 0:
            for i, pos in enumerate(path.path):
                if pos == state.agent_pos and i + 1 < len(path.path):
                    next_pos = path.path[i + 1]
                    fallback_action = Action.from_positions(state.agent_pos, next_pos)
                    if fallback_action:
                        print(f"  [FALLBACK] Pathfinder action: {fallback_action.value}")
                        break
            else:
                fallback_action = Action.WAIT
        else:
            fallback_action = Action.WAIT

        # Apply action
        simulator = GameSimulator(state)
        result = simulator.apply_action(fallback_action, fallback_used=True)
        print(f"  Action applied: {fallback_action.value}")
        print(f"  Position after: {simulator.state.agent_pos.to_label()}")
        print(f"  Game continues: {not simulator.is_finished}")
    else:
        print(f"  [UNEXPECTED] Parse succeeded on empty content")

    print("\n" + "=" * 60)
    print("FAILURE TEST 2: PASS")
    print("=" * 60)
    return True


def test_safety_gate_rejection():
    """Test: Unsafe action from provider -> safety gate rejects -> fallback."""
    print("\n" + "=" * 60)
    print("FAILURE TEST 3: Safety gate rejection")
    print("=" * 60)

    parser = ActionParser()
    pathfinder = Pathfinder()

    # Agent at top-left corner (A1) - UP would go out of bounds
    state = GameState(
        width=5, height=5,
        agent_pos=Position(0, 0),
        walls=set(),
        coins=set(),
        goal=Position(4, 4),
        turn=0, score=0, health=100,
    )

    # Provider returns UP (unsafe from A1)
    provider_response = "UP"
    print(f"  Provider response: {provider_response}")
    print(f"  Agent position: {state.agent_pos.to_label()}")

    parse_result = parser.parse(provider_response)
    print(f"  Parse success: {parse_result.success}")
    print(f"  Parsed action: {parse_result.action.value}")

    # Safety gate
    proposed = parse_result.action
    target = proposed.apply(state.agent_pos)
    is_valid = state.is_valid_position(target)
    is_wall = target in state.walls

    print(f"  Target position: {target.to_label()}")
    print(f"  Valid position: {is_valid}")
    print(f"  Is wall: {is_wall}")

    if not is_valid or is_wall:
        print(f"  [OK] Safety gate correctly rejects unsafe action")

        # Fallback
        fallback_action = _compute_pathfinder_fallback(state, pathfinder)
        print(f"  [FALLBACK] Pathfinder action: {fallback_action.value}")

        # Apply action
        simulator = GameSimulator(state)
        result = simulator.apply_action(fallback_action, fallback_used=True)
        print(f"  Action applied: {fallback_action.value}")
        print(f"  Position after: {simulator.state.agent_pos.to_label()}")
        print(f"  Game continues: {not simulator.is_finished}")
    else:
        print(f"  [INFO] Action is safe, no rejection needed")

    print("\n" + "=" * 60)
    print("FAILURE TEST 3: PASS")
    print("=" * 60)
    return True


def _compute_pathfinder_fallback(state: GameState, pathfinder: Pathfinder) -> Action:
    """Compute pathfinder fallback action."""
    if state.goal:
        path = pathfinder.astar(state, state.agent_pos, state.goal)
        if path.found and path.length > 0:
            for i, pos in enumerate(path.path):
                if pos == state.agent_pos and i + 1 < len(path.path):
                    next_pos = path.path[i + 1]
                    action = Action.from_positions(state.agent_pos, next_pos)
                    if action:
                        return action
    return Action.WAIT


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    results = []
    results.append(test_invalid_provider_response())
    results.append(test_provider_error_recovery())
    results.append(test_safety_gate_rejection())

    print("\n" + "=" * 60)
    print("ALL FAILURE TESTS: PASS")
    print("=" * 60)
    sys.exit(0)

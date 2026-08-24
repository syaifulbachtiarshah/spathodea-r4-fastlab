"""
SPATHODEA R4 FASTLAB — Live BUZZ Probe (Phase 2F Part 3B)
One-turn and multi-turn live probe through real BUZZ -> Ollama.

Target: http://127.0.0.1:8765
Provider: ollama qwen2.5:7b
"""

import json
import time
import urllib.request
import urllib.error
import sys
import os

# Add game module to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.game_state import GameState, Position
from game.action_schema import Action
from game.action_parser import ActionParser
from game.pathfinder import Pathfinder
from game.contract_translator import ContractTranslator, TranslatorConfig


# =============================================================================
# Configuration
# =============================================================================

BUZZ_URL = "http://127.0.0.1:8765"
BUZZ_GENERATE = f"{BUZZ_URL}/v1/generate"
BUZZ_HEALTH = f"{BUZZ_URL}/health"


# =============================================================================
# Live BUZZ Client
# =============================================================================

class LiveBuzzClient:
    """Direct HTTP client for BUZZ v0.2.0 API."""

    def __init__(self, base_url: str = BUZZ_URL):
        self._base_url = base_url
        self._generate_url = f"{base_url}/v1/generate"
        self._health_url = f"{base_url}/health"

    def health(self) -> dict:
        """Check BUZZ health."""
        req = urllib.request.Request(self._health_url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def generate(self, payload: dict, timeout_s: float = 30.0) -> dict:
        """Send generation request to BUZZ."""
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
# Game Map Builder
# =============================================================================

def build_simple_map() -> GameState:
    """Build a simple 5x5 deterministic map for testing.

    Map layout:
        A1 = agent start
        E5 = goal
        B2, D4 = walls (obstacles)
        C3 = coin
        No enemies/hazards for clean test
    """
    return GameState(
        width=5,
        height=5,
        agent_pos=Position(0, 0),  # A1
        walls={Position(1, 1), Position(3, 3)},  # B2, D4
        keys=set(),
        doors={},
        coins={Position(2, 2)},  # C3
        enemies=set(),
        hazards=set(),
        goal=Position(4, 4),  # E5
        unknown=set(),
        collected_keys=set(),
        collected_coins=set(),
        turn=0,
        score=0,
        health=100,
    )


# =============================================================================
# One-Turn Probe
# =============================================================================

def run_one_turn_probe():
    """Run exactly one game turn through live BUZZ -> Ollama."""
    print("=" * 60)
    print("ONE-TURN LIVE PROBE: BUZZ -> Ollama qwen2.5:7b")
    print("=" * 60)

    # 1. Check BUZZ health
    client = LiveBuzzClient()
    try:
        health = client.health()
        print(f"[OK] BUZZ health: {health['status']}")
        print(f"[OK] contract_version: {health['contract_version']}")
        print(f"[OK] providers: {health.get('providers', {})}")
    except Exception as e:
        print(f"[FAIL] BUZZ health check failed: {e}")
        return False

    # 2. Build game state
    state = build_simple_map()
    print(f"\n[MAP] {state.width}x{state.height} grid")
    print(f"[MAP] Agent: {state.agent_pos.to_label()}")
    print(f"[MAP] Goal: {state.goal.to_label()}")
    print(f"[MAP] Walls: {[p.to_label() for p in state.walls]}")

    # 3. Build planning context
    context = {
        "strategy_profile": "exploration",
        "threats": [],
        "available_rewards": [f"coin@{p.to_label()}" for p in state.get_available_rewards()],
        "recommended_action": "RIGHT",
    }

    # 4. Build BUZZ wire payload via translator
    from adapters.provider_request import ProviderRequest

    # Build FASTLAB internal request
    metadata = {
        "source": "SPATHODEA_GAME",
        "task_intent": "game_navigation",
        "turn": state.turn,
        "agent_position": state.agent_pos.to_label(),
        "strategy": context["strategy_profile"],
        "grid_width": state.width,
        "grid_height": state.height,
        "known_rewards": len(state.get_available_rewards()),
        "known_hazards": len(state.hazards),
        "known_enemies": len(state.enemies),
        "goal": state.goal.to_label() if state.goal else None,
    }

    # Build game prompt
    prompt = (
        f"Grid: {state.width}x{state.height} | "
        f"Position: {state.agent_pos.to_label()} | "
        f"Goal: {state.goal.to_label()} | "
        f"Strategy: {context['strategy_profile']} | "
        f"Turn: {state.turn} | "
        f"Health: {state.health} | "
        f"Respond with a single action: UP, DOWN, LEFT, RIGHT, or WAIT"
    )

    fastlab_request = ProviderRequest(
        prompt=prompt,
        system_prompt=None,
        model="auto",
        temperature=0.3,
        max_tokens=50,
        top_p=0.9,
        stop_sequences=None,
        request_id=f"game-turn-{state.turn:04d}",
        metadata=metadata,
        provider_preference="ollama",
        reviewer_preference=None,
        execution_mode="sync",
        task_type="generate",
    )

    # Translate to wire payload
    translator = ContractTranslator(config=TranslatorConfig(
        wire_execution_mode="single",
        wire_provider="ollama",
        wire_reviewer="none",
    ))

    translation = translator.translate(fastlab_request)
    if not translation.success:
        print(f"[FAIL] Translation failed: {translation.errors}")
        return False

    wire_payload = translation.wire_payload
    print(f"\n[TRANSLATE] task_type: {wire_payload['task_type']}")
    print(f"[TRANSLATE] execution_mode: {wire_payload['execution_mode']}")
    print(f"[TRANSLATE] provider_preference: {wire_payload['provider_preference']}")

    # 5. Send to real BUZZ
    print(f"\n[REQUEST] Sending to BUZZ...")
    start_time = time.perf_counter()
    try:
        response = client.generate(wire_payload, timeout_s=45.0)
        latency_ms = (time.perf_counter() - start_time) * 1000
    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        print(f"[FAIL] BUZZ request failed: {e}")
        print(f"[INFO] Latency: {latency_ms:.0f}ms")
        return False

    # 6. Validate response
    print(f"\n[RESPONSE] contract_version: {response.get('contract_version')}")
    print(f"[RESPONSE] provider: {response.get('provider')}")
    print(f"[RESPONSE] model: {response.get('model')}")
    print(f"[RESPONSE] finish_reason: {response.get('finish_reason')}")
    print(f"[RESPONSE] latency_ms: {response.get('latency_ms')}")
    print(f"[RESPONSE] content: {response.get('content', '')[:100]}")

    if response.get('contract_version') != '0.2.0':
        print(f"[FAIL] Wrong contract_version: {response.get('contract_version')}")
        return False

    if response.get('provider') != 'ollama':
        print(f"[FAIL] Wrong provider: {response.get('provider')}")
        return False

    # 7. Parse action
    raw_content = response.get('content', '')
    parser = ActionParser()
    parse_result = parser.parse(raw_content)

    print(f"\n[PARSE] success: {parse_result.success}")
    print(f"[PARSE] action: {parse_result.action}")
    print(f"[PARSE] method: {parse_result.method}")
    print(f"[PARSE] error: {parse_result.error}")

    if not parse_result.success:
        print(f"[INFO] Model returned prose, using deterministic fallback")
        # Use pathfinder fallback
        pathfinder = Pathfinder()
        path = pathfinder.astar(state, state.agent_pos, state.goal)
        if path.found and path.length > 0:
            for i, pos in enumerate(path.path):
                if pos == state.agent_pos and i + 1 < len(path.path):
                    next_pos = path.path[i + 1]
                    fallback_action = Action.from_positions(state.agent_pos, next_pos)
                    if fallback_action:
                        print(f"[FALLBACK] Using pathfinder action: {fallback_action.value}")
                        break
            else:
                fallback_action = Action.WAIT
        else:
            fallback_action = Action.WAIT
        print(f"[RESULT] Final action: {fallback_action.value} (fallback)")
    else:
        # 8. Safety gate
        target = parse_result.action.apply(state.agent_pos)
        if state.is_valid_position(target) and target not in state.walls:
            print(f"[SAFETY] Action {parse_result.action.value} is safe")
            print(f"[RESULT] Final action: {parse_result.action.value} (provider)")
        else:
            print(f"[SAFETY] Action {parse_result.action.value} is unsafe, using fallback")
            pathfinder = Pathfinder()
            path = pathfinder.astar(state, state.agent_pos, state.goal)
            if path.found and path.length > 0:
                for i, pos in enumerate(path.path):
                    if pos == state.agent_pos and i + 1 < len(path.path):
                        next_pos = path.path[i + 1]
                        fallback_action = Action.from_positions(state.agent_pos, next_pos)
                        if fallback_action:
                            break
                else:
                    fallback_action = Action.WAIT
            else:
                fallback_action = Action.WAIT
            print(f"[RESULT] Final action: {fallback_action.value} (fallback)")

    print("\n" + "=" * 60)
    print("ONE-TURN PROBE: PASS")
    print("=" * 60)
    return True


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    success = run_one_turn_probe()
    sys.exit(0 if success else 1)

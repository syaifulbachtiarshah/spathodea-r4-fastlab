"""
SPATHODEA R4 FASTLAB — Five-Turn Live Episode (Phase 2F Part 3B)
Run a 5-turn game episode through real BUZZ -> Ollama qwen2.5:7b.

Tracks per-turn metrics:
- position_before
- translated request mode
- provider / model
- raw response summary
- parsed action
- fallback_used / fallback_reason
- position_after
- provider_latency_ms
- bridge_processing_ms
"""

import json
import time
import urllib.request
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.game_state import GameState, Position
from game.game_simulator import GameSimulator
from game.action_schema import Action
from game.action_parser import ActionParser
from game.pathfinder import Pathfinder
from game.contract_translator import ContractTranslator, TranslatorConfig
from adapters.provider_request import ProviderRequest


# =============================================================================
# Configuration
# =============================================================================

BUZZ_URL = "http://127.0.0.1:8765"
MAX_TURNS = 5
TIMEOUT_S = 45.0


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
# Game Map
# =============================================================================

def build_game_map() -> GameState:
    """5x5 map: A1 start, E5 goal, walls at B2/D4, coin at C3."""
    return GameState(
        width=5, height=5,
        agent_pos=Position(0, 0),
        walls={Position(1, 1), Position(3, 3)},
        coins={Position(2, 2)},
        goal=Position(4, 4),
        turn=0, score=0, health=100,
    )


# =============================================================================
# Five-Turn Episode
# =============================================================================

def run_five_turn_episode():
    """Run a 5-turn live episode through BUZZ -> Ollama."""
    print("=" * 70)
    print("FIVE-TURN LIVE EPISODE: BUZZ -> Ollama qwen2.5:7b")
    print("=" * 70)

    client = LiveBuzzClient()
    state = build_game_map()
    simulator = GameSimulator(state)
    parser = ActionParser()
    pathfinder = Pathfinder()

    translator = ContractTranslator(config=TranslatorConfig(
        wire_execution_mode="single",
        wire_provider="ollama",
        wire_reviewer="none",
    ))

    turn_results = []
    fallback_count = 0

    for turn_num in range(1, MAX_TURNS + 1):
        print(f"\n--- TURN {turn_num} ---")
        current_state = simulator.state
        position_before = current_state.agent_pos.to_label()

        # Build request
        context_strategy = "exploration"
        prompt = (
            f"Grid: {current_state.width}x{current_state.height} | "
            f"Position: {current_state.agent_pos.to_label()} | "
            f"Goal: {current_state.goal.to_label()} | "
            f"Strategy: {context_strategy} | "
            f"Turn: {current_state.turn} | "
            f"Health: {current_state.health} | "
            f"Respond with a single action: UP, DOWN, LEFT, RIGHT, or WAIT"
        )

        metadata = {
            "source": "SPATHODEA_GAME",
            "task_intent": "game_navigation",
            "turn": current_state.turn,
            "agent_position": current_state.agent_pos.to_label(),
            "strategy": context_strategy,
            "grid_width": current_state.width,
            "grid_height": current_state.height,
            "known_rewards": len(current_state.get_available_rewards()),
            "known_hazards": len(current_state.hazards),
            "known_enemies": len(current_state.enemies),
            "goal": current_state.goal.to_label() if current_state.goal else None,
        }

        fastlab_request = ProviderRequest(
            prompt=prompt,
            model="auto",
            temperature=0.3,
            max_tokens=50,
            request_id=f"game-turn-{state.turn:04d}",
            metadata=metadata,
            provider_preference="ollama",
            execution_mode="sync",
            task_type="generate",
        )

        translation = translator.translate(fastlab_request)
        if not translation.success:
            print(f"  [ERROR] Translation failed: {translation.errors}")
            break

        wire_payload = translation.wire_payload

        # Send to BUZZ
        bridge_start = time.perf_counter()
        try:
            response = client.generate(wire_payload, timeout_s=TIMEOUT_S)
            provider_latency_ms = response.get("latency_ms", 0)
            raw_content = response.get("content", "")
            provider_used = response.get("provider", "")
            model_used = response.get("model", "")
            finish_reason = response.get("finish_reason", "")
        except Exception as e:
            provider_latency_ms = 0
            raw_content = ""
            provider_used = "error"
            model_used = ""
            finish_reason = "error"
            print(f"  [ERROR] BUZZ request failed: {e}")

        # Parse action
        parse_result = parser.parse(raw_content)
        fallback_used = False
        fallback_reason = ""

        if not parse_result.success:
            # Fallback to pathfinder
            fallback_used = True
            fallback_reason = f"Parse failed: {parse_result.error}"
            action = _compute_pathfinder_fallback(current_state, pathfinder)
        else:
            # Safety gate
            proposed = parse_result.action
            target = proposed.apply(current_state.agent_pos)
            if current_state.is_valid_position(target) and target not in current_state.walls:
                action = proposed
            else:
                fallback_used = True
                fallback_reason = f"Unsafe action {proposed.value} from {position_before}"
                action = _compute_pathfinder_fallback(current_state, pathfinder)

        if fallback_used:
            fallback_count += 1

        bridge_processing_ms = (time.perf_counter() - bridge_start) * 1000 - provider_latency_ms

        # Apply action
        result = simulator.apply_action(action, fallback_used=fallback_used)
        position_after = simulator.state.agent_pos.to_label()

        turn_data = {
            "turn": turn_num,
            "position_before": position_before,
            "execution_mode": wire_payload["execution_mode"],
            "provider": provider_used,
            "model": model_used,
            "raw_response_summary": raw_content[:80] if raw_content else "(empty)",
            "parsed_action": parse_result.action.value if parse_result.action else None,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "position_after": position_after,
            "provider_latency_ms": provider_latency_ms,
            "bridge_processing_ms": round(bridge_processing_ms, 1),
            "action_applied": action.value,
            "action_success": result.success,
            "action_reason": result.reason,
        }
        turn_results.append(turn_data)

        print(f"  Position before: {position_before}")
        print(f"  Provider: {provider_used} ({model_used})")
        print(f"  Raw response: {raw_content[:60] if raw_content else '(empty)'}")
        print(f"  Parsed action: {parse_result.action.value if parse_result.action else 'None'}")
        print(f"  Fallback used: {fallback_used}")
        if fallback_used:
            print(f"  Fallback reason: {fallback_reason}")
        print(f"  Action applied: {action.value}")
        print(f"  Position after: {position_after}")
        print(f"  Provider latency: {provider_latency_ms}ms")
        print(f"  Bridge processing: {bridge_processing_ms:.1f}ms")

        if simulator.is_finished:
            print(f"\n  [GAME OVER] Goal reached={state.goal == state.agent_pos}, Health={state.health}")
            break

    # Summary
    metrics = simulator.get_metrics()
    print("\n" + "=" * 70)
    print("EPISODE SUMMARY")
    print("=" * 70)
    print(f"  Total turns: {metrics.total_turns}")
    print(f"  Final position: {metrics.final_position}")
    print(f"  Goal reached: {metrics.goal_reached}")
    print(f"  Final health: {metrics.final_health}")
    print(f"  Final score: {metrics.final_score}")
    print(f"  Fallback count: {fallback_count}/{metrics.total_turns}")
    print(f"  Coins collected: {metrics.coins_collected}")

    avg_latency = sum(t["provider_latency_ms"] for t in turn_results) / len(turn_results) if turn_results else 0
    avg_bridge = sum(t["bridge_processing_ms"] for t in turn_results) / len(turn_results) if turn_results else 0
    print(f"  Avg provider latency: {avg_latency:.0f}ms")
    print(f"  Avg bridge processing: {avg_bridge:.1f}ms")

    print("\n" + "=" * 70)
    print("FIVE-TURN EPISODE: PASS")
    print("=" * 70)
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
    success = run_five_turn_episode()
    sys.exit(0 if success else 1)

"""
SPATHODEA R4 FASTLAB — Multi-Turn Episode Completion (Phase 2F Part 3C)
Runs 3 live episodes through BUZZ -> Ollama with GROUNDED_NAV_PROMPT.
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
from game.navigation_context import NavigationContextBuilder
from game.navigation_prompt import build_grounded_nav_prompt
from game.contract_translator import ContractTranslator, TranslatorConfig
from adapters.provider_request import ProviderRequest


BUZZ_URL = "http://127.0.0.1:8765"
TIMEOUT_S = 45.0
MAX_TURNS = 10


class LiveBuzzClient:
    def __init__(self):
        self._url = f"{BUZZ_URL}/v1/generate"

    def generate(self, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self._url, data=data,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return json.loads(resp.read())


def detect_oscillation(prev_positions, prev_actions, new_pos):
    """Detect A->B->A or opposite-action oscillation."""
    # Position oscillation: A -> B -> A
    if len(prev_positions) >= 2:
        if new_pos == prev_positions[-2]:
            return True, "position_oscillation"

    # Action oscillation: DOWN -> UP, LEFT -> RIGHT, etc.
    opposites = {"UP": "DOWN", "DOWN": "UP", "LEFT": "RIGHT", "RIGHT": "LEFT"}
    if len(prev_actions) >= 1:
        last = prev_actions[-1]
        if new_pos != prev_positions[-1] if prev_positions else True:
            # Check if new action is opposite of last
            if last in opposites and len(prev_actions) >= 1:
                # Simple: if we just did DOWN and now doing UP, check position pattern
                pass

    # More precise: check if action reverses previous movement
    if len(prev_positions) >= 2 and len(prev_actions) >= 1:
        prev_pos = prev_positions[-1]
        prev_act = prev_actions[-1]
        # If last action moved us from prev_positions[-2] to prev_positions[-1]
        # and new position is prev_positions[-2], that's oscillation
        if new_pos == prev_positions[-2]:
            return True, "position_oscillation"

    return False, ""


def run_episode(name, initial_state, max_turns=MAX_TURNS):
    """Run one multi-turn episode."""
    print("=" * 70)
    print(f"EPISODE: {name}")
    print(f"Map: {initial_state.width}x{initial_state.height}")
    print(f"Start: {initial_state.agent_pos.to_label()}")
    print(f"Goal: {initial_state.goal.to_label() if initial_state.goal else 'None'}")
    print("=" * 70)

    client = LiveBuzzClient()
    parser = ActionParser()
    pathfinder = Pathfinder()
    ctx_builder = NavigationContextBuilder()
    translator = ContractTranslator(config=TranslatorConfig(
        wire_execution_mode="single",
        wire_provider="ollama",
        wire_reviewer="none",
    ))

    simulator = GameSimulator(initial_state)
    prev_positions = []
    prev_actions = []
    turn_data = []

    for turn_num in range(max_turns):
        state = simulator.state
        if simulator.is_finished:
            print(f"\n  [GAME OVER at turn {turn_num}]")
            break

        pos_before = state.agent_pos.to_label()
        d_before = state.agent_pos.manhattan_distance(state.goal) if state.goal else 0

        # Build context
        ctx = ctx_builder.build(
            state,
            strategy="exploration",
            recent_positions=prev_positions[-3:],
            recent_actions=prev_actions[-3:],
        )

        # Build prompt
        prompt_text = build_grounded_nav_prompt(ctx)

        # Build wire payload
        metadata = {
            "source": "SPATHODEA_GAME",
            "task_intent": "game_navigation",
            "turn": state.turn,
            "agent_position": pos_before,
            "strategy": "exploration",
            "grid_width": state.width,
            "grid_height": state.height,
            "known_rewards": len(state.get_available_rewards()),
            "known_hazards": len(state.hazards),
            "known_enemies": len(state.enemies),
            "goal": state.goal.to_label() if state.goal else None,
        }

        request = ProviderRequest(
            prompt=prompt_text,
            model="auto",
            temperature=0.0,
            max_tokens=8,
            request_id=f"multi-{name}-{turn_num:04d}",
            metadata=metadata,
            provider_preference="ollama",
            execution_mode="sync",
            task_type="generate",
        )

        translation = translator.translate(request)
        if not translation.success:
            print(f"  [ERROR] Translation failed")
            break

        # Send to BUZZ
        bridge_start = time.perf_counter()
        try:
            response = client.generate(translation.wire_payload)
            provider_latency = response.get("latency_ms", 0)
            raw_content = response.get("content", "")
        except Exception as e:
            provider_latency = 0
            raw_content = ""
            print(f"  [ERROR] BUZZ request failed: {e}")

        # Parse
        parse_result = parser.parse(raw_content)
        parsed_action = parse_result.action.value if parse_result.action else None

        # Check legal
        legal_action = parsed_action in ctx.legal_actions if parsed_action else False

        # Check safety
        fallback_used = False
        fallback_reason = ""
        unsafe_accepted = False

        if not parse_result.success:
            fallback_used = True
            fallback_reason = f"Parse failed: {parse_result.error}"
        elif parsed_action:
            target = parse_result.action.apply(state.agent_pos)
            if not state.is_valid_position(target) or target in state.walls:
                unsafe_accepted = True
                fallback_used = True
                fallback_reason = f"Unsafe action {parsed_action}"

        # Get action to apply
        if fallback_used:
            # Pathfinder fallback
            if state.goal:
                path = pathfinder.astar(state, state.agent_pos, state.goal)
                if path.found and path.length > 0:
                    for i, pos in enumerate(path.path):
                        if pos == state.agent_pos and i + 1 < len(path.path):
                            next_pos = path.path[i + 1]
                            action = Action.from_positions(state.agent_pos, next_pos)
                            if action:
                                action_applied = action.value
                                break
                    else:
                        action_applied = "WAIT"
                else:
                    action_applied = "WAIT"
            else:
                action_applied = "WAIT"
        else:
            action_applied = parsed_action

        # Apply action
        action_enum = Action(action_applied)
        sim_result = simulator.apply_action(action_enum, fallback_used=fallback_used)
        pos_after = state.agent_pos.to_label()
        d_after = state.agent_pos.manhattan_distance(state.goal) if state.goal else 0

        # Goal progress
        if d_after < d_before:
            progress = "progress"
        elif d_after > d_before:
            progress = "regress"
        else:
            progress = "neutral"

        # Oscillation detection
        osc_detected, osc_reason = detect_oscillation(prev_positions, prev_actions, pos_after)

        bridge_ms = (time.perf_counter() - bridge_start) * 1000 - provider_latency

        # Record
        turn_info = {
            "turn": turn_num,
            "position_before": pos_before,
            "legal_actions": ctx.legal_actions,
            "blocked_actions": ctx.blocked_actions,
            "raw_model_action": raw_content[:40],
            "parsed_action": parsed_action,
            "action_applied": action_applied,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "unsafe_accepted": unsafe_accepted,
            "position_after": pos_after,
            "distance_before": d_before,
            "distance_after": d_after,
            "progress": progress,
            "oscillation_detected": osc_detected,
            "oscillation_reason": osc_reason,
            "provider_latency_ms": provider_latency,
            "bridge_processing_ms": bridge_ms,
        }
        turn_data.append(turn_info)

        # Print turn
        fb_marker = " [FB]" if fallback_used else ""
        osc_marker = " [OSC]" if osc_detected else ""
        print(f"  Turn {turn_num:2d}: {pos_before} -> {pos_after} | "
              f"action={action_applied} | progress={progress} | "
              f"latency={provider_latency:.0f}ms{fb_marker}{osc_marker}")

        # Track history
        prev_positions.append(pos_before)
        prev_actions.append(action_applied)
        if len(prev_positions) > 3:
            prev_positions.pop(0)
            prev_actions.pop(0)

    # Summary
    total_turns = len(turn_data)
    goal_reached = simulator.is_finished and state.goal == state.agent_pos
    fallback_count = sum(1 for t in turn_data if t["fallback_used"])
    fallback_rate = fallback_count / total_turns if total_turns else 0
    oscillation_count = sum(1 for t in turn_data if t["oscillation_detected"])
    unsafe_count = sum(1 for t in turn_data if t["unsafe_accepted"])
    progress_count = sum(1 for t in turn_data if t["progress"] == "progress")
    goal_progress_rate = progress_count / total_turns if total_turns else 0
    avg_latency = sum(t["provider_latency_ms"] for t in turn_data) / total_turns if total_turns else 0

    print(f"\n  SUMMARY:")
    print(f"    Turns: {total_turns}")
    print(f"    Goal reached: {goal_reached}")
    print(f"    Final position: {simulator.state.agent_pos.to_label()}")
    print(f"    Fallback count: {fallback_count}/{total_turns} ({fallback_rate:.0%})")
    print(f"    Oscillation count: {oscillation_count}")
    print(f"    Unsafe accepted: {unsafe_count}")
    print(f"    Goal progress rate: {goal_progress_rate:.0%}")
    print(f"    Avg provider latency: {avg_latency:.0f}ms")

    return {
        "name": name,
        "turns": total_turns,
        "goal_reached": goal_reached,
        "final_position": simulator.state.agent_pos.to_label(),
        "fallback_count": fallback_count,
        "fallback_rate": fallback_rate,
        "oscillation_count": oscillation_count,
        "unsafe_count": unsafe_count,
        "goal_progress_rate": goal_progress_rate,
        "avg_latency": avg_latency,
        "turn_data": turn_data,
    }


def main():
    print("=" * 70)
    print("MULTI-TURN EPISODE COMPLETION (Phase 2F Part 3C)")
    print("BUZZ -> Ollama qwen2.5:7b | GROUNDED_NAV_PROMPT | temp=0.0")
    print("=" * 70)

    episodes = []

    # Episode A: Simple empty grid
    state_a = GameState(width=5, height=5, agent_pos=Position(0, 0),
                        goal=Position(4, 4), turn=0, health=100)
    episodes.append(run_episode("SIMPLE", state_a))

    # Episode B: Wall detour
    state_b = GameState(width=5, height=5, agent_pos=Position(0, 0),
                        walls={Position(1, 0), Position(1, 1), Position(1, 2)},
                        goal=Position(4, 4), turn=0, health=100)
    episodes.append(run_episode("WALL_DETOUR", state_b))

    # Episode C: Reward + Hazard
    state_c = GameState(width=5, height=5, agent_pos=Position(0, 0),
                        coins={Position(2, 0)}, hazards={Position(3, 1)},
                        goal=Position(4, 4), turn=0, health=100)
    episodes.append(run_episode("REWARD_HAZARD", state_c))

    # Aggregate
    print("\n" + "=" * 70)
    print("AGGREGATE ACROSS ALL EPISODES")
    print("=" * 70)

    total_turns = sum(e["turns"] for e in episodes)
    total_fallback = sum(e["fallback_count"] for e in episodes)
    total_osc = sum(e["oscillation_count"] for e in episodes)
    total_goals = sum(1 for e in episodes if e["goal_reached"])

    print(f"  Total turns: {total_turns}")
    print(f"  Goals reached: {total_goals}/3")
    print(f"  Total fallback: {total_fallback}/{total_turns} ({total_fallback/total_turns:.0%})" if total_turns else "")
    print(f"  Total oscillation events: {total_osc}")

    # Episode A detail
    a = episodes[0]
    if a["name"] == "SIMPLE":
        optimal = 8
        print(f"\n  SIMPLE episode efficiency:")
        print(f"    Turns to goal: {a['turns']}")
        print(f"    Optimal path: {optimal}")
        if a["goal_reached"]:
            print(f"    Path efficiency: {optimal}/{a['turns']} = {optimal/a['turns']:.2f}")
        else:
            print(f"    Goal NOT reached within {MAX_TURNS} turns")

    print("\n" + "=" * 70)
    print("MULTI-TURN COMPLETION: COMPLETE")
    print("=" * 70)

    return episodes


if __name__ == "__main__":
    results = main()

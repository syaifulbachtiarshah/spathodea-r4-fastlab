"""
SPATHODEA R4 FASTLAB — Live Navigation Evaluation (Phase 2F Part 3C)
Compares BASELINE_PROMPT vs GROUNDED_NAV_PROMPT using real BUZZ -> Ollama.

Runs:
- 12 deterministic one-turn scenarios
- 3 deterministic multi-turn episodes

Measures:
- parse_success_rate
- legal_action_rate
- unsafe_action_count
- fallback_count / fallback_rate
- oscillation_count
- goal_progress_action_rate
- provider_latency_ms (avg/p50/max)
- bridge_processing_ms
"""

import json
import time
import urllib.request
import sys
import os
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.game_state import GameState, Position
from game.game_simulator import GameSimulator
from game.action_schema import Action
from game.action_parser import ActionParser
from game.pathfinder import Pathfinder
from game.navigation_context import NavigationContextBuilder
from game.navigation_prompt import build_baseline_prompt, build_grounded_nav_prompt
from game.contract_translator import ContractTranslator, TranslatorConfig
from adapters.provider_request import ProviderRequest


# =============================================================================
# Configuration
# =============================================================================

BUZZ_URL = "http://127.0.0.1:8765"
TIMEOUT_S = 45.0
TEMPERATURE = 0.0
MAX_TOKENS = 8


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
# Metrics
# =============================================================================

@dataclass
class TurnMetrics:
    turn: int = 0
    position_before: str = ""
    position_after: str = ""
    raw_response: str = ""
    parsed_action: Optional[str] = None
    parse_success: bool = False
    legal_action: bool = False
    unsafe_accepted: bool = False
    fallback_used: bool = False
    fallback_reason: str = ""
    oscillation_detected: bool = False
    goal_progress: str = ""  # progress / neutral / regress / same
    provider_latency_ms: float = 0.0
    bridge_processing_ms: float = 0.0
    distance_before: int = 0
    distance_after: int = 0

    def to_dict(self) -> dict:
        return {
            "turn": self.turn,
            "position_before": self.position_before,
            "position_after": self.position_after,
            "raw_response": self.raw_response[:80],
            "parsed_action": self.parsed_action,
            "parse_success": self.parse_success,
            "legal_action": self.legal_action,
            "unsafe_accepted": self.unsafe_accepted,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "oscillation_detected": self.oscillation_detected,
            "goal_progress": self.goal_progress,
            "provider_latency_ms": self.provider_latency_ms,
            "bridge_processing_ms": self.bridge_processing_ms,
            "distance_before": self.distance_before,
            "distance_after": self.distance_after,
        }


@dataclass
class EvalResult:
    mode: str
    scenario_name: str
    turns: list = field(default_factory=list)
    total_turns: int = 0
    goal_reached: bool = False
    final_position: str = ""

    @property
    def parse_success_rate(self) -> float:
        if not self.turns:
            return 0.0
        return sum(1 for t in self.turns if t["parse_success"]) / len(self.turns)

    @property
    def legal_action_rate(self) -> float:
        if not self.turns:
            return 0.0
        return sum(1 for t in self.turns if t["legal_action"]) / len(self.turns)

    @property
    def unsafe_count(self) -> int:
        return sum(1 for t in self.turns if t["unsafe_accepted"])

    @property
    def fallback_count(self) -> int:
        return sum(1 for t in self.turns if t["fallback_used"])

    @property
    def fallback_rate(self) -> float:
        if not self.turns:
            return 0.0
        return self.fallback_count / len(self.turns)

    @property
    def oscillation_count(self) -> int:
        return sum(1 for t in self.turns if t["oscillation_detected"])

    @property
    def goal_progress_rate(self) -> float:
        if not self.turns:
            return 0.0
        return sum(1 for t in self.turns if t["goal_progress"] == "progress") / len(self.turns)

    @property
    def avg_provider_latency(self) -> float:
        if not self.turns:
            return 0.0
        return sum(t["provider_latency_ms"] for t in self.turns) / len(self.turns)

    @property
    def p50_provider_latency(self) -> float:
        if not self.turns:
            return 0.0
        lats = sorted(t["provider_latency_ms"] for t in self.turns)
        return lats[len(lats) // 2]

    @property
    def max_provider_latency(self) -> float:
        if not self.turns:
            return 0.0
        return max(t["provider_latency_ms"] for t in self.turns)

    @property
    def avg_bridge_processing(self) -> float:
        if not self.turns:
            return 0.0
        return sum(t["bridge_processing_ms"] for t in self.turns) / len(self.turns)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "scenario": self.scenario_name,
            "total_turns": self.total_turns,
            "goal_reached": self.goal_reached,
            "final_position": self.final_position,
            "parse_success_rate": round(self.parse_success_rate, 3),
            "legal_action_rate": round(self.legal_action_rate, 3),
            "unsafe_count": self.unsafe_count,
            "fallback_count": self.fallback_count,
            "fallback_rate": round(self.fallback_rate, 3),
            "oscillation_count": self.oscillation_count,
            "goal_progress_rate": round(self.goal_progress_rate, 3),
            "avg_provider_latency_ms": round(self.avg_provider_latency, 0),
            "p50_provider_latency_ms": round(self.p50_provider_latency, 0),
            "max_provider_latency_ms": round(self.max_provider_latency, 0),
            "avg_bridge_processing_ms": round(self.avg_bridge_processing, 1),
        }


# =============================================================================
# Scenario Definitions
# =============================================================================

def build_one_turn_scenarios() -> list[tuple[str, GameState]]:
    """Build 12 deterministic one-turn scenarios.

    Covers:
    - Four corners (A1, E1, A5, E5)
    - Four edges (C1, A3, E3, C5)
    - Center (C3)
    - Wall beside agent
    - Goal directly adjacent
    - Reward vs direct-goal choice
    """
    scenarios = []

    # 1. Corner A1 - UP/LEFT illegal
    s = GameState(width=5, height=5, agent_pos=Position(0, 0),
                  goal=Position(4, 4), turn=0, health=100)
    scenarios.append(("corner_A1", s))

    # 2. Corner E1 - UP/RIGHT illegal
    s = GameState(width=5, height=5, agent_pos=Position(4, 0),
                  goal=Position(0, 4), turn=0, health=100)
    scenarios.append(("corner_E1", s))

    # 3. Corner A5 - DOWN/LEFT illegal
    s = GameState(width=5, height=5, agent_pos=Position(0, 4),
                  goal=Position(4, 0), turn=0, health=100)
    scenarios.append(("corner_A5", s))

    # 4. Corner E5 - DOWN/RIGHT illegal
    s = GameState(width=5, height=5, agent_pos=Position(4, 4),
                  goal=Position(0, 0), turn=0, health=100)
    scenarios.append(("corner_E5", s))

    # 5. Edge top C1 - UP illegal
    s = GameState(width=5, height=5, agent_pos=Position(2, 0),
                  goal=Position(2, 4), turn=0, health=100)
    scenarios.append(("edge_C1", s))

    # 6. Edge left A3 - LEFT illegal
    s = GameState(width=5, height=5, agent_pos=Position(0, 2),
                  goal=Position(4, 2), turn=0, health=100)
    scenarios.append(("edge_A3", s))

    # 7. Edge right E3 - RIGHT illegal
    s = GameState(width=5, height=5, agent_pos=Position(4, 2),
                  goal=Position(0, 2), turn=0, health=100)
    scenarios.append(("edge_E3", s))

    # 8. Edge bottom C5 - DOWN illegal
    s = GameState(width=5, height=5, agent_pos=Position(2, 4),
                  goal=Position(2, 0), turn=0, health=100)
    scenarios.append(("edge_C5", s))

    # 9. Center C3 - all moves legal
    s = GameState(width=5, height=5, agent_pos=Position(2, 2),
                  goal=Position(4, 4), turn=0, health=100)
    scenarios.append(("center_C3", s))

    # 10. Wall beside agent (B2 blocks RIGHT from A2)
    s = GameState(width=5, height=5, agent_pos=Position(0, 1),
                  walls={Position(1, 1)}, goal=Position(4, 4), turn=0, health=100)
    scenarios.append(("wall_beside", s))

    # 11. Goal adjacent (goal at B1, agent at A1)
    s = GameState(width=5, height=5, agent_pos=Position(0, 0),
                  goal=Position(1, 0), turn=0, health=100)
    scenarios.append(("goal_adjacent", s))

    # 12. Reward vs goal choice (coin at B1, goal at B2)
    s = GameState(width=5, height=5, agent_pos=Position(0, 0),
                  coins={Position(1, 0)}, goal=Position(1, 1), turn=0, health=100)
    scenarios.append(("reward_vs_goal", s))

    return scenarios


def build_multi_turn_episodes() -> list[tuple[str, GameState]]:
    """Build 3 deterministic multi-turn episodes."""
    episodes = []

    # Episode 1: Simple empty grid
    s = GameState(width=5, height=5, agent_pos=Position(0, 0),
                  goal=Position(4, 4), turn=0, health=100)
    episodes.append(("simple_empty", s))

    # Episode 2: Walls requiring route change
    s = GameState(width=5, height=5, agent_pos=Position(0, 0),
                  walls={Position(1, 0), Position(1, 1), Position(1, 2)},
                  goal=Position(4, 4), turn=0, health=100)
    episodes.append(("walls_route", s))

    # Episode 3: Reward/hazard-aware map
    s = GameState(width=5, height=5, agent_pos=Position(0, 0),
                  coins={Position(2, 0)}, hazards={Position(3, 1)},
                  goal=Position(4, 4), turn=0, health=100)
    episodes.append(("reward_hazard", s))

    return episodes


# =============================================================================
# Navigation Evaluator
# =============================================================================

class NavigationEvaluator:
    """Evaluates navigation prompts through real BUZZ -> Ollama."""

    def __init__(self):
        self._client = LiveBuzzClient()
        self._parser = ActionParser()
        self._pathfinder = Pathfinder()
        self._ctx_builder = NavigationContextBuilder()
        self._translator = ContractTranslator(config=TranslatorConfig(
            wire_execution_mode="single",
            wire_provider="ollama",
            wire_reviewer="none",
        ))

    def evaluate_one_turn(
        self,
        scenario_name: str,
        state: GameState,
        mode: str,
    ) -> EvalResult:
        """Evaluate a single-turn scenario."""
        result = EvalResult(mode=mode, scenario_name=scenario_name, total_turns=1)

        # Build context
        ctx = self._ctx_builder.build(state, strategy="exploration")

        # Build prompt
        if mode == "baseline":
            prompt_text = build_baseline_prompt(ctx)
        else:
            prompt_text = build_grounded_nav_prompt(ctx)

        # Send to BUZZ
        turn_metrics = self._send_and_parse(
            state, ctx, prompt_text, mode, turn_num=0
        )
        result.turns.append(turn_metrics.__dict__)
        result.final_position = turn_metrics.position_after
        result.goal_reached = (turn_metrics.position_after == ctx.goal)

        return result

    def evaluate_multi_turn(
        self,
        episode_name: str,
        initial_state: GameState,
        mode: str,
        max_turns: int = 10,
    ) -> EvalResult:
        """Evaluate a multi-turn episode."""
        result = EvalResult(mode=mode, scenario_name=episode_name)
        simulator = GameSimulator(initial_state)

        recent_positions = []
        recent_actions = []
        prev_positions = []

        for turn_num in range(max_turns):
            state = simulator.state
            if simulator.is_finished:
                break

            # Build context
            ctx = self._ctx_builder.build(
                state,
                strategy="exploration",
                recent_positions=recent_positions,
                recent_actions=recent_actions,
            )

            # Build prompt
            if mode == "baseline":
                prompt_text = build_baseline_prompt(ctx)
            else:
                prompt_text = build_grounded_nav_prompt(ctx)

            # Detect oscillation before sending
            oscillation = False
            if len(prev_positions) >= 2:
                if state.agent_pos.to_label() == prev_positions[-2]:
                    oscillation = True

            # Send to BUZZ
            turn_metrics = self._send_and_parse(
                state, ctx, prompt_text, mode, turn_num=turn_num
            )
            turn_metrics.oscillation_detected = oscillation

            # Apply action
            action = Action(turn_metrics.parsed_action) if turn_metrics.parsed_action else Action.WAIT
            simulator.apply_action(action, fallback_used=turn_metrics.fallback_used)

            # Track history
            prev_positions.append(state.agent_pos.to_label())
            recent_positions.append(state.agent_pos.to_label())
            recent_actions.append(turn_metrics.parsed_action or "WAIT")
            if len(recent_positions) > 3:
                recent_positions.pop(0)
                recent_actions.pop(0)

            result.turns.append(turn_metrics.__dict__)

        result.total_turns = len(result.turns)
        result.final_position = simulator.state.agent_pos.to_label()
        result.goal_reached = simulator.is_finished and simulator.state.score > 0

        return result

    def _send_and_parse(
        self,
        state: GameState,
        ctx,
        prompt_text: str,
        mode: str,
        turn_num: int,
    ) -> TurnMetrics:
        """Send prompt to BUZZ and parse response."""
        metrics = TurnMetrics(turn=turn_num)
        metrics.position_before = state.agent_pos.to_label()
        metrics.distance_before = (
            state.agent_pos.manhattan_distance(state.goal) if state.goal else 0
        )

        # Build wire payload
        metadata = {
            "source": "SPATHODEA_GAME",
            "task_intent": "game_navigation",
            "turn": state.turn,
            "agent_position": state.agent_pos.to_label(),
            "strategy": "exploration",
            "grid_width": state.width,
            "grid_height": state.height,
            "known_rewards": len(state.get_available_rewards()),
            "known_hazards": len(state.hazards),
            "known_enemies": len(state.enemies),
            "goal": state.goal.to_label() if state.goal else None,
        }

        fastlab_request = ProviderRequest(
            prompt=prompt_text,
            model="auto",
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            request_id=f"nav-eval-{mode}-{turn_num:04d}",
            metadata=metadata,
            provider_preference="ollama",
            execution_mode="sync",
            task_type="generate",
        )

        translation = self._translator.translate(fastlab_request)
        if not translation.success:
            metrics.fallback_used = True
            metrics.fallback_reason = f"Translation failed: {translation.errors}"
            metrics.parsed_action = self._pathfinder_fallback(state).value
            metrics.legal_action = metrics.parsed_action in ctx.legal_actions
            return metrics

        wire_payload = translation.wire_payload

        # Send to BUZZ
        bridge_start = time.perf_counter()
        try:
            response = self._client.generate(wire_payload, timeout_s=TIMEOUT_S)
            metrics.provider_latency_ms = response.get("latency_ms", 0)
            raw_content = response.get("content", "")
        except Exception as e:
            metrics.provider_latency_ms = 0
            raw_content = ""

        metrics.raw_response = raw_content

        # Parse
        parse_result = self._parser.parse(raw_content)
        metrics.parse_success = parse_result.success

        if not parse_result.success:
            metrics.fallback_used = True
            metrics.fallback_reason = f"Parse failed: {parse_result.error}"
            metrics.parsed_action = self._pathfinder_fallback(state).value
        else:
            proposed = parse_result.action.value
            metrics.parsed_action = proposed

            # Check legal
            metrics.legal_action = proposed in ctx.legal_actions

            # Check safety
            target = parse_result.action.apply(state.agent_pos)
            if not state.is_valid_position(target) or target in state.walls:
                metrics.unsafe_accepted = True
                metrics.fallback_used = True
                metrics.fallback_reason = f"Unsafe action {proposed}"
                metrics.parsed_action = self._pathfinder_fallback(state).value
            else:
                # Apply action for position_after
                new_pos = parse_result.action.apply(state.agent_pos)
                metrics.position_after = new_pos.to_label()
                metrics.distance_after = (
                    new_pos.manhattan_distance(state.goal) if state.goal else 0
                )

                # Goal progress
                if metrics.distance_after < metrics.distance_before:
                    metrics.goal_progress = "progress"
                elif metrics.distance_after > metrics.distance_before:
                    metrics.goal_progress = "regress"
                else:
                    metrics.goal_progress = "neutral"

                metrics.bridge_processing_ms = (time.perf_counter() - bridge_start) * 1000 - metrics.provider_latency_ms
                return metrics

        # Fallback path
        fb_action = Action(metrics.parsed_action)
        new_pos = fb_action.apply(state.agent_pos)
        if state.is_valid_position(new_pos):
            metrics.position_after = new_pos.to_label()
            metrics.distance_after = (
                new_pos.manhattan_distance(state.goal) if state.goal else 0
            )
        else:
            metrics.position_after = state.agent_pos.to_label()
            metrics.distance_after = metrics.distance_before

        if metrics.distance_after < metrics.distance_before:
            metrics.goal_progress = "progress"
        elif metrics.distance_after > metrics.distance_before:
            metrics.goal_progress = "regress"
        else:
            metrics.goal_progress = "neutral"

        metrics.bridge_processing_ms = (time.perf_counter() - bridge_start) * 1000 - metrics.provider_latency_ms
        return metrics

    def _pathfinder_fallback(self, state: GameState) -> Action:
        """Compute pathfinder fallback action."""
        if state.goal:
            path = self._pathfinder.astar(state, state.agent_pos, state.goal)
            if path.found and path.length > 0:
                for i, pos in enumerate(path.path):
                    if pos == state.agent_pos and i + 1 < len(path.path):
                        next_pos = path.path[i + 1]
                        action = Action.from_positions(state.agent_pos, next_pos)
                        if action:
                            return action
        return Action.WAIT


# =============================================================================
# Main Evaluation
# =============================================================================

def run_evaluation():
    """Run full evaluation: baseline vs grounded."""
    print("=" * 70)
    print("NAVIGATION INTELLIGENCE EVALUATION (Phase 2F Part 3C)")
    print("BUZZ -> Ollama qwen2.5:7b | temperature=0.0 | max_tokens=8")
    print("=" * 70)

    evaluator = NavigationEvaluator()

    # ---- One-turn scenarios ----
    print("\n" + "=" * 70)
    print("ONE-TURN SCENARIOS (12 scenarios)")
    print("=" * 70)

    scenarios = build_one_turn_scenarios()
    baseline_one = []
    grounded_one = []

    for name, state in scenarios:
        print(f"\n  [{name}]")

        # Baseline
        b_result = evaluator.evaluate_one_turn(name, state, "baseline")
        baseline_one.append(b_result)
        print(f"    BASELINE:  parse={b_result.parse_success_rate:.0%} "
              f"legal={b_result.legal_action_rate:.0%} "
              f"unsafe={b_result.unsafe_count} "
              f"fallback={b_result.fallback_count} "
              f"action={b_result.turns[0]['parsed_action']}")

        # Grounded
        g_result = evaluator.evaluate_one_turn(name, state, "grounded")
        grounded_one.append(g_result)
        print(f"    GROUNDED:  parse={g_result.parse_success_rate:.0%} "
              f"legal={g_result.legal_action_rate:.0%} "
              f"unsafe={g_result.unsafe_count} "
              f"fallback={g_result.fallback_count} "
              f"action={g_result.turns[0]['parsed_action']}")

    # ---- Multi-turn episodes ----
    print("\n" + "=" * 70)
    print("MULTI-TURN EPISODES (3 episodes, max 10 turns)")
    print("=" * 70)

    episodes = build_multi_turn_episodes()
    baseline_multi = []
    grounded_multi = []

    for name, state in episodes:
        print(f"\n  [{name}]")

        # Baseline
        b_result = evaluator.evaluate_multi_turn(name, state, "baseline")
        baseline_multi.append(b_result)
        print(f"    BASELINE:  turns={b_result.total_turns} "
              f"goal={b_result.goal_reached} "
              f"fallback={b_result.fallback_count}/{b_result.total_turns} "
              f"oscillation={b_result.oscillation_count} "
              f"avg_lat={b_result.avg_provider_latency:.0f}ms")

        # Grounded
        g_result = evaluator.evaluate_multi_turn(name, state, "grounded")
        grounded_multi.append(g_result)
        print(f"    GROUNDED:  turns={g_result.total_turns} "
              f"goal={g_result.goal_reached} "
              f"fallback={g_result.fallback_count}/{g_result.total_turns} "
              f"oscillation={g_result.oscillation_count} "
              f"avg_lat={g_result.avg_provider_latency:.0f}ms")

    # ---- Aggregate ----
    print("\n" + "=" * 70)
    print("AGGREGATE METRICS")
    print("=" * 70)

    def agg_one(results):
        total = len(results)
        parse = sum(r.parse_success_rate for r in results) / total if total else 0
        legal = sum(r.legal_action_rate for r in results) / total if total else 0
        unsafe = sum(r.unsafe_count for r in results)
        fallback = sum(r.fallback_count for r in results)
        lat = sum(r.avg_provider_latency for r in results) / total if total else 0
        return parse, legal, unsafe, fallback, lat

    def agg_multi(results):
        total = len(results)
        fallback = sum(r.fallback_count for r in results)
        total_turns = sum(r.total_turns for r in results)
        osc = sum(r.oscillation_count for r in results)
        goals = sum(1 for r in results if r.goal_reached)
        return fallback, total_turns, osc, goals

    b_parse, b_legal, b_unsafe, b_fb, b_lat = agg_one(baseline_one)
    g_parse, g_legal, g_unsafe, g_fb, g_lat = agg_one(grounded_one)

    b_fb_m, b_turns_m, b_osc, b_goals = agg_multi(baseline_multi)
    g_fb_m, g_turns_m, g_osc, g_goals = agg_multi(grounded_multi)

    print(f"\n  ONE-TURN:")
    print(f"  {'Metric':<25} {'Baseline':>12} {'Grounded':>12} {'Delta':>12}")
    print(f"  {'-'*61}")
    print(f"  {'parse_success_rate':<25} {b_parse:>11.0%} {g_parse:>11.0%} {g_parse-b_parse:>+11.0%}")
    print(f"  {'legal_action_rate':<25} {b_legal:>11.0%} {g_legal:>11.0%} {g_legal-b_legal:>+11.0%}")
    print(f"  {'unsafe_count':<25} {b_unsafe:>12} {g_unsafe:>12} {g_unsafe-b_unsafe:>+12}")
    print(f"  {'fallback_count':<25} {b_fb:>12} {g_fb:>12} {g_fb-b_fb:>+12}")
    print(f"  {'avg_provider_latency_ms':<25} {b_lat:>11.0f} {g_lat:>11.0f} {g_lat-b_lat:>+11.0f}")

    print(f"\n  MULTI-TURN:")
    print(f"  {'Metric':<25} {'Baseline':>12} {'Grounded':>12} {'Delta':>12}")
    print(f"  {'-'*61}")
    print(f"  {'fallback_count':<25} {b_fb_m:>12} {g_fb_m:>12} {g_fb_m-b_fb_m:>+12}")
    print(f"  {'total_turns':<25} {b_turns_m:>12} {g_turns_m:>12} {g_turns_m-b_turns_m:>+12}")
    fb_rate_b = b_fb_m / b_turns_m if b_turns_m else 0
    fb_rate_g = g_fb_m / g_turns_m if g_turns_m else 0
    print(f"  {'fallback_rate':<25} {fb_rate_b:>11.0%} {fb_rate_g:>11.0%} {fb_rate_g-fb_rate_b:>+11.0%}")
    print(f"  {'oscillation_count':<25} {b_osc:>12} {g_osc:>12} {g_osc-b_osc:>+12}")
    print(f"  {'goals_reached':<25} {b_goals:>12} {g_goals:>12} {g_goals-b_goals:>+12}")

    print("\n" + "=" * 70)
    print("EVALUATION COMPLETE")
    print("=" * 70)

    return {
        "baseline_one_turn": [r.to_dict() for r in baseline_one],
        "grounded_one_turn": [r.to_dict() for r in grounded_one],
        "baseline_multi_turn": [r.to_dict() for r in baseline_multi],
        "grounded_multi_turn": [r.to_dict() for r in grounded_multi],
    }


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    results = run_evaluation()

    # Save results
    output_path = os.path.join(os.path.dirname(__file__), "navigation_eval_results.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {output_path}")

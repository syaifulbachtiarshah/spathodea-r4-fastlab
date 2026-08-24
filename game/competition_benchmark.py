"""
SPATHODEA R4 FASTLAB — Competition Benchmark (Phase 2F Part 3D)
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
from game.game_simulator import GameSimulator, SimConfig
from game.action_schema import Action
from game.action_parser import ActionParser
from game.pathfinder import Pathfinder
from game.strategy import Strategy, StrategyProfile
from game.navigation_context import NavigationContextBuilder
from game.navigation_prompt import build_grounded_nav_prompt
from game.oscillation_detector import OscillationDetector
from game.contract_translator import ContractTranslator, TranslatorConfig
from adapters.provider_request import ProviderRequest
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

BUZZ_URL = "http://127.0.0.1:8765"
TIMEOUT_S = 45.0
TEMPERATURE = 0.0
MAX_TOKENS = 8
MODELS = ["qwen2.5:7b", "llama3.2:3b"]


class LiveBuzzClient:
    def __init__(self, base_url=BUZZ_URL):
        self._generate_url = f"{base_url}/v1/generate"
        self._health_url = f"{base_url}/health"

    def health(self):
        req = urllib.request.Request(self._health_url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def generate(self, payload, timeout_s=TIMEOUT_S):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._generate_url, data=data,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read())


class CompetitionBenchmark:
    def __init__(self):
        self._client = LiveBuzzClient()
        self._parser = ActionParser()
        self._pathfinder = Pathfinder()
        self._ctx_builder = NavigationContextBuilder()
        self._translator = ContractTranslator(config=TranslatorConfig(
            wire_execution_mode="single", wire_provider="ollama", wire_reviewer="none",
        ))

    def _call_provider(self, model, prompt, state, strategy="exploration"):
        bridge_start = time.perf_counter()
        metadata = {
            "source": "SPATHODEA_GAME", "task_intent": "game_navigation",
            "turn": state.turn, "agent_position": state.agent_pos.to_label(),
            "strategy": strategy, "grid_width": state.width, "grid_height": state.height,
            "known_rewards": len(state.get_available_rewards()),
            "known_hazards": len(state.hazards), "known_enemies": len(state.enemies),
            "goal": state.goal.to_label() if state.goal else None,
        }
        fastlab_request = ProviderRequest(
            prompt=prompt, model="auto", temperature=TEMPERATURE, max_tokens=MAX_TOKENS,
            request_id=f"bench-{model}-{int(time.time()*1000)}", metadata=metadata,
            provider_preference="ollama", execution_mode="sync", task_type="generate",
        )
        translation = self._translator.translate(fastlab_request)
        if not translation.success:
            bridge_ms = (time.perf_counter() - bridge_start) * 1000
            return "", 0.0, bridge_ms
        wire_payload = translation.wire_payload
        wire_payload["model"] = model
        try:
            response = self._client.generate(wire_payload, timeout_s=TIMEOUT_S)
            provider_latency = response.get("latency_ms", 0)
            raw_content = response.get("content", "")
        except Exception:
            provider_latency = 0.0
            raw_content = ""
        bridge_ms = (time.perf_counter() - bridge_start) * 1000 - provider_latency
        return raw_content, provider_latency, bridge_ms

    def _pathfinder_fallback(self, state):
        if state.goal:
            path = self._pathfinder.astar(state, state.agent_pos, state.goal)
            if path.found and path.length > 0:
                for i, pos in enumerate(path.path):
                    if pos == state.agent_pos and i + 1 < len(path.path):
                        action = Action.from_positions(state.agent_pos, path.path[i + 1])
                        if action:
                            return action
        return Action.WAIT

    def run_one_turn_benchmark(self, model):
        agg = ModelOneTurnAgg(model=model)
        scenarios = build_one_turn_scenarios()
        for name, state, expected in scenarios:
            ctx = self._ctx_builder.build(state, strategy="exploration")
            prompt = build_grounded_nav_prompt(ctx)
            raw, lat, bridge = self._call_provider(model, prompt, state)
            agg.latencies.append(lat)
            metrics = OneTurnMetrics(scenario_name=name, model=model,
                raw_response=raw, provider_latency_ms=lat, bridge_processing_ms=bridge)
            agg.total_scenarios += 1
            parse_result = self._parser.parse(raw)
            metrics.parse_success = parse_result.success
            if parse_result.success:
                agg.parse_success_count += 1
                action_str = parse_result.action.value
                metrics.parsed_action = action_str
                metrics.legal_action = action_str in expected["legal_actions"]
                if metrics.legal_action:
                    agg.legal_action_count += 1
                target = parse_result.action.apply(state.agent_pos)
                if not state.is_valid_position(target) or target in state.walls:
                    metrics.unsafe_accepted = True
                    agg.unsafe_count += 1
                if state.goal:
                    d_b = state.agent_pos.manhattan_distance(state.goal)
                    d_a = target.manhattan_distance(state.goal)
                    if d_a < d_b:
                        metrics.goal_progress = "progress"
                        agg.goal_progress_count += 1
                    elif d_a > d_b:
                        metrics.goal_progress = "regress"
            else:
                metrics.fallback_used = True
                metrics.fallback_reason = parse_result.error
                agg.fallback_count += 1
                fb = self._pathfinder_fallback(state)
                metrics.parsed_action = fb.value
                if state.goal:
                    d_b = state.agent_pos.manhattan_distance(state.goal)
                    target = fb.apply(state.agent_pos)
                    d_a = target.manhattan_distance(state.goal) if state.is_valid_position(target) else d_b
                    if d_a < d_b:
                        metrics.goal_progress = "progress"
                        agg.goal_progress_count += 1
        return agg

    def run_multi_turn_benchmark(self, model):
        results = []
        episodes = build_multi_turn_episodes()
        for name, state, config in episodes:
            result = MultiTurnMetrics(episode_name=name, model=model,
                optimal_path_length=config["optimal_path_length"])
            sim = GameSimulator(state)
            detector = OscillationDetector()
            recent_positions, recent_actions, latencies = [], [], []
            for turn_num in range(config["max_turns"]):
                if sim.is_finished:
                    break
                cur_state = sim.state
                ctx = self._ctx_builder.build(cur_state, strategy=config["strategy"],
                    recent_positions=recent_positions, recent_actions=recent_actions)
                prompt = build_grounded_nav_prompt(ctx)
                raw, lat, _ = self._call_provider(model, prompt, cur_state)
                latencies.append(lat)
                parse_result = self._parser.parse(raw)
                result.total_turns += 1
                if parse_result.success:
                    action = parse_result.action
                    target = action.apply(cur_state.agent_pos)
                    if not cur_state.is_valid_position(target) or target in cur_state.walls:
                        action = self._pathfinder_fallback(cur_state)
                        result.fallback_count += 1
                        result.unsafe_accepted_actions += 1
                else:
                    action = self._pathfinder_fallback(cur_state)
                    result.fallback_count += 1
                new_pos = action.apply(cur_state.agent_pos)
                if cur_state.is_valid_position(new_pos):
                    osc = detector.check(new_pos.to_label(), action.value, turn=turn_num)
                    if osc.event_detected:
                        result.oscillation_events += 1
                    if osc.is_repeated_loop:
                        result.repeated_loops += 1
                sim.apply_action(action, fallback_used=(not parse_result.success))
                recent_positions.append(cur_state.agent_pos.to_label())
                recent_actions.append(action.value)
                if len(recent_positions) > 3:
                    recent_positions.pop(0)
                    recent_actions.pop(0)
                if sim.is_finished and sim.state.score > 0:
                    result.goal_reached = True
                    result.turns_to_goal = turn_num + 1
            result.final_position = sim.state.agent_pos.to_label()
            result.avg_provider_latency = sum(latencies) / len(latencies) if latencies else 0.0
            results.append(result)
        return results

    def run_strategy_benchmark(self, model):
        all_scenarios = build_strategy_scenarios()
        results = {}
        for strategy_name, scenarios in all_scenarios.items():
            strategy_results = []
            for name, state, config in scenarios:
                sim = GameSimulator(state, config=SimConfig(
                    coin_reward=10, goal_reward=100, hazard_damage=20, enemy_damage=30))
                detector = OscillationDetector()
                recent_positions, recent_actions = [], []
                metric = StrategyMetrics(strategy=strategy_name, scenario_name=name)
                for turn_num in range(config["max_turns"]):
                    if sim.is_finished:
                        break
                    cur_state = sim.state
                    ctx = self._ctx_builder.build(cur_state, strategy=strategy_name,
                        recent_positions=recent_positions, recent_actions=recent_actions)
                    prompt = build_grounded_nav_prompt(ctx)
                    raw, _, _ = self._call_provider(model, prompt, cur_state, strategy=strategy_name)
                    parse_result = self._parser.parse(raw)
                    if parse_result.success:
                        action = parse_result.action
                        target = action.apply(cur_state.agent_pos)
                        if not cur_state.is_valid_position(target) or target in cur_state.walls:
                            action = self._pathfinder_fallback(cur_state)
                            metric.fallback_count += 1
                            metric.unsafe_actions += 1
                    else:
                        action = self._pathfinder_fallback(cur_state)
                        metric.fallback_count += 1
                    new_pos = action.apply(cur_state.agent_pos)
                    if cur_state.is_valid_position(new_pos):
                        osc = detector.check(new_pos.to_label(), action.value, turn=turn_num)
                        if osc.event_detected:
                            metric.oscillation_events += 1
                    sim.apply_action(action, fallback_used=(not parse_result.success))
                    recent_positions.append(cur_state.agent_pos.to_label())
                    recent_actions.append(action.value)
                    if len(recent_positions) > 3:
                        recent_positions.pop(0)
                        recent_actions.pop(0)
                metric.turns = sim.metrics.total_turns
                metric.goal_reached = sim.metrics.goal_reached
                metric.score = sim.metrics.final_score
                metric.rewards_collected = sim.metrics.coins_collected
                metric.health_remaining = sim.metrics.final_health
                if config["optimal_path_length"] > 0 and metric.turns > 0:
                    metric.path_efficiency = config["optimal_path_length"] / metric.turns
                strategy_results.append(metric)
            results[strategy_name] = strategy_results
        return results

    def compute_readiness_score(self, one_turn, multi_turn, strategy_results):
        scores = {}
        for model in MODELS:
            ot = one_turn.get(model)
            mt = multi_turn.get(model)
            rs = strategy_results.get(model, {})

            safety = 1.0
            if ot:
                safety -= ot.unsafe_rate * 0.5
                safety -= (1.0 - ot.legal_action_rate) * 0.5
            if mt:
                for m in mt:
                    safety -= (m.unsafe_accepted_actions / max(m.total_turns, 1)) * 0.1

            goal = 0.0
            if ot:
                goal = ot.goal_progress_rate
            if mt:
                goal = (goal + mt.goal_completion_rate) / 2 if goal else mt.goal_completion_rate

            efficiency = 0.0
            if mt:
                efficiency = mt.avg_path_efficiency

            fallback = 1.0
            if ot:
                fallback -= ot.fallback_rate * 0.5
            if mt:
                fallback -= mt.fallback_rate * 0.5
            fallback = max(0.0, fallback)

            oscillation = 1.0
            if mt:
                total_osc = mt.total_oscillation
                total_turns = mt.total_turns
                if total_turns > 0:
                    oscillation -= min(1.0, total_osc / total_turns)

            latency = 1.0
            all_lats = []
            if ot:
                all_lats.extend(ot.latencies)
            if mt:
                all_lats.extend(mt.latencies)
            if all_lats:
                avg = sum(all_lats) / len(all_lats)
                if avg > 10000:
                    latency = 0.2
                elif avg > 5000:
                    latency = 0.4
                elif avg > 2000:
                    latency = 0.7
                else:
                    latency = 1.0

            score = ReadinessScore(
                model=model, safety_score=safety, goal_score=goal,
                efficiency_score=efficiency, fallback_score=fallback,
                oscillation_score=oscillation, latency_score=latency,
            )
            scores[model] = score
        return scores

    def select_config(self, readiness_scores, strategy_results):
        best_model = max(readiness_scores.keys(),
            key=lambda m: readiness_scores[m].total_score)
        second_models = [m for m in readiness_scores if m != best_model]
        second_model = second_models[0] if second_models else best_model

        strategy_totals = {}
        for model, strats in strategy_results.items():
            for strat_name, metrics_list in strats.items():
                if strat_name not in strategy_totals:
                    strategy_totals[strat_name] = []
                for m in metrics_list:
                    strategy_totals[strat_name].append(m.goal_reached)

        best_strategy = "adaptive"
        if strategy_totals:
            best_strategy = max(strategy_totals.keys(),
                key=lambda s: sum(strategy_totals[s]) / max(len(strategy_totals[s]), 1))

        return {
            "PRIMARY_MODEL": best_model,
            "SECONDARY_MODEL": second_model,
            "DEFAULT_STRATEGY": best_strategy,
            "SAFETY_FALLBACK": "pathfinder_astar",
        }


def run_full_benchmark():
    print("=" * 70)
    print("COMPETITION READINESS BENCHMARK (Phase 2F Part 3D)")
    print("BUZZ -> Ollama | temperature=0.0 | max_tokens=8")
    print("DO NOT connect real POLYCC game")
    print("=" * 70)

    bench = CompetitionBenchmark()

    try:
        health = bench._client.health()
        print(f"\n[BUZZ] status={health['status']} contract={health['contract_version']}")
    except Exception as e:
        print(f"\n[BUZZ] UNAVAILABLE: {e}")
        return None

    one_turn_results = {}
    multi_turn_results = {}
    strategy_results = {}
    latency_distributions = {}

    for model in MODELS:
        print(f"\n{'=' * 70}")
        print(f"MODEL: {model}")
        print(f"{'=' * 70}")

        print(f"\n--- Stage A: One-Turn Benchmark (15 scenarios) ---")
        ot = bench.run_one_turn_benchmark(model)
        one_turn_results[model] = ot
        print(f"  parse={ot.parse_success_rate:.0%} legal={ot.legal_action_rate:.0%} "
              f"unsafe={ot.unsafe_count} fallback={ot.fallback_count}")
        print(f"  goal_progress={ot.goal_progress_rate:.0%}")
        print(f"  latency: avg={ot.avg_latency_ms:.0f}ms p50={ot.p50_latency_ms:.0f}ms "
              f"max={ot.max_latency_ms:.0f}ms")

        print(f"\n--- Stage B: Multi-Turn Benchmark (3 episodes) ---")
        mt = bench.run_multi_turn_benchmark(model)
        multi_turn_results[model] = ModelMultiTurnAgg(model=model, total_episodes=len(mt))
        agg = multi_turn_results[model]
        for m in mt:
            agg.goals_reached += m.goal_reached
            agg.total_turns += m.total_turns
            agg.total_fallback += m.fallback_count
            agg.total_oscillation += m.oscillation_events
            agg.total_repeated_loops += m.repeated_loops
            agg.total_unsafe += m.unsafe_accepted_actions
            agg.episode_efficiencies.append(m.path_efficiency_ratio)
            if m.avg_provider_latency > 0:
                agg.latencies.append(m.avg_provider_latency)
            print(f"  [{m.episode_name}] turns={m.total_turns} goal={m.goal_reached} "
                  f"eff={m.path_efficiency_ratio:.2f} fallback={m.fallback_count} "
                  f"osc={m.oscillation_events}")
        print(f"  aggregate: goals={agg.goals_reached}/{agg.total_episodes} "
              f"eff={agg.avg_path_efficiency:.2f} fb_rate={agg.fallback_rate:.0%}")

        print(f"\n--- Stage C: Strategy Benchmark ---")
        sb = bench.run_strategy_benchmark(model)
        strategy_results[model] = sb
        for strat, metrics_list in sb.items():
            for m in metrics_list:
                print(f"  [{strat}/{m.scenario_name}] goal={m.goal_reached} "
                      f"score={m.score} health={m.health_remaining} "
                      f"turns={m.turns} eff={m.path_efficiency:.2f} "
                      f"osc={m.oscillation_events}")

        print(f"\n--- Stage D: Latency Classification ---")
        all_lats = list(ot.latencies)
        for m in mt:
            if m.avg_provider_latency > 0:
                all_lats.append(m.avg_provider_latency)
        ld = LatencyDistribution(model=model, latencies=all_lats)
        latency_distributions[model] = ld
        cls = ld.classify()
        print(f"  count={ld.count} avg={ld.avg_ms:.0f}ms p50={ld.p50_ms:.0f}ms "
              f"p90={ld.p90_ms:.0f}ms max={ld.max_ms:.0f}ms")
        print(f"  distribution: {cls}")

    print(f"\n{'=' * 70}")
    print("Stage E: SPATHODEA_INTERNAL_READINESS_SCORE")
    print(f"{'=' * 70}")

    readiness = bench.compute_readiness_score(one_turn_results, multi_turn_results, strategy_results)
    for model, score in readiness.items():
        d = score.to_dict()
        print(f"\n  [{model}] grade={d['grade']} score={d['SPATHODEA_INTERNAL_READINESS_SCORE']}")
        for k, v in d["component_scores"].items():
            print(f"    {k}: {v}")

    print(f"\n{'=' * 70}")
    print("Stage F: PRIMARY + FALLBACK CONFIG")
    print(f"{'=' * 70}")

    config = bench.select_config(readiness, strategy_results)
    for k, v in config.items():
        print(f"  {k}: {v}")

    results = {
        "one_turn": {m: ot.to_dict() for m, ot in one_turn_results.items()},
        "multi_turn": {m: mt.to_dict() for m, mt in multi_turn_results.items()},
        "strategy": {
            m: {s: [x.to_dict() for x in ml] for s, ml in sr.items()}
            for m, sr in strategy_results.items()
        },
        "latency": {m: ld.to_dict() for m, ld in latency_distributions.items()},
        "readiness": {m: s.to_dict() for m, s in readiness.items()},
        "config": config,
    }

    print(f"\n{'=' * 70}")
    print("BENCHMARK COMPLETE")
    print(f"{'=' * 70}")
    return results


if __name__ == "__main__":
    results = run_full_benchmark()
    if results:
        out = os.path.join(os.path.dirname(__file__), "competition_benchmark_results.json")
        with open(out, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nResults saved to: {out}")

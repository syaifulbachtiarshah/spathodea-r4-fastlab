"""
SPATHODEA R4 FASTLAB — Benchmark Scenarios (Phase 2F Part 3D)
Deterministic scenarios for competition readiness benchmark.

All scenarios are fully deterministic. No randomness. No live game.
"""

from .game_state import GameState, Position


# =============================================================================
# Stage A: One-Turn Scenarios (12 minimum)
# =============================================================================

def build_one_turn_scenarios() -> list[tuple[str, GameState, dict]]:
    """Build deterministic one-turn scenarios.

    Returns list of (name, state, expected) tuples.
    expected contains:
        - legal_actions: list of valid action strings
        - blocked_actions: list of invalid action strings
        - goal_direction: preferred direction toward goal
        - ideal_action: best single action (if obvious)
    """
    scenarios = []

    # 1. Corner A1 — UP/LEFT out of bounds
    s = GameState(width=5, height=5, agent_pos=Position(0, 0),
                  goal=Position(4, 4), turn=0, health=100)
    scenarios.append(("corner_A1", s, {
        "legal_actions": ["DOWN", "RIGHT", "WAIT"],
        "blocked_actions": ["UP", "LEFT"],
        "goal_direction": "RIGHT+DOWN",
        "ideal_action": "RIGHT",
    }))

    # 2. Corner E1 — UP/RIGHT out of bounds
    s = GameState(width=5, height=5, agent_pos=Position(4, 0),
                  goal=Position(0, 4), turn=0, health=100)
    scenarios.append(("corner_E1", s, {
        "legal_actions": ["DOWN", "LEFT", "WAIT"],
        "blocked_actions": ["UP", "RIGHT"],
        "goal_direction": "LEFT+DOWN",
        "ideal_action": "LEFT",
    }))

    # 3. Corner A5 — DOWN/LEFT out of bounds
    s = GameState(width=5, height=5, agent_pos=Position(0, 4),
                  goal=Position(4, 0), turn=0, health=100)
    scenarios.append(("corner_A5", s, {
        "legal_actions": ["UP", "RIGHT", "WAIT"],
        "blocked_actions": ["DOWN", "LEFT"],
        "goal_direction": "RIGHT+UP",
        "ideal_action": "RIGHT",
    }))

    # 4. Corner E5 — DOWN/RIGHT out of bounds
    s = GameState(width=5, height=5, agent_pos=Position(4, 4),
                  goal=Position(0, 0), turn=0, health=100)
    scenarios.append(("corner_E5", s, {
        "legal_actions": ["UP", "LEFT", "WAIT"],
        "blocked_actions": ["DOWN", "RIGHT"],
        "goal_direction": "LEFT+UP",
        "ideal_action": "LEFT",
    }))

    # 5. Edge top C1 — UP out of bounds
    s = GameState(width=5, height=5, agent_pos=Position(2, 0),
                  goal=Position(2, 4), turn=0, health=100)
    scenarios.append(("edge_C1", s, {
        "legal_actions": ["DOWN", "LEFT", "RIGHT", "WAIT"],
        "blocked_actions": ["UP"],
        "goal_direction": "DOWN",
        "ideal_action": "DOWN",
    }))

    # 6. Edge left A3 — LEFT out of bounds
    s = GameState(width=5, height=5, agent_pos=Position(0, 2),
                  goal=Position(4, 2), turn=0, health=100)
    scenarios.append(("edge_A3", s, {
        "legal_actions": ["UP", "DOWN", "RIGHT", "WAIT"],
        "blocked_actions": ["LEFT"],
        "goal_direction": "RIGHT",
        "ideal_action": "RIGHT",
    }))

    # 7. Edge right E3 — RIGHT out of bounds
    s = GameState(width=5, height=5, agent_pos=Position(4, 2),
                  goal=Position(0, 2), turn=0, health=100)
    scenarios.append(("edge_E3", s, {
        "legal_actions": ["UP", "DOWN", "LEFT", "WAIT"],
        "blocked_actions": ["RIGHT"],
        "goal_direction": "LEFT",
        "ideal_action": "LEFT",
    }))

    # 8. Edge bottom C5 — DOWN out of bounds
    s = GameState(width=5, height=5, agent_pos=Position(2, 4),
                  goal=Position(2, 0), turn=0, health=100)
    scenarios.append(("edge_C5", s, {
        "legal_actions": ["UP", "LEFT", "RIGHT", "WAIT"],
        "blocked_actions": ["DOWN"],
        "goal_direction": "UP",
        "ideal_action": "UP",
    }))

    # 9. Center C3 — all directional moves legal
    s = GameState(width=5, height=5, agent_pos=Position(2, 2),
                  goal=Position(4, 4), turn=0, health=100)
    scenarios.append(("center_C3", s, {
        "legal_actions": ["UP", "DOWN", "LEFT", "RIGHT", "WAIT"],
        "blocked_actions": [],
        "goal_direction": "RIGHT+DOWN",
        "ideal_action": "RIGHT",
    }))

    # 10. Wall beside — B2 blocks RIGHT from A2
    s = GameState(width=5, height=5, agent_pos=Position(0, 1),
                  walls={Position(1, 1)}, goal=Position(4, 4), turn=0, health=100)
    scenarios.append(("wall_beside", s, {
        "legal_actions": ["UP", "DOWN", "WAIT"],
        "blocked_actions": ["LEFT", "RIGHT"],
        "goal_direction": "RIGHT+DOWN",
        "ideal_action": "DOWN",
    }))

    # 11. Goal adjacent — agent at A1, goal at B1
    s = GameState(width=5, height=5, agent_pos=Position(0, 0),
                  goal=Position(1, 0), turn=0, health=100)
    scenarios.append(("goal_adjacent", s, {
        "legal_actions": ["DOWN", "RIGHT", "WAIT"],
        "blocked_actions": ["UP", "LEFT"],
        "goal_direction": "RIGHT",
        "ideal_action": "RIGHT",
    }))

    # 12. Reward vs goal — coin at B1, goal at B2
    s = GameState(width=5, height=5, agent_pos=Position(0, 0),
                  coins={Position(1, 0)}, goal=Position(1, 1), turn=0, health=100)
    scenarios.append(("reward_vs_goal", s, {
        "legal_actions": ["DOWN", "RIGHT", "WAIT"],
        "blocked_actions": ["UP", "LEFT"],
        "goal_direction": "RIGHT+DOWN",
        "ideal_action": "RIGHT",
    }))

    # 13. Hazard adjacent — hazard at B1, agent at A1, goal at C1
    s = GameState(width=5, height=5, agent_pos=Position(0, 0),
                  hazards={Position(1, 0)}, goal=Position(2, 0), turn=0, health=100)
    scenarios.append(("hazard_adjacent", s, {
        "legal_actions": ["DOWN", "RIGHT", "WAIT"],
        "blocked_actions": ["UP", "LEFT"],
        "goal_direction": "RIGHT",
        "ideal_action": "DOWN",
    }))

    # 14. Forced DOWN — wall at B1, hazard at A2, agent at A1
    s = GameState(width=5, height=5, agent_pos=Position(0, 0),
                  walls={Position(1, 0)}, hazards={Position(0, 1)},
                  goal=Position(4, 4), turn=0, health=100)
    scenarios.append(("forced_down", s, {
        "legal_actions": ["RIGHT", "WAIT"],
        "blocked_actions": ["UP", "LEFT"],
        "goal_direction": "RIGHT+DOWN",
        "ideal_action": "RIGHT",
    }))

    # 15. Low health — agent at 10hp, hazard ahead
    s = GameState(width=5, height=5, agent_pos=Position(2, 2),
                  hazards={Position(3, 2)}, goal=Position(4, 2), turn=5, health=10)
    scenarios.append(("low_health", s, {
        "legal_actions": ["UP", "DOWN", "LEFT", "RIGHT", "WAIT"],
        "blocked_actions": [],
        "goal_direction": "RIGHT",
        "ideal_action": "UP",
    }))

    return scenarios


# =============================================================================
# Stage B: Multi-Turn Episodes
# =============================================================================

def build_multi_turn_episodes() -> list[tuple[str, GameState, dict]]:
    """Build deterministic multi-turn episodes.

    Returns list of (name, state, config) tuples.
    config contains:
        - max_turns: maximum turns to run
        - optimal_path_length: BFS shortest path length
        - strategy: strategy profile to use
    """
    episodes = []

    # 1. Simple empty 5x5 — A1 to E5
    s = GameState(width=5, height=5, agent_pos=Position(0, 0),
                  goal=Position(4, 4), turn=0, health=100)
    episodes.append(("simple_empty", s, {
        "max_turns": 10,
        "optimal_path_length": 8,
        "strategy": "exploration",
    }))

    # 2. Wall detour — vertical wall forces route change
    s = GameState(width=5, height=5, agent_pos=Position(0, 0),
                  walls={Position(1, 0), Position(1, 1), Position(1, 2)},
                  goal=Position(4, 4), turn=0, health=100)
    episodes.append(("wall_detour", s, {
        "max_turns": 10,
        "optimal_path_length": 8,
        "strategy": "exploration",
    }))

    # 3. Reward + hazard — coin on path, hazard off-path
    s = GameState(width=5, height=5, agent_pos=Position(0, 0),
                  coins={Position(2, 0)}, hazards={Position(3, 1)},
                  goal=Position(4, 4), turn=0, health=100)
    episodes.append(("reward_hazard", s, {
        "max_turns": 10,
        "optimal_path_length": 8,
        "strategy": "exploration",
    }))

    return episodes


# =============================================================================
# Stage C: Strategy-Specific Scenarios
# =============================================================================

def build_strategy_scenarios() -> dict[str, list[tuple[str, GameState, dict]]]:
    """Build scenarios designed to expose strategy differences.

    Returns dict mapping strategy_name to list of (name, state, config) tuples.
    """
    scenarios = {}

    # SAFE strategy — hazards/enemy pressure
    safe_scenarios = []

    # Safe scenario 1: path through hazard zone
    s = GameState(width=5, height=5, agent_pos=Position(0, 2),
                  hazards={Position(2, 2), Position(3, 2)},
                  goal=Position(4, 2), turn=0, health=100)
    safe_scenarios.append(("safe_hazard_detour", s, {
        "max_turns": 10,
        "optimal_path_length": 4,
        "expected_hazard_avoidance": True,
    }))

    # Safe scenario 2: enemy proximity
    s = GameState(width=5, height=5, agent_pos=Position(0, 0),
                  enemies={Position(2, 1)}, goal=Position(4, 4),
                  turn=0, health=100)
    safe_scenarios.append(("safe_enemy_avoidance", s, {
        "max_turns": 10,
        "optimal_path_length": 8,
        "expected_enemy_avoidance": True,
    }))

    scenarios["safe"] = safe_scenarios

    # SPEEDRUN — clear shortest route
    speedrun_scenarios = []

    # Speedrun scenario 1: empty grid, straight shot
    s = GameState(width=5, height=5, agent_pos=Position(0, 0),
                  goal=Position(4, 0), turn=0, health=100)
    speedrun_scenarios.append(("speedrun_straight", s, {
        "max_turns": 6,
        "optimal_path_length": 4,
    }))

    # Speedrun scenario 2: slight detour needed
    s = GameState(width=5, height=5, agent_pos=Position(0, 0),
                  walls={Position(2, 0)}, goal=Position(4, 0),
                  turn=0, health=100)
    speedrun_scenarios.append(("speedrun_detour", s, {
        "max_turns": 8,
        "optimal_path_length": 6,
    }))

    scenarios["speedrun"] = speedrun_scenarios

    # REWARD_MAX — reward detour available
    reward_scenarios = []

    # Reward scenario 1: coin off main path
    s = GameState(width=5, height=5, agent_pos=Position(0, 0),
                  coins={Position(2, 1)}, goal=Position(4, 4),
                  turn=0, health=100)
    reward_scenarios.append(("reward_detour", s, {
        "max_turns": 10,
        "optimal_path_length": 8,
        "expected_coin_collection": True,
    }))

    # Reward scenario 2: multiple coins
    s = GameState(width=5, height=5, agent_pos=Position(0, 0),
                  coins={Position(1, 0), Position(2, 1), Position(3, 2)},
                  goal=Position(4, 4), turn=0, health=100)
    reward_scenarios.append(("reward_multiple", s, {
        "max_turns": 10,
        "optimal_path_length": 8,
        "expected_coin_collection": True,
    }))

    scenarios["reward_max"] = reward_scenarios

    # ADAPTIVE — health/hazard/reward combination
    adaptive_scenarios = []

    # Adaptive scenario 1: mixed risk/reward
    s = GameState(width=5, height=5, agent_pos=Position(0, 0),
                  coins={Position(2, 0)}, hazards={Position(3, 1)},
                  enemies=set(), goal=Position(4, 4),
                  turn=0, health=80)
    adaptive_scenarios.append(("adaptive_mixed", s, {
        "max_turns": 10,
        "optimal_path_length": 8,
        "expected_balance": True,
    }))

    # Adaptive scenario 2: low health + reward nearby
    s = GameState(width=5, height=5, agent_pos=Position(0, 0),
                  coins={Position(1, 1)}, hazards={Position(2, 2)},
                  goal=Position(4, 4), turn=3, health=30)
    adaptive_scenarios.append(("adaptive_low_health", s, {
        "max_turns": 10,
        "optimal_path_length": 8,
        "expected_conservative": True,
    }))

    scenarios["adaptive"] = adaptive_scenarios

    return scenarios

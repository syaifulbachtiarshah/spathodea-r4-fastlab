# 🎮 Game Agent Integration Specification

> **SPATHODEA R4 FASTLAB — Phase 2F (Parts 1 & 2)**
> Module: `game/`
> Status: Offline adapter layer with BUZZ bridge simulation — no live competition connection
> Date: 2026-08-24

---

## 1. Overview

The Game Agent Adapter provides an offline adapter layer for the POLYCC grid-navigation competition game. It converts game state + strategy into deterministic action recommendations without requiring LLM calls or network access.

### 1.1 Future Topology

```
GAME (competition API)
  → GameAgentAdapter (state normalization + strategy)
  → BUZZ gateway (POST /v1/generate)
  → LLM provider (openai/gemini/ollama)
  → normalized action
  → GAME
```

### 1.2 Current Topology (Phase 2F Part 2)

```
GAME STATE (manual/test)
  → GameAgentAdapter (planning context)
  → BuzzGameBridge (ProviderRequest construction)
  → SimulatedProvider (mock responses)
  → ActionParser (response parsing)
  → Safety Gate (action validation)
  → GameSimulator (state application)
  → TurnController (orchestration + combat log)
```

Simulated BUZZ bridge. No live provider calls. Fully offline.

---

## 2. Coordinate System

Grid positions use alphanumeric labels:

| Label | Internal (col, row) | Description |
|-------|---------------------|-------------|
| `A1`  | `(0, 0)`           | Top-left corner |
| `B3`  | `(1, 2)`           | Column B, Row 3 |
| `J10` | `(9, 9)`           | Column J, Row 10 |
| `Z1`  | `(25, 0)`          | Column Z, Row 1 |

- **Column** = letter (A=0, B=1, ..., Z=25, AA=26, AB=27, ...)
- **Row** = 1-based number (1=top row internally 0-indexed)
- Internal representation: `Position(col: int, row: int)` — 0-indexed

---

## 3. Game State Schema

```python
GameState:
    width: int              # Grid columns (≥ 1)
    height: int             # Grid rows (≥ 1)
    agent_pos: Position     # Current agent location
    walls: set[Position]    # Impassable cells
    keys: set[Position]     # Collectible keys
    doors: dict[Position → Position|None]  # Door → required key (None = any key)
    coins: set[Position]    # Collectible rewards
    enemies: set[Position]  # Dangerous NPCs
    hazards: set[Position]  # Traps/damage zones
    goal: Position|None     # Objective/exit
    unknown: set[Position]  # Fog-of-war cells
    collected_keys: set[Position]   # Keys already held
    collected_coins: set[Position]  # Coins already collected
    turn: int               # Current turn number
    score: int              # Accumulated score
    health: int             # Agent HP (0–100)
```

### 3.1 Cell Type Priority

When a position has multiple attributes, display priority (highest first):

1. AGENT (agent's current position)
2. WALL (impassable)
3. DOOR (may be locked)
4. ENEMY (dangerous)
5. HAZARD (dangerous)
6. GOAL (objective)
7. KEY (collectible)
8. COIN (reward)
9. UNKNOWN (fog)
10. EMPTY (walkable)

### 3.2 Walkability Rules

A cell is walkable if:
- Within grid bounds
- NOT a wall
- NOT a locked door (unless agent holds required key)

Enemies and hazards are walkable (but dangerous).

---

## 4. Action Schema

### 4.1 Core Actions (Active)

| Action | Delta (dcol, drow) | Effect |
|--------|-------------------|--------|
| `UP`    | `(0, -1)` | Move one cell up (decrease row) |
| `DOWN`  | `(0, +1)` | Move one cell down (increase row) |
| `LEFT`  | `(-1, 0)` | Move one cell left (decrease col) |
| `RIGHT` | `(+1, 0)` | Move one cell right (increase col) |
| `WAIT`  | `(0, 0)`  | Stay in place (skip turn) |

### 4.2 Future Actions (Reserved)

| Action | Purpose | Status |
|--------|---------|--------|
| `INTERACT` | Interact with adjacent object | Not implemented |
| `PICKUP` | Pick up item at current position | Not implemented |
| `ATTACK` | Attack adjacent enemy | Not implemented |

Future actions are defined but not active until competition API confirms support.

### 4.3 Action Validity

An action is valid if:
- The resulting position is walkable
- `WAIT` is always valid

Invalid actions result in no movement (agent stays in place).

---

## 5. Strategy Profiles

### 5.1 Profile Summary

| Profile | Goal | Risk Tolerance | Collects Rewards |
|---------|------|----------------|-----------------|
| `safe` | Minimize danger exposure | 0.0 (risk-averse) | No |
| `speedrun` | Shortest path to goal | 1.0 (risk-neutral) | No |
| `reward_max` | Maximize score | 0.4 (moderate) | Yes |
| `adaptive` | Balance all factors | 0.5 (balanced) | Yes |

### 5.2 Cost Weights (Default Values)

| Parameter | safe | speedrun | reward_max | adaptive |
|-----------|------|----------|-----------|----------|
| `hazard_weight` | 50.0 | 1.0 | 15.0 | 10.0 |
| `enemy_weight` | 40.0 | 1.0 | 12.0 | 8.0 |
| `reward_weight` | 0.0 | 0.0 | -5.0 | -2.0 |
| `door_weight` | 100.0 | 5.0 | 20.0 | 30.0 |
| `movement_cost` | 1.0 | 1.0 | 1.0 | 1.0 |
| `max_detour_ratio` | 3.0 | 1.0 | 3.0 | 2.0 |
| `enemy_proximity_radius` | 3 | 0 | 2 | 2 |

### 5.3 Strategy Behavior

**safe:**
- Weighted A* with very high hazard/enemy costs
- Avoids any cell adjacent to enemies (radius=3)
- Never detours for rewards
- Prefers longer safe paths over short dangerous ones

**speedrun:**
- Pure A* (Manhattan heuristic, uniform cost)
- Ignores hazards/enemies as cost factors
- Shortest path regardless of danger
- Only collects keys when doors block the path

**reward_max:**
- Weighted A* with negative reward costs (incentive)
- Actively detours to collect coins within `max_detour_ratio`
- Still reaches objective (never abandons goal for rewards)
- Moderate hazard avoidance

**adaptive:**
- Adjusts behavior based on health:
  - health > 50: Collects nearby rewards
  - health ≤ 30: Switches to goal-priority mode
- Moderate cost weights for balanced routing
- Context-sensitive decisions

---

## 6. Pathfinding Algorithms

### 6.1 BFS (Breadth-First Search)

- **Use case:** Unweighted shortest path, reachability checks
- **Guarantee:** Optimal path length (fewest steps)
- **Cost model:** Uniform (every step = 1)
- **Ignores:** Hazards, enemies, rewards as cost factors

### 6.2 A* (A-Star)

- **Use case:** Heuristic shortest path (speedrun strategy)
- **Heuristic:** Manhattan distance
- **Guarantee:** Optimal given uniform costs
- **Ignores:** Cell danger levels

### 6.3 Weighted A*

- **Use case:** Cost-aware pathfinding (safe/reward_max/adaptive)
- **Heuristic:** Manhattan distance × movement_cost
- **Cost model:** Per-cell costs based on strategy weights
- **Accounts for:** Hazards, enemies, enemy adjacency, rewards, unknown cells

### 6.4 Cost Calculation (Weighted A*)

```python
cell_cost(pos) = movement_cost
    + hazard_weight    (if pos is hazard)
    + enemy_weight×5   (if pos is enemy)
    + enemy_adjacent   (if pos is adjacent to enemy)
    + unknown_cost     (if pos is unknown/fog)
    + reward_weight    (if pos has uncollected reward — usually negative)

# Floor at 0.01 to prevent zero/negative costs
final_cost = max(0.01, cell_cost)
```

---

## 7. Game Agent Adapter

### 7.1 Interface

```python
adapter = GameAgentAdapter(
    strategy_profile="adaptive",      # safe|speedrun|reward_max|adaptive
    navigation_prompt=None,           # Optional untrusted guidance
)

context = adapter.plan(game_state)    # Returns PlanningContext
action = context.recommended_action   # Action enum value
```

### 7.2 Planning Context Output

```python
PlanningContext:
    game_state_summary: str           # Compact state description
    objective: str                    # Current objective description
    strategy_profile: str             # Active strategy name
    path_to_goal: PathResult|None     # Planned path
    available_rewards: list[str]      # Uncollected reward labels
    threats: list[str]                # Known threat labels
    recommended_action: Action        # Next action to take
    reasoning: str                    # Human-readable explanation
    navigation_prompt: str|None       # External guidance (stored, not trusted)
    confidence: float                 # 0.0–1.0 confidence level
```

### 7.3 Decision Priority

1. If no goal defined → WAIT
2. If at goal → WAIT (goal reached)
3. If path blocked and keys available → seek nearest key
4. If path blocked and no keys → WAIT (unreachable)
5. Strategy-specific routing to goal

### 7.4 Navigation Prompt Handling

- **Stored** in PlanningContext for logging/audit
- **Never trusted** as game-state truth
- **Game state always overrides** contradictory prompt claims
- Prompt cannot make agent ignore walls, enemies, or goal position
- Future: may influence tie-breaking in LLM-assisted mode

---

## 8. Combat Log Format

Each turn produces a structured log entry:

```json
{
    "turn": 5,
    "agent_position": "C3",
    "chosen_action": "RIGHT",
    "strategy": "adaptive",
    "reason": "Adaptive: following balanced path (3 steps)",
    "known_rewards": 2,
    "known_hazards": 1,
    "path_length": 3,
    "status": "ok"
}
```

### 8.1 Status Values

| Status | Meaning |
|--------|---------|
| `ok` | Action executed normally |
| `damaged` | Agent took damage this turn |
| `collected` | Item collected (key or coin) |
| `blocked` | Action was invalid/blocked |
| `goal_reached` | Agent arrived at goal |

### 8.2 Security

- No API keys or secrets in log
- No raw prompts stored (only navigation_prompt reference)
- No provider credentials
- Safe for external audit/export

---

## 9. BUZZ Bridge (Phase 2F Part 2 — Simulated)

### 9.1 Bridge Flow (Implemented)

```
GameAgentAdapter.plan(state)
  → PlanningContext
  → BuzzGameBridge.build_request(state, context)
  → ProviderRequest v0.2.0
  → SimulatedProvider.generate(request)
  → ProviderResponse
  → ActionParser.parse(response.content)
  → ActionParseResult
  → Safety Gate validation
  → final Action
  → GameSimulator.apply_action(action)
  → TurnLogEntry
```

### 9.2 Request Mapping (GAME → BUZZ)

| Game Concept | ProviderRequest Field | Value |
|-------------|----------------------|-------|
| Navigation intent | `metadata.task_intent` | `"game_navigation"` |
| Source identifier | `metadata.source` | `"SPATHODEA_GAME"` |
| Turn number | `metadata.turn` | `int` |
| Agent position | `metadata.agent_position` | Label (e.g. "C3") |
| Strategy name | `metadata.strategy` | Profile name |
| Grid dimensions | `metadata.grid_width/height` | `int` |
| Reward count | `metadata.known_rewards` | `int` |
| Hazard count | `metadata.known_hazards` | `int` |
| Enemy count | `metadata.known_enemies` | `int` |
| Goal position | `metadata.goal` | Label or null |
| Task type | `task_type` | `"generate"` (v0.2.0 compatible) |
| Provider | `provider_preference` | Configurable |
| Reviewer | `reviewer_preference` | Configurable |
| Execution | `execution_mode` | Configurable (default: sync) |
| Temperature | `temperature` | `0.3` (low for deterministic actions) |
| Max tokens | `max_tokens` | `50` (actions are short) |

**Security:** No hidden validator data, expected_behavior, or validation_rules are sent.

### 9.3 Contract Compatibility

- Uses existing BUZZ v0.2.0 contract (unchanged)
- `task_type = "generate"` (game_navigation is NOT a valid task_type)
- Intent communicated via `metadata.task_intent = "game_navigation"`
- `metadata.source = "SPATHODEA_GAME"`
- Provider/reviewer preference flows through existing fields
- All requests pass `ProviderRequest.validate()` without errors

### 9.4 Action Parsing Rules

Provider output is parsed in priority order:

| Priority | Format | Example | Method |
|----------|--------|---------|--------|
| 1 | Fenced JSON | ` ```json\n{"action":"UP"}\n``` ` | `fenced_json` |
| 2 | Plain JSON | `{"action": "RIGHT"}` | `json` |
| 3 | Plain text | `UP` | `plain_text` |

**Rejection criteria (immediate fail):**
- Empty or whitespace-only output
- HTML content (`<html>`, `<body>`, etc.)
- Python tracebacks
- Malformed JSON (when JSON-like input detected)
- Multiple conflicting action words
- Unknown/invalid action value
- Future reserved actions (INTERACT, PICKUP, ATTACK)

**Case handling:** All action names are case-insensitive.

### 9.5 Safety Gate

Before applying any provider-suggested action:

| Check | Condition | Result if Failed |
|-------|-----------|-----------------|
| Grid bounds | Target position within grid | Fallback |
| Wall collision | Target is not a wall | Fallback |
| Locked door | Target not locked (or key held) | Fallback |
| Action validity | Action produces valid movement | Fallback |

**WAIT is always safe** — never rejected by safety gate.

### 9.6 Fallback Behavior

When provider output cannot produce a valid action:

| Priority | Fallback | Source Label |
|----------|----------|-------------|
| 1 | Pathfinder-computed action toward goal | `fallback_pathfinder` |
| 2 | WAIT | `fallback_wait` |

Fallback reason is always recorded in the turn log.

### 9.7 Provider Failure Handling

| Failure Mode | Response | Fallback Triggered |
|-------------|----------|-------------------|
| Timeout (>5000ms) | Use pathfinder | Yes |
| Unavailable (connection refused) | Use pathfinder | Yes |
| Contract mismatch (wrong version) | Do NOT trust output | Yes |
| Invalid/unparseable response | Use pathfinder | Yes |
| Valid action into wall | Safety gate → pathfinder | Yes |

**The game NEVER crashes** due to provider failure.

---

## 10. Turn Controller

### 10.1 Pipeline Per Turn

```
1. state → GameAgentAdapter.plan() → PlanningContext
2. PlanningContext → BuzzGameBridge.request_action() → BridgeResult
3. BridgeResult.action → GameSimulator.apply_action() → ActionResult
4. Record TurnLogEntry with all metrics
```

### 10.2 Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_turns` | 100 | Maximum turns before forced termination |
| `strategy` | "adaptive" | Strategy profile name |
| `provider` | "mock" | Provider preference for BUZZ |
| `reviewer` | None | Reviewer preference |
| `execution_mode` | "sync" | BUZZ execution mode |

### 10.3 Episode Termination

| Condition | `termination_reason` |
|-----------|---------------------|
| Agent reaches goal | `goal_reached` |
| Agent health ≤ 0 | `agent_dead` |
| Turn count ≥ max_turns | `max_turns_exceeded` |

---

## 11. Game Simulator

### 11.1 Action Application Rules

| Event | Effect |
|-------|--------|
| Move to coin cell | Collect coin, +`coin_reward` score |
| Move to key cell | Collect key, unlock matching doors |
| Move to hazard cell | Take `hazard_damage` to health |
| Move to enemy cell | Take `enemy_damage` to health |
| Move to goal cell | +`goal_reward` score, episode ends |
| Move to wall/locked door | Action blocked, agent stays |
| WAIT | Turn advances, no movement |

### 11.2 Default Scoring

| Parameter | Default Value |
|-----------|---------------|
| `coin_reward` | 10 |
| `key_reward` | 5 |
| `goal_reward` | 100 |
| `hazard_damage` | 20 |
| `enemy_damage` | 30 |
| `turn_penalty` | 0 |

---

## 12. Combat Log (Extended — Part 2)

Each turn produces an extended structured log entry:

```json
{
    "turn": 5,
    "position_before": "C3",
    "provider_requested": "mock",
    "provider_used": "mock",
    "raw_action_summary": "RIGHT",
    "parsed_action": "RIGHT",
    "final_action": "RIGHT",
    "fallback_used": false,
    "fallback_reason": "",
    "position_after": "D3",
    "score": 10,
    "health": 100,
    "status": "ok",
    "pathfinder_ms": 0.125,
    "bridge_processing_ms": 0.042,
    "turn_processing_ms": 0.312
}
```

### 12.1 Status Values (Extended)

| Status | Meaning |
|--------|---------|
| `ok` | Action executed normally |
| `damaged` | Agent took damage this turn |
| `collected` | Item collected (key or coin) |
| `blocked` | Action was invalid/blocked |
| `goal_reached` | Agent arrived at goal |
| `dead` | Agent health dropped to 0 |
| `fallback` | Provider failed, fallback used |

### 12.2 Security

- No API keys or secrets in log
- No raw prompts stored (only truncated summary ≤100 chars)
- No provider credentials
- No validation rules or hidden data
- Safe for external audit/export

---

## 13. Performance Metrics

Timing is tracked **separately** to avoid mixing local computation with future provider latency:

| Metric | Scope | Measures |
|--------|-------|----------|
| `pathfinder_ms` | Per turn | Time in GameAgentAdapter.plan() (includes pathfinding) |
| `bridge_processing_ms` | Per turn | Time in BuzzGameBridge (request build + parse + safety gate) |
| `turn_processing_ms` | Per turn | Total wall-clock time for the entire turn |
| `total_pathfinder_ms` | Episode | Sum of all pathfinder_ms |
| `total_bridge_ms` | Episode | Sum of all bridge_processing_ms |
| `total_turn_ms` | Episode | Sum of all turn_processing_ms |

**Important:** These do NOT include future provider inference latency. When live providers are connected, provider latency will be a separate metric.

---

## 14. File Structure

```
game/
├── __init__.py              # Package exports (Part 1 + Part 2)
├── game_state.py            # GameState + Position + CellType
├── action_schema.py         # Action enum + ActionResult
├── strategy.py              # Strategy profiles + configuration
├── pathfinder.py            # BFS + A* + Weighted A* algorithms
├── game_agent_adapter.py    # GameAgentAdapter + PlanningContext + CombatLogEntry
├── action_parser.py         # ActionParser + ActionParseResult (Part 2)
├── buzz_game_bridge.py      # BuzzGameBridge + BridgeConfig + SimulatedProvider (Part 2)
├── game_simulator.py        # GameSimulator + SimulationMetrics + SimConfig (Part 2)
└── turn_controller.py       # TurnController + TurnLogEntry + EpisodeResult (Part 2)

tests/
├── test_game_adapter.py     # Part 1: 10 scenario tests + unit tests (59 tests)
└── test_game_buzz_bridge.py # Part 2: 20+ bridge/simulator tests (50+ tests)

docs/
└── GAME_AGENT_INTEGRATION_SPEC.md  # This document
```

---

## 15. Assumptions Requiring Official Competition Evidence

The following design decisions are based on reasonable assumptions and **require validation** against the official POLYCC competition specification when available:

| # | Assumption | Impact if Wrong | Mitigation |
|---|-----------|-----------------|------------|
| 1 | Grid uses discrete cardinal movement (no diagonal) | Action schema needs expansion | FutureAction enum ready for extensions |
| 2 | Coordinate system is column-letter + row-number | Label parsing needs update | Position.from_label() is isolated and replaceable |
| 3 | Turn-based (not real-time) | May need async/timing layer | Adapter is stateless per call |
| 4 | Single agent (not multi-agent) | State needs agent_id field | Adapter is instance-based |
| 5 | Keys unlock specific doors (not generic) | Door-key mapping logic changes | doors dict already supports None (any key) |
| 6 | Enemies are static (not moving) | Pathfinding needs prediction | Can extend with enemy_movement model |
| 7 | Full observability (no fog-of-war by default) | Unknown cells handling differs | unknown set already supported |
| 8 | Goal is a single fixed position | May need multi-goal support | find_path_via_waypoints() exists |
| 9 | Health is 0–100 integer | Scale may differ | health field is generic int |
| 10 | Score is additive per coin | Scoring model may be complex | score field allows arbitrary updates |
| 11 | API response format for actions | Adapter translation layer needed | Action schema is adapter-based |
| 12 | Competition timing constraints | May need response budget | plan() is O(grid_size) deterministic |

---

## 16. Testing

### 16.1 Part 1 Test Scenarios

| # | Scenario | Validates |
|---|----------|-----------|
| 1 | Simple shortest path | BFS/A* correctness |
| 2 | Blocked path (full wall) | Unreachability detection |
| 3 | Key then locked door | Key collection → door opening sequence |
| 4 | Avoid hazard | Safe strategy weighted routing |
| 5 | Collect reward | reward_max detour behavior |
| 6 | Reward vs shortest tradeoff | max_detour_ratio enforcement |
| 7 | Enemy avoidance | Enemy cost + adjacency penalty |
| 8 | Unreachable objective | Graceful WAIT + low confidence |
| 9 | Contradictory navigation prompt | State overrides untrusted prompt |
| 10 | Adaptive strategy | Health-based behavior switching |

### 16.2 Part 2 Test Scenarios (Bridge / Simulator)

| # | Scenario | Validates |
|---|----------|-----------|
| 1 | Valid UP action | Parser accepts plain UP |
| 2 | Valid DOWN action | Parser accepts plain DOWN |
| 3 | Valid LEFT action | Parser accepts plain LEFT |
| 4 | Valid RIGHT action | Parser accepts plain RIGHT |
| 5 | JSON action output | Parser handles `{"action":"X"}` |
| 6 | Malformed JSON | Fallback triggered on bad JSON |
| 7 | Invalid action word | Unknown word → fallback |
| 8 | Conflicting actions | Multiple actions → fallback |
| 9 | Wall collision | Safety gate blocks wall move |
| 10 | Out-of-bounds | Safety gate blocks edge move |
| 11 | Locked door | Safety gate blocks locked door |
| 12 | Provider timeout | Simulated timeout → pathfinder fallback |
| 13 | Provider unavailable | Simulated unavailable → fallback |
| 14 | Contract mismatch | Wrong version → do not trust output |
| 15 | Fallback to pathfinder | Pathfinder gives valid action toward goal |
| 16 | Fallback to WAIT | No path available → WAIT |
| 17 | Goal reached | Simulator detects goal + awards score |
| 18 | Coin collection | Coin collected + score updated |
| 19 | Key collection | Key collected + door unlocked |
| 20 | Hazard contact | Hazard damages health |
| 21 | Max-turn termination | Episode ends at turn limit |
| 22 | Strategy propagation | Strategy flows through request metadata |
| 23 | Full simulated episode | End-to-end episode with metrics |

### 16.3 Test Properties

- **Deterministic:** Same inputs always produce same outputs
- **Offline:** No network, no API keys, no LLM
- **Fast:** All tests complete in < 1 second
- **Independent:** No shared state between tests

---

*Document version: 2F/2.0*
*Created: 2026-08-24*
*Updated: 2026-08-24 (Part 2 — BUZZ bridge simulation)*
*Status: Offline adapter layer with simulated bridge — awaiting competition API specification*

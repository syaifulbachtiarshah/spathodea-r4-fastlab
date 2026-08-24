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

## 14. Contract Translator (Phase 2F Part 3A)

### 14.1 Problem

FASTLAB internal contract and ATAN BUZZ wire contract both use version `"0.2.0"` but their execution/task semantics differ:

| Dimension | FASTLAB Internal | ATAN BUZZ Wire |
|-----------|-----------------|----------------|
| `execution_mode` | `sync \| async \| batch` | `single \| fallback \| consensus` |
| `task_type` | `generate \| review \| score \| adversarial \| paraphrase` | `game_navigation` (+ future wire tasks) |
| Game intent | `metadata.task_intent = "game_navigation"` | `task_type = "game_navigation"` |

These are **NOT equivalent dimensions**. Translation is explicit, not mechanical.

### 14.2 Contract Namespaces

```
SOURCE_CONTRACT = "FASTLAB-0.2.0"
TARGET_CONTRACT = "ATAN-BUZZ-0.2.0"
WIRE_CONTRACT_VERSION = "0.2.0"
```

### 14.3 Translation Rules

| FASTLAB Field | Wire Field | Rule |
|--------------|-----------|------|
| `task_type = "generate"` | `task_type = "game_navigation"` | Translated when `metadata.task_intent == "game_navigation"` |
| `execution_mode = "sync"` | `execution_mode` | **NOT** derived from FASTLAB; set via `TranslatorConfig.wire_execution_mode` |
| `provider_preference` | `provider_preference` | Preserved if valid wire provider |
| `reviewer_preference` | `reviewer_preference` | Preserved if valid wire reviewer |
| `prompt` | `prompt` | Passed through unchanged |
| `model`, `temperature`, etc. | Same fields | Passed through unchanged |
| `metadata` (safe fields only) | `metadata` | Filtered to safe game fields + translator context |

**Critical:** `sync` does NOT map to `single`. Wire execution mode is an explicit configuration choice.

### 14.4 Wire Execution Modes

| Mode | Provider | Reviewer | Description |
|------|----------|----------|-------------|
| `single` | Required | Should be `none` | Single provider, no review |
| `fallback` | `auto` or explicit | `none` | Primary with fallback chain |
| `consensus` | Required | **Required** (not `none`) | Generator + reviewer agreement |

### 14.5 Wire Provider/Reviewer Validation

| Role | Valid Values |
|------|-------------|
| Wire provider | `auto`, `mock`, `ollama`, `openai`, `gemini` |
| Wire reviewer | `none`, `auto`, `openai`, `gemini` |

### 14.6 Validation Order

1. FASTLAB `ProviderRequest.validate()` — must pass (never bypass)
2. `metadata.task_intent == "game_navigation"` — must be present
3. `wire_execution_mode` — must be valid (`single \| fallback \| consensus`)
4. `wire_provider` — must be in allowed set
5. `wire_reviewer` — must be in allowed set
6. Combination check: consensus requires reviewer ≠ `none`

### 14.7 Metadata Filtering

Only these fields are forwarded to wire metadata:

```
turn, agent_position, strategy, grid_width, grid_height,
known_rewards, known_hazards, known_enemies, goal, source, task_intent
```

Added by translator:
```
source_contract = "FASTLAB-0.2.0"
target_contract = "ATAN-BUZZ-0.2.0"
```

**Never forwarded:** API keys, secrets, debug fields, internal state.

### 14.8 Future Wire Translation (Not Yet Implemented)

The future live-BUZZ transport layer may translate FASTLAB internal
semantics into the local BUZZ wire vocabulary:

```
FASTLAB (internal):              WIRE (to BUZZ gateway):
  execution_mode = sync            execution_mode = single
  task_type = generate             task_type = game_navigation
  metadata.task_intent = game_nav  (conveyed via task_type)
```

This wire translation is produced offline for validation. It is NOT sent to a live endpoint yet.

---

## 18. Navigation Intelligence (Phase 2F Part 3C)

### 18.1 Grounded Navigation Architecture

The grounded navigation system improves decision quality by providing the LLM with explicit legal action constraints and goal direction information.

```
GameState
  → NavigationContextBuilder → NavigationContext
  → NavigationPromptBuilder → grounded prompt
  → ContractTranslator → BUZZ wire payload
  → BUZZ → Ollama qwen2.5:7b
  → ActionParser → Action
  → OscillationDetector → oscillation check
  → Safety Gate → validation
  → GameSimulator.apply_action()
```

Key components:
- `game/navigation_context.py` — Builds deterministic context from GameState
- `game/navigation_prompt.py` — Constructs grounded prompts with legal actions
- `game/oscillation_detector.py` — Detects A→B→A position oscillation patterns

### 18.2 Grounded Prompt Structure

The grounded prompt includes:

| Section | Purpose |
|---------|---------|
| `ROLE` | Defines agent as grid-navigation decision agent |
| `OBJECTIVE` | Move safely toward goal |
| `STATE` | Position, goal, grid dimensions, health, turn, strategy |
| `GOAL_DIRECTION` | Horizontal (LEFT/RIGHT/SAME) and vertical (UP/DOWN/SAME) |
| `LEGAL_ACTIONS` | Computed legal actions from current position |
| `BLOCKED_ACTIONS` | Actions blocked with reasons (OUT_OF_BOUNDS, WALL, LOCKED_DOOR) |
| `REWARDS` | Known reward positions |
| `HAZARDS` | Known hazard positions |
| `ENEMIES` | Known enemy positions |
| `RECENT_HISTORY` | Previous 3 positions and actions |
| `RULES` | Constraints (choose only from LEGAL_ACTIONS, no explanation) |
| `OUTPUT` | Format specification (exactly one action token) |

### 18.3 One-Turn Benchmark

**Configuration:** `temperature=0.0`, `max_tokens=8`, `qwen2.5:7b`

| Metric | Baseline | Grounded | Delta |
|--------|----------|----------|-------|
| Parse success rate | 100% | 100% | — |
| Legal action rate | 67% | **100%** | +33% |
| Unsafe count | 2 | **0** | -2 |
| Goal progress rate | 17% | **83%** | +66% |
| UP bias | 6/6 (100%) | **2/6 (33%)** | -67% |
| Avg latency | 3759ms | 4884ms | +1125ms |

**Result:** Grounded prompt eliminates illegal actions and UP bias.

### 18.4 Multi-Turn Benchmark

**Episodes:** 3 deterministic episodes, max 10 turns each

| Episode | Turns | Goal Reached | Fallback | Oscillation | Unsafe | Progress Rate |
|---------|-------|--------------|----------|-------------|--------|---------------|
| SIMPLE | 10 | Yes | 0/10 | 2 | 0 | 90% |
| WALL_DETOUR | 10 | Yes | 0/10 | 2 | 0 | 90% |
| REWARD_HAZARD | 10 | Yes | 0/10 | 2 | 0 | 90% |
| **Total** | **30** | **3/3** | **0/30** | **6** | **0** | **90%** |

### 18.5 Oscillation Detector

**Definition:**
- **Oscillation event:** `P[n-2] == P[n]` AND `P[n-1] != P[n]`
  - Example: A5→A4→A5 = 1 event
- **Repeated loop:** 3+ consecutive oscillation events (A→B→A→B→A)
- **Action oscillation:** DOWN→UP→DOWN or LEFT→RIGHT→LEFT

**Results:**
- Total oscillation events: 6 (2 per episode)
- Repeated sustained loops: 0
- All oscillations were isolated events, not sustained bouncing

### 18.6 Simple Map Efficiency

| Metric | Value |
|--------|-------|
| Turns to goal | 10 |
| Optimal path length | 8 |
| Path efficiency | 0.80 |

**Known limitation:** Model exhibits one oscillation at corner A5 (A5→A4→A5) before committing to RIGHT direction. This adds 2 extra turns but does not prevent goal completion.

### 18.7 Provider Latency Observations

| Episode | Avg Latency | p50 | Max |
|---------|-------------|-----|-----|
| SIMPLE | 6084ms | 1091ms | 14135ms |
| WALL_DETOUR | 9130ms | 11029ms | 14008ms |
| REWARD_HAZARD | 12952ms | 12255ms | 14988ms |

**Notes:**
- Grounded prompt is ~30% slower than baseline due to longer prompt length
- First 2-3 turns typically faster (shorter prompt processing)
- Later turns slower (more recent history in prompt)
- All latencies within acceptable limits for turn-based game

### 18.8 Final Verified Metrics

**Grounded navigation (Part 3C) targets:**

| Target | Result | Status |
|--------|--------|--------|
| 100% parse success | 100% | PASS |
| 100% legal actions | 100% | PASS |
| 0 unsafe accepted | 0 | PASS |
| Fallback ≤10% | 0% | PASS |
| No repeated simple-map loops | 0 | PASS |
| Simple map goal reached | Yes | PASS |

### 18.9 Files Created (Part 3C)

```
game/
├── navigation_context.py      # NavigationContextBuilder
├── navigation_prompt.py       # Baseline + grounded prompt builders
├── live_navigation_eval.py    # Evaluation framework
├── live_multiturn_eval.py     # Multi-turn episode runner
├── oscillation_detector.py    # Oscillation detection
└── check_oscillation.py       # Utility script

tests/
└── test_navigation_intelligence.py  # 35 tests (27 + 8 oscillation)
```

---

## 19. File Structure (Updated)

```
game/
├── __init__.py              # Package exports (Part 1 + 2 + 3C)
├── game_state.py            # GameState + Position + CellType
├── action_schema.py         # Action enum + ActionResult
├── strategy.py              # Strategy profiles + configuration
├── pathfinder.py            # BFS + A* + Weighted A* algorithms
├── game_agent_adapter.py    # GameAgentAdapter + PlanningContext + CombatLogEntry
├── action_parser.py         # ActionParser + ActionParseResult (Part 2)
├── buzz_game_bridge.py      # BuzzGameBridge + BridgeConfig + SimulatedProvider (Part 2)
├── game_simulator.py        # GameSimulator + SimulationMetrics + SimConfig (Part 2)
├── turn_controller.py       # TurnController + TurnLogEntry + EpisodeResult (Part 2)
├── contract_translator.py   # ContractTranslator + TranslatorConfig (Part 3A)
├── navigation_context.py    # NavigationContextBuilder (Part 3C)
├── navigation_prompt.py     # Grounded prompt builder (Part 3C)
├── live_navigation_eval.py  # Evaluation framework (Part 3C)
├── live_multiturn_eval.py   # Multi-turn episode runner (Part 3C)
├── oscillation_detector.py  # Oscillation detection (Part 3C)
├── live_buzz_probe.py       # One-turn live probe (Part 3B)
├── live_buzz_episode.py     # Five-turn live episode (Part 3B)
└── live_buzz_failure.py     # Failure recovery tests (Part 3B)

tests/
├── test_game_adapter.py         # Part 1: 10 scenario tests + unit tests (59 tests)
├── test_game_buzz_bridge.py     # Part 2: 20+ bridge/simulator tests (50 tests)
├── test_contract_translator.py  # Part 3A: 18+ translator tests (35+ tests)
└── test_navigation_intelligence.py  # Part 3C: 35 tests (27 + 8 oscillation)

docs/
└── GAME_AGENT_INTEGRATION_SPEC.md  # This document
```

---

## 20. Assumptions Requiring Official Competition Evidence

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

## 17. Testing

### 17.1 Part 1 Test Scenarios

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

### 17.2 Part 2 Test Scenarios (Bridge / Simulator)

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

### 17.3 Part 3A Test Scenarios (Contract Translator)

| # | Scenario | Validates |
|---|----------|-----------|
| 1 | Valid game request → single | Full translation success |
| 2 | task_type generate → game_navigation | Wire task_type mapping |
| 3 | sync NOT blindly mapped | FASTLAB exec_mode ignored for wire |
| 4 | Explicit single | Wire mode = single |
| 5 | Explicit fallback | Wire mode = fallback |
| 6 | Explicit consensus | Wire mode = consensus (with reviewer) |
| 7 | Provider preservation | Wire provider from config |
| 8 | Reviewer preservation | Wire reviewer from config |
| 9 | Invalid provider | Rejected with error |
| 10 | Invalid reviewer | Rejected with error |
| 11 | Consensus without reviewer | Configuration error |
| 12 | FASTLAB validation failure | Empty prompt rejected first |
| 13 | Metadata preservation | Safe fields forwarded |
| 14 | Contract namespace | SOURCE/TARGET in result + metadata |
| 15 | contract_version = 0.2.0 | Wire version correct |
| 16 | No mutation | Original request unchanged |
| 17 | Deterministic | Same input → same output |
| 18 | No secrets | No sensitive data in wire |

### 17.4 Test Properties

- **Deterministic:** Same inputs always produce same outputs
- **Offline:** No network, no API keys, no LLM
- **Fast:** All tests complete in < 1 second
- **Independent:** No shared state between tests

---

*Document version: 2F/4.0*
*Created: 2026-08-24*
*Updated: 2026-08-24 (Part 3C — Navigation Intelligence verified)*
*Status: Offline adapter layer with grounded navigation — awaiting competition API specification*

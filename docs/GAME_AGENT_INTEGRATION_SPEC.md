# 🎮 Game Agent Integration Specification

> **SPATHODEA R4 FASTLAB — Phase 2F Part 1**
> Module: `game/`
> Status: Offline adapter layer — no live competition connection
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

### 1.2 Current Topology (Phase 2F Part 1)

```
GAME STATE (manual/test)
  → GameAgentAdapter
  → deterministic pathfinding
  → recommended action
```

No BUZZ connection. No provider calls. Fully offline.

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

## 9. BUZZ Integration (Future — Not Active)

### 9.1 Planned Flow

```
GameAgentAdapter.plan_with_buzz(state)
  → build PlanningContext
  → serialize to ProviderRequest
  → send to BUZZ POST /v1/generate
  → parse ProviderResponse
  → extract action from LLM response
  → validate action against game state
  → return validated action (or fallback to deterministic)
```

### 9.2 Contract Compatibility

- Uses existing BUZZ v0.2.0 contract (unchanged)
- `task_type = "generate"`
- `metadata.source = "FASTLAB_GAME_AGENT"`
- `metadata.record_type = "game_navigation"`
- Provider preference flows through existing fields

### 9.3 Fallback Behavior

If BUZZ is unavailable or LLM response is invalid:
1. Log the failure
2. Fall back to deterministic `plan()` result
3. Never block on LLM timeout in game context

---

## 10. File Structure

```
game/
├── __init__.py              # Package exports
├── game_state.py            # GameState + Position + CellType
├── action_schema.py         # Action enum + ActionResult
├── strategy.py              # Strategy profiles + configuration
├── pathfinder.py            # BFS + A* + Weighted A* algorithms
└── game_agent_adapter.py    # GameAgentAdapter + PlanningContext + CombatLogEntry

tests/
└── test_game_adapter.py     # 10 deterministic scenario tests + unit tests

docs/
└── GAME_AGENT_INTEGRATION_SPEC.md  # This document
```

---

## 11. Assumptions Requiring Official Competition Evidence

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

## 12. Testing

### 12.1 Test Scenarios

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

### 12.2 Test Properties

- **Deterministic:** Same inputs always produce same outputs
- **Offline:** No network, no API keys, no LLM
- **Fast:** All tests complete in < 1 second
- **Independent:** No shared state between tests

---

*Document version: 2F/1.0*
*Created: 2026-08-24*
*Status: Offline adapter layer — awaiting competition API specification*

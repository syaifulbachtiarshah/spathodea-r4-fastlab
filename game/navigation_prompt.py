"""
SPATHODEA R4 FASTLAB — Navigation Prompt Builder (Phase 2F Part 3C)
Constructs deterministic prompts for grid navigation decisions.

Two modes:
- BASELINE_PROMPT: Part 3B style (simple, no legal action grounding)
- GROUNDED_NAV_PROMPT: Part 3C style (legal actions, goal direction, oscillation awareness)
"""

from .navigation_context import NavigationContext


# =============================================================================
# Baseline Prompt (Part 3B style)
# =============================================================================

def build_baseline_prompt(ctx: NavigationContext) -> str:
    """Build the baseline Part 3B style prompt.

    Simple state dump without legal action grounding.
    This is what the model currently receives.
    """
    parts = [
        f"Grid: {ctx.grid_width}x{ctx.grid_height}",
        f"Position: {ctx.current_position}",
        f"Goal: {ctx.goal or 'None'}",
        f"Strategy: {ctx.strategy}",
        f"Turn: {ctx.turn}",
        f"Health: {ctx.health}",
    ]

    if ctx.known_rewards:
        parts.append(f"Rewards: {', '.join(ctx.known_rewards[:5])}")
    if ctx.known_hazards:
        parts.append(f"Hazards: {', '.join(ctx.known_hazards[:5])}")
    if ctx.known_enemies:
        parts.append(f"Enemies: {', '.join(ctx.known_enemies[:5])}")

    parts.append("Respond with a single action: UP, DOWN, LEFT, RIGHT, or WAIT")

    return " | ".join(parts)


# =============================================================================
# Grounded Navigation Prompt (Part 3C)
# =============================================================================

def build_grounded_nav_prompt(ctx: NavigationContext) -> str:
    """Build the grounded navigation prompt with legal action constraints.

    Deterministic. Concise. No ambiguity.
    Model must choose ONLY from legal actions.
    """
    lines = []

    # Role
    lines.append("ROLE:")
    lines.append("You are a grid-navigation decision agent.")
    lines.append("")

    # Objective
    lines.append("OBJECTIVE:")
    lines.append("Move safely toward the goal while following the current strategy.")
    lines.append("")

    # State
    lines.append("STATE:")
    lines.append(f"Position: {ctx.current_position}")
    lines.append(f"Goal: {ctx.goal or 'None'}")
    lines.append(f"Grid: {ctx.grid_width}x{ctx.grid_height}")
    lines.append(f"Health: {ctx.health}")
    lines.append(f"Turn: {ctx.turn}")
    lines.append(f"Strategy: {ctx.strategy}")
    lines.append("")

    # Goal direction
    lines.append("GOAL_DIRECTION:")
    lines.append(f"Horizontal: {ctx.goal_direction_horizontal}")
    lines.append(f"Vertical: {ctx.goal_direction_vertical}")
    lines.append("")

    # Legal actions
    legal_str = ", ".join(ctx.legal_actions)
    lines.append("LEGAL_ACTIONS:")
    lines.append(legal_str)
    lines.append("")

    # Blocked actions
    if ctx.blocked_actions:
        lines.append("BLOCKED_ACTIONS:")
        for action, reason in sorted(ctx.blocked_actions.items()):
            lines.append(f"{action}: {reason}")
        lines.append("")

    # Rewards
    if ctx.known_rewards:
        lines.append("REWARDS:")
        lines.append(", ".join(ctx.known_rewards[:5]))
        lines.append("")

    # Hazards
    if ctx.known_hazards:
        lines.append("HAZARDS:")
        lines.append(", ".join(ctx.known_hazards[:5]))
        lines.append("")

    # Enemies
    if ctx.known_enemies:
        lines.append("ENEMIES:")
        lines.append(", ".join(ctx.known_enemies[:5]))
        lines.append("")

    # Recent history
    if ctx.recent_positions or ctx.recent_actions:
        lines.append("RECENT_HISTORY:")
        for i in range(max(len(ctx.recent_positions), len(ctx.recent_actions))):
            pos = ctx.recent_positions[i] if i < len(ctx.recent_positions) else "?"
            act = ctx.recent_actions[i] if i < len(ctx.recent_actions) else "?"
            lines.append(f"  {pos} <- {act}")
        lines.append("")

    # Rules
    lines.append("RULES:")
    lines.append("1. Choose ONLY from LEGAL_ACTIONS.")
    lines.append("2. Prefer progress toward the goal unless strategy/reward/safety provides a better reason.")
    lines.append("3. Avoid immediate oscillation unless necessary.")
    lines.append("4. Never choose an action listed under BLOCKED_ACTIONS.")
    lines.append("5. Return exactly ONE token.")
    lines.append("6. No explanation.")
    lines.append("7. No JSON.")
    lines.append("8. No punctuation.")
    lines.append("")

    # Output format
    lines.append("OUTPUT:")
    lines.append("UP | DOWN | LEFT | RIGHT | WAIT")
    lines.append("")
    lines.append("YOUR RESPONSE MUST BE EXACTLY ONE VALUE FROM LEGAL_ACTIONS.")

    return "\n".join(lines)


# =============================================================================
# Prompt Selector
# =============================================================================

def build_prompt(ctx: NavigationContext, mode: str = "grounded") -> str:
    """Build prompt based on mode.

    Args:
        ctx: Navigation context
        mode: "baseline" or "grounded"

    Returns:
        Formatted prompt string
    """
    if mode == "baseline":
        return build_baseline_prompt(ctx)
    return build_grounded_nav_prompt(ctx)

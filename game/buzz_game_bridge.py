"""
SPATHODEA R4 FASTLAB — BUZZ Game Bridge (Phase 2F Part 2)
Offline bridge between GameAgentAdapter and BUZZ ProviderRequest/ProviderResponse.

Converts:
    PlanningContext + GameState → ProviderRequest v0.2.0

Handles:
    ProviderResponse → ActionParseResult → validated Action

Uses mock/simulated responses only. No live API calls.

Contract: BUZZ v0.2.0 (unchanged)

NOTE — Future Wire Translation:
    The future live-BUZZ transport layer may translate FASTLAB internal
    semantics into the local BUZZ wire vocabulary.

    Example future translation:

        FASTLAB (internal):
            execution_mode = sync
            task_type = generate
            metadata.task_intent = game_navigation

        WIRE (to BUZZ gateway):
            execution_mode = single
            task_type = game_navigation

    This wire translation is NOT implemented yet. The current bridge
    uses FASTLAB-internal ProviderRequest v0.2.0 fields directly.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

from .game_state import GameState, Position
from .action_schema import Action
from .strategy import Strategy, StrategyProfile
from .pathfinder import Pathfinder, CostConfig
from .game_agent_adapter import PlanningContext
from .action_parser import ActionParser, ActionParseResult

# Import BUZZ adapters
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.provider_request import ProviderRequest, CONTRACT_VERSION
from adapters.provider_response import ProviderResponse


# =============================================================================
# Bridge Configuration
# =============================================================================

@dataclass
class BridgeConfig:
    """Configuration for the BUZZ game bridge.

    Attributes:
        provider_preference: Preferred generation provider
        reviewer_preference: Preferred review provider
        execution_mode: sync|async|batch (always sync for game)
        timeout_ms: Simulated timeout threshold
        fallback_on_error: Whether to use deterministic fallback on provider error
        fallback_on_timeout: Whether to use deterministic fallback on timeout
        fallback_on_invalid: Whether to use deterministic fallback on invalid parse
    """
    provider_preference: Optional[str] = "mock"
    reviewer_preference: Optional[str] = None
    execution_mode: str = "sync"
    timeout_ms: float = 5000.0
    fallback_on_error: bool = True
    fallback_on_timeout: bool = True
    fallback_on_invalid: bool = True

    def to_dict(self) -> dict:
        return {
            "provider_preference": self.provider_preference,
            "reviewer_preference": self.reviewer_preference,
            "execution_mode": self.execution_mode,
            "timeout_ms": self.timeout_ms,
            "fallback_on_error": self.fallback_on_error,
            "fallback_on_timeout": self.fallback_on_timeout,
            "fallback_on_invalid": self.fallback_on_invalid,
        }


# =============================================================================
# Bridge Result
# =============================================================================

@dataclass
class BridgeResult:
    """Result of a bridge request cycle.

    Attributes:
        action: Final validated action (after safety gate)
        source: Where the action came from (provider|fallback_pathfinder|fallback_wait)
        provider_requested: Provider preference that was sent
        provider_used: Provider that actually responded
        parse_result: ActionParseResult from parsing provider output
        fallback_used: Whether fallback was triggered
        fallback_reason: Why fallback was needed (if any)
        bridge_processing_ms: Time spent in bridge logic (not provider inference)
        raw_action_summary: Truncated summary of raw provider output
        request_id: Request ID used
    """
    action: Action = Action.WAIT
    source: str = "fallback_wait"
    provider_requested: Optional[str] = None
    provider_used: Optional[str] = None
    parse_result: Optional[ActionParseResult] = None
    fallback_used: bool = False
    fallback_reason: str = ""
    bridge_processing_ms: float = 0.0
    raw_action_summary: str = ""
    request_id: str = ""

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "source": self.source,
            "provider_requested": self.provider_requested,
            "provider_used": self.provider_used,
            "parse_result": self.parse_result.to_dict() if self.parse_result else None,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "bridge_processing_ms": round(self.bridge_processing_ms, 3),
            "raw_action_summary": self.raw_action_summary,
            "request_id": self.request_id,
        }


# =============================================================================
# Simulated Provider Response (for offline testing)
# =============================================================================

class SimulatedProvider:
    """Simulated provider for offline bridge testing.

    Can simulate various scenarios:
    - Normal valid action responses
    - Timeouts
    - Unavailability
    - Contract mismatches
    - Invalid/malformed responses
    """

    def __init__(self):
        self._next_response: Optional[ProviderResponse] = None
        self._simulate_timeout: bool = False
        self._simulate_unavailable: bool = False
        self._simulate_contract_mismatch: bool = False
        self._latency_ms: float = 10.0

    def set_response(self, response: ProviderResponse):
        """Set the next response to return."""
        self._next_response = response

    def set_action_response(self, action_text: str, request_id: str = "sim-001"):
        """Convenience: set a response containing an action string."""
        self._next_response = ProviderResponse(
            content=action_text,
            model="sim-model-v1",
            request_id=request_id,
            finish_reason="stop",
            usage={"prompt_tokens": 50, "completion_tokens": 5, "total_tokens": 55},
            latency_ms=self._latency_ms,
            provider="mock",
            error=None,
            metadata={},
        )

    def set_timeout(self, enabled: bool = True):
        """Simulate provider timeout."""
        self._simulate_timeout = enabled

    def set_unavailable(self, enabled: bool = True):
        """Simulate provider unavailability."""
        self._simulate_unavailable = enabled

    def set_contract_mismatch(self, enabled: bool = True):
        """Simulate contract version mismatch."""
        self._simulate_contract_mismatch = enabled

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Simulate generating a response.

        Args:
            request: ProviderRequest to process

        Returns:
            Simulated ProviderResponse
        """
        if self._simulate_timeout:
            return ProviderResponse(
                content="",
                model="",
                request_id=request.request_id,
                finish_reason="error",
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                latency_ms=5001.0,
                provider="mock",
                error="mock: request timed out after 5000ms",
                metadata={"error_type": "timeout"},
            )

        if self._simulate_unavailable:
            return ProviderResponse(
                content="",
                model="",
                request_id=request.request_id,
                finish_reason="error",
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                latency_ms=0.0,
                provider="mock",
                error="mock: provider unavailable (connection refused)",
                metadata={"error_type": "unavailable"},
            )

        if self._simulate_contract_mismatch:
            return ProviderResponse(
                content="INVALID_CONTRACT_RESPONSE",
                model="wrong-model",
                request_id="wrong-id",
                finish_reason="stop",
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                latency_ms=self._latency_ms,
                provider="unknown",
                error=None,
                metadata={"contract_version": "9.9.9"},
            )

        if self._next_response is not None:
            resp = self._next_response
            # Update request_id to match
            resp.request_id = request.request_id
            return resp

        # Default: return a valid action
        return ProviderResponse(
            content="UP",
            model="sim-model-v1",
            request_id=request.request_id,
            finish_reason="stop",
            usage={"prompt_tokens": 50, "completion_tokens": 1, "total_tokens": 51},
            latency_ms=self._latency_ms,
            provider="mock",
            error=None,
            metadata={},
        )

    def reset(self):
        """Reset all simulation flags."""
        self._next_response = None
        self._simulate_timeout = False
        self._simulate_unavailable = False
        self._simulate_contract_mismatch = False


# =============================================================================
# BUZZ Game Bridge
# =============================================================================

class BuzzGameBridge:
    """Bridge between GameAgentAdapter and BUZZ ProviderRequest/ProviderResponse.

    Converts game planning context into BUZZ requests, parses responses,
    applies safety gate, and provides deterministic fallback.

    Usage:
        bridge = BuzzGameBridge(config=BridgeConfig(...))
        result = bridge.request_action(state, context)
        safe_action = result.action
    """

    def __init__(
        self,
        config: Optional[BridgeConfig] = None,
        provider: Optional[SimulatedProvider] = None,
    ):
        """Initialize the bridge.

        Args:
            config: Bridge configuration
            provider: Simulated provider (for offline testing)
        """
        self._config = config or BridgeConfig()
        self._provider = provider or SimulatedProvider()
        self._parser = ActionParser()
        self._pathfinder = Pathfinder()

    @property
    def config(self) -> BridgeConfig:
        return self._config

    @property
    def provider(self) -> SimulatedProvider:
        return self._provider

    # =========================================================================
    # Request Building
    # =========================================================================

    def build_request(self, state: GameState, context: PlanningContext) -> ProviderRequest:
        """Convert game state + planning context into a BUZZ ProviderRequest.

        Uses task_type="generate" (v0.2.0 contract compatible).
        Game navigation intent stored in metadata.task_intent.

        Does NOT include validation rules or hidden data in the request.

        Args:
            state: Current game state
            context: Planning context from GameAgentAdapter

        Returns:
            ProviderRequest ready for BUZZ dispatch
        """
        # Build the navigation prompt for the provider
        prompt = self._build_game_prompt(state, context)

        # Build metadata — observable game facts only
        metadata = {
            "source": "SPATHODEA_GAME",
            "task_intent": "game_navigation",
            "turn": state.turn,
            "agent_position": state.agent_pos.to_label(),
            "strategy": context.strategy_profile,
            "grid_width": state.width,
            "grid_height": state.height,
            "known_rewards": len(state.get_available_rewards()),
            "known_hazards": len(state.hazards),
            "known_enemies": len(state.enemies),
            "goal": state.goal.to_label() if state.goal else None,
        }

        return ProviderRequest(
            prompt=prompt,
            system_prompt=None,
            model="auto",
            temperature=0.3,  # Low temperature for deterministic game actions
            max_tokens=50,    # Actions are short
            top_p=0.9,
            stop_sequences=None,
            request_id=f"game-turn-{state.turn:04d}",
            metadata=metadata,
            provider_preference=self._config.provider_preference,
            reviewer_preference=self._config.reviewer_preference,
            execution_mode=self._config.execution_mode,
            task_type="generate",  # v0.2.0 contract; game intent in metadata
        )

    def _build_game_prompt(self, state: GameState, context: PlanningContext) -> str:
        """Build the game navigation prompt for the provider.

        Contains observable state only. No secrets, no validator data.
        """
        parts = [
            f"Grid: {state.width}x{state.height}",
            f"Position: {state.agent_pos.to_label()}",
            f"Goal: {state.goal.to_label() if state.goal else 'None'}",
            f"Strategy: {context.strategy_profile}",
            f"Turn: {state.turn}",
            f"Health: {state.health}",
        ]

        if context.threats:
            parts.append(f"Threats: {', '.join(context.threats[:5])}")
        if context.available_rewards:
            parts.append(f"Rewards: {', '.join(context.available_rewards[:5])}")

        parts.append("Respond with a single action: UP, DOWN, LEFT, RIGHT, or WAIT")

        return " | ".join(parts)

    # =========================================================================
    # Response Handling
    # =========================================================================

    def request_action(
        self,
        state: GameState,
        context: PlanningContext,
    ) -> BridgeResult:
        """Full bridge cycle: build request → provider → parse → safety gate.

        Args:
            state: Current game state
            context: Planning context with recommended_action as fallback

        Returns:
            BridgeResult with final safe action
        """
        start_ms = time.perf_counter() * 1000.0

        # 1. Build request
        request = self.build_request(state, context)
        result = BridgeResult(
            provider_requested=self._config.provider_preference,
            request_id=request.request_id,
        )

        # 2. Send to provider (simulated)
        response = self._provider.generate(request)
        result.provider_used = response.provider

        # 3. Check for provider-level errors
        if response.is_error:
            error_type = response.metadata.get("error_type", "unknown")
            if error_type == "timeout" and self._config.fallback_on_timeout:
                result = self._apply_fallback(
                    state, context, result,
                    reason=f"Provider timeout: {response.error}"
                )
            elif error_type == "unavailable" and self._config.fallback_on_error:
                result = self._apply_fallback(
                    state, context, result,
                    reason=f"Provider unavailable: {response.error}"
                )
            else:
                result = self._apply_fallback(
                    state, context, result,
                    reason=f"Provider error: {response.error}"
                )
            result.bridge_processing_ms = time.perf_counter() * 1000.0 - start_ms
            return result

        # 4. Check for contract mismatch
        resp_contract = response.metadata.get("contract_version")
        if resp_contract and resp_contract != CONTRACT_VERSION:
            result = self._apply_fallback(
                state, context, result,
                reason=f"Contract mismatch: expected {CONTRACT_VERSION}, got {resp_contract}"
            )
            result.bridge_processing_ms = time.perf_counter() * 1000.0 - start_ms
            return result

        # 5. Parse the provider response content
        raw_content = response.content or ""
        result.raw_action_summary = raw_content[:100]
        parse_result = self._parser.parse(raw_content)
        result.parse_result = parse_result

        if not parse_result.success:
            if self._config.fallback_on_invalid:
                result = self._apply_fallback(
                    state, context, result,
                    reason=f"Parse failed: {parse_result.error}"
                )
            else:
                result.action = Action.WAIT
                result.source = "fallback_wait"
                result.fallback_used = True
                result.fallback_reason = f"Parse failed (no fallback): {parse_result.error}"
            result.bridge_processing_ms = time.perf_counter() * 1000.0 - start_ms
            return result

        # 6. Safety gate — validate the parsed action against game state
        proposed_action = parse_result.action
        safe_action, gate_reason = self._safety_gate(state, proposed_action)

        if safe_action != proposed_action:
            result.action = safe_action
            result.source = "fallback_pathfinder" if safe_action != Action.WAIT else "fallback_wait"
            result.fallback_used = True
            result.fallback_reason = gate_reason
        else:
            result.action = safe_action
            result.source = "provider"
            result.fallback_used = False

        result.bridge_processing_ms = time.perf_counter() * 1000.0 - start_ms
        return result

    # =========================================================================
    # Safety Gate
    # =========================================================================

    def _safety_gate(self, state: GameState, action: Action) -> tuple[Action, str]:
        """Validate an action against game state constraints.

        Checks:
        - Grid bounds
        - Wall collision
        - Locked door rules
        - Impossible movement

        Returns:
            (safe_action, reason) — safe_action == action if valid, else fallback
        """
        # WAIT is always safe
        if action == Action.WAIT:
            return (Action.WAIT, "")

        # Compute target position
        target = action.apply(state.agent_pos)

        # Check bounds
        if not state.is_valid_position(target):
            fallback = self._compute_safe_fallback(state)
            return (fallback, f"Action {action.value} goes out of bounds to {target.to_label()}")

        # Check wall
        if target in state.walls:
            fallback = self._compute_safe_fallback(state)
            return (fallback, f"Action {action.value} hits wall at {target.to_label()}")

        # Check locked door
        if target in state.doors and not state._can_open_door(target):
            fallback = self._compute_safe_fallback(state)
            return (fallback, f"Action {action.value} hits locked door at {target.to_label()}")

        # Action is valid
        return (action, "")

    def _compute_safe_fallback(self, state: GameState) -> Action:
        """Compute a safe fallback action using local pathfinding.

        Fallback order:
        1. Pathfinder-computed action toward goal
        2. WAIT
        """
        if state.goal:
            path = self._pathfinder.astar(state, state.agent_pos, state.goal)
            if path.found and path.length > 0:
                # Get next step
                for i, pos in enumerate(path.path):
                    if pos == state.agent_pos and i + 1 < len(path.path):
                        next_pos = path.path[i + 1]
                        action = Action.from_positions(state.agent_pos, next_pos)
                        if action:
                            return action

        return Action.WAIT

    # =========================================================================
    # Fallback
    # =========================================================================

    def _apply_fallback(
        self,
        state: GameState,
        context: PlanningContext,
        result: BridgeResult,
        reason: str,
    ) -> BridgeResult:
        """Apply deterministic fallback action.

        Fallback order:
        1. Locally computed safe pathfinder action
        2. WAIT
        """
        result.fallback_used = True
        result.fallback_reason = reason

        # Try pathfinder fallback
        fallback_action = self._compute_safe_fallback(state)
        if fallback_action != Action.WAIT:
            result.action = fallback_action
            result.source = "fallback_pathfinder"
        else:
            result.action = Action.WAIT
            result.source = "fallback_wait"

        return result

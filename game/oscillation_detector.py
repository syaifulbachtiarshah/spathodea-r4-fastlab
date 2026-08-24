"""
SPATHODEA R4 FASTLAB — Oscillation Detection (Phase 2F Part 3C Patch)
Detects two-cell oscillation events and repeated loops.

Definition:
- Oscillation event: P[n-2] == P[n] AND P[n-1] != P[n]
  Example: A5 -> A4 -> A5 = 1 event

- Repeated loop: Same two-cell bounce continues
  Example: A5 -> A4 -> A5 -> A4 -> A5 = repeated loop

- Action oscillation: DOWN -> UP -> DOWN or LEFT -> RIGHT -> LEFT
"""

from dataclasses import dataclass, field
from typing import Optional


# =============================================================================
# Oscillation Result
# =============================================================================

@dataclass
class OscillationResult:
    """Result of oscillation detection for a single turn."""
    event_detected: bool = False
    event_reason: str = ""
    is_repeated_loop: bool = False
    loop_length: int = 0  # Number of oscillation events in sequence

    def to_dict(self) -> dict:
        return {
            "event_detected": self.event_detected,
            "event_reason": self.event_reason,
            "is_repeated_loop": self.is_repeated_loop,
            "loop_length": self.loop_length,
        }


# =============================================================================
# Oscillation Detector
# =============================================================================

class OscillationDetector:
    """Tracks position and action history to detect oscillation patterns.

    Usage:
        detector = OscillationDetector()
        for turn in episode:
            result = detector.check(new_position, new_action)
            if result.event_detected:
                ...
    """

    OPPOSITES = {
        "UP": "DOWN",
        "DOWN": "UP",
        "LEFT": "RIGHT",
        "RIGHT": "LEFT",
    }

    def __init__(self, history_size: int = 5):
        self._positions: list[str] = []
        self._actions: list[str] = []
        self._history_size = history_size
        self._oscillation_events: list[int] = []  # turn numbers
        self._consecutive_oscillation_count: int = 0

    @property
    def oscillation_events(self) -> list[int]:
        """Turn numbers where oscillation events occurred."""
        return list(self._oscillation_events)

    @property
    def total_events(self) -> int:
        """Total oscillation events."""
        return len(self._oscillation_events)

    @property
    def is_in_repeated_loop(self) -> bool:
        """Whether currently in a repeated oscillation loop."""
        return self._consecutive_oscillation_count >= 2

    @property
    def repeated_loop_count(self) -> int:
        """Number of repeated loops (sequences of 3+ oscillation events)."""
        count = 0
        consecutive = 0
        for _ in self._oscillation_events:
            consecutive += 1
            if consecutive >= 3:
                count += 1
        return count

    def check(self, new_position: str, new_action: str, turn: int = 0) -> OscillationResult:
        """Check if the new position/action creates an oscillation.

        Args:
            new_position: Position label after action (e.g., "A5")
            new_action: Action taken (e.g., "DOWN")
            turn: Current turn number

        Returns:
            OscillationResult with detection details
        """
        result = OscillationResult()

        # Need at least 2 previous positions to detect A->B->A
        if len(self._positions) >= 2:
            prev_prev = self._positions[-2]
            prev = self._positions[-1]

            # Position oscillation: P[n-2] == P[n] AND P[n-1] != P[n]
            if new_position == prev_prev and prev != new_position:
                result.event_detected = True
                result.event_reason = f"position_oscillation: {prev_prev}->{prev}->{new_position}"

                # Track consecutive oscillations
                self._consecutive_oscillation_count += 1
                result.is_repeated_loop = self._consecutive_oscillation_count >= 2
                result.loop_length = self._consecutive_oscillation_count

                self._oscillation_events.append(turn)

        # Action oscillation: opposite action pattern
        if not result.event_detected and len(self._actions) >= 2:
            prev_action = self._actions[-1]
            prev_prev_action = self._actions[-2]

            if (prev_prev_action == self.OPPOSITES.get(prev_action) and
                new_action == prev_action):
                result.event_detected = True
                result.event_reason = f"action_oscillation: {prev_prev_action}->{prev_action}->{new_action}"

                self._consecutive_oscillation_count += 1
                result.is_repeated_loop = self._consecutive_oscillation_count >= 2
                result.loop_length = self._consecutive_oscillation_count

                if turn not in self._oscillation_events:
                    self._oscillation_events.append(turn)

        # If no oscillation detected, reset consecutive count
        if not result.event_detected:
            self._consecutive_oscillation_count = 0

        # Update history
        self._positions.append(new_position)
        self._actions.append(new_action)
        if len(self._positions) > self._history_size:
            self._positions.pop(0)
            self._actions.pop(0)

        return result

    def reset(self):
        """Reset detector state."""
        self._positions.clear()
        self._actions.clear()
        self._oscillation_events.clear()
        self._consecutive_oscillation_count = 0


# =============================================================================
# Offline Analysis Function
# =============================================================================

def analyze_trajectory(positions: list[str], actions: list[str]) -> dict:
    """Analyze a complete trajectory for oscillation patterns.

    Args:
        positions: List of position labels (including start)
        actions: List of actions taken

    Returns:
        Dict with oscillation analysis
    """
    detector = OscillationDetector()
    events = []

    for i in range(len(actions)):
        new_pos = positions[i + 1] if i + 1 < len(positions) else positions[i]
        result = detector.check(new_pos, actions[i], turn=i)
        if result.event_detected:
            events.append({
                "turn": i,
                "reason": result.event_reason,
                "is_repeated_loop": result.is_repeated_loop,
            })

    return {
        "total_events": detector.total_events,
        "repeated_loop_count": detector.repeated_loop_count,
        "events": events,
        "positions": positions,
        "actions": actions,
    }

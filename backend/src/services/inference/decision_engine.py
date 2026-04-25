"""Map raw model scores to alert levels with hysteresis."""

from __future__ import annotations

from src.services.inference.contracts import InferenceWorkerConfig


class DecisionEngine:
    """Threshold smoothed inference scores to ``alert_level`` strings.

    Hysteresis thresholds prevent rapid bouncing at level boundaries:
      - normal  → warning : score >= 0.50
      - warning → normal  : score <  0.45
      - warning → alert   : score >= 0.80
      - alert   → warning : score <  0.72
    """

    _WARNING_ENTER: float = 0.50
    _WARNING_EXIT: float = 0.45
    _ALERT_ENTER: float = 0.80
    _ALERT_EXIT: float = 0.72

    def __init__(self, config: InferenceWorkerConfig) -> None:
        self._warning = config.score_warning_threshold
        self._alert = config.score_alert_threshold
        self._track_states: dict[str, str] = {}

    def get_state(self, track_id: str) -> str:
        """Return the current alert level for a track without modifying state."""
        return self._track_states.get(track_id, "normal")

    def classify(self, score: float, *, track_id: str | None = None) -> str:
        """Return the alert level for a smoothed confidence score.

        When ``track_id`` is provided, hysteresis is applied using per-track
        state.  Without it the call is stateless (for backward compatibility).
        """
        if track_id is None:
            return self._stateless_classify(score)

        current = self._track_states.get(track_id, "normal")
        next_state = self._transition(current, score)
        self._track_states[track_id] = next_state
        return next_state

    def _transition(self, current: str, score: float) -> str:
        if current == "normal":
            if score >= self._ALERT_ENTER:
                return "alert"
            if score >= self._WARNING_ENTER:
                return "warning"
            return "normal"
        if current == "warning":
            if score >= self._ALERT_ENTER:
                return "alert"
            if score < self._WARNING_EXIT:
                return "normal"
            return "warning"
        if current == "alert":
            if score < self._ALERT_EXIT:
                return "warning"
            return "alert"
        return "normal"

    def _stateless_classify(self, score: float) -> str:
        if score >= self._ALERT_ENTER:
            return "alert"
        if score >= self._WARNING_ENTER:
            return "warning"
        return "normal"

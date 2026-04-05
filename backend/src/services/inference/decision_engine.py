"""Map raw model scores to alert levels."""

from __future__ import annotations

from src.services.inference.contracts import InferenceWorkerConfig


class DecisionEngine:
    """Threshold raw inference scores to ``alert_level`` strings.

    Levels (per plan §3.13):
      - score >= alert_threshold   → "alert"
      - score >= warning_threshold → "warning"
      - otherwise                  → "normal"
    """

    def __init__(self, config: InferenceWorkerConfig) -> None:
        self._warning = config.score_warning_threshold
        self._alert = config.score_alert_threshold

    def classify(self, score: float) -> str:
        """Return the alert level for a raw model confidence score."""
        if score >= self._alert:
            return "alert"
        if score >= self._warning:
            return "warning"
        return "normal"

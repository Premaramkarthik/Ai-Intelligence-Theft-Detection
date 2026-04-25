"""Map raw model scores to alert levels."""

from __future__ import annotations

from src.services.inference.contracts import InferenceWorkerConfig


class DecisionEngine:
    """Threshold smoothed inference scores to ``alert_level`` strings.

    The VJEPA model outputs class-1 (shoplifter) probability:
      - score >= alert_threshold   → "alert"    (default 0.65)
      - score >= warning_threshold → "warning"  (default 0.50)
      - otherwise                  → "normal"   (non-shoplifter)
    """

    def __init__(self, config: InferenceWorkerConfig) -> None:
        self._warning = config.score_warning_threshold
        self._alert = config.score_alert_threshold

    def classify(self, score: float) -> str:
        """Return the alert level for a smoothed confidence score."""
        if score >= self._alert:
            return "alert"
        if score >= self._warning:
            return "warning"
        return "normal"

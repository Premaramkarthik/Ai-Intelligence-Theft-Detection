"""Shared tracking contracts used across detectors, trackers, and workers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(slots=True, frozen=True)
class PersonDetection:
    """A single person detection in left-top-width-height format."""

    left: float
    top: float
    width: float
    height: float
    confidence: float
    class_name: str = "person"


class PersonDetector(Protocol):
    """Protocol implemented by all person detectors used by tracking workers."""

    def detect(self, frame: np.ndarray) -> list[PersonDetection]:
        """Detect visible persons in a single BGR frame."""

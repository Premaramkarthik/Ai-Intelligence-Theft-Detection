"""
shared.types — Public API for all shared data contracts.

Import from here, not from the submodule directly:
    from shared.types import BBox, Detection, DetectionEvent, FramePointer
"""
from shared.types.models import (
    BBox,
    Detection,
    TrackedPerson,
    FramePointer,
    InteractionState,
    TrackState,
    DetectionEvent,
)

__all__ = [
    "BBox",
    "Detection",
    "TrackedPerson",
    "FramePointer",
    "InteractionState",
    "TrackState",
    "DetectionEvent",
]

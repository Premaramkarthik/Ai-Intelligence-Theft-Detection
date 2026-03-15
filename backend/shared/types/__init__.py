"""
shared.types — Public API for all shared data contracts.

Import from here, not from the submodule directly:
    from shared.types import BBox, Detection, DetectionEvent, FramePointer
"""
from shared.types.models import (
    BBox,
    Detection,
    DetectionEvent,
    FramePointer,
    InteractionState,
    TrackState,
    TrackedPerson,
)
from shared.types.status import CameraFleetStatus, GpuStatus, SystemResourceStatus, SystemStatusMessage

__all__ = [
    "BBox",
    "Detection",
    "TrackedPerson",
    "FramePointer",
    "InteractionState",
    "TrackState",
    "DetectionEvent",
    "CameraFleetStatus",
    "GpuStatus",
    "SystemResourceStatus",
    "SystemStatusMessage",
]

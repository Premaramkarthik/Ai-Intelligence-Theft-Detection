"""
shared — Top-level package for cross-service utilities.

Re-exports the most commonly used symbols so services can do either:

    # Flat import (recommended for frequently used items)
    from shared import get_settings, get_logger, BBox, DetectionEvent, FramePointer

    # Or scoped import
    from shared.types import BBox, Detection
    from shared.core import get_settings
    from shared.logging import get_logger
    from shared.shm import RingBufferWriter, RingBufferReader
"""
from shared.core.settings import Settings, get_settings
from shared.logging.logger import get_logger, root as root_logger
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
    # core
    "Settings",
    "get_settings",
    # logging
    "get_logger",
    "root_logger",
    # types
    "BBox",
    "Detection",
    "TrackedPerson",
    "FramePointer",
    "InteractionState",
    "TrackState",
    "DetectionEvent",
]

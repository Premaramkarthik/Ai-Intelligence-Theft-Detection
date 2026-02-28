"""
Shared type definitions used across all pipeline services.
Single source of truth for data contracts between services.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


# ── Detection ─────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class BBox:
    """Axis-aligned bounding box in pixel coordinates."""
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    def iou(self, other: "BBox") -> float:
        """Intersection over Union."""
        ix1 = max(self.x1, other.x1)
        iy1 = max(self.y1, other.y1)
        ix2 = min(self.x2, other.x2)
        iy2 = min(self.y2, other.y2)
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        inter = (ix2 - ix1) * (iy2 - iy1)
        return inter / (self.area + other.area - inter)


@dataclass(slots=True)
class Detection:
    """Result of a single-frame object detection."""
    bbox: BBox
    confidence: float
    class_id: int
    class_name: str
    mask: object | None = None        # np.ndarray segmentation mask, optional
    keypoints: object | None = None   # np.ndarray pose keypoints, optional


@dataclass(slots=True)
class TrackedPerson:
    """A detected person with a stable ByteTrack ID."""
    track_id: int
    bbox: BBox
    confidence: float
    mask: object | None = None        # segmentation mask for background blur


# ── Shared Memory Pointer ─────────────────────────────────────────────────────

@dataclass(slots=True)
class FramePointer:
    """
    Lightweight Redis payload — replaces full image transport.
    """
    camera_id: str
    slot_id: int
    t_capture: float            # time.time()
    trace_id: str = "0"         # UUID for end-to-end tracking

    def to_bytes(self) -> bytes:
        import json
        return json.dumps({
            "camera_id": self.camera_id,
            "slot_id": self.slot_id,
            "t_capture": self.t_capture,
            "trace_id": self.trace_id,
        }).encode()

    @classmethod
    def from_bytes(cls, data: bytes) -> "FramePointer":
        import json
        d = json.loads(data)
        return cls(
            camera_id=d["camera_id"],
            slot_id=d["slot_id"],
            t_capture=d["t_capture"],
            trace_id=d.get("trace_id", "0"),
        )


# ── Interaction State Machine ─────────────────────────────────────────────────

class InteractionState(Enum):
    IDLE = auto()
    WATCHING = auto()
    TRIGGERED = auto()


@dataclass
class TrackState:
    """Per-track state for item interaction detection."""
    track_id: int
    state: InteractionState = InteractionState.IDLE
    consecutive_frames: int = 0
    last_seen_ts: float = 0.0
    baseline_item_positions: dict = field(default_factory=dict)


# ── Persistence Event ─────────────────────────────────────────────────────────

@dataclass(slots=True)
class DetectionEvent:
    """
    Lightweight JSON payload pushed to Redis `persistence_queue`.
    Inference never touches the DB directly.
    """
    camera_id: str
    class_name: str
    confidence: float
    slot_id: int
    t_capture: int
    t_output: int
    trace_id: str

from __future__ import annotations

from dataclasses import dataclass

from services.inference.services.interaction import ItemInteractionDetector
from services.inference.services.temporal_buffer import TemporalBuffer
from shared.core.config import CameraConfig
from shared.core.settings import Settings
from shared.types.events import IncidentPayload


@dataclass
class CameraRuntimeState:
    interaction: ItemInteractionDetector
    buffer: TemporalBuffer
    frame_count: int = 0
    skip_n: int = 3
    last_masks: list | None = None
    last_items: list | None = None
    last_tracks: list[dict] | None = None
    active_task: bool = False
    current_incident: IncidentPayload | None = None
    config: CameraConfig | None = None


class CameraStateStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._states: dict[str, CameraRuntimeState] = {}

    def new_state(self) -> CameraRuntimeState:
        return CameraRuntimeState(
            interaction=ItemInteractionDetector(
                hand_dist_px=self._settings.hand_dist_px,
                interaction_frames=self._settings.interaction_frames,
            ),
            buffer=TemporalBuffer(maxlen=self._settings.temporal_window),
            last_masks=[],
            last_items=[],
            last_tracks=[],
        )

    def get(self, camera_id: str) -> CameraRuntimeState:
        if camera_id not in self._states:
            self._states[camera_id] = self.new_state()
        return self._states[camera_id]

    def mark_task_complete(self, camera_id: str) -> None:
        state = self._states.get(camera_id)
        if state:
            state.active_task = False

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from src.core.logger.logger import get_logger
from src.services.deep_sort_realtime.deepsort_tracker import DeepSort


class DeepSortTrackerBridge:
    def __init__(self, enabled: bool, embedder: str | None) -> None:
        self._logger = get_logger(__name__)
        self._enabled = enabled
        self._available = False
        self._tracker: Any = None

        if not enabled:
            return

        vendored_package_root = Path(__file__).resolve().parents[1]
        if str(vendored_package_root) not in sys.path:
            sys.path.insert(0, str(vendored_package_root))

        kwargs: dict[str, Any] = {"embedder": None if embedder in {None, "none"} else embedder}
        self._tracker = DeepSort(**kwargs)
        self._available = True

    @property
    def available(self) -> bool:
        return self._available

    def idle_tracks(self) -> list[dict[str, Any]]:
        if not self._available:
            return []
        return []

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from src.core.logger.logger import get_logger


class DeepSortTrackerBridge:
    def __init__(self, enabled: bool, embedder: str | None) -> None:
        self._logger = get_logger(__name__)
        self._enabled = enabled
        self._available = False
        self._tracker: Any = None

        if not enabled:
            return

        repo_root = Path(__file__).resolve().parents[4]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

        try:
            from deep_sort_realtime.deepsort_tracker import DeepSort
        except ImportError as exc:
            self._logger.warning("Deep SORT bridge could not be enabled: %s", exc)
            return

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

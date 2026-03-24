from __future__ import annotations

from pathlib import Path


class SqlQueryLoader:
    def __init__(self) -> None:
        self._cache: dict[Path, str] = {}

    def load(self, path: Path) -> str:
        query = self._cache.get(path)
        if query is None:
            query = path.read_text(encoding="utf-8").strip()
            self._cache[path] = query
        return query

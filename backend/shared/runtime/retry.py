from __future__ import annotations


def next_backoff_delay(attempt: int, *, base: float = 1.0, cap: float = 30.0) -> float:
    if attempt <= 0:
        return base
    return min(base * (2 ** (attempt - 1)), cap)

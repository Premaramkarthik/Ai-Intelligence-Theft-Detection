"""
shared.logging — Centralised JSON structured logger.

    from shared.logging import get_logger
    log = get_logger(__name__)
"""
from shared.logging.logger import get_logger, root

__all__ = [
    "get_logger",
    "root",
]

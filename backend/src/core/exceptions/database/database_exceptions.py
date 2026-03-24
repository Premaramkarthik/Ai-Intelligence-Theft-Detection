from __future__ import annotations

from src.core.exceptions.base.app_exception import AppException


class DatabaseUnavailableException(AppException):
    def __init__(self, message: str = "Database is unavailable.") -> None:
        super().__init__(message=message, error_code="DATABASE_UNAVAILABLE", status_code=503)

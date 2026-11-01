"""Raise ServiceError anywhere to return the contract error envelope."""

from typing import Any

from aec_contracts import ErrorCode


class ServiceError(Exception):
    """Raise anywhere to return the contract error envelope."""

    def __init__(self, status: int, code: ErrorCode, message: str | None = None, **details: Any) -> None:
        self.status, self.code, self.message, self.details = status, code, message, details


class NotImplementedYet(ServiceError):
    def __init__(self) -> None:
        super().__init__(501, ErrorCode.INTERNAL_ERROR, "not implemented")

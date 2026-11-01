"""Raise ServiceError anywhere to return the contract error envelope."""

from typing import Any

from aec_contracts import ErrorCode, ErrorEnvelope
from fastapi.responses import JSONResponse

from .observability import request_id_var


class ServiceError(Exception):
    """Raise anywhere to return the contract error envelope."""

    def __init__(self, status: int, code: ErrorCode, message: str | None = None,
                 headers: dict[str, str] | None = None, **details: Any) -> None:
        self.status, self.code, self.message, self.headers, self.details = status, code, message, headers, details


def not_found() -> ServiceError:
    return ServiceError(404, ErrorCode.NOT_FOUND, "Not found.")


def stale_model(head_version: int | None = None) -> ServiceError:
    error = ServiceError(409, ErrorCode.STALE_MODEL, "The plan changed since you loaded it.")
    if head_version is not None:
        error.details = {"head_version": head_version}
    return error


def model_not_ready() -> ServiceError:
    return ServiceError(409, ErrorCode.MODEL_NOT_READY, "The plan is still being processed.")


def envelope(status: int, code: ErrorCode, message: str | None = None,
             headers: dict[str, str] | None = None, **details: Any) -> JSONResponse:
    body = ErrorEnvelope.of(code, message, **details).model_dump(mode="json")
    return JSONResponse(body, status_code=status, headers={"X-Request-ID": request_id_var.get(), **(headers or {})})

"""Error envelope and the closed set of error codes (CONTRACTS.md §1)."""

from enum import StrEnum
from typing import Any

from .model import Strict


class ErrorCode(StrEnum):
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    VALIDATION_ERROR = "validation_error"
    CONFLICT = "conflict"
    STALE_MODEL = "stale_model"
    MODEL_NOT_READY = "model_not_ready"
    ALREADY_PROCESSING = "already_processing"
    QUOTA_EXCEEDED = "quota_exceeded"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    RATE_LIMITED = "rate_limited"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    INTERNAL_ERROR = "internal_error"


HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.UNAUTHORIZED: 401, ErrorCode.FORBIDDEN: 403, ErrorCode.NOT_FOUND: 404,
    ErrorCode.VALIDATION_ERROR: 422, ErrorCode.CONFLICT: 409, ErrorCode.STALE_MODEL: 409,
    ErrorCode.MODEL_NOT_READY: 409, ErrorCode.ALREADY_PROCESSING: 409, ErrorCode.QUOTA_EXCEEDED: 409,
    ErrorCode.PAYLOAD_TOO_LARGE: 413, ErrorCode.UNSUPPORTED_MEDIA_TYPE: 415, ErrorCode.RATE_LIMITED: 429,
    ErrorCode.UPSTREAM_UNAVAILABLE: 502, ErrorCode.INTERNAL_ERROR: 500,
}


class ErrorBody(Strict):
    code: ErrorCode
    message: str | None = None
    details: dict[str, Any] = {}


class ErrorEnvelope(Strict):
    error: ErrorBody

    @classmethod
    def of(cls, code: ErrorCode, message: str | None = None, **details: Any) -> "ErrorEnvelope":
        return cls(error=ErrorBody(code=code, message=message, details=details))

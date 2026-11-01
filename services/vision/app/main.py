"""Vision service: app factory, health, error envelope, request IDs, JSON logging."""

import json
import logging
import time
import uuid
from contextvars import ContextVar
from typing import Any

from aec_contracts import ErrorCode, ErrorEnvelope
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import Settings, get_settings
from .errors import ServiceError
from .v1 import router as v1_router

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
log = logging.getLogger("vision")

STATUS_CODES = {401: ErrorCode.UNAUTHORIZED, 403: ErrorCode.FORBIDDEN, 404: ErrorCode.NOT_FOUND,
                409: ErrorCode.CONFLICT, 413: ErrorCode.PAYLOAD_TOO_LARGE, 415: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
                422: ErrorCode.VALIDATION_ERROR, 429: ErrorCode.RATE_LIMITED, 502: ErrorCode.UPSTREAM_UNAVAILABLE,
                503: ErrorCode.UPSTREAM_UNAVAILABLE}


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S") + f".{int(record.msecs):03d}Z",
            "level": record.levelname, "service": self.service, "logger": record.name,
            "request_id": request_id_var.get(), "msg": record.getMessage(),
        }
        out.update(getattr(record, "fields", {}))
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler()
    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter(settings.service_name))
    logging.Formatter.converter = time.gmtime
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level)


def _envelope(status: int, code: ErrorCode, message: str | None = None, **details: Any) -> JSONResponse:
    body = ErrorEnvelope.of(code, message, **details).model_dump(mode="json")
    return JSONResponse(body, status_code=status, headers={"X-Request-ID": request_id_var.get()})


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    app = FastAPI(title="AEC Vision service", version=settings.version)
    app.dependency_overrides[get_settings] = lambda: settings

    @app.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Any:
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = request_id_var.set(rid[:128])
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid[:128]
        log.info("request", extra={"fields": {"method": request.method, "path": request.url.path,
                                               "status": response.status_code, "request_id": rid[:128],
                                               "duration_ms": round((time.perf_counter() - start) * 1000, 1)}})
        return response

    @app.exception_handler(ServiceError)
    async def service_error(_: Request, exc: ServiceError) -> JSONResponse:
        return _envelope(exc.status, exc.code, exc.message, **exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
        return _envelope(422, ErrorCode.VALIDATION_ERROR, "Request validation failed.", errors=errors)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = STATUS_CODES.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        return _envelope(exc.status_code, code, str(exc.detail) if exc.detail else None)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error")
        return _envelope(500, ErrorCode.INTERNAL_ERROR, "Unexpected error.")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name, "version": settings.version}

    @app.get("/readyz")
    def readyz() -> dict[str, str]:
        # P1: check real dependencies here.
        return {"status": "ok"}

    app.include_router(v1_router)
    return app


app = create_app()

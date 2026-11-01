"""Core API service: app factory, health, error envelope, request IDs, security middleware."""

import logging
import time
import uuid
from typing import Any

from aec_contracts import ErrorCode
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.exc import DataError, SQLAlchemyError
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import Settings, get_settings
from .container import Container, build_container
from .errors import ServiceError, envelope
from .observability import configure_logging, request_id_var
from .v1 import router as v1_router

log = logging.getLogger("api")

STATUS_CODES = {401: ErrorCode.UNAUTHORIZED, 403: ErrorCode.FORBIDDEN, 404: ErrorCode.NOT_FOUND,
                405: ErrorCode.NOT_FOUND, 409: ErrorCode.CONFLICT, 413: ErrorCode.PAYLOAD_TOO_LARGE,
                415: ErrorCode.UNSUPPORTED_MEDIA_TYPE, 422: ErrorCode.VALIDATION_ERROR, 429: ErrorCode.RATE_LIMITED,
                502: ErrorCode.UPSTREAM_UNAVAILABLE, 503: ErrorCode.UPSTREAM_UNAVAILABLE}
SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
                    "Referrer-Policy": "no-referrer", "Cache-Control": "no-store"}
TOO_LARGE = "The request body is too large."


class BodySizeLimit:
    """Caps the body before any parser spools it, including chunked requests with no Content-Length."""

    def __init__(self, app: ASGIApp, limit: int) -> None:
        self.app, self.limit = app, limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = Headers(scope=scope).get("content-length", "")
        if declared.isdigit() and int(declared) > self.limit:
            await envelope(413, ErrorCode.PAYLOAD_TOO_LARGE, TOO_LARGE)(scope, receive, send)
            return
        seen, over = 0, False

        async def counted() -> Message:
            nonlocal seen, over
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.limit:
                    over = True
                    return {"type": "http.disconnect"}
            return message

        async def guarded(message: Message) -> None:
            if not over:
                await send(message)

        try:
            await self.app(scope, counted, guarded)
        except Exception:
            if not over:
                raise
        if over:
            await envelope(413, ErrorCode.PAYLOAD_TOO_LARGE, TOO_LARGE)(scope, receive, send)


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    app = FastAPI(title="AEC Core API service", version=settings.version)
    app.state.container = container or build_container(settings)

    app.add_middleware(BodySizeLimit, limit=max(settings.max_upload_bytes, settings.max_audio_bytes) + 1024 * 1024)

    @app.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Any:
        rid = (request.headers.get("X-Request-ID") or uuid.uuid4().hex)[:128]
        token = request_id_var.set(rid)
        start = time.perf_counter()
        try:
            try:
                response: Response = await call_next(request)
            except Exception:  # handled here, inside CORS, so the browser can read the 500 envelope
                log.exception("unhandled error")
                response = envelope(500, ErrorCode.INTERNAL_ERROR, "Unexpected error.")
            log.info("request", extra={"fields": {
                "method": request.method, "path": request.url.path, "status": response.status_code,
                "user_id": getattr(request.state, "user_id", None),
                "duration_ms": round((time.perf_counter() - start) * 1000, 1)}})
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        response.headers.update(SECURITY_HEADERS)
        return response

    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )

    @app.exception_handler(ServiceError)
    async def service_error(_: Request, exc: ServiceError) -> JSONResponse:
        return envelope(exc.status, exc.code, exc.message, exc.headers, **exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
        return envelope(422, ErrorCode.VALIDATION_ERROR, "Request validation failed.", errors=errors)

    @app.exception_handler(DataError)
    async def data_error(_: Request, exc: DataError) -> JSONResponse:
        # Text Postgres cannot store (a NUL byte, say). Pydantic lets it through, the database refuses it.
        return envelope(422, ErrorCode.VALIDATION_ERROR, "The request contains characters that cannot be stored.")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = STATUS_CODES.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        return envelope(exc.status_code, code, str(exc.detail) if exc.detail else None)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name, "version": settings.version}

    @app.get("/readyz")
    def readyz(request: Request) -> dict[str, str]:
        try:
            with request.app.state.container.session_factory() as session:
                session.execute(text("select 1"))
        except SQLAlchemyError as exc:
            log.warning("database not ready", extra={"fields": {"error": type(exc).__name__}})
            raise ServiceError(503, ErrorCode.UPSTREAM_UNAVAILABLE, "The database is unavailable.") from exc
        return {"status": "ok"}

    app.include_router(v1_router)
    return app


app = create_app()

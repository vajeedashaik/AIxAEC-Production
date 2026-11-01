"""HTTP plumbing for the internal services: token, request ID, bounded retry, circuit breaker."""

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx
from aec_contracts import ErrorCode
from pydantic import ValidationError

from ..errors import ServiceError
from ..observability import request_id_var

log = logging.getLogger("api.clients")

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 0.5
BREAKER_THRESHOLD = 5
BREAKER_RESET_SECONDS = 30.0


class RetryableUpstream(ServiceError):
    """A 5xx or connection failure. Only these are retried."""


class CircuitBreaker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures = 0
        self._opened_at: float | None = None

    def allow(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return True
            if time.monotonic() - self._opened_at < BREAKER_RESET_SECONDS:
                return False
            self._opened_at = time.monotonic()  # half-open: one probe per reset window
            return True

    def record(self, ok: bool) -> None:
        with self._lock:
            self._failures = 0 if ok else self._failures + 1
            self._opened_at = time.monotonic() if self._failures >= BREAKER_THRESHOLD else None


def call_with_retry[T](fn: Callable[[], T], attempts: int = MAX_ATTEMPTS) -> T:
    for attempt in range(attempts - 1):
        try:
            return fn()
        except RetryableUpstream:
            time.sleep(BACKOFF_SECONDS * 2**attempt)
    return fn()


class ServiceClient:
    def __init__(self, name: str, base_url: str, token: str, timeout: float) -> None:
        self.name = name
        self.breaker = CircuitBreaker()
        self._http = httpx.Client(base_url=base_url, timeout=timeout, headers={"X-Internal-Token": token})

    def post[T](self, path: str, parse: Callable[[Any], T], *, retry: bool = True, **kwargs: Any) -> T:
        def once() -> Any:
            return self._send(path, kwargs)

        raw = call_with_retry(once) if retry else once()
        try:
            return parse(raw)
        except ValidationError as exc:
            log.error("upstream broke the contract", extra={"fields": {"service": self.name, "path": path}})
            raise self._down(502) from exc

    def _send(self, path: str, kwargs: dict[str, Any]) -> Any:
        fields: dict[str, Any] = {"service": self.name, "path": path}
        if not self.breaker.allow():
            raise self._down(503)
        try:
            response = self._http.post(path, headers={"X-Request-ID": request_id_var.get()}, **kwargs)
        except httpx.TransportError as exc:
            self.breaker.record(False)
            log.warning("upstream unreachable", extra={"fields": {**fields, "error": type(exc).__name__}})
            raise self._down(503, RetryableUpstream) from exc
        fields["status"] = response.status_code
        if response.status_code >= 500:
            self.breaker.record(False)
            log.warning("upstream failed", extra={"fields": fields})
            raise self._down(502, RetryableUpstream)
        self.breaker.record(True)  # the service answered, so a 4xx is our bug, not an outage
        if response.status_code >= 400:
            log.error("upstream refused", extra={"fields": fields})
            raise self._down(502)
        try:
            return response.json()
        except ValueError as exc:
            raise self._down(502) from exc

    def _down(self, status: int, kind: type[ServiceError] = ServiceError) -> ServiceError:
        return kind(status, ErrorCode.UPSTREAM_UNAVAILABLE, f"The {self.name} service is unavailable.")

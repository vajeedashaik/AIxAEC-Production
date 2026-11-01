"""Structured JSON logs with request IDs and secret redaction."""

import json
import logging
import re
import time
from contextvars import ContextVar
from typing import Any

from .config import Settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_SECRETS = re.compile(
    r"(?i)\bbearer\s+[\w.~+/=-]+"                   # Authorization values
    r"|\beyJ[\w-]+\.[\w-]+\.[\w-]*"                 # JWTs
    r"|\bsk[-_][\w-]{8,}"                           # API keys
    r"|\b(?:token|apikey|api_key|secret|password)=[^\s&\"']+"
)


def redact(text: str) -> str:
    return _SECRETS.sub("[REDACTED]", text)


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
        return redact(json.dumps(out, default=str))


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(settings.service_name) if settings.log_format == "json"
                         else RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.Formatter.converter = time.gmtime
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # its INFO lines carry signed URLs

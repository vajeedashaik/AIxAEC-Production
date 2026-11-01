"""POST /v1/analyze (CONTRACTS.md §5)."""

import hmac
from typing import Annotated
from uuid import UUID

from aec_contracts import AnalyzeOptions, AnalyzeResult, ErrorCode
from fastapi import APIRouter, Depends, File, Form, Header, UploadFile
from pydantic import ValidationError

from .config import Settings, get_settings
from .errors import ServiceError
from .pipeline.runner import run_pipeline


def require_internal_token(
    settings: Annotated[Settings, Depends(get_settings)],
    x_internal_token: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.internal_service_token.get_secret_value()
    if x_internal_token is None or not hmac.compare_digest(x_internal_token.encode(), expected.encode()):
        raise ServiceError(401, ErrorCode.UNAUTHORIZED)


router = APIRouter(prefix="/v1", dependencies=[Depends(require_internal_token)])


# Sync on purpose: FastAPI runs it in the threadpool, so the CPU-bound pipeline never blocks the event loop.
@router.post("/analyze", response_model=AnalyzeResult)
def analyze(
    file: Annotated[UploadFile, File(description="PNG / JPG / PDF")],
    floorplan_id: Annotated[UUID, Form()],
    settings: Annotated[Settings, Depends(get_settings)],
    options: Annotated[str | None, Form(description='JSON, e.g. {"ocr": true, "max_dimension": 2400}')] = None,
) -> AnalyzeResult:
    try:
        parsed = AnalyzeOptions.model_validate_json(options) if options else AnalyzeOptions()
    except ValidationError as exc:
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        raise ServiceError(422, ErrorCode.VALIDATION_ERROR, "Invalid options.", errors=errors) from exc
    data = file.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise ServiceError(413, ErrorCode.PAYLOAD_TOO_LARGE, "The file is too large.")
    return run_pipeline(data, file.content_type, floorplan_id, parsed, settings)

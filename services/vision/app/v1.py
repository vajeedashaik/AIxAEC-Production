"""POST /v1/analyze (CONTRACTS.md §5). P0 stub: contract wired, returns 501."""

import hmac
from typing import Annotated
from uuid import UUID

from aec_contracts import AnalyzeResult, ErrorCode
from fastapi import APIRouter, Depends, File, Form, Header, UploadFile

from .config import Settings, get_settings
from .errors import NotImplementedYet, ServiceError


def require_internal_token(
    settings: Annotated[Settings, Depends(get_settings)],
    x_internal_token: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.internal_service_token.get_secret_value()
    if x_internal_token is None or not hmac.compare_digest(x_internal_token.encode(), expected.encode()):
        raise ServiceError(401, ErrorCode.UNAUTHORIZED)


router = APIRouter(prefix="/v1", dependencies=[Depends(require_internal_token)])


@router.post("/analyze", response_model=AnalyzeResult)
def analyze(
    file: Annotated[UploadFile, File(description="PNG / JPG / PDF")],
    floorplan_id: Annotated[UUID, Form()],
    options: Annotated[str | None, Form(description='JSON, e.g. {"ocr": true, "max_dimension": 2400}')] = None,
) -> AnalyzeResult:
    raise NotImplementedYet()

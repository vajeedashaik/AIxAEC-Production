"""Language routes (CONTRACTS.md §7). P0 stub: contract wired, returns 501."""

import hmac
from typing import Annotated

from aec_contracts import (
    ClassifyRoomsRequest,
    ClassifyRoomsResult,
    ErrorCode,
    ParseRequest,
    ParseResult,
    TranscribeResult,
)
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


@router.post("/commands/parse", response_model=ParseResult)
def parse(body: ParseRequest) -> ParseResult:
    raise NotImplementedYet()


@router.post("/rooms/classify", response_model=ClassifyRoomsResult)
def classify(body: ClassifyRoomsRequest) -> ClassifyRoomsResult:
    raise NotImplementedYet()


@router.post("/speech/transcribe", response_model=TranscribeResult)
def transcribe(
    audio: Annotated[UploadFile, File(description="webm / ogg / wav / mp4 / mpeg / flac, max 10 MiB / 60 s")],
    language: Annotated[str, Form()] = "en",
) -> TranscribeResult:
    raise NotImplementedYet()

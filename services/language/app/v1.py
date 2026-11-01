"""Language routes (CONTRACTS.md §7). Sync routes on purpose: FastAPI runs them in its threadpool."""

import hmac
from typing import Annotated

from aec_contracts import (
    ACCEPTED_AUDIO_TYPES,
    MAX_AUDIO_BYTES,
    ClassifyRoomsRequest,
    ClassifyRoomsResult,
    ErrorCode,
    ParseRequest,
    ParseResult,
    TranscribeResult,
)
from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile

from .classify import classify_rooms
from .config import Settings, get_settings
from .errors import ServiceError


def require_internal_token(
    settings: Annotated[Settings, Depends(get_settings)],
    x_internal_token: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.internal_service_token.get_secret_value()
    if x_internal_token is None or not hmac.compare_digest(x_internal_token.encode(), expected.encode()):
        raise ServiceError(401, ErrorCode.UNAUTHORIZED)


router = APIRouter(prefix="/v1", dependencies=[Depends(require_internal_token)])


@router.post("/commands/parse", response_model=ParseResult)
def parse(body: ParseRequest, request: Request) -> ParseResult:
    result: ParseResult = request.app.state.parser.parse(body.instruction, body.brief)
    return result


@router.post("/rooms/classify", response_model=ClassifyRoomsResult)
def classify(body: ClassifyRoomsRequest, request: Request) -> ClassifyRoomsResult:
    return classify_rooms(body.labels, request.app.state.llm_client)


@router.post("/speech/transcribe", response_model=TranscribeResult)
def transcribe(
    request: Request,
    audio: Annotated[UploadFile, File(description="webm / ogg / wav / mp4 / mpeg / flac, max 10 MiB / 60 s")],
    language: Annotated[str, Form(pattern=r"^[a-z]{2,3}$")] = "en",
) -> TranscribeResult:
    content_type = (audio.content_type or "").split(";")[0].strip().lower()  # "audio/webm;codecs=opus"
    if content_type not in ACCEPTED_AUDIO_TYPES:
        raise ServiceError(415, ErrorCode.UNSUPPORTED_MEDIA_TYPE, "Unsupported audio type.",
                           accepted=list(ACCEPTED_AUDIO_TYPES))
    data = audio.file.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise ServiceError(413, ErrorCode.PAYLOAD_TOO_LARGE, "Audio is larger than 10 MiB.")
    result: TranscribeResult = request.app.state.speech.transcribe(data, language)
    return result

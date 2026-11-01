"""Language service DTOs (CONTRACTS.md §7)."""

from typing import Any, Literal

from pydantic import Field

from .geometry import PlanBrief
from .model import RoomType, Strict

ACCEPTED_AUDIO_TYPES: tuple[str, ...] = (
    "audio/webm", "audio/ogg", "audio/wav", "audio/x-wav", "audio/mp4", "audio/mpeg", "audio/flac",
)
MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_AUDIO_SECONDS = 60


class ParseRequest(Strict):
    instruction: str = Field(min_length=1, max_length=500)
    brief: PlanBrief


class ParseResult(Strict):
    status: Literal["PARSED", "UNKNOWN", "ERROR"]
    command: dict[str, Any] | None = None  # raw, UNTRUSTED. Must be re-validated downstream.
    provider: Literal["rules", "llm"]
    model: str | None = None               # LLM model id actually used
    detail: str | None = None              # user-safe reason for UNKNOWN / ERROR


class ClassifyRoomsRequest(Strict): labels: list[str] = Field(max_length=200)


class RoomClassification(Strict):
    label: str; room_type: RoomType; confidence: float = Field(ge=0, le=1)
    source: Literal["rules", "llm"]


class ClassifyRoomsResult(Strict): results: list[RoomClassification]   # same order as input


class TranscribeResult(Strict):
    text: str = Field(max_length=500); language: str; duration_ms: int
    provider: Literal["whisper", "stub"]

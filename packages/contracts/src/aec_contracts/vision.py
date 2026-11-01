"""Vision service DTOs (CONTRACTS.md §5)."""

from typing import Literal, Self, get_args

from pydantic import Field, model_validator

from .model import FloorPlanModel, Strict

StageName = Literal["preprocess", "wall_detection", "ocr", "object_detection",
                    "room_detection", "calibration", "semantic_assembly", "artifacts"]
STAGE_NAMES: tuple[str, ...] = get_args(StageName)
CRITICAL_STAGES = ("preprocess", "wall_detection", "semantic_assembly")


class AnalyzeOptions(Strict):
    """The optional `options` JSON form field of POST /v1/analyze."""
    ocr: bool = True
    object_detection: bool = True
    max_dimension: int = Field(default=2400, gt=0, le=10000)


class StageReport(Strict):
    name: StageName
    status: Literal["ok", "degraded", "failed", "skipped"]
    duration_ms: int = Field(ge=0)
    error: str | None = Field(default=None, max_length=500)   # user-safe text only
    detail: dict[str, int | float | str | bool | None] = {}   # e.g. {"walls": 14, "deskew_deg": 0.8}


ArtifactKind = Literal["preprocessed", "walls_overlay", "detected_elements", "semantic_model"]


class ArtifactPayload(Strict):
    kind: ArtifactKind
    content_type: Literal["image/png", "application/json"]
    data_base64: str


class AnalyzeResult(Strict):
    status: Literal["COMPLETED", "FAILED"]
    model: FloorPlanModel | None          # None iff FAILED
    stages: list[StageReport]             # always all 8, in order (skipped after a critical failure)
    artifacts: list[ArtifactPayload] = []
    warnings: list[str] = []              # e.g. "Only page 1 of 3 was processed."
    error: str | None = None              # "Processing failed at stage 'wall_detection'."

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.model is None) != (self.status == "FAILED"):
            raise ValueError("model must be null iff status is FAILED")
        if tuple(s.name for s in self.stages) != STAGE_NAMES:
            raise ValueError(f"stages must be exactly {STAGE_NAMES} in order")
        return self

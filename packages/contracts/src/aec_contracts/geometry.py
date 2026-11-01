"""Geometry service DTOs (CONTRACTS.md §6)."""

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, TypeAdapter

from .commands import Command
from .model import FloorPlanModel, ModelSummary, RoomType, Strict
from .results import Candidate, ChangeSet, RejectStage


class ExecuteRequest(Strict):
    model: FloorPlanModel
    command: dict[str, Any]  # raw/untrusted; geometry validates with COMMAND_ADAPTER (stage "schema")
    dry_run: bool = False    # identical computation; caller decides whether to persist


class ExecuteApplied(Strict):
    status: Literal["APPLIED"]
    command: Command        # resolved: target_id set, target_query cleared
    model: FloorPlanModel   # the new candidate model (validated)
    changes: ChangeSet
    summary: str            # "Moved wall 300 mm left; 2 rooms resized."


class ExecuteClarification(Strict):
    status: Literal["CLARIFICATION"]
    question: str           # "Which wall do you mean?"
    candidates: list[Candidate] = Field(min_length=2)


class ExecuteRejected(Strict):
    status: Literal["REJECTED"]
    stage: RejectStage
    detail: str             # plain English, actionable ("Set a scale first to use millimetres.")


ExecuteResult = Annotated[ExecuteApplied | ExecuteClarification | ExecuteRejected, Field(discriminator="status")]
EXECUTE_RESULT_ADAPTER: TypeAdapter[ExecuteResult] = TypeAdapter(ExecuteResult)


class ModelRequest(Strict):
    """Body of /v1/models/insights, /v1/models/brief and /v1/models/validate."""
    model: FloorPlanModel


class RoomRef(Strict): id: UUID; label: str | None; area_px: float


class MetricInsights(Strict):
    total_area_m2: float; average_room_area_m2: float
    total_wall_length_m: float; exterior_wall_length_m: float; interior_wall_length_m: float


class Insights(Strict):
    counts: ModelSummary
    total_area_px: float; average_room_area_px: float
    largest_room: RoomRef | None; smallest_room: RoomRef | None
    total_wall_length_px: float; exterior_wall_length_px: float; interior_wall_length_px: float
    rooms_by_type: dict[RoomType, int]
    metric: MetricInsights | None        # only when mm_per_pixel is set


class RoomBrief(Strict): label: str | None; room_type: RoomType; wall_count: int


class PlanBrief(Strict):
    """No coordinates and no ids: the only plan context an LLM ever sees."""
    rooms: list[RoomBrief]; counts: ModelSummary; has_scale: bool
    image_width: int; image_height: int


class ValidationIssue(Strict):
    code: str
    message: str
    element_id: UUID | None


class ValidateResult(Strict):
    valid: bool
    issues: list[ValidationIssue]

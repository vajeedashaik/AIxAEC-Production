"""Public API DTOs used by apps/web (CONTRACTS.md §8)."""

from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from .commands import EngineCommand
from .geometry import Insights
from .model import FloorPlanModel, ModelSummary, Strict
from .results import Candidate, ChangeSet, RejectStage
from .vision import ArtifactKind, StageReport

JobStatus = Literal["PENDING", "PROCESSING", "COMPLETED", "FAILED"]


class Me(Strict): id: UUID; clerk_user_id: str; email: str | None; display_name: str | None; created_at: datetime


class ProjectCreate(Strict):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ProjectUpdate(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class Project(Strict):
    id: UUID; name: str; description: str | None
    floorplan_count: int; thumbnail_url: str | None        # signed URL of latest preprocessed artifact
    created_at: datetime; updated_at: datetime


class Page[T](Strict): items: list[T]; total: int; limit: int; offset: int


class Job(Strict):
    id: UUID; floorplan_id: UUID; status: JobStatus; attempts: int
    stages: list[StageReport]; error_message: str | None
    created_at: datetime; started_at: datetime | None; finished_at: datetime | None


class FloorPlan(Strict):
    id: UUID; project_id: UUID; version: int
    original_filename: str; content_type: str; size_bytes: int
    status: JobStatus; current_model_version: int | None
    download_url: str | None; latest_job: Job | None
    warnings: list[str] = []; created_at: datetime


class ModelEnvelope(Strict):
    floorplan_id: UUID; version: int; model: FloorPlanModel; summary: ModelSummary; insights: Insights


class Artifact(Strict): id: UUID; job_id: UUID; kind: ArtifactKind; content_type: str; size_bytes: int; url: str


class CommandRequest(Strict):
    instruction: str | None = Field(default=None, min_length=1, max_length=500)
    command: dict[str, Any] | None = None  # structured (from point-and-click / clarification pick)
    expected_version: int | None = None

    @model_validator(mode="after")
    def _exactly_one_input(self) -> Self:
        if (self.instruction is None) == (self.command is None):
            raise ValueError("exactly one of instruction / command must be set")
        return self


class CommandResponse(Strict):
    status: Literal["APPLIED", "PREVIEW", "CLARIFICATION", "REJECTED"]
    version: int | None = None             # HEAD after the call (APPLIED) or base version (PREVIEW)
    model: FloorPlanModel | None = None    # APPLIED: new HEAD; PREVIEW: candidate (not persisted)
    changes: ChangeSet | None = None
    command: EngineCommand | None = None         # resolved command; on CLARIFICATION the parsed one (target_query set)
    summary: str | None = None
    question: str | None = None
    candidates: list[Candidate] = []
    stage: RejectStage | None = None
    detail: str | None = None
    transcript: str | None = None          # voice routes only
    edit_id: UUID | None = None


class VersionInfo(Strict):
    version: int; origin: Literal["PROCESSING", "EDIT"]; parent_version: int | None
    discarded: bool; is_head: bool; created_at: datetime; edit_id: UUID | None


class EditLogEntry(Strict):
    id: UUID; instruction: str | None; operation: str | None
    status: Literal["APPLIED", "REJECTED", "CLARIFICATION", "UNDO", "REDO"]
    stage: RejectStage | None; error: str | None
    parent_version: int | None; result_version: int | None; created_at: datetime


class History(Strict):
    head_version: int | None; can_undo: bool; can_redo: bool
    versions: list[VersionInfo]; edits: list[EditLogEntry]

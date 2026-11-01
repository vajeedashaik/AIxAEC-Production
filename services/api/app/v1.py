"""Public API routes (CONTRACTS.md §8). P0 stub: contract wired, returns 501."""

from typing import Annotated
from uuid import UUID

from aec_contracts import (
    Artifact,
    CommandRequest,
    CommandResponse,
    ErrorCode,
    FloorPlan,
    History,
    Job,
    Me,
    ModelEnvelope,
    Page,
    Project,
    ProjectCreate,
    ProjectUpdate,
)
from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile

from .errors import NotImplementedYet, ServiceError


def require_bearer(authorization: Annotated[str | None, Header()] = None) -> str:
    # P3: verify the Clerk session JWT against CLERK_JWKS_URL and provision the user. P0 only checks presence.
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ServiceError(401, ErrorCode.UNAUTHORIZED)
    return token


router = APIRouter(prefix="/v1", dependencies=[Depends(require_bearer)])


@router.get("/me", response_model=Me)
def me() -> Me:
    raise NotImplementedYet()


@router.get("/projects", response_model=Page[Project])
def list_projects(limit: Annotated[int, Query(ge=1, le=100)] = 20,
                  offset: Annotated[int, Query(ge=0)] = 0) -> Page[Project]:
    raise NotImplementedYet()


@router.post("/projects", response_model=Project, status_code=201)
def create_project(body: ProjectCreate) -> Project:
    raise NotImplementedYet()


@router.get("/projects/{project_id}", response_model=Project)
def get_project(project_id: UUID) -> Project:
    raise NotImplementedYet()


@router.patch("/projects/{project_id}", response_model=Project)
def update_project(project_id: UUID, body: ProjectUpdate) -> Project:
    raise NotImplementedYet()


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: UUID) -> None:
    raise NotImplementedYet()


@router.get("/projects/{project_id}/floorplans", response_model=list[FloorPlan])
def list_floorplans(project_id: UUID) -> list[FloorPlan]:
    raise NotImplementedYet()


@router.post("/projects/{project_id}/floorplans", response_model=FloorPlan, status_code=201)
def upload_floorplan(project_id: UUID, file: Annotated[UploadFile, File()], process: bool = True) -> FloorPlan:
    raise NotImplementedYet()


@router.get("/floorplans/{floorplan_id}", response_model=FloorPlan)
def get_floorplan(floorplan_id: UUID) -> FloorPlan:
    raise NotImplementedYet()


@router.delete("/floorplans/{floorplan_id}", status_code=204)
def delete_floorplan(floorplan_id: UUID) -> None:
    raise NotImplementedYet()


@router.post("/floorplans/{floorplan_id}/process", response_model=Job, status_code=202)
def process_floorplan(floorplan_id: UUID) -> Job:
    raise NotImplementedYet()


@router.get("/floorplans/{floorplan_id}/job", response_model=Job)
def get_job(floorplan_id: UUID) -> Job:
    raise NotImplementedYet()


@router.get("/floorplans/{floorplan_id}/model", response_model=ModelEnvelope)
def get_model(floorplan_id: UUID, version: Annotated[int | None, Query(ge=1)] = None) -> ModelEnvelope:
    raise NotImplementedYet()


@router.get("/floorplans/{floorplan_id}/artifacts", response_model=list[Artifact])
def list_artifacts(floorplan_id: UUID) -> list[Artifact]:
    raise NotImplementedYet()


@router.post("/floorplans/{floorplan_id}/commands/interpret", response_model=CommandResponse)
def interpret_command(floorplan_id: UUID, body: CommandRequest) -> CommandResponse:
    raise NotImplementedYet()


@router.post("/floorplans/{floorplan_id}/commands", response_model=CommandResponse)
def apply_command(floorplan_id: UUID, body: CommandRequest) -> CommandResponse:
    raise NotImplementedYet()


@router.post("/floorplans/{floorplan_id}/commands/voice", response_model=CommandResponse)
def voice_command(
    floorplan_id: UUID,
    audio: Annotated[UploadFile, File()],
    expected_version: Annotated[int | None, Form()] = None,
    dry_run: Annotated[bool, Form()] = False,
) -> CommandResponse:
    raise NotImplementedYet()


@router.post("/floorplans/{floorplan_id}/model/undo", response_model=CommandResponse)
def undo(floorplan_id: UUID, expected_version: int | None = None) -> CommandResponse:
    raise NotImplementedYet()


@router.post("/floorplans/{floorplan_id}/model/redo", response_model=CommandResponse)
def redo(floorplan_id: UUID, expected_version: int | None = None) -> CommandResponse:
    raise NotImplementedYet()


@router.get("/floorplans/{floorplan_id}/history", response_model=History)
def history(floorplan_id: UUID) -> History:
    raise NotImplementedYet()

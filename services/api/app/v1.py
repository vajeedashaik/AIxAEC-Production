"""Public API routes (CONTRACTS.md §8). Plain def routes: they run in the threadpool, sync DB and HTTP are fine."""

import logging
from collections.abc import Iterator
from typing import Annotated
from uuid import UUID, uuid4

from aec_contracts import (
    Artifact,
    CommandRequest,
    CommandResponse,
    ErrorCode,
    FloorPlan,
    FloorPlanModel,
    History,
    Job,
    Me,
    ModelEnvelope,
    Page,
    Project,
    ProjectCreate,
    ProjectUpdate,
)
from aec_contracts.analysis import Analysis, AnalysisQuery, Answer, AskRequest, LayoutGoal, LayoutSuggestions
from aec_contracts.language import ACCEPTED_AUDIO_TYPES
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import Ctx, CurrentUser, container
from .editing import run_command
from .errors import ServiceError, model_not_ready, not_found
from .jobs import enqueue
from .orm import LIVE_STATUSES, FloorplanRow, JobRow, ProjectRow, UserRow
from .repo import artifact_dtos, floorplan_dtos, get_floorplan, get_project, job_dto, latest_job, project_dtos
from .storage import ARTIFACT_BUCKET, SOURCE_BUCKET
from .uploads import read_capped, validate_upload
from .versions import history as load_history
from .versions import load_model, move_head, version_row

log = logging.getLogger("api.v1")
MAX_CACHED_INSIGHTS = 1024

router = APIRouter(prefix="/v1")


def get_session(request: Request) -> Iterator[Session]:
    with container(request).session_factory() as session:
        yield session


Db = Annotated[Session, Depends(get_session)]


def _delete_blobs(c: Ctx, bucket: str, prefix: str) -> None:
    try:
        c.blobs.delete_prefix(bucket, prefix)
    except ServiceError:  # the row is already gone, so the worst case is an orphan blob
        log.error("orphaned blobs after delete", extra={"fields": {"bucket": bucket, "prefix": prefix}})


@router.get("/me", response_model=Me)
def me(user: CurrentUser) -> Me:
    return user


# --- projects ---

@router.get("/projects", response_model=Page[Project])
def list_projects(user: CurrentUser, c: Ctx, session: Db, limit: Annotated[int, Query(ge=1, le=100)] = 20,
                  offset: Annotated[int, Query(ge=0)] = 0) -> Page[Project]:
    owned = ProjectRow.owner_id == user.id
    total = session.scalar(select(func.count()).select_from(ProjectRow).where(owned)) or 0
    rows = list(session.scalars(select(ProjectRow).where(owned)
                                .order_by(ProjectRow.created_at.desc(), ProjectRow.id).limit(limit).offset(offset)))
    return Page[Project](items=project_dtos(c, session, rows), total=total, limit=limit, offset=offset)


@router.post("/projects", response_model=Project, status_code=201)
def create_project(body: ProjectCreate, user: CurrentUser, c: Ctx, session: Db) -> Project:
    session.scalars(select(UserRow.id).where(UserRow.id == user.id).with_for_update()).one()  # serialises the quota
    count = session.scalar(select(func.count()).select_from(ProjectRow).where(ProjectRow.owner_id == user.id)) or 0
    if count >= c.settings.max_projects_per_user:
        raise ServiceError(409, ErrorCode.QUOTA_EXCEEDED, "You have reached the project limit.")
    row = ProjectRow(owner_id=user.id, name=body.name, description=body.description)
    session.add(row)
    session.commit()
    return project_dtos(c, session, [row])[0]


@router.get("/projects/{project_id}", response_model=Project)
def read_project(project_id: UUID, user: CurrentUser, c: Ctx, session: Db) -> Project:
    return project_dtos(c, session, [get_project(session, user.id, project_id)])[0]


@router.patch("/projects/{project_id}", response_model=Project)
def update_project(project_id: UUID, body: ProjectUpdate, user: CurrentUser, c: Ctx, session: Db) -> Project:
    row = get_project(session, user.id, project_id)
    if body.name is not None:
        row.name = body.name
    if "description" in body.model_fields_set:
        row.description = body.description
    session.commit()
    session.refresh(row)  # updated_at comes from a trigger
    return project_dtos(c, session, [row])[0]


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: UUID, user: CurrentUser, c: Ctx, session: Db) -> None:
    session.delete(get_project(session, user.id, project_id))
    session.commit()
    _delete_blobs(c, SOURCE_BUCKET, f"{project_id}/")
    _delete_blobs(c, ARTIFACT_BUCKET, f"{project_id}/")


# --- floor plans ---

@router.get("/projects/{project_id}/floorplans", response_model=list[FloorPlan])
def list_floorplans(project_id: UUID, user: CurrentUser, c: Ctx, session: Db) -> list[FloorPlan]:
    get_project(session, user.id, project_id)
    rows = list(session.scalars(select(FloorplanRow).where(FloorplanRow.project_id == project_id)
                                .order_by(FloorplanRow.version.desc())))
    return floorplan_dtos(c, session, rows)


def _check_floorplan_quota(c: Ctx, session: Session, project_id: UUID) -> None:
    count = session.scalar(select(func.count()).select_from(FloorplanRow)
                           .where(FloorplanRow.project_id == project_id)) or 0
    if count >= c.settings.max_floorplans_per_project:
        raise ServiceError(409, ErrorCode.QUOTA_EXCEEDED, "This project has reached the floor plan limit.")


@router.post("/projects/{project_id}/floorplans", response_model=FloorPlan, status_code=201)
def upload_floorplan(project_id: UUID, file: Annotated[UploadFile, File()], user: CurrentUser, c: Ctx, session: Db,
                     process: bool = True) -> FloorPlan:
    get_project(session, user.id, project_id)
    _check_floorplan_quota(c, session, project_id)
    session.rollback()  # no open transaction across validation and the storage upload
    upload = validate_upload(file.file, file.filename, file.content_type, c.settings.max_upload_bytes,
                             c.settings.max_image_pixels)
    floorplan_id = uuid4()
    key = f"{project_id}/{floorplan_id}/source.{upload.extension}"
    c.blobs.put(SOURCE_BUCKET, key, upload.data, upload.content_type)
    try:
        get_project(session, user.id, project_id, lock=True)  # serialises quota and next version
        _check_floorplan_quota(c, session, project_id)
        latest = session.scalar(select(func.coalesce(func.max(FloorplanRow.version), 0))
                                .where(FloorplanRow.project_id == project_id)) or 0
        row = FloorplanRow(id=floorplan_id, project_id=project_id, version=latest + 1,
                           original_filename=upload.filename, storage_key=key, content_type=upload.content_type,
                           size_bytes=len(upload.data), checksum_sha256=upload.sha256, warnings=upload.warnings)
        session.add(row)
        session.flush()
        if process:
            enqueue(session, row, c.settings.processing_stale_seconds)
        session.commit()
    except Exception:
        session.rollback()
        _delete_blobs(c, SOURCE_BUCKET, f"{project_id}/{floorplan_id}/")
        raise
    return floorplan_dtos(c, session, [row])[0]


@router.get("/floorplans/{floorplan_id}", response_model=FloorPlan)
def read_floorplan(floorplan_id: UUID, user: CurrentUser, c: Ctx, session: Db) -> FloorPlan:
    return floorplan_dtos(c, session, [get_floorplan(session, user.id, floorplan_id)])[0]


@router.delete("/floorplans/{floorplan_id}", status_code=204)
def delete_floorplan(floorplan_id: UUID, user: CurrentUser, c: Ctx, session: Db) -> None:
    row = get_floorplan(session, user.id, floorplan_id)
    project_id = row.project_id
    session.delete(row)
    session.commit()
    _delete_blobs(c, SOURCE_BUCKET, f"{project_id}/{floorplan_id}/")
    _delete_blobs(c, ARTIFACT_BUCKET, f"{project_id}/{floorplan_id}/")


@router.post("/floorplans/{floorplan_id}/process", response_model=Job, status_code=202)
def process_floorplan(floorplan_id: UUID, user: CurrentUser, c: Ctx, session: Db) -> Job:
    floorplan = get_floorplan(session, user.id, floorplan_id, lock=True)
    job = enqueue(session, floorplan, c.settings.processing_stale_seconds)
    session.commit()
    return job_dto(job)


@router.get("/floorplans/{floorplan_id}/job", response_model=Job)
def read_job(floorplan_id: UUID, user: CurrentUser, session: Db) -> Job:
    get_floorplan(session, user.id, floorplan_id)
    job: JobRow | None = latest_job(session, floorplan_id)
    if job is None:
        raise not_found()
    return job_dto(job)


# --- model ---

@router.get("/floorplans/{floorplan_id}/model", response_model=ModelEnvelope)
def read_model(floorplan_id: UUID, user: CurrentUser, c: Ctx, session: Db,
               version: Annotated[int | None, Query(ge=1)] = None) -> ModelEnvelope:
    floorplan = get_floorplan(session, user.id, floorplan_id)
    if version is None:
        version = floorplan.current_model_version
        if version is None or floorplan.status in LIVE_STATUSES:
            raise model_not_ready()
    row = version_row(session, floorplan_id, version)
    if row is None:
        raise not_found()
    session.rollback()  # no open transaction across the geometry call
    model = load_model(row)
    key = (floorplan_id, version)
    insights = c.insights_cache.get(key)  # versions are immutable, so entries never go stale
    if insights is None:
        insights = c.geometry.insights(model)
        if len(c.insights_cache) >= MAX_CACHED_INSIGHTS:
            c.insights_cache.clear()
        c.insights_cache[key] = insights
    return ModelEnvelope(floorplan_id=floorplan_id, version=version, model=model, summary=model.summary(),
                         insights=insights)


@router.get("/floorplans/{floorplan_id}/artifacts", response_model=list[Artifact])
def list_artifacts(floorplan_id: UUID, user: CurrentUser, c: Ctx, session: Db) -> list[Artifact]:
    get_floorplan(session, user.id, floorplan_id)
    return artifact_dtos(c, session, floorplan_id)


# --- building intelligence ---

def _model_at(session: Session, user: CurrentUser, floorplan_id: UUID, version: int | None) -> FloorPlanModel:
    floorplan = get_floorplan(session, user.id, floorplan_id)
    if version is None:
        version = floorplan.current_model_version
        if version is None or floorplan.status in LIVE_STATUSES:
            raise model_not_ready()
    row = version_row(session, floorplan_id, version)
    if row is None:
        raise not_found()
    session.rollback()  # no open transaction across the service call
    return load_model(row)


@router.post("/floorplans/{floorplan_id}/analysis", response_model=Analysis)
def analysis(floorplan_id: UUID, body: AnalysisQuery, user: CurrentUser, c: Ctx, session: Db) -> Analysis:
    return c.geometry.analysis(_model_at(session, user, floorplan_id, body.version), body.rates)


@router.post("/floorplans/{floorplan_id}/ask", response_model=Answer)
def ask(floorplan_id: UUID, body: AskRequest, user: CurrentUser, c: Ctx, session: Db) -> Answer:
    model = _model_at(session, user, floorplan_id, body.version)
    answer = c.geometry.answer(model, body.question)
    if answer.status != "UNKNOWN":
        return answer
    try:
        result = c.language.answer(body.question, c.geometry.facts(model))
    except ServiceError:  # the rules' honest "can't answer" stands when the assistant is down
        return answer
    if result.status == "ANSWERED" and result.answer:
        return Answer(status="ANSWERED", answer=result.answer, source="llm")
    return answer


@router.post("/floorplans/{floorplan_id}/layouts", response_model=LayoutSuggestions)
def layouts(floorplan_id: UUID, body: LayoutGoal, user: CurrentUser, c: Ctx, session: Db) -> LayoutSuggestions:
    return c.geometry.layouts(_model_at(session, user, floorplan_id, None), body.goal)


# --- edits ---

@router.post("/floorplans/{floorplan_id}/commands/interpret", response_model=CommandResponse)
def interpret_command(floorplan_id: UUID, body: CommandRequest, user: CurrentUser, c: Ctx) -> CommandResponse:
    return run_command(c, user, floorplan_id, instruction=body.instruction, command=body.command,
                       expected_version=body.expected_version, persist=False)


@router.post("/floorplans/{floorplan_id}/commands", response_model=CommandResponse)
def apply_command(floorplan_id: UUID, body: CommandRequest, user: CurrentUser, c: Ctx) -> CommandResponse:
    return run_command(c, user, floorplan_id, instruction=body.instruction, command=body.command,
                       expected_version=body.expected_version, persist=True)


@router.post("/floorplans/{floorplan_id}/commands/voice", response_model=CommandResponse)
def voice_command(
    floorplan_id: UUID,
    audio: Annotated[UploadFile, File()],
    user: CurrentUser,
    c: Ctx,
    expected_version: Annotated[int | None, Form()] = None,
    dry_run: Annotated[bool, Form()] = False,
) -> CommandResponse:
    with c.session_factory() as session:
        get_floorplan(session, user.id, floorplan_id)  # 404 before spending time on speech
    content_type = (audio.content_type or "").split(";")[0].strip().lower()
    if content_type not in ACCEPTED_AUDIO_TYPES:
        raise ServiceError(415, ErrorCode.UNSUPPORTED_MEDIA_TYPE, "This audio format is not supported.")
    data = read_capped(audio.file, c.settings.max_audio_bytes)
    if not data:
        raise ServiceError(422, ErrorCode.VALIDATION_ERROR, "The recording is empty.")
    transcript = c.language.transcribe(data, audio.filename or "audio", content_type).text
    return run_command(c, user, floorplan_id, instruction=transcript, expected_version=expected_version,
                       persist=not dry_run, transcript=transcript)


@router.post("/floorplans/{floorplan_id}/model/undo", response_model=CommandResponse)
def undo(floorplan_id: UUID, user: CurrentUser, session: Db, expected_version: int | None = None) -> CommandResponse:
    return move_head(session, user.id, user.id, floorplan_id, "UNDO", expected_version)


@router.post("/floorplans/{floorplan_id}/model/redo", response_model=CommandResponse)
def redo(floorplan_id: UUID, user: CurrentUser, session: Db, expected_version: int | None = None) -> CommandResponse:
    return move_head(session, user.id, user.id, floorplan_id, "REDO", expected_version)


@router.get("/floorplans/{floorplan_id}/history", response_model=History)
def history(floorplan_id: UUID, user: CurrentUser, session: Db) -> History:
    return load_history(session, user.id, floorplan_id)



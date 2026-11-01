"""Owner-scoped lookups and ORM → DTO mapping. Another user's resource is indistinguishable from a missing one."""

import logging
from uuid import UUID

from aec_contracts import Artifact, FloorPlan, Job, Project, StageReport
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .container import Container
from .errors import ServiceError, not_found
from .orm import ArtifactRow, FloorplanRow, JobRow, ProjectRow
from .storage import ARTIFACT_BUCKET, SOURCE_BUCKET

log = logging.getLogger("api.repo")


def get_project(session: Session, owner_id: UUID, project_id: UUID, lock: bool = False) -> ProjectRow:
    query = select(ProjectRow).where(ProjectRow.id == project_id, ProjectRow.owner_id == owner_id)
    row = session.scalars(query.with_for_update() if lock else query).first()
    if row is None:
        raise not_found()
    return row


def get_floorplan(session: Session, owner_id: UUID, floorplan_id: UUID, lock: bool = False) -> FloorplanRow:
    query = (select(FloorplanRow).join(ProjectRow, FloorplanRow.project_id == ProjectRow.id)
             .where(FloorplanRow.id == floorplan_id, ProjectRow.owner_id == owner_id))
    row = session.scalars(query.with_for_update(of=FloorplanRow) if lock else query).first()
    if row is None:
        raise not_found()
    return row


def job_dto(job: JobRow) -> Job:
    return Job(id=job.id, floorplan_id=job.floorplan_id, status=job.status,
               attempts=job.attempts, stages=[StageReport.model_validate(s) for s in job.stages],
               error_message=job.error_message, created_at=job.created_at,
               started_at=job.started_at, finished_at=job.finished_at)


def latest_job(session: Session, floorplan_id: UUID) -> JobRow | None:
    return session.scalars(select(JobRow).where(JobRow.floorplan_id == floorplan_id)
                           .order_by(JobRow.created_at.desc()).limit(1)).first()


def _signed(c: Container, bucket: str, keys: list[str]) -> dict[str, str]:
    """Best effort: a storage outage must not take listings down, since URLs are nullable there."""
    try:
        return c.blobs.signed_urls(bucket, keys) if keys else {}
    except ServiceError:
        return {}


def floorplan_dtos(c: Container, session: Session, rows: list[FloorplanRow]) -> list[FloorPlan]:
    jobs = session.scalars(select(JobRow).where(JobRow.floorplan_id.in_([r.id for r in rows]))
                           .distinct(JobRow.floorplan_id).order_by(JobRow.floorplan_id, JobRow.created_at.desc()))
    by_floorplan = {j.floorplan_id: j for j in jobs}
    urls = _signed(c, SOURCE_BUCKET, [r.storage_key for r in rows])
    out = []
    for r in rows:
        job = by_floorplan.get(r.id)
        out.append(FloorPlan(
            id=r.id, project_id=r.project_id, version=r.version, original_filename=r.original_filename,
            content_type=r.content_type, size_bytes=r.size_bytes, status=r.status,
            current_model_version=r.current_model_version, download_url=urls.get(r.storage_key),
            latest_job=job_dto(job) if job else None, warnings=r.warnings, created_at=r.created_at))
    return out


def project_dtos(c: Container, session: Session, rows: list[ProjectRow]) -> list[Project]:
    ids = [r.id for r in rows]
    counts = dict(session.execute(select(FloorplanRow.project_id, func.count()).where(FloorplanRow.project_id.in_(ids))
                                  .group_by(FloorplanRow.project_id)).tuples().all())
    thumbs = dict(session.execute(
        select(FloorplanRow.project_id, ArtifactRow.storage_key)
        .join(ArtifactRow, ArtifactRow.floorplan_id == FloorplanRow.id)
        .where(FloorplanRow.project_id.in_(ids), ArtifactRow.kind == "preprocessed")
        .distinct(FloorplanRow.project_id).order_by(FloorplanRow.project_id, ArtifactRow.created_at.desc())
    ).tuples().all())
    urls = _signed(c, ARTIFACT_BUCKET, list(thumbs.values()))
    return [Project(id=r.id, name=r.name, description=r.description, floorplan_count=counts.get(r.id, 0),
                    thumbnail_url=urls.get(thumbs.get(r.id, "")), created_at=r.created_at, updated_at=r.updated_at)
            for r in rows]


def artifact_dtos(c: Container, session: Session, floorplan_id: UUID) -> list[Artifact]:
    # Newest per kind: re-processing supersedes older artifacts.
    rows = list(session.scalars(select(ArtifactRow).where(ArtifactRow.floorplan_id == floorplan_id)
                                .distinct(ArtifactRow.kind).order_by(ArtifactRow.kind, ArtifactRow.created_at.desc())))
    urls = c.blobs.signed_urls(ARTIFACT_BUCKET, [r.storage_key for r in rows]) if rows else {}
    return [Artifact(id=r.id, job_id=r.job_id, kind=r.kind, content_type=r.content_type,
                     size_bytes=r.size_bytes, url=urls[r.storage_key]) for r in rows if r.storage_key in urls]

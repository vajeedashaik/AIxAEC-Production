"""The processing queue on Postgres. processing_jobs is the source of truth for job state."""

import base64
import logging
import threading
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from aec_contracts import AnalyzeResult, ErrorCode, FloorPlanModel, RoomType, Source, StageReport
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from .container import Container
from .errors import ServiceError
from .observability import request_id_var
from .orm import ArtifactRow, FloorplanRow, JobRow, ProjectRow
from .storage import ARTIFACT_BUCKET, SOURCE_BUCKET
from .versions import append_version

log = logging.getLogger("api.jobs")

HEARTBEAT_SECONDS = 15.0
MAX_CLASSIFY_LABELS = 200
GENERIC_FAILURE = "Processing failed unexpectedly. Please try again."
EXTENSIONS = {"image/png": "png", "application/json": "json"}

CLAIM_SQL = text("""
    UPDATE processing_jobs
    SET status = 'PROCESSING', attempts = attempts + 1, started_at = now(), heartbeat_at = now()
    WHERE id = (
        SELECT id FROM processing_jobs
        WHERE status = 'PENDING'
           OR (status = 'PROCESSING' AND heartbeat_at < now() - make_interval(secs => :stale))
        ORDER BY created_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING id, floorplan_id, attempts
""")


@dataclass(frozen=True)
class Claim:
    job_id: UUID
    floorplan_id: UUID
    attempts: int  # fencing token: a takeover bumps attempts, so a slow worker cannot commit over the new one


def enqueue(session: Session, floorplan: FloorplanRow, stale_seconds: int) -> JobRow:
    """Caller holds the floorplan row lock and commits."""
    alive_since = func.now() - func.make_interval(0, 0, 0, 0, 0, 0, stale_seconds)
    live = (JobRow.floorplan_id == floorplan.id, JobRow.status.in_(("PENDING", "PROCESSING")))
    session.execute(update(JobRow)
                    .where(*live, func.coalesce(JobRow.heartbeat_at, JobRow.created_at) < alive_since)
                    .values(status="FAILED", error_message="The worker stopped responding.", finished_at=func.now()))
    if session.scalar(select(JobRow.id).where(*live).limit(1)) is not None:
        raise ServiceError(409, ErrorCode.ALREADY_PROCESSING, "This plan is already being processed.")
    job = JobRow(floorplan_id=floorplan.id, stages=[], status="PENDING", attempts=0)
    session.add(job)
    floorplan.status = "PENDING"
    session.flush()
    return job


def claim_next(c: Container) -> Claim | None:
    with c.session_factory() as session:
        row = session.execute(CLAIM_SQL, {"stale": c.settings.processing_stale_seconds}).first()
        session.commit()
    if row is None:
        return None
    claim = Claim(row.id, row.floorplan_id, row.attempts)
    # Separate transaction: routes lock floorplan → job, so holding the job lock here could deadlock.
    with c.session_factory() as session:
        session.execute(update(FloorplanRow).where(FloorplanRow.id == claim.floorplan_id).values(status="PROCESSING"))
        session.commit()
    return claim


def _owned_job(session: Session, claim: Claim) -> JobRow | None:
    return session.scalars(select(JobRow).where(JobRow.id == claim.job_id, JobRow.attempts == claim.attempts,
                                                JobRow.status == "PROCESSING").with_for_update()).first()


def fail_job(c: Container, claim: Claim, message: str, stages: list[StageReport] | None = None,
             warnings: list[str] | None = None) -> None:
    with c.session_factory() as session:
        floorplan = session.get(FloorplanRow, claim.floorplan_id, with_for_update=True)
        job = _owned_job(session, claim)
        if floorplan is None or job is None:  # deleted, or another worker owns it now
            return
        job.status, job.error_message, job.finished_at = "FAILED", message[:500], func.now()
        if stages is not None:
            job.stages = [s.model_dump(mode="json") for s in stages]
        floorplan.status = "FAILED"
        floorplan.warnings = list(dict.fromkeys([*floorplan.warnings, *(warnings or [])]))
        session.commit()


def _classify_rooms(c: Container, model: FloorPlanModel) -> None:
    """Best effort: a failure leaves rooms UNKNOWN."""
    rooms = [r for r in model.rooms if r.room_type == RoomType.UNKNOWN and r.label_text]
    labels = list(dict.fromkeys(r.label_text for r in rooms if r.label_text))[:MAX_CLASSIFY_LABELS]
    if not labels:
        return
    try:
        results = c.language.classify(labels).results
    except ServiceError:
        log.warning("room classification unavailable")
        return
    if len(results) != len(labels):
        log.warning("room classification returned the wrong number of results")
        return
    by_label = dict(zip(labels, results, strict=True))
    for room in rooms:
        found = by_label.get(room.label_text or "")
        if found and found.room_type != RoomType.UNKNOWN:
            room.room_type, room.room_type_source = found.room_type, Source.INFERRED
            room.room_type_confidence = found.confidence


def _store_artifacts(c: Container, project_id: UUID, claim: Claim, result: AnalyzeResult) -> list[dict[str, Any]]:
    rows = []
    for artifact in result.artifacts:
        data = base64.b64decode(artifact.data_base64, validate=True)
        key = f"{project_id}/{claim.floorplan_id}/{claim.job_id}/{artifact.kind}.{EXTENSIONS[artifact.content_type]}"
        c.blobs.put(ARTIFACT_BUCKET, key, data, artifact.content_type)
        rows.append({"kind": artifact.kind, "storage_key": key, "content_type": artifact.content_type,
                     "size_bytes": len(data)})
    return rows


def _complete(c: Container, project_id: UUID, claim: Claim, result: AnalyzeResult, model: FloorPlanModel,
              artifacts: list[dict[str, Any]]) -> None:
    with c.session_factory() as session:
        floorplan = session.get(FloorplanRow, claim.floorplan_id, with_for_update=True)
        job = _owned_job(session, claim)
        if floorplan is None:
            c.blobs.delete_prefix(ARTIFACT_BUCKET, f"{project_id}/{claim.floorplan_id}/")
            return
        if job is None:
            log.warning("lost the job to another worker, dropping this result")
            return
        append_version(session, floorplan, model.model_dump(mode="json"), "PROCESSING", job_id=claim.job_id)
        session.add_all(ArtifactRow(floorplan_id=floorplan.id, job_id=claim.job_id, **row) for row in artifacts)
        job.status, job.finished_at = "COMPLETED", func.now()
        job.stages = [s.model_dump(mode="json") for s in result.stages]
        floorplan.status = "COMPLETED"
        floorplan.warnings = list(dict.fromkeys([*floorplan.warnings, *result.warnings]))
        session.commit()


def _run(c: Container, claim: Claim) -> None:
    with c.session_factory() as session:
        loaded = session.execute(
            select(FloorplanRow, ProjectRow.id).join(ProjectRow, FloorplanRow.project_id == ProjectRow.id)
            .where(FloorplanRow.id == claim.floorplan_id)).first()
    if loaded is None:
        return
    floorplan, project_id = loaded.tuple()
    source = c.blobs.get(SOURCE_BUCKET, floorplan.storage_key)
    result = c.vision.analyze(claim.floorplan_id, source, floorplan.original_filename, floorplan.content_type)
    if result.status == "FAILED" or result.model is None:
        fail_job(c, claim, result.error or GENERIC_FAILURE, result.stages, result.warnings)
        return
    if result.model.floorplan_id != claim.floorplan_id:
        raise ValueError("vision returned a model for another floorplan")
    _classify_rooms(c, result.model)
    artifacts = _store_artifacts(c, project_id, claim, result)
    _complete(c, project_id, claim, result, result.model, artifacts)


def _heartbeat(c: Container, claim: Claim, stop: threading.Event) -> None:
    while not stop.wait(HEARTBEAT_SECONDS):
        try:
            with c.session_factory() as session:
                session.execute(update(JobRow).where(JobRow.id == claim.job_id, JobRow.attempts == claim.attempts,
                                                     JobRow.status == "PROCESSING").values(heartbeat_at=func.now()))
                session.commit()
        except Exception:
            log.exception("heartbeat failed")  # keep beating: stale recovery is the backstop


def process_claim(c: Container, claim: Claim) -> None:
    """Never leaves a job stuck in PROCESSING: any exception ends in FAILED with a user-safe message."""
    token = request_id_var.set(f"job-{claim.job_id}")
    stop = threading.Event()
    beat = threading.Thread(target=_heartbeat, args=(c, claim, stop), daemon=True)
    beat.start()
    try:
        _run(c, claim)
    except ServiceError as exc:
        log.warning("job failed", extra={"fields": {"error": exc.message}})
        fail_job(c, claim, exc.message or GENERIC_FAILURE)
    except Exception:
        log.exception("job crashed")
        fail_job(c, claim, GENERIC_FAILURE)
    finally:
        stop.set()
        beat.join()
        request_id_var.reset(token)

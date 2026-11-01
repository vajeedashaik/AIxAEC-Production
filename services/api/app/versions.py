"""Append-only model versions and the HEAD pointer. Undo/redo copy no data, they only move HEAD."""

from typing import Any, Literal
from uuid import UUID

from aec_contracts import CommandResponse, EditLogEntry, ErrorCode, FloorPlanModel, History, VersionInfo
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .errors import ServiceError, model_not_ready, not_found, stale_model
from .orm import LIVE_STATUSES, EditRow, FloorplanRow, ModelRow
from .repo import get_floorplan

HISTORY_EDIT_LIMIT = 200


def require_head(floorplan: FloorplanRow) -> int:
    """HEAD is current_model_version, never max(version). No edits while a re-process is running."""
    head = floorplan.current_model_version
    if head is None or floorplan.status in LIVE_STATUSES:
        raise model_not_ready()
    return head


def version_row(session: Session, floorplan_id: UUID, version: int) -> ModelRow | None:
    return session.scalars(select(ModelRow).where(ModelRow.floorplan_id == floorplan_id,
                                                  ModelRow.version == version)).first()


def load_model(row: ModelRow) -> FloorPlanModel:
    return FloorPlanModel.model_validate(row.data)


def _swap_head(session: Session, floorplan: FloorplanRow, old: int | None, new: int) -> None:
    moved = session.execute(
        update(FloorplanRow)
        .where(FloorplanRow.id == floorplan.id, FloorplanRow.current_model_version.is_not_distinct_from(old))
        .values(current_model_version=new).returning(FloorplanRow.id)
    ).first()
    if moved is None:
        raise stale_model()


def append_version(session: Session, floorplan: FloorplanRow, data: dict[str, Any],
                   origin: Literal["PROCESSING", "EDIT"], job_id: UUID | None = None,
                   edit_id: UUID | None = None) -> int:
    """Caller holds the floorplan row lock. Anything after HEAD leaves the redo path but stays for audit."""
    head = floorplan.current_model_version
    if head is not None:
        session.execute(update(ModelRow).where(ModelRow.floorplan_id == floorplan.id, ModelRow.version > head,
                                               ModelRow.discarded.is_(False)).values(discarded=True))
    latest = session.scalar(select(func.coalesce(func.max(ModelRow.version), 0))
                            .where(ModelRow.floorplan_id == floorplan.id)) or 0
    version = latest + 1
    session.add(ModelRow(floorplan_id=floorplan.id, job_id=job_id, edit_id=edit_id, version=version, origin=origin,
                         parent_version=head, data=data))
    session.flush()
    _swap_head(session, floorplan, head, version)
    return version


def commit_or_stale(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise stale_model() from exc


def _child(session: Session, floorplan_id: UUID, version: int) -> int | None:
    return session.scalar(select(ModelRow.version)
                          .where(ModelRow.floorplan_id == floorplan_id, ModelRow.parent_version == version,
                                 ModelRow.discarded.is_(False)).order_by(ModelRow.version.desc()).limit(1))


def move_head(session: Session, owner_id: UUID, user_id: UUID, floorplan_id: UUID,
              direction: Literal["UNDO", "REDO"], expected_version: int | None) -> CommandResponse:
    floorplan = get_floorplan(session, owner_id, floorplan_id, lock=True)
    head = require_head(floorplan)
    if expected_version is not None and expected_version != head:
        raise stale_model(head)
    head_row = version_row(session, floorplan_id, head)
    if head_row is None:
        raise not_found()
    target = head_row.parent_version if direction == "UNDO" else _child(session, floorplan_id, head)
    if target is None:
        raise ServiceError(409, ErrorCode.CONFLICT, f"There is nothing to {direction.lower()}.")
    target_row = version_row(session, floorplan_id, target)
    if target_row is None:
        raise not_found()
    edit = EditRow(floorplan_id=floorplan_id, user_id=user_id, status=direction, parent_version=head,
                   result_version=target)
    session.add(edit)
    session.flush()
    _swap_head(session, floorplan, head, target)
    commit_or_stale(session)
    verb = "Undid" if direction == "UNDO" else "Redid"
    return CommandResponse(status="APPLIED", version=target, model=load_model(target_row), edit_id=edit.id,
                           summary=f"{verb} the change (now at version {target}).")


def history(session: Session, owner_id: UUID, floorplan_id: UUID) -> History:
    floorplan = get_floorplan(session, owner_id, floorplan_id)
    head = floorplan.current_model_version
    columns = (ModelRow.version, ModelRow.origin, ModelRow.parent_version, ModelRow.discarded, ModelRow.created_at,
               ModelRow.edit_id)  # data is left out: a model document can be megabytes
    rows = session.execute(select(*columns).where(ModelRow.floorplan_id == floorplan_id)
                           .order_by(ModelRow.version)).all()
    head_row = next((r for r in rows if r.version == head), None)
    # shortcut: only the newest edits are returned, add pagination if the UI ever needs the full log.
    edits = session.scalars(select(EditRow).where(EditRow.floorplan_id == floorplan_id)
                            .order_by(EditRow.created_at.desc()).limit(HISTORY_EDIT_LIMIT)).all()
    return History(
        head_version=head,
        can_undo=head_row is not None and head_row.parent_version is not None,
        can_redo=any(r.parent_version == head and not r.discarded for r in rows) if head is not None else False,
        versions=[VersionInfo(version=r.version, origin=r.origin, parent_version=r.parent_version,
                              discarded=r.discarded, is_head=r.version == head, created_at=r.created_at,
                              edit_id=r.edit_id) for r in rows],
        edits=[EditLogEntry(id=e.id, instruction=e.instruction, operation=e.operation,
                            status=e.status, stage=e.stage,
                            error=e.error, parent_version=e.parent_version, result_version=e.result_version,
                            created_at=e.created_at) for e in edits],
    )

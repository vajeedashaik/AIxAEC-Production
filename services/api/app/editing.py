"""Edit orchestration: HEAD → parse (language) → execute (geometry) → persist. No transaction spans an HTTP call."""

import logging
from typing import Any, Literal
from uuid import UUID

from aec_contracts import (
    Candidate,
    CommandResponse,
    ExecuteApplied,
    ExecuteClarification,
    ExecuteRejected,
    FloorPlanModel,
    Me,
)
from aec_contracts.commands import COMMAND_ADAPTER
from aec_contracts.errors import ErrorCode
from pydantic import ValidationError

from .container import Container
from .errors import ServiceError, not_found, stale_model
from .orm import EditRow
from .repo import get_floorplan
from .versions import append_version, commit_or_stale, load_model, require_head, version_row

log = logging.getLogger("api.editing")

PARSE_UNAVAILABLE = "The command assistant is unavailable right now. Your plan was not changed."
PARSE_UNKNOWN = "Sorry, I didn't understand that as a plan edit."
Stage = Literal["parse", "schema", "entity_resolution", "semantic_validation", "geometry", "constraints"]


def _operation(command: dict[str, Any] | None) -> str | None:
    operation = (command or {}).get("operation")
    return operation[:60] if isinstance(operation, str) else None  # raw commands are untrusted


def _load_head(c: Container, user: Me, floorplan_id: UUID, expected_version: int | None) -> tuple[int, FloorPlanModel]:
    with c.session_factory() as session:
        floorplan = get_floorplan(session, user.id, floorplan_id)
        head = require_head(floorplan)
        if expected_version is not None and expected_version != head:
            raise stale_model(head)
        row = version_row(session, floorplan_id, head)
        if row is None:
            raise not_found()
        return head, load_model(row)


def _audit(c: Container, user: Me, floorplan_id: UUID, status: Literal["REJECTED", "CLARIFICATION"], *,
           base: int, instruction: str | None, command: dict[str, Any] | None, stage: Stage | None = None,
           error: str | None = None, clarification: dict[str, Any] | None = None) -> UUID:
    with c.session_factory() as session:
        edit = EditRow(floorplan_id=floorplan_id, user_id=user.id, instruction=instruction, command=command,
                       operation=_operation(command), status=status, stage=stage,
                       error=error[:500] if error else None, clarification=clarification, parent_version=base)
        session.add(edit)
        session.commit()
        return edit.id


def _reject(c: Container, user: Me, floorplan_id: UUID, persist: bool, base: int, instruction: str | None,
            command: dict[str, Any] | None, stage: Stage, detail: str, transcript: str | None) -> CommandResponse:
    edit_id = None
    if persist:
        edit_id = _audit(c, user, floorplan_id, "REJECTED", base=base, instruction=instruction, command=command,
                         stage=stage, error=detail)
    return CommandResponse(status="REJECTED", version=base, stage=stage, detail=detail, transcript=transcript,
                           edit_id=edit_id)


def _parse(c: Container, model: FloorPlanModel, instruction: str) -> tuple[dict[str, Any] | None, str | None]:
    """Returns (raw command, rejection detail). The command stays untrusted until geometry validates it."""
    brief = c.geometry.brief(model)  # geometry down is an outage (503), not a parse rejection
    try:
        parsed = c.language.parse(instruction, brief)
    except ServiceError:
        return None, PARSE_UNAVAILABLE
    if parsed.status == "ERROR":
        return None, PARSE_UNAVAILABLE
    if parsed.status == "UNKNOWN" or parsed.command is None:
        return None, parsed.detail or PARSE_UNKNOWN
    return parsed.command, None


def _commit_applied(c: Container, user: Me, floorplan_id: UUID, base: int, instruction: str | None,
                    result: ExecuteApplied) -> tuple[int, UUID]:
    resolved = result.command.model_dump(mode="json")
    with c.session_factory() as session:
        floorplan = get_floorplan(session, user.id, floorplan_id, lock=True)
        if floorplan.current_model_version != base:
            raise stale_model(floorplan.current_model_version)
        edit = EditRow(floorplan_id=floorplan_id, user_id=user.id, instruction=instruction, command=resolved,
                       operation=result.command.operation, status="APPLIED", parent_version=base)
        session.add(edit)
        session.flush()
        version = append_version(session, floorplan, result.model.model_dump(mode="json"), "EDIT", edit_id=edit.id)
        edit.result_version = version
        commit_or_stale(session)
        return version, edit.id


def run_command(c: Container, user: Me, floorplan_id: UUID, *, instruction: str | None = None,
                command: dict[str, Any] | None = None, expected_version: int | None = None,
                persist: bool, transcript: str | None = None) -> CommandResponse:
    """persist=False is interpret: never persisted, never audited."""
    base, model = _load_head(c, user, floorplan_id, expected_version)

    def reject(stage: Stage, detail: str, raw: dict[str, Any] | None = None) -> CommandResponse:
        return _reject(c, user, floorplan_id, persist, base, instruction, raw, stage, detail, transcript)

    if instruction is not None:
        if not instruction.strip():
            return reject("parse", "I didn't catch an instruction. Please try again.")
        command, detail = _parse(c, model, instruction)
        if detail is not None or command is None:
            return reject("parse", detail or PARSE_UNKNOWN)
    assert command is not None  # CommandRequest guarantees exactly one of instruction / command

    result = c.geometry.execute(model, command, dry_run=not persist)
    if isinstance(result, ExecuteRejected):
        return reject(result.stage, result.detail, command)
    if isinstance(result, ExecuteClarification):
        return _clarify(c, user, floorplan_id, persist, base, instruction, command, result, transcript)
    if result.model.floorplan_id != floorplan_id:
        log.error("geometry returned a model for another floorplan")
        raise ServiceError(502, ErrorCode.UPSTREAM_UNAVAILABLE, "The geometry service is unavailable.")
    if not persist:
        return CommandResponse(status="PREVIEW", version=base, model=result.model, changes=result.changes,
                               command=result.command, summary=result.summary, transcript=transcript)
    version, edit_id = _commit_applied(c, user, floorplan_id, base, instruction, result)
    return CommandResponse(status="APPLIED", version=version, model=result.model, changes=result.changes,
                           command=result.command, summary=result.summary, transcript=transcript, edit_id=edit_id)


def _clarify(c: Container, user: Me, floorplan_id: UUID, persist: bool, base: int, instruction: str | None,
             command: dict[str, Any], result: ExecuteClarification, transcript: str | None) -> CommandResponse:
    candidates: list[Candidate] = result.candidates
    edit_id = None
    if persist:
        clarification = {"question": result.question, "candidates": [x.model_dump(mode="json") for x in candidates]}
        edit_id = _audit(c, user, floorplan_id, "CLARIFICATION", base=base, instruction=instruction, command=command,
                         clarification=clarification)
    # The unresolved command comes back so the client can re-send it with the picked target_id.
    # Geometry passed its schema stage, so this validates; if it somehow doesn't, the client asks to rephrase.
    try:
        parsed = COMMAND_ADAPTER.validate_python(command)
    except ValidationError:
        parsed = None
    return CommandResponse(status="CLARIFICATION", version=base, question=result.question, candidates=candidates,
                           command=parsed, transcript=transcript, edit_id=edit_id)

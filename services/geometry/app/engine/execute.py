"""The execute pipeline: schema → entity_resolution → semantic_validation → geometry → constraints → summary."""

from typing import Any

from aec_contracts import AddWall, ExecuteApplied, ExecuteClarification, ExecuteRejected, ExecuteResult, FloorPlanModel
from aec_contracts.commands import ENGINE_COMMAND_ADAPTER, EngineCommand
from pydantic import ValidationError

from .changes import build_changes
from .constraints import validate_model
from .errors import ClarificationNeeded, ConstraintViolation, EngineError, SchemaError
from .geom import to_px
from .operations import apply_operation
from .resolve import resolve_target
from .semantic import check_semantics
from .summary import build_summary


def _schema_sentence(exc: ValidationError) -> str:
    first = exc.errors(include_url=False, include_input=False)[0]
    if first["type"] == "union_tag_not_found":
        return "The command has no operation."
    if first["type"] == "union_tag_invalid":
        return "The command's operation isn't one I know."
    # The union tag leads the loc ("MOVE_WALL", "distance", "value"): the operation isn't part of the field's name.
    field = ".".join(str(part) for part in first["loc"][1:])
    message = first["msg"].removeprefix("Value error, ").rstrip(".")
    if first["type"] == "missing":
        return f"The command is missing '{field}'."
    return f"The command's '{field}' is invalid: {message}." if field else f"The command is invalid: {message}."


def _parse_command(raw: dict[str, Any]) -> EngineCommand:
    try:
        return ENGINE_COMMAND_ADAPTER.validate_python(raw)
    except ValidationError as exc:
        raise SchemaError(_schema_sentence(exc)) from exc


def _revalidate(candidate: FloorPlanModel) -> FloorPlanModel:
    try:
        return FloorPlanModel.model_validate(candidate.model_dump())
    except ValidationError as exc:
        first = exc.errors(include_url=False, include_input=False)[0]
        if "must differ" in first["msg"]:
            raise ConstraintViolation("That would collapse a connected wall to nothing; try a shorter move.") from exc
        if first["loc"][-1] in ("x", "y"):
            raise ConstraintViolation("That would push part of the plan outside the image.") from exc
        raise ConstraintViolation(f"That edit would produce an invalid plan: {first['msg']}.") from exc


def _run(model: FloorPlanModel, raw: dict[str, Any]) -> ExecuteApplied:
    command = _parse_command(raw)
    for field in ("distance", "width"):  # mm on an unscaled plan fails before we ask "which wall?"
        if (value := getattr(command, field, None)) is not None:
            to_px(value, model.coordinate_system)
    if not isinstance(command, AddWall):
        target = resolve_target(model, command, command.operation)
        command = command.model_copy(update={"target_id": target, "target_query": None})
    check_semantics(model, command)
    candidate = _revalidate(apply_operation(model, command))
    issues = validate_model(candidate, before=model)
    if issues:
        raise ConstraintViolation(issues[0].message)
    return ExecuteApplied(status="APPLIED", command=command, model=candidate,
                          changes=build_changes(model, candidate),
                          summary=build_summary(model, candidate, command))


def execute(model: FloorPlanModel, raw_command: dict[str, Any], dry_run: bool = False) -> ExecuteResult:
    """`dry_run` changes nothing here: it exists for API semantics and logging. The caller decides what to persist."""
    try:
        return _run(model, raw_command)
    except ClarificationNeeded as asked:
        return ExecuteClarification(status="CLARIFICATION", question=asked.question, candidates=asked.candidates)
    except EngineError as refused:
        return ExecuteRejected(status="REJECTED", stage=refused.stage, detail=refused.detail)

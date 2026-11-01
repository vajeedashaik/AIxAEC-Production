from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from aec_contracts import ExecuteApplied, ExecuteClarification, ExecuteRejected, ExecuteResult, FloorPlanModel

from app.engine.execute import execute

FIXTURES = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "fixtures"


def load(name: str) -> FloorPlanModel:
    return FloorPlanModel.model_validate_json((FIXTURES / f"{name}.model.json").read_text(encoding="utf-8"))


@pytest.fixture
def apartment() -> FloorPlanModel:
    return load("apartment")


@pytest.fixture
def unscaled() -> FloorPlanModel:
    return load("apartment.unscaled")


@pytest.fixture
def two_room() -> FloorPlanModel:
    return load("two_room")


def el(items: Any, prefix: str) -> Any:
    """Element by id prefix, so tests read like the fixture ids."""
    return next(i for i in items if str(i.id).startswith(prefix))


def wid(model: FloorPlanModel, prefix: str) -> UUID:
    return el(model.walls, prefix).id  # type: ignore[no-any-return]


def room(model: FloorPlanModel, label: str) -> Any:
    return next(r for r in model.rooms if r.label_text == label)


def run(model: FloorPlanModel, **command: Any) -> ExecuteResult:
    """Every test run also proves determinism and that the input model is left alone."""
    before = model.model_dump_json()
    first = execute(model, command)
    second = execute(model, command)
    assert first.model_dump_json() == second.model_dump_json()
    assert model.model_dump_json() == before
    return first


def applied(model: FloorPlanModel, **command: Any) -> ExecuteApplied:
    result = run(model, **command)
    assert isinstance(result, ExecuteApplied), result
    FloorPlanModel.model_validate(result.model.model_dump())
    return result


def rejected(model: FloorPlanModel, stage: str, **command: Any) -> str:
    result = run(model, **command)
    assert isinstance(result, ExecuteRejected), result
    assert result.stage == stage, result
    assert "\n" not in result.detail
    return result.detail


def clarified(model: FloorPlanModel, **command: Any) -> ExecuteClarification:
    result = run(model, **command)
    assert isinstance(result, ExecuteClarification), result
    assert len(result.candidates) >= 2
    return result


def pts(polygon: Any) -> list[tuple[float, float]]:
    return [(p.x, p.y) for p in polygon]

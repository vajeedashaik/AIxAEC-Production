import copy
from typing import Any

import pytest
from conftest import FIXTURES, load
from pydantic import BaseModel, TypeAdapter, ValidationError

from aec_contracts import (
    EXECUTE_RESULT_ADAPTER,
    HTTP_STATUS,
    STAGE_NAMES,
    AnalyzeResult,
    Artifact,
    ClassifyRoomsRequest,
    CommandResponse,
    ErrorCode,
    ErrorEnvelope,
    ExecuteRequest,
    FloorPlan,
    History,
    Job,
    Me,
    ModelEnvelope,
    Page,
    ParseRequest,
    PlanBrief,
    Project,
    TranscribeResult,
)

API_MODELS: dict[str, Any] = {
    "me": Me, "projects.list": Page[Project], "projects.create": Project, "projects.get": Project,
    "projects.update": Project, "floorplans.list": list[FloorPlan], "floorplans.upload": FloorPlan,
    "floorplans.get": FloorPlan, "floorplans.process": Job, "floorplans.job": Job,
    "floorplans.model": ModelEnvelope, "floorplans.artifacts": list[Artifact],
    "commands.interpret": CommandResponse, "commands.apply": CommandResponse,
    "commands.clarification": CommandResponse, "commands.rejected": CommandResponse,
    "commands.voice": CommandResponse, "model.undo": CommandResponse, "model.redo": CommandResponse,
    "history": History, "error.stale_model": ErrorEnvelope,
}


def test_every_api_fixture_has_a_model() -> None:
    names = {p.stem for p in (FIXTURES / "api").glob("*.json")}
    assert names == set(API_MODELS) | {"healthz"}


@pytest.mark.parametrize("name", sorted(API_MODELS))
def test_api_fixture_validates(name: str) -> None:
    raw = load(f"api/{name}.json")
    adapter: TypeAdapter[Any] = TypeAdapter(API_MODELS[name])
    value = adapter.validate_python(raw)
    assert adapter.validate_json(adapter.dump_json(value)) == value


def test_api_fixture_statuses() -> None:
    assert load("api/commands.interpret.json")["status"] == "PREVIEW"
    assert load("api/commands.apply.json")["status"] == "APPLIED"
    assert load("api/commands.voice.json")["transcript"]
    assert load("api/floorplans.upload.json")["latest_job"]["status"] == "PENDING"


def _stages(status: str = "ok") -> list[dict[str, Any]]:
    return [{"name": n, "status": status, "duration_ms": 1} for n in STAGE_NAMES]


def test_analyze_result_consistency(apartment: dict[str, Any]) -> None:
    AnalyzeResult.model_validate({"status": "COMPLETED", "model": apartment, "stages": _stages()})
    AnalyzeResult.model_validate({"status": "FAILED", "model": None, "stages": _stages("skipped"),
                                  "error": "Processing failed at stage 'wall_detection'."})
    with pytest.raises(ValidationError, match="null iff"):
        AnalyzeResult.model_validate({"status": "FAILED", "model": apartment, "stages": _stages()})
    with pytest.raises(ValidationError, match="null iff"):
        AnalyzeResult.model_validate({"status": "COMPLETED", "model": None, "stages": _stages()})
    with pytest.raises(ValidationError, match="in order"):
        AnalyzeResult.model_validate({"status": "COMPLETED", "model": apartment, "stages": _stages()[::-1]})


def test_execute_result_union(apartment: dict[str, Any]) -> None:
    applied = load("api/commands.apply.json")
    r = EXECUTE_RESULT_ADAPTER.validate_python({"status": "APPLIED", "command": applied["command"],
                                                "model": applied["model"], "changes": applied["changes"],
                                                "summary": applied["summary"]})
    assert r.status == "APPLIED"
    cands = load("api/commands.clarification.json")["candidates"]
    assert EXECUTE_RESULT_ADAPTER.validate_python(
        {"status": "CLARIFICATION", "question": "Which?", "candidates": cands}).status == "CLARIFICATION"
    with pytest.raises(ValidationError):  # clarification needs >= 2 candidates
        EXECUTE_RESULT_ADAPTER.validate_python({"status": "CLARIFICATION", "question": "?", "candidates": cands[:1]})
    with pytest.raises(ValidationError):
        EXECUTE_RESULT_ADAPTER.validate_python({"status": "REJECTED", "stage": "vibes", "detail": "x"})
    ExecuteRequest.model_validate({"model": apartment, "command": {"anything": "goes here"}})


def test_language_bounds() -> None:
    brief = PlanBrief.model_validate({"rooms": [], "counts": load("api/floorplans.model.json")["summary"],
                                      "has_scale": False, "image_width": 10, "image_height": 10})
    with pytest.raises(ValidationError):
        ParseRequest(instruction="x" * 501, brief=brief)
    with pytest.raises(ValidationError):
        ClassifyRoomsRequest(labels=["a"] * 201)
    with pytest.raises(ValidationError):
        TranscribeResult(text="x" * 501, language="en", duration_ms=1, provider="stub")


def test_plan_brief_has_no_ids_or_coordinates() -> None:
    def keys(schema: dict[str, Any]) -> set[str]:
        out: set[str] = set()
        for d in [schema, *schema.get("$defs", {}).values()]:
            out |= set(d.get("properties", {}))
        return out
    assert not keys(PlanBrief.model_json_schema()) & {"id", "x", "y", "polygon", "bbox", "start", "end"}


def test_error_envelope() -> None:
    assert set(HTTP_STATUS) == set(ErrorCode)
    env = ErrorEnvelope.of(ErrorCode.STALE_MODEL, "changed", head_version=2)
    assert env.model_dump(mode="json") == {"error": {"code": "stale_model", "message": "changed",
                                                     "details": {"head_version": 2}}}
    ErrorEnvelope.model_validate({"error": {"code": "unauthorized"}})
    with pytest.raises(ValidationError):
        ErrorEnvelope.model_validate({"error": {"code": "teapot"}})


@pytest.mark.parametrize("name", sorted(API_MODELS))
def test_public_dtos_forbid_extra(name: str) -> None:
    raw = load(f"api/{name}.json")
    bad = copy.deepcopy(raw)
    (bad[0] if isinstance(bad, list) else bad)["unexpected"] = True
    with pytest.raises(ValidationError, match="Extra inputs"):
        TypeAdapter(API_MODELS[name]).validate_python(bad)


def test_strict_base_everywhere() -> None:
    import aec_contracts as c
    for name in c.__all__:
        obj = getattr(c, name)
        if isinstance(obj, type) and issubclass(obj, BaseModel):
            assert obj.model_config.get("extra") == "forbid", name

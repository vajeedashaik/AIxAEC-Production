import json
import statistics
import time
from pathlib import Path
from typing import Any

import pytest
from aec_contracts import EXECUTE_RESULT_ADAPTER, Insights, PlanBrief, ValidateResult
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from app.config import Settings
from app.engine.execute import execute
from app.main import create_app

from .conftest import load

TOKEN = "test-token"
HEADERS = {"X-Internal-Token": TOKEN}
FIXTURES = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "fixtures"
MODEL = json.loads((FIXTURES / "apartment.model.json").read_text(encoding="utf-8"))
client = TestClient(create_app(Settings(environment="test", internal_service_token=TOKEN)))  # type: ignore[arg-type]

ROUTES = [
    ("/v1/commands/execute", {"model": MODEL, "command": {"operation": "DELETE_WALL", "target_query": "x"}}),
    ("/v1/models/insights", {"model": MODEL}),
    ("/v1/models/brief", {"model": MODEL}),
    ("/v1/models/validate", {"model": MODEL}),
]


@pytest.mark.parametrize("path,body", ROUTES)
def test_requires_internal_token(path: str, body: dict[str, object]) -> None:
    for headers in ({}, {"X-Internal-Token": "wrong"}):
        r = client.post(path, json=body, headers=headers)
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "unauthorized"


def post(path: str, **body: Any) -> Any:
    r = client.post(path, json={"model": MODEL, **body}, headers=HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("command,status", [
    ({"operation": "MOVE_WALL", "target_query": "wall between kitchen and living", "direction": "LEFT",
      "distance": {"value": 300, "unit": "mm"}}, "APPLIED"),
    ({"operation": "MOVE_WALL", "target_query": "kitchen wall", "direction": "LEFT",
      "distance": {"value": 300, "unit": "mm"}}, "CLARIFICATION"),
    ({"operation": "DELETE_WALL", "target_query": "north wall of living"}, "REJECTED"),
    ({"operation": "NOPE"}, "REJECTED"),
    ({}, "REJECTED"),
])
def test_execute_always_answers_200_with_a_union_member(command: dict[str, Any], status: str) -> None:
    body = post("/v1/commands/execute", command=command)
    assert EXECUTE_RESULT_ADAPTER.validate_python(body).status == status


def test_dry_run_changes_nothing_in_the_computation() -> None:
    command = {"operation": "SET_SCALE", "target_query": "north wall of kitchen", "length_mm": 3600}
    assert post("/v1/commands/execute", command=command, dry_run=True) == post("/v1/commands/execute", command=command)


FINITE = st.floats(allow_nan=False, allow_infinity=False)
JSON = st.recursive(st.none() | st.booleans() | st.integers() | FINITE | st.text(max_size=20),
                    lambda c: st.lists(c, max_size=3) | st.dictionaries(st.text(max_size=8), c, max_size=3),
                    max_leaves=6)
OPERATION = st.sampled_from(["MOVE_WALL", "ADD_WALL", "DELETE_WALL", "RESIZE_ROOM", "ADD_DOOR", "ADD_WINDOW",
                             "DELETE_DOOR", "DELETE_WINDOW", "RENAME_ROOM", "SET_SCALE", "NOPE"])
QUERY = st.text(max_size=40) | st.sampled_from(["kitchen", "north wall of hall", "door", "wall between a and b"])
POINT = st.fixed_dictionaries({"x": FINITE, "y": FINITE})
FIELDS = {"target_query": QUERY, "direction": st.sampled_from(["LEFT", "UP", "x"]), "name": st.text(max_size=90),
          "distance": st.fixed_dictionaries({"value": FINITE, "unit": st.sampled_from(["px", "mm", "ft"])}),
          "mode": st.sampled_from(["EXPAND", "CONTRACT"]), "length_mm": FINITE, "position": FINITE,
          "start": POINT, "end": POINT, "thickness_px": FINITE, "extra": JSON}


@settings(max_examples=150, deadline=None, database=None)
@given(st.fixed_dictionaries({"operation": OPERATION}, optional=FIELDS), st.dictionaries(st.text(max_size=8), JSON))
def test_any_command_gets_a_result_member(command: dict[str, Any], junk: dict[str, Any]) -> None:
    model = load("apartment")
    for raw in (command, junk):
        assert execute(model, raw).status in ("APPLIED", "CLARIFICATION", "REJECTED")


def test_insights_brief_validate_routes() -> None:
    assert Insights.model_validate(post("/v1/models/insights")).counts.rooms == 5
    assert PlanBrief.model_validate(post("/v1/models/brief")).has_scale
    assert ValidateResult.model_validate(post("/v1/models/validate")).valid


def test_validate_reports_issues() -> None:
    broken = json.loads(json.dumps(MODEL))
    polygon = broken["rooms"][0]["polygon"]
    polygon[1], polygon[2] = polygon[2], polygon[1]
    r = client.post("/v1/models/validate", json={"model": broken}, headers=HEADERS).json()
    assert r["valid"] is False
    assert r["issues"][0]["code"] == "room_invalid" and r["issues"][0]["element_id"] == broken["rooms"][0]["id"]


def test_envelope_is_validated() -> None:
    for path in ("/v1/models/brief", "/v1/commands/execute"):
        r = client.post(path, json={"model": {"nope": 1}}, headers=HEADERS)
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "validation_error"


def test_openapi_shows_contract() -> None:
    spec = client.get("/openapi.json").json()
    assert {p for p, _ in ROUTES} <= set(spec["paths"])
    assert {"ExecuteApplied", "Insights", "PlanBrief", "ValidateResult"} <= set(spec["components"]["schemas"])


def test_execute_budget() -> None:
    model = load("apartment")
    command = {"operation": "MOVE_WALL", "target_query": "wall between kitchen and living", "direction": "LEFT",
               "distance": {"value": 300, "unit": "mm"}}
    runs = []
    for _ in range(9):
        start = time.perf_counter()
        execute(model, command)
        runs.append(time.perf_counter() - start)
    assert statistics.median(runs) < 0.05

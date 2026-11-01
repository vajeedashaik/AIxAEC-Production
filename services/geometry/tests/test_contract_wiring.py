import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

TOKEN = "test-token"
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


@pytest.mark.parametrize("path,body", ROUTES)
def test_stub_returns_501(path: str, body: dict[str, object]) -> None:
    r = client.post(path, json=body, headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 501
    assert r.json()["error"] == {"code": "internal_error", "message": "not implemented", "details": {}}


def test_envelope_is_validated() -> None:
    r = client.post("/v1/models/brief", json={"model": {"nope": 1}}, headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_openapi_shows_contract() -> None:
    spec = client.get("/openapi.json").json()
    assert {p for p, _ in ROUTES} <= set(spec["paths"])
    assert {"ExecuteApplied", "Insights", "PlanBrief", "ValidateResult"} <= set(spec["components"]["schemas"])

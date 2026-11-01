import uuid

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

TOKEN = "test-token"
client = TestClient(create_app(Settings(environment="test", internal_service_token=TOKEN)))  # type: ignore[arg-type]
FORM = {"floorplan_id": str(uuid.uuid4())}
FILES = {"file": ("plan.png", b"\x89PNG\r\n\x1a\n", "image/png")}


def test_analyze_requires_internal_token() -> None:
    for headers in ({}, {"X-Internal-Token": "wrong"}):
        r = client.post("/v1/analyze", data=FORM, files=FILES, headers=headers)
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "unauthorized"


def test_analyze_stub_returns_501() -> None:
    r = client.post("/v1/analyze", data=FORM, files=FILES, headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 501
    assert r.json() == {"error": {"code": "internal_error", "message": "not implemented", "details": {}}}


def test_analyze_validates_multipart() -> None:
    r = client.post("/v1/analyze", data={"floorplan_id": "nope"}, files=FILES, headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_openapi_shows_contract() -> None:
    spec = client.get("/openapi.json").json()
    assert "/v1/analyze" in spec["paths"]
    assert "AnalyzeResult" in spec["components"]["schemas"]

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

TOKEN = "test-token"
client = TestClient(create_app(Settings(environment="test", internal_service_token=TOKEN)))  # type: ignore[arg-type]
COUNTS = {k: 0 for k in ("walls", "doors", "windows", "columns", "stairs", "furniture", "dimensions", "rooms")}
BRIEF = {"rooms": [], "counts": COUNTS, "has_scale": False, "image_width": 10, "image_height": 10}

ROUTES: list[tuple[str, dict[str, Any]]] = [
    ("/v1/commands/parse", {"json": {"instruction": "delete the kitchen door", "brief": BRIEF}}),
    ("/v1/rooms/classify", {"json": {"labels": ["KITCHEN"]}}),
    ("/v1/speech/transcribe", {"files": {"audio": ("a.wav", b"RIFF", "audio/wav")}, "data": {"language": "en"}}),
]


@pytest.mark.parametrize("path,kwargs", ROUTES)
def test_requires_internal_token(path: str, kwargs: dict[str, Any]) -> None:
    for headers in ({}, {"X-Internal-Token": "wrong"}):
        r = client.post(path, headers=headers, **kwargs)
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("path,kwargs", ROUTES)
def test_stub_returns_501(path: str, kwargs: dict[str, Any]) -> None:
    r = client.post(path, headers={"X-Internal-Token": TOKEN}, **kwargs)
    assert r.status_code == 501
    assert r.json()["error"]["message"] == "not implemented"


def test_parse_request_is_validated() -> None:
    r = client.post("/v1/commands/parse", json={"instruction": "", "brief": BRIEF}, headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 422


def test_openapi_shows_contract() -> None:
    spec = client.get("/openapi.json").json()
    assert {p for p, _ in ROUTES} <= set(spec["paths"])
    assert {"ParseResult", "ClassifyRoomsResult", "TranscribeResult"} <= set(spec["components"]["schemas"])

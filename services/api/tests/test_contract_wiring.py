import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

client = TestClient(create_app(Settings(environment="test")))
P, F = uuid.uuid4(), uuid.uuid4()
AUTH = {"Authorization": "Bearer test-session-token"}
CMD = {"json": {"instruction": "move the kitchen wall 300 mm left"}}

ROUTES: list[tuple[str, str, dict[str, Any]]] = [
    ("GET", "/v1/me", {}),
    ("GET", "/v1/projects?limit=20&offset=0", {}),
    ("POST", "/v1/projects", {"json": {"name": "Flat"}}),
    ("GET", f"/v1/projects/{P}", {}),
    ("PATCH", f"/v1/projects/{P}", {"json": {"name": "Flat 2"}}),
    ("DELETE", f"/v1/projects/{P}", {}),
    ("GET", f"/v1/projects/{P}/floorplans", {}),
    ("POST", f"/v1/projects/{P}/floorplans", {"files": {"file": ("a.png", b"\x89PNG", "image/png")}}),
    ("GET", f"/v1/floorplans/{F}", {}),
    ("DELETE", f"/v1/floorplans/{F}", {}),
    ("POST", f"/v1/floorplans/{F}/process", {}),
    ("GET", f"/v1/floorplans/{F}/job", {}),
    ("GET", f"/v1/floorplans/{F}/model?version=1", {}),
    ("GET", f"/v1/floorplans/{F}/artifacts", {}),
    ("POST", f"/v1/floorplans/{F}/commands/interpret", CMD),
    ("POST", f"/v1/floorplans/{F}/commands", CMD),
    ("POST", f"/v1/floorplans/{F}/commands/voice", {"files": {"audio": ("a.webm", b"x", "audio/webm")}}),
    ("POST", f"/v1/floorplans/{F}/model/undo?expected_version=2", {}),
    ("POST", f"/v1/floorplans/{F}/model/redo?expected_version=1", {}),
    ("GET", f"/v1/floorplans/{F}/history", {}),
]


def test_every_contract_route_is_registered() -> None:
    assert len(ROUTES) == 20
    paths = client.get("/openapi.json").json()["paths"]
    assert len([m for p, ops in paths.items() if p.startswith("/v1") for m in ops]) == len(ROUTES)


@pytest.mark.parametrize("method,path,kwargs", ROUTES, ids=lambda v: v if isinstance(v, str) else "")
def test_requires_bearer(method: str, path: str, kwargs: dict[str, Any]) -> None:
    for headers in ({}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer "}):
        r = client.request(method, path, headers=headers, **kwargs)
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("method,path,kwargs", ROUTES, ids=lambda v: v if isinstance(v, str) else "")
def test_stub_returns_501(method: str, path: str, kwargs: dict[str, Any]) -> None:
    r = client.request(method, path, headers=AUTH, **kwargs)
    assert r.status_code == 501
    assert r.json()["error"] == {"code": "internal_error", "message": "not implemented", "details": {}}


def test_command_request_exactly_one_is_enforced() -> None:
    r = client.post(f"/v1/floorplans/{F}/commands", json={}, headers=AUTH)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_projects_limit_is_bounded() -> None:
    assert client.get("/v1/projects?limit=101", headers=AUTH).status_code == 422

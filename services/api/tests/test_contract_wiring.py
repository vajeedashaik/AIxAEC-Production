"""Every route in CONTRACTS.md §8, with the IDOR sweep that walks all of them as a second user."""

import uuid
from typing import Any

import pytest
import respx

from .conftest import PNG_1PX, Api

CMD = {"json": {"instruction": "move the kitchen wall 300 mm left"}}


def routes(p: object, f: object) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        ("GET", "/v1/me", {}),
        ("GET", "/v1/projects?limit=20&offset=0", {}),
        ("POST", "/v1/projects", {"json": {"name": "Flat"}}),
        ("GET", f"/v1/projects/{p}", {}),
        ("PATCH", f"/v1/projects/{p}", {"json": {"name": "Flat 2"}}),
        ("DELETE", f"/v1/projects/{p}", {}),
        ("GET", f"/v1/projects/{p}/floorplans", {}),
        ("POST", f"/v1/projects/{p}/floorplans", {"files": {"file": ("a.png", PNG_1PX, "image/png")}}),
        ("GET", f"/v1/floorplans/{f}", {}),
        ("DELETE", f"/v1/floorplans/{f}", {}),
        ("POST", f"/v1/floorplans/{f}/process", {}),
        ("GET", f"/v1/floorplans/{f}/job", {}),
        ("GET", f"/v1/floorplans/{f}/model?version=1", {}),
        ("GET", f"/v1/floorplans/{f}/artifacts", {}),
        ("POST", f"/v1/floorplans/{f}/commands/interpret", CMD),
        ("POST", f"/v1/floorplans/{f}/commands", CMD),
        ("POST", f"/v1/floorplans/{f}/commands/voice", {"files": {"audio": ("a.webm", b"x", "audio/webm")}}),
        ("POST", f"/v1/floorplans/{f}/model/undo?expected_version=2", {}),
        ("POST", f"/v1/floorplans/{f}/model/redo?expected_version=1", {}),
        ("GET", f"/v1/floorplans/{f}/history", {}),
    ]


NOT_OWNER_SCOPED = {"/v1/me", "/v1/projects", "/v1/projects?limit=20&offset=0"}


def test_every_contract_route_is_registered(api: Api) -> None:
    table = routes("{project_id}", "{floorplan_id}")
    assert len(table) == 20
    expected = {(m.lower(), path.split("?")[0]) for m, path, _ in table}
    paths = api.client.get("/openapi.json").json()["paths"]
    assert {(m, p) for p, ops in paths.items() if p.startswith("/v1") for m in ops} == expected


def test_every_route_requires_a_bearer_token(api: Api) -> None:
    for method, path, kwargs in routes(uuid.uuid4(), uuid.uuid4()):
        for headers in ({}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer "}):
            r = api.client.request(method, path, headers=headers, **kwargs)
            assert (r.status_code, r.json()["error"]["code"]) == (401, "unauthorized"), f"{method} {path}"


def test_idor_sweep(api: Api, upstream: respx.MockRouter) -> None:
    floorplan_id = api.ready_floorplan("owner")
    assert api.edit(floorplan_id, "owner").json()["status"] == "APPLIED"
    project_id = api.request("GET", f"/v1/floorplans/{floorplan_id}", "owner").json()["project_id"]
    before = api.request("GET", f"/v1/floorplans/{floorplan_id}/history", "owner").json()
    calls = upstream.calls.call_count

    swept = 0
    for method, path, kwargs in routes(project_id, floorplan_id):
        if path in NOT_OWNER_SCOPED:
            continue
        swept += 1
        r = api.request(method, path, "intruder", **kwargs)
        assert (r.status_code, r.json()["error"]["code"]) == (404, "not_found"), f"{method} {path}: {r.text}"
    assert swept == 17

    # Nothing moved, and the intruder never reached a downstream service.
    assert upstream.calls.call_count == calls
    assert api.request("GET", f"/v1/floorplans/{floorplan_id}/history", "owner").json() == before
    assert api.request("GET", "/v1/projects", "intruder").json()["total"] == 0


def test_command_request_exactly_one_is_enforced(api: Api) -> None:
    r = api.request("POST", f"/v1/floorplans/{uuid.uuid4()}/commands", json={})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "validation_error")


def test_projects_limit_is_bounded(api: Api) -> None:
    assert api.request("GET", "/v1/projects?limit=101").status_code == 422


@pytest.mark.parametrize("path", ["/v1/projects/not-a-uuid", "/v1/floorplans/not-a-uuid"])
def test_bad_ids_are_validation_errors(api: Api, path: str) -> None:
    assert api.request("GET", path).status_code == 422

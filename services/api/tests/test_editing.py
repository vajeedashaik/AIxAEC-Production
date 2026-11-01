"""Edit orchestration, undo/redo/discard, voice, and the end-to-end workflow."""

import json
import threading
from typing import Any

import httpx
import pytest
import respx
from aec_contracts import CommandResponse, History, ModelEnvelope
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.orm import EditRow, ModelRow

from .conftest import Api, AppFactory, applied, fixture

CLARIFY = {"status": "CLARIFICATION", "question": "Which wall do you mean?", "candidates": [
    {"id": "11111111-1111-4111-8111-111111111111", "kind": "wall", "label": "north wall", "x": 1, "y": 2},
    {"id": "22222222-2222-4222-8222-222222222222", "kind": "wall", "label": "south wall", "x": 3, "y": 4},
]}
REJECT = {"status": "REJECTED", "stage": "semantic_validation", "detail": "Set a scale first to use millimetres."}


def history(api: Api, floorplan_id: str) -> History:
    return History.model_validate(api.request("GET", f"/v1/floorplans/{floorplan_id}/history").json())


def undo(api: Api, floorplan_id: str, **params: Any) -> httpx.Response:
    return api.request("POST", f"/v1/floorplans/{floorplan_id}/model/undo", params=params)


def redo(api: Api, floorplan_id: str, **params: Any) -> httpx.Response:
    return api.request("POST", f"/v1/floorplans/{floorplan_id}/model/redo", params=params)


def versions_count(factory: sessionmaker[Session]) -> int:
    with factory() as session:
        return session.scalar(select(func.count()).select_from(ModelRow)) or 0


# --- applying ---

def test_instruction_applies_new_version(api: Api, upstream: respx.MockRouter,
                                         transactional: sessionmaker[Session]) -> None:
    floorplan_id = api.ready_floorplan()
    r = api.edit(floorplan_id, instruction="move the wall 300 mm left", expected_version=1)
    body = CommandResponse.model_validate(r.json())
    assert (r.status_code, body.status, body.version) == (200, "APPLIED", 2)
    assert body.model and body.changes and body.command and body.summary and body.edit_id
    assert api.head(floorplan_id) == 2

    # The LLM only ever saw the brief, and geometry received the raw command to validate.
    parse_body = json.loads(upstream["parse"].calls.last.request.content)
    assert set(parse_body) == {"instruction", "brief"}
    assert json.loads(upstream["execute"].calls.last.request.content)["command"]["operation"] == "MOVE_WALL"

    with transactional() as session:
        edit = session.scalars(select(EditRow)).one()
        row = session.scalars(select(ModelRow).where(ModelRow.version == 2)).one()
    assert (edit.status, edit.operation, edit.parent_version, edit.result_version) == ("APPLIED", "DELETE_WALL", 1, 2)
    assert edit.instruction == "move the wall 300 mm left"
    assert (row.origin, row.parent_version, row.edit_id) == ("EDIT", 1, edit.id)


def test_structured_command_skips_language(api: Api, upstream: respx.MockRouter) -> None:
    floorplan_id = api.ready_floorplan()
    command = {"operation": "DELETE_WALL", "target_query": "kitchen"}
    assert api.edit(floorplan_id, command=command).json()["status"] == "APPLIED"
    assert not upstream["parse"].called
    assert not upstream["brief"].called


def test_stale_expected_version_is_409(api: Api, upstream: respx.MockRouter) -> None:
    floorplan_id = api.ready_floorplan()
    r = api.edit(floorplan_id, instruction="x", expected_version=99)
    assert r.status_code == 409
    expected = fixture("api/error.stale_model.json")
    expected["error"]["details"]["head_version"] = 1
    assert r.json() == expected
    assert not upstream["execute"].called


def test_edit_before_a_model_exists_is_not_ready(api: Api, upstream: respx.MockRouter) -> None:
    plan = api.upload(api.project())
    r = api.edit(plan["id"])
    assert (r.status_code, r.json()["error"]["code"]) == (409, "model_not_ready")


def test_edit_while_reprocessing_is_not_ready(api: Api, upstream: respx.MockRouter) -> None:
    floorplan_id = api.ready_floorplan()
    api.request("POST", f"/v1/floorplans/{floorplan_id}/process")
    assert api.edit(floorplan_id).json()["error"]["code"] == "model_not_ready"
    assert undo(api, floorplan_id).json()["error"]["code"] == "model_not_ready"
    assert api.request("GET", f"/v1/floorplans/{floorplan_id}/model").json()["error"]["code"] == "model_not_ready"
    assert api.request("GET", f"/v1/floorplans/{floorplan_id}/model?version=1").status_code == 200


# --- interpret ---

def test_interpret_previews_without_persisting(api: Api, upstream: respx.MockRouter,
                                               transactional: sessionmaker[Session]) -> None:
    floorplan_id = api.ready_floorplan()
    r = api.request("POST", f"/v1/floorplans/{floorplan_id}/commands/interpret", json={"instruction": "move it"})
    body = CommandResponse.model_validate(r.json())
    assert (body.status, body.version, body.edit_id) == ("PREVIEW", 1, None)
    assert body.model and body.changes
    assert json.loads(upstream["execute"].calls.last.request.content)["dry_run"] is True
    assert api.head(floorplan_id) == 1
    assert versions_count(transactional) == 1
    with transactional() as session:
        assert session.scalars(select(EditRow)).first() is None


@pytest.mark.parametrize("answer,status", [(CLARIFY, "CLARIFICATION"), (REJECT, "REJECTED")])
def test_interpret_never_audits_other_outcomes(api: Api, upstream: respx.MockRouter,
                                               transactional: sessionmaker[Session], answer: Any, status: str) -> None:
    floorplan_id = api.ready_floorplan()
    upstream["execute"].mock(side_effect=None, return_value=httpx.Response(200, json=answer))
    body = api.request("POST", f"/v1/floorplans/{floorplan_id}/commands/interpret", json={"instruction": "x"}).json()
    assert body["status"] == status
    assert body["edit_id"] is None
    with transactional() as session:
        assert session.scalars(select(EditRow)).first() is None


# --- rejections and clarifications are audited, model untouched ---

def test_rejected_edit_is_audited_and_model_untouched(api: Api, upstream: respx.MockRouter,
                                                      transactional: sessionmaker[Session]) -> None:
    floorplan_id = api.ready_floorplan()
    upstream["execute"].mock(side_effect=None, return_value=httpx.Response(200, json=REJECT))
    body = CommandResponse.model_validate(api.edit(floorplan_id).json())
    assert (body.status, body.stage, body.version) == ("REJECTED", "semantic_validation", 1)
    assert body.detail == REJECT["detail"]
    assert api.head(floorplan_id) == 1
    assert versions_count(transactional) == 1
    with transactional() as session:
        edit = session.scalars(select(EditRow)).one()
    assert (edit.status, edit.stage, edit.error, edit.result_version) == (
        "REJECTED", "semantic_validation", REJECT["detail"], None)
    assert edit.operation == "MOVE_WALL"
    assert edit.id == body.edit_id


def test_clarification_is_audited(api: Api, upstream: respx.MockRouter, transactional: sessionmaker[Session]) -> None:
    floorplan_id = api.ready_floorplan()
    upstream["execute"].mock(side_effect=None, return_value=httpx.Response(200, json=CLARIFY))
    body = CommandResponse.model_validate(api.edit(floorplan_id).json())
    assert (body.status, body.question, len(body.candidates)) == ("CLARIFICATION", CLARIFY["question"], 2)
    assert body.command is not None and body.command.operation == "MOVE_WALL"  # re-sent with the picked target_id
    with transactional() as session:
        edit = session.scalars(select(EditRow)).one()
    assert edit.status == "CLARIFICATION"
    assert edit.clarification and edit.clarification["question"] == CLARIFY["question"]
    assert api.head(floorplan_id) == 1


@pytest.mark.parametrize("parsed,detail", [
    ({"status": "UNKNOWN", "provider": "rules", "detail": "That isn't an edit."}, "That isn't an edit."),
    ({"status": "UNKNOWN", "provider": "rules"}, "didn't understand"),
    ({"status": "ERROR", "provider": "llm", "detail": "stack trace from provider"}, "unavailable"),
])
def test_parse_failures_reject_at_parse(api: Api, upstream: respx.MockRouter, transactional: sessionmaker[Session],
                                        parsed: dict[str, Any], detail: str) -> None:
    floorplan_id = api.ready_floorplan()
    upstream["parse"].respond(200, json=parsed)
    body = api.edit(floorplan_id).json()
    assert (body["status"], body["stage"]) == ("REJECTED", "parse")
    assert detail in body["detail"]
    assert "stack trace" not in body["detail"]
    assert not upstream["execute"].called
    with transactional() as session:
        assert session.scalars(select(EditRow)).one().stage == "parse"


@pytest.mark.parametrize("failure", [httpx.Response(500), httpx.ConnectError("down")])
def test_language_down_rejects_at_parse_with_model_unchanged(api: Api, upstream: respx.MockRouter,
                                                             failure: Any) -> None:
    floorplan_id = api.ready_floorplan()
    upstream["parse"].mock(side_effect=[failure])
    body = api.edit(floorplan_id).json()
    assert (body["status"], body["stage"]) == ("REJECTED", "parse")
    assert "not changed" in body["detail"]
    assert api.head(floorplan_id) == 1


def test_geometry_down_is_an_upstream_error_with_model_unchanged(api: Api, upstream: respx.MockRouter) -> None:
    floorplan_id = api.ready_floorplan()
    upstream["execute"].mock(side_effect=httpx.ConnectError("down"))
    r = api.edit(floorplan_id)
    assert (r.status_code, r.json()["error"]["code"]) == (503, "upstream_unavailable")
    assert upstream["execute"].call_count == 3
    assert api.head(floorplan_id) == 1


def test_geometry_breaking_the_contract_is_502(api: Api, upstream: respx.MockRouter) -> None:
    floorplan_id = api.ready_floorplan()
    upstream["execute"].mock(side_effect=None, return_value=httpx.Response(200, json={"status": "APPLIED"}))
    assert api.edit(floorplan_id).status_code == 502
    assert api.head(floorplan_id) == 1


def test_circuit_breaker_opens_then_recovers(api: Api, upstream: respx.MockRouter,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    from app.clients import base

    floorplan_id = api.ready_floorplan()
    good = upstream["execute"].side_effect
    command = {"operation": "DELETE_WALL", "target_query": "x"}
    upstream["execute"].mock(side_effect=httpx.ConnectError("down"))
    api.edit(floorplan_id, command=command)  # 3 failures
    api.edit(floorplan_id, command=command)  # 2 more reach the threshold of 5, the 3rd retry is refused
    calls = upstream["execute"].call_count
    assert calls == 5
    assert api.edit(floorplan_id, command=command).status_code == 503
    assert upstream["execute"].call_count == calls  # open: not even attempted

    monkeypatch.setattr(base, "BREAKER_RESET_SECONDS", 0)
    upstream["execute"].mock(side_effect=good)
    assert api.edit(floorplan_id).json()["status"] == "APPLIED"


def test_upstream_never_sees_the_user_token(api: Api, upstream: respx.MockRouter) -> None:
    floorplan_id = api.ready_floorplan()
    api.edit(floorplan_id)
    for call in upstream.calls:
        assert "authorization" not in call.request.headers
        assert call.request.headers["x-internal-token"]
        assert call.request.headers["x-request-id"]


# --- concurrency ---

def test_six_parallel_edits_one_applied_five_stale(make_api: AppFactory, committed: sessionmaker[Session],
                                                   upstream: respx.MockRouter) -> None:
    api = make_api(committed)
    floorplan_id = api.ready_floorplan()
    barrier = threading.Barrier(6, timeout=20)

    def together(request: httpx.Request) -> httpx.Response:  # all six hold the same base version
        barrier.wait()
        return applied(request)

    upstream["execute"].mock(side_effect=together)
    results: list[httpx.Response] = []

    def post() -> None:
        results.append(TestClient(api.client.app, raise_server_exceptions=False).post(
            f"/v1/floorplans/{floorplan_id}/commands",
            json={"command": {"operation": "DELETE_WALL", "target_query": "x"}},
            headers=api.auth()))

    threads = [threading.Thread(target=post) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(r.status_code for r in results) == [200, 409, 409, 409, 409, 409]
    assert {r.json()["error"]["code"] for r in results if r.status_code == 409} == {"stale_model"}
    assert api.head(floorplan_id) == 2
    assert versions_count(committed) == 2
    with committed() as session:
        assert session.scalar(select(func.count()).select_from(EditRow)) == 1


# --- undo / redo / discard ---

def test_undo_redo_move_head_and_copy_nothing(api: Api, upstream: respx.MockRouter,
                                              transactional: sessionmaker[Session]) -> None:
    floorplan_id = api.ready_floorplan()
    edited = api.edit(floorplan_id).json()["model"]

    u = undo(api, floorplan_id, expected_version=2)
    body = CommandResponse.model_validate(u.json())
    assert (u.status_code, body.status, body.version) == (200, "APPLIED", 1)
    assert body.edit_id and body.model
    assert len(edited["walls"]) == len(body.model.walls) + 1
    assert api.head(floorplan_id) == 1

    r = redo(api, floorplan_id, expected_version=1)
    assert (r.json()["status"], r.json()["version"]) == ("APPLIED", 2)
    assert api.request("GET", f"/v1/floorplans/{floorplan_id}/model").json()["version"] == 2

    assert versions_count(transactional) == 2
    h = history(api, floorplan_id)
    assert [(e.status, e.parent_version, e.result_version) for e in h.edits] == [
        ("REDO", 1, 2), ("UNDO", 2, 1), ("APPLIED", 1, 2)]


def test_nothing_to_undo_or_redo_is_conflict(api: Api, upstream: respx.MockRouter) -> None:
    floorplan_id = api.ready_floorplan()
    for call in (undo, redo):
        r = call(api, floorplan_id)
        assert (r.status_code, r.json()["error"]["code"]) == (409, "conflict")


def test_undo_redo_check_expected_version(api: Api, upstream: respx.MockRouter) -> None:
    floorplan_id = api.ready_floorplan()
    api.edit(floorplan_id)
    assert undo(api, floorplan_id, expected_version=1).json()["error"]["code"] == "stale_model"
    assert api.head(floorplan_id) == 2
    undo(api, floorplan_id)
    assert redo(api, floorplan_id, expected_version=2).json()["error"]["code"] == "stale_model"


def test_new_edit_discards_redo_branch_and_keeps_it_for_audit(api: Api, upstream: respx.MockRouter) -> None:
    floorplan_id = api.ready_floorplan()
    api.edit(floorplan_id)  # v2
    api.edit(floorplan_id)  # v3
    undo(api, floorplan_id)
    undo(api, floorplan_id)  # HEAD v1
    assert api.edit(floorplan_id).json()["version"] == 4  # numbers are never reused

    h = history(api, floorplan_id)
    assert {v.version: v.discarded for v in h.versions} == {1: False, 2: True, 3: True, 4: False}
    assert (h.head_version, h.can_undo, h.can_redo) == (4, True, False)
    assert [v.is_head for v in h.versions] == [False, False, False, True]
    assert redo(api, floorplan_id).status_code == 409
    assert api.request("GET", f"/v1/floorplans/{floorplan_id}/model?version=2").status_code == 200  # still readable

    undo(api, floorplan_id)
    assert redo(api, floorplan_id).json()["version"] == 4  # redo follows the live branch


def test_reprocess_then_undo_returns_to_edits(api: Api, upstream: respx.MockRouter) -> None:
    floorplan_id = api.ready_floorplan()
    edited = api.edit(floorplan_id).json()  # v2
    api.request("POST", f"/v1/floorplans/{floorplan_id}/process")
    api.run_worker()  # v3 branches from HEAD
    h = history(api, floorplan_id)
    assert (h.head_version, h.versions[-1].origin, h.versions[-1].parent_version) == (3, "PROCESSING", 2)

    back = undo(api, floorplan_id).json()
    assert back["version"] == 2
    assert back["model"]["walls"] == edited["model"]["walls"]


def test_reprocess_while_behind_discards_the_redo_branch(api: Api, upstream: respx.MockRouter) -> None:
    floorplan_id = api.ready_floorplan()
    api.edit(floorplan_id)  # v2
    undo(api, floorplan_id)  # HEAD v1
    api.request("POST", f"/v1/floorplans/{floorplan_id}/process")
    api.run_worker()  # v3, child of v1
    undo(api, floorplan_id)
    assert redo(api, floorplan_id).json()["version"] == 3  # not the abandoned v2


def test_history_on_an_unprocessed_plan(api: Api) -> None:
    plan = api.upload(api.project())
    h = history(api, plan["id"])
    assert (h.head_version, h.can_undo, h.can_redo, h.versions, h.edits) == (None, False, False, [], [])


# --- model ---

def test_model_envelope_and_insights_cache(api: Api, upstream: respx.MockRouter) -> None:
    floorplan_id = api.ready_floorplan()
    for _ in range(2):
        r = api.request("GET", f"/v1/floorplans/{floorplan_id}/model")
        envelope = ModelEnvelope.model_validate(r.json())
    assert envelope.version == 1
    assert envelope.summary == envelope.model.summary()
    assert upstream["insights"].call_count == 1
    assert api.request("GET", f"/v1/floorplans/{floorplan_id}/model?version=9").status_code == 404


def test_head_is_the_pointer_not_max_version(api: Api, upstream: respx.MockRouter) -> None:
    floorplan_id = api.ready_floorplan()
    api.edit(floorplan_id)
    undo(api, floorplan_id)
    assert api.request("GET", f"/v1/floorplans/{floorplan_id}/model").json()["version"] == 1


# --- voice ---

def voice(api: Api, floorplan_id: str, mime: str = "audio/webm;codecs=opus", data: bytes = b"sound",
          **form: Any) -> httpx.Response:
    return api.request("POST", f"/v1/floorplans/{floorplan_id}/commands/voice",
                       files={"audio": ("a.webm", data, mime)}, data=form)


def test_voice_happy_path(api: Api, upstream: respx.MockRouter, transactional: sessionmaker[Session]) -> None:
    floorplan_id = api.ready_floorplan()
    body = CommandResponse.model_validate(voice(api, floorplan_id).json())
    assert (body.status, body.transcript, body.version) == ("APPLIED", "move the wall 300 mm left", 2)
    with transactional() as session:
        assert session.scalars(select(EditRow)).one().instruction == "move the wall 300 mm left"


def test_voice_dry_run_is_a_preview(api: Api, upstream: respx.MockRouter) -> None:
    floorplan_id = api.ready_floorplan()
    r = voice(api, floorplan_id, dry_run="true", expected_version="1")
    assert (r.json()["status"], r.json()["transcript"]) == ("PREVIEW", "move the wall 300 mm left")
    assert api.head(floorplan_id) == 1


def test_voice_rejects_unsupported_type(api: Api, upstream: respx.MockRouter) -> None:
    floorplan_id = api.ready_floorplan()
    r = voice(api, floorplan_id, mime="video/mp4")
    assert (r.status_code, r.json()["error"]["code"]) == (415, "unsupported_media_type")
    assert not upstream["transcribe"].called


def test_voice_rejects_oversize(make_api: AppFactory, transactional: sessionmaker[Session],
                                upstream: respx.MockRouter) -> None:
    api = make_api(transactional, max_audio_bytes=4)
    floorplan_id = api.ready_floorplan()
    r = voice(api, floorplan_id, data=b"12345")
    assert (r.status_code, r.json()["error"]["code"]) == (413, "payload_too_large")
    assert not upstream["transcribe"].called


def test_voice_empty_recording_and_silence(api: Api, upstream: respx.MockRouter) -> None:
    floorplan_id = api.ready_floorplan()
    assert voice(api, floorplan_id, data=b"").status_code == 422
    upstream["transcribe"].respond(200, json={"text": "  ", "language": "en", "duration_ms": 1, "provider": "stub"})
    body = voice(api, floorplan_id).json()
    assert (body["status"], body["stage"]) == ("REJECTED", "parse")
    assert not upstream["execute"].called


def test_voice_speech_down_is_upstream_error(api: Api, upstream: respx.MockRouter) -> None:
    floorplan_id = api.ready_floorplan()
    upstream["transcribe"].respond(500)
    assert voice(api, floorplan_id).status_code == 502
    assert api.head(floorplan_id) == 1


# --- end to end ---

def test_end_to_end_workflow(api: Api, upstream: respx.MockRouter) -> None:
    project_id = api.project()
    plan = api.upload(project_id, process=False)
    assert api.request("POST", f"/v1/floorplans/{plan['id']}/process").status_code == 202
    api.run_worker()
    assert api.request("GET", f"/v1/floorplans/{plan['id']}/job").json()["status"] == "COMPLETED"

    model = ModelEnvelope.model_validate(api.request("GET", f"/v1/floorplans/{plan['id']}/model").json())
    assert model.version == 1

    preview = api.request("POST", f"/v1/floorplans/{plan['id']}/commands/interpret",
                          json={"instruction": "move the kitchen wall 300 mm left", "expected_version": 1}).json()
    assert (preview["status"], preview["version"]) == ("PREVIEW", 1)

    edit = api.edit(plan["id"], instruction="move the kitchen wall 300 mm left", expected_version=1).json()
    assert (edit["status"], edit["version"]) == ("APPLIED", 2)

    assert undo(api, plan["id"], expected_version=2).json()["version"] == 1
    assert redo(api, plan["id"], expected_version=1).json()["version"] == 2

    h = history(api, plan["id"])
    assert (h.head_version, h.can_undo, h.can_redo) == (2, True, False)
    assert [(v.version, v.origin, v.is_head) for v in h.versions] == [(1, "PROCESSING", False), (2, "EDIT", True)]
    assert [e.status for e in h.edits] == ["REDO", "UNDO", "APPLIED"]
    assert h.versions[1].edit_id == h.edits[2].id

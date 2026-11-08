"""Job lifecycle: atomic claim, poison guard, stale recovery, fencing, failure handling."""

import threading
import time
from typing import Any
from uuid import UUID

import httpx
import pytest
import respx
from aec_contracts import Artifact, FloorPlanModel, Job
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from app import jobs
from app.jobs import Claim, claim_next, process_claim
from app.orm import ArtifactRow, FloorplanRow, JobRow, ModelRow
from app.worker import run_forever, run_once

from .conftest import Api, AppFactory, analyze_result, floorplan_id_of


def job_of(api: Api, floorplan_id: str) -> Job:
    return Job.model_validate(api.request("GET", f"/v1/floorplans/{floorplan_id}/job").json())


def make_stale(factory: sessionmaker[Session], job_id: Any, attempts: int = 1) -> None:
    with factory() as session:
        session.execute(update(JobRow).where(JobRow.id == job_id).values(
            status="PROCESSING", attempts=attempts, heartbeat_at=func.now() - text("interval '2 hours'")))
        session.commit()


def test_happy_path(api: Api, upstream: respx.MockRouter, transactional: sessionmaker[Session]) -> None:
    project_id = api.project()
    plan = api.upload(project_id)
    assert plan["status"] == "PENDING"
    assert api.request("GET", f"/v1/floorplans/{plan['id']}/model").json()["error"]["code"] == "model_not_ready"

    api.run_worker()

    job = job_of(api, plan["id"])
    assert (job.status, job.attempts, job.error_message) == ("COMPLETED", 1, None)
    assert len(job.stages) == 8
    assert job.started_at and job.finished_at
    after = api.request("GET", f"/v1/floorplans/{plan['id']}").json()
    assert (after["status"], after["current_model_version"]) == ("COMPLETED", 1)

    listed = api.request("GET", f"/v1/floorplans/{plan['id']}/artifacts").json()
    artifacts = [Artifact.model_validate(a) for a in listed]
    assert sorted(a.kind for a in artifacts) == ["preprocessed", "semantic_model"]
    assert ("artifacts", f"{project_id}/{plan['id']}/{job.id}/preprocessed.png") in api.blobs.objects
    assert upstream["analyze"].calls.last.request.headers["X-Internal-Token"]
    assert upstream["analyze"].calls.last.request.headers["X-Request-ID"] == f"job-{job.id}"

    with transactional() as session:
        row = session.scalars(select(ModelRow)).one()
    assert (row.origin, row.parent_version, row.version, row.job_id) == ("PROCESSING", None, 1, job.id)


def test_process_conflicts_while_live_then_allows_retry(api: Api, upstream: respx.MockRouter) -> None:
    plan = api.upload(api.project())
    r = api.request("POST", f"/v1/floorplans/{plan['id']}/process")
    assert (r.status_code, r.json()["error"]["code"]) == (409, "already_processing")
    api.run_worker()
    r = api.request("POST", f"/v1/floorplans/{plan['id']}/process")
    assert r.status_code == 202
    assert Job.model_validate(r.json()).status == "PENDING"
    assert api.request("GET", f"/v1/floorplans/{plan['id']}").json()["status"] == "PENDING"


def test_process_fails_stale_job_and_enqueues(api: Api, transactional: sessionmaker[Session]) -> None:
    plan = api.upload(api.project())
    old = plan["latest_job"]["id"]
    make_stale(transactional, old)
    r = api.request("POST", f"/v1/floorplans/{plan['id']}/process")
    assert r.status_code == 202
    assert r.json()["id"] != old
    with transactional() as session:
        assert session.get(JobRow, UUID(old)).status == "FAILED"  # type: ignore[union-attr]


def test_claim_exclusivity_with_two_concurrent_workers(make_api: AppFactory, committed: sessionmaker[Session]) -> None:
    api = make_api(committed)
    project_id = api.project()
    expected = {api.upload(project_id)["latest_job"]["id"] for _ in range(8)}
    barrier = threading.Barrier(2)
    claimed: list[list[Claim]] = [[], []]

    def worker(out: list[Claim]) -> None:
        barrier.wait()
        while (claim := claim_next(api.c)) is not None:
            out.append(claim)

    threads = [threading.Thread(target=worker, args=(claimed[i],)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ids = [str(c.job_id) for out in claimed for c in out]
    assert sorted(ids) == sorted(expected)  # each job exactly once
    assert claim_next(api.c) is None


def test_stale_job_is_recovered(api: Api, upstream: respx.MockRouter, transactional: sessionmaker[Session]) -> None:
    plan = api.upload(api.project())
    make_stale(transactional, plan["latest_job"]["id"])
    api.run_worker()
    job = job_of(api, plan["id"])
    assert (job.status, job.attempts) == ("COMPLETED", 2)


def test_fresh_processing_job_is_not_stolen(api: Api, transactional: sessionmaker[Session]) -> None:
    api.upload(api.project())
    assert claim_next(api.c) is not None
    assert claim_next(api.c) is None


def test_attempts_cap_gives_up(api: Api, upstream: respx.MockRouter, transactional: sessionmaker[Session]) -> None:
    plan = api.upload(api.project())
    make_stale(transactional, plan["latest_job"]["id"], attempts=api.c.settings.processing_max_attempts)
    api.run_worker()
    job = job_of(api, plan["id"])
    assert job.status == "FAILED"
    assert "giving up" in (job.error_message or "")
    assert not upstream["analyze"].called
    assert api.request("GET", f"/v1/floorplans/{plan['id']}").json()["status"] == "FAILED"


def test_vision_failed_persists_stages_and_warnings(api: Api, upstream: respx.MockRouter) -> None:
    def failed(request: httpx.Request) -> httpx.Response:
        body = analyze_result(floorplan_id_of(request), status="FAILED", model=None, artifacts=[],
                              warnings=["Only page 1 of 3 was processed."],
                              error="Processing failed at stage 'wall_detection'.")
        body["stages"][1].update(status="failed", error="no walls")
        return httpx.Response(200, json=body)

    upstream["analyze"].mock(side_effect=failed)
    plan = api.upload(api.project())
    api.run_worker()
    job = job_of(api, plan["id"])
    assert job.status == "FAILED"
    assert job.error_message == "Processing failed at stage 'wall_detection'."
    assert [s.status for s in job.stages][1] == "failed"
    assert len(job.stages) == 8
    after = api.request("GET", f"/v1/floorplans/{plan['id']}").json()
    assert (after["status"], after["current_model_version"]) == ("FAILED", None)
    assert after["warnings"] == ["Only page 1 of 3 was processed."]
    assert upstream["analyze"].call_count == 1  # a clean FAILED is final, no retry


def test_vision_5xx_is_retried_with_a_bound(api: Api, upstream: respx.MockRouter) -> None:
    upstream["analyze"].respond(500)
    plan = api.upload(api.project())
    api.run_worker()
    assert upstream["analyze"].call_count == 3
    job = job_of(api, plan["id"])
    assert job.status == "FAILED"
    assert job.error_message == "The vision service is unavailable."


def test_vision_recovers_on_retry(api: Api, upstream: respx.MockRouter) -> None:
    good = upstream["analyze"].side_effect
    responses = iter([httpx.ConnectError("down"), None])

    def flaky(request: httpx.Request) -> httpx.Response:
        failure = next(responses)
        if failure:
            raise failure
        assert callable(good)
        result = good(request)
        assert isinstance(result, httpx.Response)
        return result

    upstream["analyze"].mock(side_effect=flaky)
    plan = api.upload(api.project())
    api.run_worker()
    assert job_of(api, plan["id"]).status == "COMPLETED"


def test_vision_4xx_is_not_retried(api: Api, upstream: respx.MockRouter) -> None:
    upstream["analyze"].respond(415)
    plan = api.upload(api.project())
    api.run_worker()
    assert upstream["analyze"].call_count == 1
    assert job_of(api, plan["id"]).status == "FAILED"


def test_crash_fails_the_job_with_a_safe_message(api: Api, upstream: respx.MockRouter) -> None:
    plan = api.upload(api.project())
    api.blobs.fail_get = True
    api.run_worker()
    job = job_of(api, plan["id"])
    assert job.status == "FAILED"
    assert job.error_message == jobs.GENERIC_FAILURE
    assert "secret-internal-detail" not in (job.error_message or "")


def test_model_for_another_floorplan_is_refused(api: Api, upstream: respx.MockRouter) -> None:
    upstream["analyze"].mock(side_effect=lambda _: httpx.Response(
        200, json=analyze_result("00000000-0000-4000-8000-000000000000")))
    plan = api.upload(api.project())
    api.run_worker()
    assert job_of(api, plan["id"]).status == "FAILED"
    assert api.head(plan["id"]) is None


def test_classification_fills_unknown_rooms_only(api: Api, upstream: respx.MockRouter) -> None:
    def with_unknown(request: httpx.Request) -> httpx.Response:
        body = analyze_result(floorplan_id_of(request))
        room = body["model"]["rooms"][0]
        room.update(room_type="UNKNOWN", room_type_source=None, room_type_confidence=None, label_text="Kitchenette")
        return httpx.Response(200, json=body)

    upstream["analyze"].mock(side_effect=with_unknown)
    floorplan_id = api.ready_floorplan()
    assert __import__("json").loads(upstream["classify"].calls.last.request.content) == {"labels": ["Kitchenette"]}
    model = FloorPlanModel.model_validate(api.request("GET", f"/v1/floorplans/{floorplan_id}/model").json()["model"])
    assert model.rooms[0].room_type == "KITCHEN"
    assert model.rooms[0].room_type_source == "INFERRED"
    assert model.rooms[0].room_type_confidence == 0.9


def test_classification_failure_leaves_rooms_unknown(api: Api, upstream: respx.MockRouter) -> None:
    def with_unknown(request: httpx.Request) -> httpx.Response:
        body = analyze_result(floorplan_id_of(request))
        body["model"]["rooms"][0].update(room_type="UNKNOWN", room_type_source=None, room_type_confidence=None,
                                         label_text="Kitchenette")
        return httpx.Response(200, json=body)

    upstream["analyze"].mock(side_effect=with_unknown)
    upstream["classify"].respond(500)
    floorplan_id = api.ready_floorplan()
    model = api.request("GET", f"/v1/floorplans/{floorplan_id}/model").json()["model"]
    assert model["rooms"][0]["room_type"] == "UNKNOWN"
    assert job_of(api, floorplan_id).status == "COMPLETED"


def test_slow_worker_cannot_commit_after_takeover(api: Api, upstream: respx.MockRouter,
                                                  transactional: sessionmaker[Session]) -> None:
    plan = api.upload(api.project())
    slow = claim_next(api.c)
    assert slow is not None
    make_stale(transactional, slow.job_id)
    fast = claim_next(api.c)
    assert fast and fast.attempts == 2

    process_claim(api.c, slow)  # finishes late, must be fenced off
    assert job_of(api, plan["id"]).status == "PROCESSING"
    assert api.head(plan["id"]) is None

    process_claim(api.c, fast)
    assert job_of(api, plan["id"]).status == "COMPLETED"
    assert api.head(plan["id"]) == 1


def test_floorplan_deleted_mid_job_cleans_up_artifacts(api: Api, upstream: respx.MockRouter) -> None:
    plan = api.upload(api.project())
    claim = claim_next(api.c)
    assert claim

    def delete_during_analysis(request: httpx.Request) -> httpx.Response:
        api.blobs.objects.update({("floorplans", "kept-copy"): b""})
        assert api.request("DELETE", f"/v1/floorplans/{plan['id']}").status_code == 204
        return httpx.Response(200, json=analyze_result(plan["id"]))

    upstream["analyze"].mock(side_effect=delete_during_analysis)
    original_get = api.blobs.get
    api.blobs.get = lambda bucket, key: b"x"  # type: ignore[method-assign]
    process_claim(api.c, claim)
    api.blobs.get = original_get  # type: ignore[method-assign]
    assert not [k for k in api.blobs.objects if k[0] == "artifacts"]


def test_heartbeat_keeps_a_long_job_alive(make_api: AppFactory, committed: sessionmaker[Session],
                                          upstream: respx.MockRouter, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs, "HEARTBEAT_SECONDS", 0.05)
    api = make_api(committed)
    plan = api.upload(api.project())
    claim = claim_next(api.c)
    assert claim
    with committed() as session:
        first = session.get(JobRow, claim.job_id).heartbeat_at  # type: ignore[union-attr]

    def slow(request: httpx.Request) -> httpx.Response:
        time.sleep(0.3)
        with committed() as session:
            beat = session.get(JobRow, claim.job_id).heartbeat_at  # type: ignore[union-attr]
        assert beat and first and beat > first
        return httpx.Response(200, json=analyze_result(plan["id"]))

    upstream["analyze"].mock(side_effect=slow)
    process_claim(api.c, claim)
    assert job_of(api, plan["id"]).status == "COMPLETED"


def test_run_forever_stops_gracefully_and_survives_errors(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    stop = threading.Event()

    def flaky(_: object) -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("database away")
        stop.set()
        return True

    monkeypatch.setattr("app.worker.run_once", flaky)
    api.c.settings.worker_poll_seconds = 0
    run_forever(api.c, stop)
    assert calls == 2


def test_run_once_on_empty_queue(api: Api) -> None:
    assert run_once(api.c) is False


def test_reprocess_with_no_new_rows_is_counted(api: Api, upstream: respx.MockRouter,
                                               transactional: sessionmaker[Session]) -> None:
    floorplan_id = api.ready_floorplan()
    api.request("POST", f"/v1/floorplans/{floorplan_id}/process")
    api.run_worker()
    with transactional() as session:
        assert session.scalar(select(func.count()).select_from(ModelRow)) == 2
        assert session.scalar(select(func.count()).select_from(ArtifactRow)) == 4
        assert session.scalars(select(FloorplanRow)).one().current_model_version == 2
    kinds = [a["kind"] for a in api.request("GET", f"/v1/floorplans/{floorplan_id}/artifacts").json()]
    assert sorted(kinds) == ["preprocessed", "semantic_model"]  # newest per kind only


def test_page_note_from_vision_replaces_the_upload_note() -> None:
    from app.jobs import merge_warnings

    upload = ["Only page 1 of 3 will be processed.", "Something else."]
    merged = merge_warnings(upload, ["Only page 1 of 3 was processed."])
    assert merged == ["Something else.", "Only page 1 of 3 was processed."]
    assert merge_warnings(upload, []) == upload  # nothing from vision: the upload note stays
    assert merge_warnings(["a"], ["a", "b"]) == ["a", "b"]

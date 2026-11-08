"""Building intelligence routes: ownership, version handling, and the rules → LLM → honest-refusal chain."""

import json
from typing import Any

import httpx
import pytest
import respx

from .conftest import Api

GEOMETRY, LANGUAGE = "http://geometry.test/v1/models", "http://language.test/v1"
UNKNOWN = {
    "status": "UNKNOWN",
    "answer": "I can't answer that from this plan's data.",
    "element_ids": [],
    "source": "rules",
}
ANSWERED = {"status": "ANSWERED", "answer": "This plan has 1 bedroom.", "element_ids": [], "source": "rules"}
LAYOUTS: dict[str, Any] = {"feasible": False, "answer": "No.", "options": []}


def url(floorplan_id: str, suffix: str) -> str:
    return f"/v1/floorplans/{floorplan_id}/{suffix}"


def test_analysis_passes_rates_through(api: Api, upstream: respx.MockRouter) -> None:
    route = upstream.post(f"{GEOMETRY}/analysis").respond(json={"needs_scale": True})
    floorplan_id = api.ready_floorplan()
    r = api.request("POST", url(floorplan_id, "analysis"), json={"rates": {"currency": "INR", "concrete_per_m3": 9000}})
    assert r.status_code == 200 and r.json()["needs_scale"] is True
    sent = json.loads(route.calls.last.request.content)
    assert sent["rates"]["currency"] == "INR" and sent["rates"]["concrete_per_m3"] == 9000
    assert sent["model"]["floorplan_id"] == floorplan_id


def test_analysis_rejects_a_negative_rate(api: Api, upstream: respx.MockRouter) -> None:
    r = api.request("POST", url(api.ready_floorplan(), "analysis"), json={"rates": {"steel_per_kg": -1}})
    assert r.status_code == 422


def test_analysis_of_a_missing_version_is_404(api: Api, upstream: respx.MockRouter) -> None:
    assert api.request("POST", url(api.ready_floorplan(), "analysis"), json={"version": 99}).status_code == 404


def test_rules_answer_never_reaches_the_llm(api: Api, upstream: respx.MockRouter) -> None:
    upstream.post(f"{GEOMETRY}/answer").respond(json=ANSWERED)
    llm = upstream.post(f"{LANGUAGE}/questions/answer").respond(json={"status": "UNKNOWN"})
    r = api.request("POST", url(api.ready_floorplan(), "ask"), json={"question": "how many bedrooms?"})
    assert r.json()["answer"] == "This plan has 1 bedroom." and not llm.called


def test_unknown_question_goes_to_the_llm_with_facts_only(api: Api, upstream: respx.MockRouter) -> None:
    upstream.post(f"{GEOMETRY}/answer").respond(json=UNKNOWN)
    upstream.post(f"{GEOMETRY}/facts").respond(json={"counts": {"rooms": 5}})
    llm = upstream.post(f"{LANGUAGE}/questions/answer").respond(json={"status": "ANSWERED", "answer": "Five rooms."})
    r = api.request("POST", url(api.ready_floorplan(), "ask"), json={"question": "describe it"})
    assert r.json()["source"] == "llm" and r.json()["answer"] == "Five rooms."
    assert set(json.loads(llm.calls.last.request.content)) == {"question", "facts"}


@pytest.mark.parametrize("reply", [httpx.Response(503), httpx.Response(200, json={"status": "ERROR"})])
def test_assistant_down_keeps_the_honest_refusal(api: Api, upstream: respx.MockRouter, reply: httpx.Response) -> None:
    upstream.post(f"{GEOMETRY}/answer").respond(json=UNKNOWN)
    upstream.post(f"{GEOMETRY}/facts").respond(json={"counts": {}})
    upstream.post(f"{LANGUAGE}/questions/answer").mock(return_value=reply)
    r = api.request("POST", url(api.ready_floorplan(), "ask"), json={"question": "describe it"})
    assert r.status_code == 200 and r.json()["status"] == "UNKNOWN"


def test_layouts_use_head(api: Api, upstream: respx.MockRouter) -> None:
    route = upstream.post(f"{GEOMETRY}/layouts").respond(json=LAYOUTS)
    r = api.request("POST", url(api.ready_floorplan(), "layouts"), json={"goal": "make the kitchen larger"})
    assert r.status_code == 200 and json.loads(route.calls.last.request.content)["goal"] == "make the kitchen larger"


def test_question_length_is_bounded(api: Api, upstream: respx.MockRouter) -> None:
    assert api.request("POST", url(api.ready_floorplan(), "ask"), json={"question": "x" * 501}).status_code == 422


def test_analysis_rejects_an_absurd_rate(api: Api, upstream: respx.MockRouter) -> None:
    r = api.request("POST", url(api.ready_floorplan(), "analysis"), json={"rates": {"concrete_per_m3": 1e308}})
    assert r.status_code == 422

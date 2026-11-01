import json
from typing import Any

import httpx
import respx
from aec_contracts import RoomType

from app.classify import classify_rooms
from app.config import Settings
from app.llm import LlmClient

URL = "http://gateway.test/v1/chat/completions"


def client() -> LlmClient:
    return LlmClient(Settings(environment="test", llm_base_url="http://gateway.test/v1", llm_api_key="k",  # type: ignore[arg-type]
                              llm_model="m"))


def reply(items: Any) -> httpx.Response:
    return httpx.Response(200, json={
        "id": "x", "object": "chat.completion", "created": 1, "model": "m",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant",
                                                                      "content": json.dumps(items)}}]})


def test_rules_only_when_llm_is_off() -> None:
    results = classify_rooms(["KITCHEN", "BED 2", "Xyzzy"], None).results
    assert [(r.room_type, r.source) for r in results] == [
        (RoomType.KITCHEN, "rules"), (RoomType.BEDROOM, "rules"), (RoomType.UNKNOWN, "rules")]
    assert results[2].confidence == 0


@respx.mock
def test_rules_hits_never_call_the_llm() -> None:
    route = respx.post(URL).mock(return_value=reply([]))
    classify_rooms(["KITCHEN", "  ", "x" * 81], client())
    assert route.call_count == 0


@respx.mock
def test_one_batched_call_with_deduplication_and_order_preserved() -> None:
    route = respx.post(URL).mock(return_value=reply([
        {"label": "Gym", "room_type": "UTILITY", "confidence": 0.6},
        {"label": "Atelier", "room_type": "OFFICE", "confidence": 0.7},
    ]))
    results = classify_rooms(["Atelier", "KITCHEN", "Gym", "Atelier"], client()).results
    assert route.call_count == 1
    assert json.loads(json.loads(route.calls[0].request.content)["messages"][1]["content"]) == ["Atelier", "Gym"]
    assert [r.label for r in results] == ["Atelier", "KITCHEN", "Gym", "Atelier"]
    assert [(r.room_type, r.source) for r in results] == [
        (RoomType.OFFICE, "llm"), (RoomType.KITCHEN, "rules"), (RoomType.UTILITY, "llm"), (RoomType.OFFICE, "llm")]
    assert results[0].confidence == 0.7


@respx.mock
def test_malformed_items_and_values_outside_the_enum_are_dropped() -> None:
    respx.post(URL).mock(return_value=reply([
        {"label": "A1", "room_type": "DUNGEON", "confidence": 0.9},
        {"label": "A2", "room_type": "OFFICE", "confidence": 7},
        {"label": "A3", "room_type": "OFFICE"},
        {"label": "A4", "room_type": "UNKNOWN", "confidence": 0.9},
        {"label": "Invented", "room_type": "OFFICE", "confidence": 0.9},
        "nonsense",
        {"label": "A5", "room_type": "GARAGE", "confidence": 0.5},
    ]))
    results = classify_rooms(["A1", "A2", "A3", "A4", "A5"], client()).results
    assert [r.label for r in results] == ["A1", "A2", "A3", "A4", "A5"]
    assert [r.source for r in results] == ["rules", "rules", "rules", "rules", "llm"]
    assert results[4].room_type is RoomType.GARAGE


@respx.mock
def test_llm_failure_or_garbage_falls_back_to_rules() -> None:
    respx.post(URL).mock(side_effect=[reply({"not": "a list"}), httpx.Response(500), httpx.Response(500)])
    c = client()
    assert classify_rooms(["Xyzzy"], c).results[0].source == "rules"
    assert classify_rooms(["Xyzzy"], c).results[0].source == "rules"

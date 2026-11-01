import json
from typing import Any

import httpx
import pytest
import respx
from aec_contracts import ClassifyRoomsResult, ErrorEnvelope, ParseResult, TranscribeResult
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import MAX_BODY_BYTES, create_app
from app.speech import STUB_TRANSCRIPT

TOKEN = "test-token"
AUTH = {"X-Internal-Token": TOKEN}
client = TestClient(create_app(Settings(environment="test", internal_service_token=TOKEN, stt_provider="stub")))  # type: ignore[arg-type]
COUNTS = {k: 0 for k in ("walls", "doors", "windows", "columns", "stairs", "furniture", "dimensions", "rooms")}
BRIEF = {"rooms": [], "counts": COUNTS, "has_scale": False, "image_width": 10, "image_height": 10}
AUDIO = {"audio": ("a.wav", b"RIFF", "audio/wav")}

ROUTES: list[tuple[str, dict[str, Any], Any]] = [
    ("/v1/commands/parse", {"json": {"instruction": "delete the kitchen door", "brief": BRIEF}}, ParseResult),
    ("/v1/rooms/classify", {"json": {"labels": ["KITCHEN"]}}, ClassifyRoomsResult),
    ("/v1/speech/transcribe", {"files": AUDIO, "data": {"language": "en"}}, TranscribeResult),
]


@pytest.mark.parametrize("path,kwargs,model", ROUTES)
def test_requires_internal_token(path: str, kwargs: dict[str, Any], model: Any) -> None:
    for headers in ({}, {"X-Internal-Token": "wrong"}):
        r = client.post(path, headers=headers, **kwargs)
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("path,kwargs,model", ROUTES)
def test_responses_validate_against_the_contract(path: str, kwargs: dict[str, Any], model: Any) -> None:
    r = client.post(path, headers=AUTH, **kwargs)
    assert r.status_code == 200, r.text
    model.model_validate(r.json())


@pytest.mark.parametrize("instruction,status,provider", [
    ("delete the kitchen door", "PARSED", "rules"),
    ("make it nicer", "UNKNOWN", "rules"),
])
def test_parse_offline(instruction: str, status: str, provider: str) -> None:
    r = client.post("/v1/commands/parse", json={"instruction": instruction, "brief": BRIEF}, headers=AUTH)
    result = ParseResult.model_validate(r.json())
    assert (result.status, result.provider) == (status, provider)
    assert result.model is None and (result.detail is None) == (status == "PARSED")


def test_parse_request_is_validated() -> None:
    r = client.post("/v1/commands/parse", json={"instruction": "", "brief": BRIEF}, headers=AUTH)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    r = client.post("/v1/commands/parse", json={"instruction": "x" * 501, "brief": BRIEF}, headers=AUTH)
    assert r.status_code == 422


def test_classify_limit_and_order() -> None:
    assert client.post("/v1/rooms/classify", json={"labels": ["x"] * 201}, headers=AUTH).status_code == 422
    r = client.post("/v1/rooms/classify", json={"labels": ["Garage", "Kitchen"]}, headers=AUTH)
    assert [x["room_type"] for x in r.json()["results"]] == ["GARAGE", "KITCHEN"]


def test_transcribe_stub_defaults_to_english() -> None:
    r = client.post("/v1/speech/transcribe", files=AUDIO, headers=AUTH)
    assert r.json() == {"text": STUB_TRANSCRIPT, "language": "en", "duration_ms": 1000, "provider": "stub"}


@pytest.mark.parametrize("content_type", ["audio/webm", "audio/webm;codecs=opus", "audio/ogg", "audio/wav",
                                          "audio/x-wav", "audio/mp4", "audio/mpeg", "audio/flac", "AUDIO/MP4"])
def test_transcribe_accepts_contract_types(content_type: str) -> None:
    r = client.post("/v1/speech/transcribe", files={"audio": ("a", b"x", content_type)}, headers=AUTH)
    assert r.status_code == 200


@pytest.mark.parametrize("content_type", ["text/plain", "video/mp4", "application/octet-stream"])
def test_transcribe_rejects_other_types(content_type: str) -> None:
    r = client.post("/v1/speech/transcribe", files={"audio": ("a", b"x", content_type)}, headers=AUTH)
    assert r.status_code == 415
    ErrorEnvelope.model_validate(r.json())
    assert r.json()["error"]["code"] == "unsupported_media_type"


def test_transcribe_size_limit() -> None:
    limit = 10 * 1024 * 1024
    ok = client.post("/v1/speech/transcribe", files={"audio": ("a", b"\0" * limit, "audio/wav")}, headers=AUTH)
    assert ok.status_code == 200
    big = client.post("/v1/speech/transcribe", files={"audio": ("a", b"\0" * (limit + 1), "audio/wav")}, headers=AUTH)
    assert big.status_code == 413
    assert big.json()["error"]["code"] == "payload_too_large"


def test_oversized_body_is_refused_before_it_is_read() -> None:
    r = client.post("/v1/speech/transcribe", files={"audio": ("a", b"\0" * (MAX_BODY_BYTES + 1), "audio/wav")},
                    headers={**AUTH, "X-Request-ID": "rid-1"})
    assert r.status_code == 413
    assert r.headers["X-Request-ID"] == "rid-1"


def test_transcribe_rejects_a_malformed_language() -> None:
    r = client.post("/v1/speech/transcribe", files=AUDIO, data={"language": "../etc"}, headers=AUTH)
    assert r.status_code == 422


def test_openapi_shows_contract() -> None:
    spec = client.get("/openapi.json").json()
    assert {p for p, _, _ in ROUTES} <= set(spec["paths"])
    assert {"ParseResult", "ClassifyRoomsResult", "TranscribeResult"} <= set(spec["components"]["schemas"])


LLM_SETTINGS: dict[str, Any] = dict(environment="test", internal_service_token=TOKEN, llm_api_key="k", llm_model="m",
                                    llm_base_url="http://gateway.test/v1")
MODELS = "http://gateway.test/v1/models"


def test_readyz_disabled_and_lazy() -> None:
    body = TestClient(create_app(Settings(environment="test"))).get("/readyz").json()
    assert body == {"status": "ok", "llm": "disabled", "stt": "lazy"}


def test_readyz_rules_mode_is_offline_even_when_configured() -> None:
    settings = Settings(**{**LLM_SETTINGS, "command_parser": "rules"})
    assert TestClient(create_app(settings)).get("/readyz").json()["llm"] == "disabled"


@respx.mock
@pytest.mark.parametrize("response,expected", [
    (httpx.Response(200, json={"object": "list", "data": []}), "configured"),
    (httpx.Response(401, json={}), "configured"),
    (httpx.ConnectError("down"), "unreachable"),
])
def test_readyz_probes_the_gateway(response: Any, expected: str) -> None:
    respx.get(MODELS).mock(side_effect=[response])
    r = TestClient(create_app(Settings(**LLM_SETTINGS))).get("/readyz")
    assert r.status_code == 200
    assert r.json()["llm"] == expected


@respx.mock
def test_hybrid_end_to_end_with_gateway_down_is_not_5xx() -> None:
    respx.post("http://gateway.test/v1/chat/completions").mock(side_effect=httpx.ConnectError("down"))
    c = TestClient(create_app(Settings(**LLM_SETTINGS)))
    r = c.post("/v1/commands/parse", json={"instruction": "make it nicer", "brief": BRIEF}, headers=AUTH)
    assert r.status_code == 200
    assert (r.json()["status"], r.json()["provider"]) == ("UNKNOWN", "rules")


@respx.mock
def test_hybrid_end_to_end_llm_answer_validates() -> None:
    answer = {"operation": "DELETE_DOOR", "target_query": "front door"}
    respx.post("http://gateway.test/v1/chat/completions").mock(return_value=httpx.Response(200, json={
        "id": "x", "object": "chat.completion", "created": 1, "model": "groq/x",
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": json.dumps(answer)}}]}))
    c = TestClient(create_app(Settings(**LLM_SETTINGS)))
    r = c.post("/v1/commands/parse", json={"instruction": "get that entry door out", "brief": BRIEF}, headers=AUTH)
    result = ParseResult.model_validate(r.json())
    assert (result.status, result.provider, result.model, result.command) == ("PARSED", "llm", "groq/x", answer)

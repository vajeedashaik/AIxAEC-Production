"""Transcribe and Bedrock providers. Nothing here touches real AWS."""

import json
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import boto3
import httpx
import pytest
import respx
from botocore.exceptions import ClientError
from botocore.stub import ANY, Stubber
from pydantic import ValidationError

from app import speech_transcribe
from app.config import Settings
from app.errors import ServiceError
from app.llm import BREAKER_THRESHOLD, LlmClient, LlmParser, LlmUnavailable
from app.llm_bedrock import BedrockLlmClient
from app.parsers import HybridParser, build_llm_client
from app.speech import build_speech
from app.speech_transcribe import TranscribeSpeech

from .test_llm import BRIEF
from .test_speech import wav_bytes

REGION = "ap-south-1"
URI = "https://transcripts.test/out.json"
ERROR = ClientError({"Error": {"Code": "Throttled", "Message": "secret detail"}}, "Op")


def settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = {"environment": "test", "aws_region": REGION, "s3_bucket": "aec-test"}
    return Settings(_env_file=None, **{**defaults, **overrides})


# --- Transcribe ---

@pytest.fixture
def speech(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TranscribeSpeech, Stubber, MagicMock]]:
    monkeypatch.setattr(speech_transcribe, "POLL_SECONDS", 0)
    client = boto3.client("transcribe", region_name=REGION)
    s3 = MagicMock()
    with Stubber(client) as stub:
        yield TranscribeSpeech(settings(stt_provider="transcribe"), client, s3), stub, s3


def job(status: str, **extra: Any) -> dict[str, Any]:
    return {"TranscriptionJob": {"TranscriptionJobStatus": status, **extra}}


def expect_start(stub: Stubber) -> None:
    stub.add_response("start_transcription_job", {}, {
        "TranscriptionJobName": ANY, "LanguageCode": "en-IN", "MediaFormat": "wav", "MediaSampleRateHertz": 16000,
        "Media": {"MediaFileUri": ANY}})


def test_transcribe_returns_text_and_cleans_up(speech: tuple[TranscribeSpeech, Stubber, MagicMock]) -> None:
    service, stub, s3 = speech
    expect_start(stub)
    stub.add_response("get_transcription_job", job("IN_PROGRESS"))
    stub.add_response("get_transcription_job", job("COMPLETED", Transcript={"TranscriptFileUri": URI}))
    stub.add_response("delete_transcription_job", {})
    with respx.mock() as router:
        router.get(URI).respond(200, json={"results": {"transcripts": [{"transcript": " move the wall "}]}})
        result = service.transcribe(wav_bytes(1), "en")
    assert (result.text, result.language, result.provider) == ("move the wall", "en", "transcribe")
    assert result.duration_ms > 0
    uploaded = s3.put_object.call_args.kwargs
    assert uploaded["Key"].startswith("tmp/speech/") and uploaded["Body"].startswith(b"RIFF")
    s3.delete_object.assert_called_once()
    stub.assert_no_pending_responses()


def test_transcribe_failed_job_is_503_and_cleans_up(speech: tuple[TranscribeSpeech, Stubber, MagicMock]) -> None:
    service, stub, s3 = speech
    expect_start(stub)
    stub.add_response("get_transcription_job", job("FAILED", FailureReason="bad media"))
    stub.add_response("delete_transcription_job", {})
    with pytest.raises(ServiceError) as caught:
        service.transcribe(wav_bytes(1), "en")
    assert caught.value.status == 503
    assert "bad media" not in (caught.value.message or "")
    s3.delete_object.assert_called_once()
    stub.assert_no_pending_responses()


def test_transcribe_deadline_is_503(speech: tuple[TranscribeSpeech, Stubber, MagicMock],
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    service, stub, _ = speech
    monkeypatch.setattr(speech_transcribe, "JOB_DEADLINE_SECONDS", 0)
    expect_start(stub)
    stub.add_response("delete_transcription_job", {})
    with pytest.raises(ServiceError) as caught:
        service.transcribe(wav_bytes(1), "en")
    assert caught.value.status == 503


def test_transcribe_upload_failure_starts_no_job(speech: tuple[TranscribeSpeech, Stubber, MagicMock]) -> None:
    service, stub, s3 = speech
    s3.put_object.side_effect = ERROR
    with pytest.raises(ServiceError) as caught:
        service.transcribe(wav_bytes(1), "en")
    assert caught.value.status == 503
    stub.assert_no_pending_responses()


def test_transcribe_transcript_download_failure_is_503(speech: tuple[TranscribeSpeech, Stubber, MagicMock]) -> None:
    service, stub, _ = speech
    expect_start(stub)
    stub.add_response("get_transcription_job", job("COMPLETED", Transcript={"TranscriptFileUri": URI}))
    stub.add_response("delete_transcription_job", {})
    with respx.mock() as router, pytest.raises(ServiceError) as caught:
        router.get(URI).mock(return_value=httpx.Response(403))
        service.transcribe(wav_bytes(1), "en")
    assert caught.value.status == 503


def test_transcribe_rejects_unknown_language(speech: tuple[TranscribeSpeech, Stubber, MagicMock]) -> None:
    service, _, s3 = speech
    with pytest.raises(ServiceError) as caught:
        service.transcribe(wav_bytes(1), "xx")
    assert caught.value.status == 422
    s3.put_object.assert_not_called()


def test_transcribe_bad_audio_uploads_nothing(speech: tuple[TranscribeSpeech, Stubber, MagicMock]) -> None:
    service, _, s3 = speech
    with pytest.raises(ServiceError) as caught:
        service.transcribe(b"not audio", "en")
    assert caught.value.status == 415
    s3.put_object.assert_not_called()


def test_build_speech_selects_transcribe() -> None:
    assert build_speech(settings(stt_provider="transcribe")).status == "configured"


@pytest.mark.parametrize(("overrides", "missing"), [
    ({"stt_provider": "transcribe", "aws_region": None}, "AWS_REGION"),
    ({"stt_provider": "transcribe", "s3_bucket": None}, "S3_BUCKET"),
    ({"llm_provider": "bedrock", "aws_region": None}, "AWS_REGION"),
])
def test_switches_refuse_to_start_without_their_settings(overrides: dict[str, Any], missing: str) -> None:
    with pytest.raises(ValidationError, match=missing):
        settings(**overrides)


# --- Bedrock ---

def bedrock(**overrides: Any) -> tuple[BedrockLlmClient, Stubber]:
    client = BedrockLlmClient(settings(llm_provider="bedrock", llm_model="test.model", llm_timeout_seconds=5,
                                       **overrides))
    return client, Stubber(client._client)


def converse_reply(text: str) -> dict[str, Any]:
    return {"output": {"message": {"role": "assistant", "content": [{"text": text}]}}, "stopReason": "end_turn",
            "usage": {"inputTokens": 1, "outputTokens": 2, "totalTokens": 3}, "metrics": {"latencyMs": 5}}


def test_bedrock_separates_system_and_returns_content() -> None:
    client, stub = bedrock()
    stub.add_response("converse", converse_reply("hello"), {
        "modelId": "test.model", "system": [{"text": "be brief"}],
        "messages": [{"role": "user", "content": [{"text": "hi"}]}], "inferenceConfig": {"maxTokens": ANY}})
    with stub:
        assert client.complete([{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}],
                               json_mode=True) == ("hello", "test.model")
    stub.assert_no_pending_responses()


def test_bedrock_errors_are_unavailable_and_trip_the_breaker() -> None:
    client, stub = bedrock()
    for _ in range(BREAKER_THRESHOLD):
        stub.add_client_error("converse", "ThrottlingException")
    with stub:
        for _ in range(BREAKER_THRESHOLD):
            with pytest.raises(LlmUnavailable):
                client.complete([{"role": "user", "content": "hi"}])
        with pytest.raises(LlmUnavailable, match="circuit open"):
            client.complete([{"role": "user", "content": "hi"}])


def test_bedrock_expired_deadline_makes_no_call() -> None:
    client, stub = bedrock()
    with stub, pytest.raises(LlmUnavailable):
        client.complete([{"role": "user", "content": "hi"}], deadline=0.0)


def test_bedrock_output_is_still_validated_as_untrusted() -> None:
    client, stub = bedrock()
    command = {"operation": "DELETE_WALL", "target_query": "wall between kitchen and bedroom"}
    stub.add_response("converse", converse_reply(f"Sure!\n{json.dumps(command)}"))
    with stub:
        result = LlmParser(client).parse("knock down the kitchen-bedroom wall", BRIEF)
    assert result.status == "PARSED" and result.provider == "llm"


def test_hybrid_falls_back_to_rules_when_bedrock_fails() -> None:
    client, stub = bedrock()
    stub.add_client_error("converse", "AccessDeniedException")
    stub.add_client_error("converse", "AccessDeniedException")
    with stub:
        result = HybridParser(LlmParser(client)).parse("do something odd with the plan", BRIEF)
    assert result.provider == "rules" and result.status == "UNKNOWN"


def test_build_llm_client_picks_the_provider() -> None:
    chosen = build_llm_client(settings(llm_provider="bedrock", llm_model="test.model"))
    assert isinstance(chosen, BedrockLlmClient)
    assert chosen.probe() == "configured"
    assert type(build_llm_client(settings(llm_model="m", llm_api_key="k"))) is LlmClient
    assert build_llm_client(settings(llm_model="m")) is None


def test_bedrock_llm_mode_needs_no_api_key() -> None:
    assert settings(command_parser="llm", llm_provider="bedrock", llm_model="m").llm_api_key is None
    with pytest.raises(ValidationError):
        settings(command_parser="llm", llm_model="m")

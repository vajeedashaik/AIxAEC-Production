"""Amazon Transcribe behind SpeechService. Batch API, so expect seconds of latency: STT_PROVIDER=whisper is faster."""

import io
import logging
import time
import wave
from typing import Any
from uuid import uuid4

import boto3
import httpx
import numpy as np
from aec_contracts import ErrorCode, TranscribeResult
from botocore.exceptions import BotoCoreError, ClientError

from .config import Settings
from .errors import ServiceError
from .speech import MAX_TRANSCRIPT_CHARS, SAMPLE_RATE, decode_audio

log = logging.getLogger("language.transcribe")

LANGUAGE_CODES = {"en": "en-IN"}
JOB_DEADLINE_SECONDS = 75.0  # under the API's 90 s transcribe timeout
POLL_SECONDS = 1.0


class _JobFailed(Exception):
    pass


def _wav(samples: np.ndarray[Any, np.dtype[np.float32]]) -> bytes:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(pcm)
    return buffer.getvalue()


class TranscribeSpeech:
    status = "configured"

    def __init__(self, settings: Settings, transcribe: Any = None, s3: Any = None) -> None:
        assert settings.s3_bucket  # Settings refuses the switch without it
        self._bucket = settings.s3_bucket
        self._transcribe = transcribe or boto3.client("transcribe", region_name=settings.aws_region)
        self._s3 = s3 or boto3.client("s3", region_name=settings.aws_region)

    def transcribe(self, audio: bytes, language: str) -> TranscribeResult:
        code = LANGUAGE_CODES.get(language)
        if code is None:
            raise ServiceError(422, ErrorCode.VALIDATION_ERROR, "Unsupported language.")
        samples = decode_audio(audio)  # same limits and errors as Whisper, before anything leaves the service
        name = f"aec-{uuid4().hex}"
        key = f"tmp/speech/{name}.wav"
        started = False
        try:
            self._s3.put_object(Bucket=self._bucket, Key=key, Body=_wav(samples), ContentType="audio/wav")
            self._transcribe.start_transcription_job(
                TranscriptionJobName=name, LanguageCode=code, MediaFormat="wav", MediaSampleRateHertz=SAMPLE_RATE,
                Media={"MediaFileUri": f"s3://{self._bucket}/{key}"})
            started = True
            text = self._read_transcript(self._wait(name))
        except (BotoCoreError, ClientError, httpx.HTTPError, KeyError, IndexError, ValueError, _JobFailed) as exc:
            log.warning("transcribe_failed", extra={"fields": {"error": type(exc).__name__}})
            raise ServiceError(503, ErrorCode.UPSTREAM_UNAVAILABLE, "Speech service is unavailable.") from exc
        finally:
            self._clean_up(key, name if started else None)
        return TranscribeResult(text=text.strip()[:MAX_TRANSCRIPT_CHARS], language=language,
                                duration_ms=round(samples.size / SAMPLE_RATE * 1000), provider="transcribe")

    def _wait(self, name: str) -> str:
        deadline = time.monotonic() + JOB_DEADLINE_SECONDS
        while time.monotonic() < deadline:
            job = self._transcribe.get_transcription_job(TranscriptionJobName=name)["TranscriptionJob"]
            status = job["TranscriptionJobStatus"]
            if status == "COMPLETED":
                return str(job["Transcript"]["TranscriptFileUri"])
            if status == "FAILED":
                raise _JobFailed(job.get("FailureReason", "unknown"))
            time.sleep(POLL_SECONDS)
        raise _JobFailed("deadline exceeded")

    def _read_transcript(self, uri: str) -> str:
        response = httpx.get(uri, timeout=10)
        response.raise_for_status()
        return str(response.json()["results"]["transcripts"][0]["transcript"])

    def _clean_up(self, key: str, job_name: str | None) -> None:
        try:
            self._s3.delete_object(Bucket=self._bucket, Key=key)
            if job_name:
                self._transcribe.delete_transcription_job(TranscriptionJobName=job_name)
        except (BotoCoreError, ClientError):
            log.warning("transcribe_cleanup_failed")  # the bucket's 1-day tmp/ expiry is the backstop

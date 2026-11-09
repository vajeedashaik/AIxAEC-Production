"""Speech-to-text: local faster-whisper, or a deterministic stub for tests."""

import io
import logging
import threading
from typing import Any, Protocol

import av
import numpy as np
from aec_contracts import MAX_AUDIO_SECONDS, ErrorCode, TranscribeResult

from .config import Settings
from .errors import ServiceError

log = logging.getLogger("language.speech")

SAMPLE_RATE = 16000
MAX_TRANSCRIPT_CHARS = 500
DOMAIN_PROMPT = ("wall, door, window, room, kitchen, bedroom, bathroom, living room, hallway, office, millimetres, "
                 "centimetres, metres, pixels, move left, move right, move up, move down, north, south, east, west, "
                 "resize, expand, shrink, rename, delete, add, scale.")
STUB_TRANSCRIPT = "move the wall between the kitchen and the living room 300 mm left"


class SpeechService(Protocol):
    @property
    def status(self) -> str: ...  # /readyz: loaded | lazy | stub

    def transcribe(self, audio: bytes, language: str) -> TranscribeResult: ...


def decode_audio(data: bytes) -> np.ndarray[Any, np.dtype[np.float32]]:
    """Any container PyAV knows (so Safari's audio/mp4 works) → 16 kHz mono float32. Enforces the duration limit.

    Decodes as it counts, unlike faster_whisper.decode_audio: browser recordings often carry no duration header, and
    10 MiB of compressed silence would expand to gigabytes before anything could check the length. (It also passes an
    option PyAV 19 removed, which is why we always hand Whisper a decoded array.)
    """
    limit = MAX_AUDIO_SECONDS * SAMPLE_RATE
    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    chunks: list[Any] = []
    total = 0

    def take(frame: av.AudioFrame | None) -> None:
        nonlocal total
        for out in resampler.resample(frame):
            array = out.to_ndarray()
            total += array.size
            if total > limit:
                raise ServiceError(413, ErrorCode.PAYLOAD_TOO_LARGE, f"Audio is longer than {MAX_AUDIO_SECONDS} s.")
            chunks.append(array)

    try:
        with av.open(io.BytesIO(data), mode="r") as container:
            for packet in container.demux(audio=0):
                try:
                    frames = packet.decode()
                except av.InvalidDataError:  # one corrupt packet in a recording shouldn't lose the rest
                    continue
                for frame in frames:
                    frame.pts = None
                    take(frame)
            take(None)
    except (av.FFmpegError, IndexError, ValueError) as exc:  # not audio, or no audio stream
        raise ServiceError(415, ErrorCode.UNSUPPORTED_MEDIA_TYPE, "Could not decode the audio.") from exc
    if not total:
        raise ServiceError(415, ErrorCode.UNSUPPORTED_MEDIA_TYPE, "The audio contains no sound data.")
    return np.concatenate(chunks, axis=None).astype(np.float32) / 32768.0


class WhisperSpeech:
    def __init__(self, settings: Settings) -> None:
        self.model_name = settings.whisper_model
        self.compute_type = settings.whisper_compute_type
        self._model: Any = None
        self._lock = threading.Lock()

    @property
    def status(self) -> str:
        return "loaded" if self._model is not None else "lazy"

    def _get_model(self) -> Any:
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel  # heavy, and unused when STT_PROVIDER=stub

                try:
                    self._model = WhisperModel(self.model_name, device="cpu", compute_type=self.compute_type)
                except Exception as exc:  # the first run downloads the model; a network failure lands here
                    log.exception("whisper_load_failed")
                    raise ServiceError(503, ErrorCode.UPSTREAM_UNAVAILABLE, "Speech model is unavailable.") from exc
            return self._model

    def transcribe(self, audio: bytes, language: str) -> TranscribeResult:
        samples = decode_audio(audio)
        model = self._get_model()
        try:
            segments, info = model.transcribe(samples, language=language, vad_filter=True,
                                              initial_prompt=DOMAIN_PROMPT)
            text = " ".join(s.text.strip() for s in segments).strip()  # segments is lazy: this runs the model
        except ValueError as exc:  # a language code Whisper doesn't know
            raise ServiceError(422, ErrorCode.VALIDATION_ERROR, "Unsupported language.") from exc
        return TranscribeResult(text=text[:MAX_TRANSCRIPT_CHARS], language=info.language,
                                duration_ms=round(samples.size / SAMPLE_RATE * 1000), provider="whisper")


class StubSpeech:
    status = "stub"

    def transcribe(self, audio: bytes, language: str) -> TranscribeResult:
        return TranscribeResult(text=STUB_TRANSCRIPT, language=language, duration_ms=1000, provider="stub")


def build_speech(settings: Settings) -> SpeechService:
    if settings.stt_provider == "transcribe":
        from .speech_transcribe import TranscribeSpeech  # imports this module's helpers

        return TranscribeSpeech(settings)
    return StubSpeech() if settings.stt_provider == "stub" else WhisperSpeech(settings)

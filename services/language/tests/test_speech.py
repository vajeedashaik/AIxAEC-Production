import io
import wave
from types import SimpleNamespace
from typing import Any

import av
import numpy as np
import pytest

from app.config import Settings
from app.errors import ServiceError
from app.speech import STUB_TRANSCRIPT, StubSpeech, WhisperSpeech, build_speech, decode_audio


def wav_bytes(seconds: float, rate: int = 8000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\0\0" * int(seconds * rate))
    return buffer.getvalue()


def mp4_bytes(seconds: float = 1.0) -> bytes:
    """What Safari's MediaRecorder sends: AAC in MP4."""
    buffer = io.BytesIO()
    with av.open(buffer, mode="w", format="mp4") as container:
        stream = container.add_stream("aac", rate=16000)
        samples = np.zeros((1, int(seconds * 16000)), dtype=np.float32)
        frame = av.AudioFrame.from_ndarray(samples, format="fltp", layout="mono")
        frame.sample_rate = 16000
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    return buffer.getvalue()


def test_stub_is_deterministic() -> None:
    result = StubSpeech().transcribe(b"anything", "en")
    assert (result.text, result.provider, result.language) == (STUB_TRANSCRIPT, "stub", "en")


def test_build_speech_selection() -> None:
    assert build_speech(Settings(environment="test", stt_provider="stub")).status == "stub"
    assert build_speech(Settings(environment="test")).status == "lazy"


def test_decode_resamples_to_16k_mono() -> None:
    samples = decode_audio(wav_bytes(2))
    assert samples.dtype == np.float32
    assert abs(samples.size - 32000) < 100


def test_decode_safari_mp4() -> None:
    assert abs(decode_audio(mp4_bytes()).size - 16000) < 3000


def test_decode_enforces_duration_without_a_header() -> None:
    decode_audio(wav_bytes(59))
    with pytest.raises(ServiceError) as err:
        decode_audio(wav_bytes(61))
    assert err.value.status == 413


@pytest.mark.parametrize("data", [b"", b"RIFF", b"\x00\x01garbage" * 100])
def test_decode_rejects_non_audio(data: bytes) -> None:
    with pytest.raises(ServiceError) as err:
        decode_audio(data)
    assert err.value.status == 415


class FakeModel:
    def __init__(self, text: str = " move left ") -> None:
        self.text, self.kwargs = text, {}  # type: dict[str, Any]

    def transcribe(self, audio: Any, **kwargs: Any) -> tuple[Any, Any]:
        self.kwargs = kwargs
        return iter([SimpleNamespace(text=self.text), SimpleNamespace(text=" now")]), SimpleNamespace(language="en")


def test_whisper_uses_vad_and_domain_prompt_and_clips() -> None:
    speech = WhisperSpeech(Settings(environment="test"))
    speech._model = fake = FakeModel("x" * 600)
    result = speech.transcribe(wav_bytes(2), "en")
    assert fake.kwargs["vad_filter"] is True and "millimetres" in fake.kwargs["initial_prompt"]
    assert len(result.text) == 500 and result.provider == "whisper"
    assert abs(result.duration_ms - 2000) < 50
    assert speech.status == "loaded"


def test_whisper_unknown_language_is_422() -> None:
    class Rejects(FakeModel):
        def transcribe(self, audio: Any, **kwargs: Any) -> tuple[Any, Any]:
            raise ValueError("'zz' is not a valid language code")

    speech = WhisperSpeech(Settings(environment="test"))
    speech._model = Rejects()
    with pytest.raises(ServiceError) as err:
        speech.transcribe(wav_bytes(1), "zz")
    assert err.value.status == 422


def test_whisper_load_failure_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    import faster_whisper

    def boom(*_: Any, **__: Any) -> None:
        raise OSError("no network")

    monkeypatch.setattr(faster_whisper, "WhisperModel", boom)
    with pytest.raises(ServiceError) as err:
        WhisperSpeech(Settings(environment="test")).transcribe(wav_bytes(1), "en")
    assert err.value.status == 503


@pytest.mark.slow
def test_real_whisper_on_silence() -> None:
    from faster_whisper import WhisperModel

    settings = Settings(environment="test")
    try:
        model = WhisperModel(settings.whisper_model, device="cpu", compute_type=settings.whisper_compute_type,
                             local_files_only=True)
    except Exception:
        pytest.skip("whisper model isn't cached")
    speech = WhisperSpeech(settings)
    speech._model = model
    result = speech.transcribe(wav_bytes(1), "en")
    assert result.language == "en" and abs(result.duration_ms - 1000) < 50

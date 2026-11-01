import copy
import json
import shutil
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
import pytest
from aec_contracts import AnalyzeOptions, AnalyzeResult

from app.config import Settings
from app.ocr.base import OcrWord
from app.pipeline.runner import run_pipeline
from app.vision.preprocess import Preprocessed, preprocess
from app.vision.walls import WallDetection, detect_walls

FIXTURES = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "fixtures"
sys.path.insert(0, str(FIXTURES))  # synthetic_plan is a plain module, not part of the contracts package

import synthetic_plan as sp  # noqa: E402

FLOORPLAN_ID = UUID("11111111-2222-3333-4444-555555555555")
TOKEN = "test-token"
SETTINGS = Settings(environment="test", ocr_provider="stub", internal_service_token=TOKEN)  # type: ignore[arg-type]

needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract binary not on PATH")


def fixture_model(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data


def word(text: str, cx: float, cy: float) -> OcrWord:
    width = 16.0 * len(text)
    return OcrWord(text, cx - width / 2, cy - 10, width, 20, 0.95)


class ScriptedOCR:
    """Stands in for Tesseract: the words the synthetic plan draws, where it draws them."""

    name = "scripted"

    def __init__(self, words: list[OcrWord]) -> None:
        self.words = words

    def recognize(self, gray: Any) -> list[OcrWord]:
        return self.words


APARTMENT_WORDS = [
    word("LIVING", 350, 325),
    word("KITCHEN", 780, 325),
    word("BEDROOM", 1130, 325),
    word("HALL", 520, 625),
    word("BATH", 1130, 800),
    word("3600", 780, 36),
]


def two_room_with_openings() -> np.ndarray:
    """The two-room plan plus a door in the interior wall and a window in the top wall."""
    model = copy.deepcopy(fixture_model("two_room.model.json"))
    model["doors"] = [{"bbox": {"x": 495, "y": 250, "width": 10, "height": 90}, "swing": "LEFT"}]
    model["windows"] = [{"bbox": {"x": 250, "y": 90, "width": 120, "height": 20}}]  # bridge limit: 14 % of 1000
    return sp._render(model, seed=11, extras=False)


def pre_and_walls(image: np.ndarray) -> tuple[Preprocessed, WallDetection]:
    pre = preprocess(image, 2400)
    return pre, detect_walls(pre.binary, pre.fine)


def analyze_png(image: np.ndarray, options: AnalyzeOptions | None = None) -> AnalyzeResult:
    return run_pipeline(sp.to_png(image), "image/png", FLOORPLAN_ID, options, SETTINGS)


@pytest.fixture(scope="session")
def two_room() -> tuple[Preprocessed, WallDetection]:
    return pre_and_walls(sp.make_two_room_plan())


@pytest.fixture(scope="session")
def apartment() -> tuple[Preprocessed, WallDetection]:
    return pre_and_walls(sp.make_apartment_plan())

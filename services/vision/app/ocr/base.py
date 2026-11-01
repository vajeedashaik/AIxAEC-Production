"""OCR provider interface."""

from dataclasses import dataclass
from typing import Protocol

from app.vision.decode import Gray


@dataclass(frozen=True)
class OcrWord:
    text: str
    x: float
    y: float
    width: float
    height: float
    confidence: float = 1.0

    @property
    def centre(self) -> tuple[float, float]:
        return self.x + self.width / 2, self.y + self.height / 2


class OCRService(Protocol):
    name: str

    def recognize(self, gray: Gray) -> list[OcrWord]: ...

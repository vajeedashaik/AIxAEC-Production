"""OCR fallback: sees no text, so rooms stay unlabelled and the scale stays unknown."""

from app.vision.decode import Gray

from .base import OcrWord


class StubOCR:
    name = "stub"

    def recognize(self, gray: Gray) -> list[OcrWord]:
        return []

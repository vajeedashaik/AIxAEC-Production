"""Tesseract via pytesseract. Sparse-text mode: plans have scattered labels, not paragraphs."""

import pytesseract  # type: ignore[import-untyped]

from app.vision.decode import Gray

from .base import OcrWord

TIMEOUT_SECONDS = 30


class TesseractOCR:
    name = "tesseract"

    def __init__(self, cmd: str | None = None) -> None:
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd

    def recognize(self, gray: Gray) -> list[OcrWord]:
        data = pytesseract.image_to_data(
            gray, config="--psm 11", output_type=pytesseract.Output.DICT, timeout=TIMEOUT_SECONDS
        )
        words = []
        for text, x, y, w, h, conf in zip(
            data["text"], data["left"], data["top"], data["width"], data["height"], data["conf"], strict=True
        ):
            if text.strip() and float(conf) >= 0:
                words.append(OcrWord(text.strip(), float(x), float(y), float(w), float(h), float(conf) / 100))
        return words

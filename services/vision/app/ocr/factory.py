"""Pick the OCR provider. `auto` degrades to the stub when Tesseract isn't installed."""

import shutil

from .base import OCRService
from .stub import StubOCR
from .tesseract import TesseractOCR
from .textract import TextractOCR


def tesseract_available(cmd: str | None) -> bool:
    return shutil.which(cmd or "tesseract") is not None


def get_ocr(provider: str, tesseract_cmd: str | None = None) -> OCRService:
    if provider == "textract":
        return TextractOCR()
    if provider == "stub" or (provider == "auto" and not tesseract_available(tesseract_cmd)):
        return StubOCR()
    return TesseractOCR(tesseract_cmd)

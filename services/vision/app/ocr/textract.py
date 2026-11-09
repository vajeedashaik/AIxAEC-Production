"""Amazon Textract. Errors aren't caught here: run_stage turns them into a degraded OCR stage."""

import os
from functools import lru_cache
from typing import Any

import boto3
import cv2

from app.vision.decode import Gray

from .base import OcrWord

MAX_IMAGE_BYTES = 10_485_760  # the DetectDocumentText limit in botocore's model
JPEG_QUALITY = 85


@lru_cache
def _default_client() -> Any:
    return boto3.client("textract", region_name=os.environ.get("AWS_REGION"))


def _encode(gray: Gray) -> bytes:
    data = cv2.imencode(".png", gray)[1].tobytes()
    if len(data) <= MAX_IMAGE_BYTES:
        return data
    return cv2.imencode(".jpg", gray, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])[1].tobytes()


class TextractOCR:
    name = "textract"

    def __init__(self, client: Any = None) -> None:
        self._client = client  # no network or client here: /readyz builds this just to read .name

    def recognize(self, gray: Gray) -> list[OcrWord]:
        client = self._client or _default_client()
        response = client.detect_document_text(Document={"Bytes": _encode(gray)})
        height, width = gray.shape[:2]
        words = []
        for block in response["Blocks"]:
            if block["BlockType"] != "WORD":
                continue
            box = block["Geometry"]["BoundingBox"]  # fractions of the page
            words.append(OcrWord(block["Text"], box["Left"] * width, box["Top"] * height, box["Width"] * width,
                                 box["Height"] * height, block["Confidence"] / 100))
        return words

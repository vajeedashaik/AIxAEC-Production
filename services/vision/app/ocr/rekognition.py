"""Amazon Rekognition DetectText, the OCR that works on a Free Plan account (Textract doesn't).
Errors aren't caught here: run_stage turns them into a degraded OCR stage."""

import os
from functools import lru_cache
from typing import Any

import boto3
import cv2

from app.vision.decode import Gray

from .base import OcrWord

MAX_IMAGE_BYTES = 5_242_880  # the DetectText limit for inline bytes
JPEG_QUALITY = 85


@lru_cache
def _default_client() -> Any:
    return boto3.client("rekognition", region_name=os.environ.get("AWS_REGION"))


def _encode(gray: Gray) -> bytes:
    data = cv2.imencode(".png", gray)[1].tobytes()
    if len(data) <= MAX_IMAGE_BYTES:
        return data
    return cv2.imencode(".jpg", gray, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])[1].tobytes()


class RekognitionOCR:
    name = "rekognition"

    def __init__(self, client: Any = None) -> None:
        self._client = client  # no network or client here: /readyz builds this just to read .name

    # shortcut: DetectText returns at most 100 words per image,
    # so a label-heavy plan loses some; tile the image if that shows up.
    def recognize(self, gray: Gray) -> list[OcrWord]:
        client = self._client or _default_client()
        response = client.detect_text(Image={"Bytes": _encode(gray)})
        height, width = gray.shape[:2]
        words = []
        for d in response["TextDetections"]:
            if d["Type"] != "WORD":
                continue
            box = d["Geometry"]["BoundingBox"]  # fractions of the image
            words.append(OcrWord(d["DetectedText"], box["Left"] * width, box["Top"] * height, box["Width"] * width,
                                 box["Height"] * height, d["Confidence"] / 100))
        return words

"""Textract provider and the Lambda entry point. Nothing here touches real AWS."""

from collections.abc import Iterator
from typing import Any
from uuid import UUID

import boto3
import numpy as np
import pytest
from aec_contracts import AnalyzeResult, StageReport
from aec_contracts.vision import STAGE_NAMES
from botocore.stub import ANY, Stubber
from moto import mock_aws

from app.lambda_handler import handler
from app.ocr import textract
from app.ocr.factory import get_ocr
from app.ocr.rekognition import RekognitionOCR
from app.ocr.textract import TextractOCR

BUCKET = "aec-test"
FLOORPLAN = "11111111-1111-1111-1111-111111111111"
IMAGE = np.zeros((200, 400), dtype=np.uint8)


def block(kind: str, text: str) -> dict[str, Any]:
    box = {"Left": 0.25, "Top": 0.5, "Width": 0.1, "Height": 0.05}
    return {"BlockType": kind, "Text": text, "Confidence": 90.0, "Geometry": {"BoundingBox": box}}


def recognize(blocks: list[dict[str, Any]]) -> list[Any]:
    client = boto3.client("textract", region_name="ap-south-1")
    with Stubber(client) as stub:
        stub.add_response("detect_document_text", {"Blocks": blocks}, {"Document": {"Bytes": ANY}})
        return TextractOCR(client).recognize(IMAGE)


def test_words_are_converted_to_pixels_and_lines_ignored() -> None:
    words = recognize([block("LINE", "KITCHEN 3600"), block("WORD", "KITCHEN")])
    assert len(words) == 1
    word = words[0]
    assert (word.text, word.x, word.y, word.width, word.height) == ("KITCHEN", 100.0, 100.0, 40.0, 10.0)
    assert word.confidence == pytest.approx(0.9)


def test_no_text_gives_no_words() -> None:
    assert recognize([]) == []


def test_oversized_png_falls_back_to_jpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    assert textract._encode(IMAGE).startswith(b"\x89PNG")
    monkeypatch.setattr(textract, "MAX_IMAGE_BYTES", 1)
    assert textract._encode(IMAGE).startswith(b"\xff\xd8")


def test_factory_builds_it_without_touching_the_network() -> None:
    assert get_ocr("textract").name == "textract"


def test_rekognition_words_are_converted_to_pixels_and_lines_ignored() -> None:
    def det(kind: str, text: str) -> dict[str, Any]:
        box = {"Left": 0.25, "Top": 0.5, "Width": 0.1, "Height": 0.05}
        return {"Type": kind, "DetectedText": text, "Confidence": 90.0, "Geometry": {"BoundingBox": box}}

    client = boto3.client("rekognition", region_name="ap-south-1")
    with Stubber(client) as stub:
        stub.add_response("detect_text", {"TextDetections": [det("LINE", "KITCHEN 3600"), det("WORD", "KITCHEN")]},
                          {"Image": {"Bytes": ANY}})
        words = RekognitionOCR(client).recognize(IMAGE)
    assert [(w.text, w.x, w.y, w.width, w.height) for w in words] == [("KITCHEN", 100.0, 100.0, 40.0, 10.0)]
    assert words[0].confidence == pytest.approx(0.9)
    assert get_ocr("rekognition").name == "rekognition"


@pytest.fixture
def s3(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


def event(content_type: str = "image/png") -> dict[str, str]:
    return {"bucket": BUCKET, "source_key": "tmp/x/source", "result_key": "tmp/x/result.json",
            "content_type": content_type, "floorplan_id": FLOORPLAN}


def test_handler_stores_the_result_and_returns_its_key(s3: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[bytes, str | None, UUID]] = []

    def pipeline(data: bytes, content_type: str | None, floorplan_id: UUID) -> AnalyzeResult:
        seen.append((data, content_type, floorplan_id))
        stages = [StageReport(name=name, status="skipped", duration_ms=0) for name in STAGE_NAMES]  # type: ignore[arg-type]
        return AnalyzeResult(status="FAILED", model=None, stages=stages, warnings=[], error="stage failed")

    monkeypatch.setattr("app.lambda_handler.run_pipeline", pipeline)
    s3.put_object(Bucket=BUCKET, Key="tmp/x/source", Body=b"plan")
    assert handler(event(), None, s3) == {"result_key": "tmp/x/result.json"}
    assert seen == [(b"plan", "image/png", UUID(FLOORPLAN))]
    stored = s3.get_object(Bucket=BUCKET, Key="tmp/x/result.json")["Body"].read()
    assert AnalyzeResult.model_validate_json(stored).error == "stage failed"


def test_handler_reports_undecodable_input(s3: Any) -> None:
    s3.put_object(Bucket=BUCKET, Key="tmp/x/source", Body=b"not an image")
    reply = handler(event(), None, s3)
    assert set(reply) == {"error"}
    assert s3.list_objects_v2(Bucket=BUCKET, Prefix="tmp/x/result")["KeyCount"] == 0

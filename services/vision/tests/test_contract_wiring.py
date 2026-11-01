import json
import uuid
from typing import Any

import pymupdf
from aec_contracts import AnalyzeResult
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

from .conftest import SETTINGS, TOKEN, sp

client = TestClient(create_app(SETTINGS))
HEADERS = {"X-Internal-Token": TOKEN}
FLOORPLAN_ID = str(uuid.uuid4())
FORM = {"floorplan_id": FLOORPLAN_ID}


def plan_file() -> dict[str, tuple[str, bytes, str]]:
    return {"file": ("plan.png", sp.to_png(sp.make_two_room_plan()), "image/png")}


def post(files: dict[str, Any], data: dict[str, str] | None = None, headers: dict[str, str] = HEADERS) -> Any:
    return client.post("/v1/analyze", data=FORM if data is None else data, files=files, headers=headers)


def test_analyze_requires_internal_token() -> None:
    for headers in ({}, {"X-Internal-Token": "wrong"}):
        r = post(plan_file(), headers=headers)
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "unauthorized"


def test_analyze_returns_the_contract() -> None:
    r = post(plan_file())
    assert r.status_code == 200, r.text
    result = AnalyzeResult.model_validate(r.json())
    assert result.status == "COMPLETED"
    assert result.model is not None
    assert str(result.model.floorplan_id) == FLOORPLAN_ID
    assert len(result.model.rooms) == 2
    assert r.headers["X-Request-ID"]


def test_analyze_validates_multipart() -> None:
    r = post(plan_file(), data={"floorplan_id": "nope"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    r = client.post("/v1/analyze", data=FORM, headers=HEADERS)
    assert r.status_code == 422


def test_options_are_validated() -> None:
    for bad in ("{not json", '{"max_dimension": -1}', '{"surprise": true}'):
        r = post(plan_file(), data={**FORM, "options": bad})
        assert r.status_code == 422, bad
        assert r.json()["error"]["code"] == "validation_error"
    r = post(plan_file(), data={**FORM, "options": json.dumps({"ocr": False})})
    assert r.status_code == 200
    assert next(s for s in r.json()["stages"] if s["name"] == "ocr")["status"] == "skipped"


def test_size_limit() -> None:
    small = TestClient(
        create_app(
            Settings(
                environment="test",
                internal_service_token=TOKEN,  # type: ignore[arg-type]
                ocr_provider="stub",
                max_upload_bytes=100,
            )
        )
    )
    r = small.post("/v1/analyze", data=FORM, files=plan_file(), headers=HEADERS)
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"


def test_unsupported_type_uses_the_envelope() -> None:
    r = post({"file": ("plan.txt", b"hello", "text/plain")})
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "unsupported_media_type"


def test_corrupt_image_uses_the_envelope() -> None:
    r = post({"file": ("plan.png", b"\x89PNG\r\n\x1a\ncorrupt", "image/png")})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert "Traceback" not in r.text


def test_encrypted_pdf_uses_the_envelope() -> None:
    doc = pymupdf.open()
    doc.new_page()
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")
    r = post({"file": ("plan.pdf", data, "application/pdf")})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_failed_analysis_is_still_200(monkeypatch: Any) -> None:
    def boom(*_: Any) -> Any:
        raise RuntimeError("internal detail C:/secret")

    monkeypatch.setattr("app.pipeline.stages.detect_walls", boom)
    r = post(plan_file())
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "FAILED" and body["model"] is None
    assert body["error"] == "Processing failed at stage 'wall_detection'."
    assert "secret" not in r.text


def test_openapi_shows_contract() -> None:
    spec = client.get("/openapi.json").json()
    assert "/v1/analyze" in spec["paths"]
    assert "AnalyzeResult" in spec["components"]["schemas"]

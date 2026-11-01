import base64
import json
import logging
import time
from typing import Any

import cv2
import numpy as np
import pymupdf
import pytest
from aec_contracts import AnalyzeOptions, AnalyzeResult, CalibrationSource, FloorPlanModel, RoomType, polygon_area

from app.config import Settings
from app.ocr.factory import get_ocr
from app.ocr.stub import StubOCR
from app.pipeline import stages
from app.pipeline.runner import run_pipeline
from app.vision.assemble import link_walls_to_rooms

from .conftest import APARTMENT_WORDS, FLOORPLAN_ID, SETTINGS, ScriptedOCR, analyze_png, needs_tesseract, sp


def scripted(monkeypatch: pytest.MonkeyPatch, words: list[Any]) -> None:
    monkeypatch.setattr(stages, "get_ocr", lambda *_: ScriptedOCR(words))


@pytest.fixture(scope="module")
def apartment_result() -> AnalyzeResult:
    with pytest.MonkeyPatch.context() as mp:
        scripted(mp, APARTMENT_WORDS)
        return analyze_png(sp.make_apartment_plan())


def test_apartment_end_to_end(apartment_result: AnalyzeResult) -> None:
    assert apartment_result.status == "COMPLETED"
    assert [s.status for s in apartment_result.stages] == ["ok"] * 8
    model = apartment_result.model
    assert model is not None
    assert model.summary().model_dump() == {
        "walls": 10,
        "doors": 4,
        "windows": 3,
        "columns": 0,
        "stairs": 1,
        "furniture": 0,
        "dimensions": 1,
        "rooms": 5,
    }
    assert {r.label_text: r.room_type for r in model.rooms} == {
        "LIVING": RoomType.LIVING_ROOM,
        "KITCHEN": RoomType.KITCHEN,
        "BEDROOM": RoomType.BEDROOM,
        "HALL": RoomType.HALLWAY,
        "BATH": RoomType.BATHROOM,
    }
    assert model.coordinate_system.mm_per_pixel == pytest.approx(10.0, rel=0.05)
    assert model.coordinate_system.calibration_source == CalibrationSource.DIMENSION_OCR


def test_openings_bound_to_their_walls(apartment_result: AnalyzeResult) -> None:
    model = apartment_result.model
    assert model is not None
    walls = {w.id: w for w in model.walls}
    for op in [*model.doors, *model.windows]:
        assert op.wall_id in walls
        wall = walls[op.wall_id]
        cx, cy = op.bbox.x + op.bbox.width / 2, op.bbox.y + op.bbox.height / 2
        assert min(abs(cy - wall.start.y), abs(cx - wall.start.x)) <= 2
        short_side = min(op.bbox.width, op.bbox.height)
        assert wall.thickness_px == short_side  # bbox spans the wall's real thickness


def test_every_room_is_linked_to_its_walls(apartment_result: AnalyzeResult) -> None:
    model = apartment_result.model
    assert model is not None
    for room in model.rooms:
        assert room.area_px == pytest.approx(polygon_area(room.polygon))
        assert len(room.wall_ids) == len(set(room.wall_ids))
        assert len(room.wall_ids) >= 4
    # The hall's long north wall also bounds living, kitchen and bedroom; it joins all four.
    y550 = next(w.id for w in model.walls if round(w.start.y) == 550 and round(w.end.y) == 550)
    linked = {r.label_text for r in model.rooms if y550 in r.wall_ids}
    assert linked == {"LIVING", "KITCHEN", "BEDROOM", "HALL"}


def test_wall_touching_only_at_its_end_is_not_linked(apartment_result: AnalyzeResult) -> None:
    model = apartment_result.model
    assert model is not None
    partition = next(w.id for w in model.walls if round(w.start.x) == 600 and round(w.end.x) == 600)
    hall = next(r for r in model.rooms if r.label_text == "HALL")
    assert partition not in hall.wall_ids


def test_linking_keeps_existing_ids_without_duplicates(apartment_result: AnalyzeResult) -> None:
    model = apartment_result.model
    assert model is not None
    before = [list(r.wall_ids) for r in model.rooms]
    link_walls_to_rooms(model.walls, model.rooms)
    assert [list(r.wall_ids) for r in model.rooms] == before


def test_response_validates_and_artifacts_decode(apartment_result: AnalyzeResult) -> None:
    round_tripped = AnalyzeResult.model_validate_json(apartment_result.model_dump_json())
    assert round_tripped.model is not None
    assert [s.name for s in round_tripped.stages] == [
        "preprocess",
        "wall_detection",
        "ocr",
        "object_detection",
        "room_detection",
        "calibration",
        "semantic_assembly",
        "artifacts",
    ]
    artifacts = {a.kind: base64.b64decode(a.data_base64) for a in apartment_result.artifacts}
    assert set(artifacts) == {"preprocessed", "walls_overlay", "detected_elements", "semantic_model"}
    for kind in ("preprocessed", "walls_overlay"):
        assert artifacts[kind].startswith(b"\x89PNG")
        assert len(artifacts[kind]) <= 2 * 1024 * 1024
    assert FloorPlanModel.model_validate_json(artifacts["semantic_model"]) == apartment_result.model
    assert len(json.loads(artifacts["detected_elements"])["walls"]) == 10


def test_identical_runs_give_identical_json(monkeypatch: pytest.MonkeyPatch) -> None:
    scripted(monkeypatch, APARTMENT_WORDS)
    a, b = analyze_png(sp.make_apartment_plan()), analyze_png(sp.make_apartment_plan())
    assert a.model is not None and b.model is not None
    assert a.model.model_dump_json() == b.model.model_dump_json()
    assert [x.model_dump() for x in a.artifacts] == [x.model_dump() for x in b.artifacts]
    assert [(s.name, s.status, s.detail) for s in a.stages] == [(s.name, s.status, s.detail) for s in b.stages]


def test_ids_derive_from_the_floorplan_id() -> None:
    from uuid import uuid4

    png = sp.to_png(sp.make_two_room_plan())
    a = run_pipeline(png, "image/png", uuid4(), None, SETTINGS).model
    b = run_pipeline(png, "image/png", uuid4(), None, SETTINGS).model
    assert a is not None and b is not None
    assert a.floorplan_id != b.floorplan_id
    assert {w.id for w in a.walls}.isdisjoint(w.id for w in b.walls)


def test_ocr_failure_degrades_and_completes(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    class Broken:
        name = "broken"

        def recognize(self, gray: Any) -> list[Any]:
            raise RuntimeError("tesseract at C:/secret/path crashed")

    monkeypatch.setattr(stages, "get_ocr", lambda *_: Broken())
    with caplog.at_level(logging.ERROR):
        result = analyze_png(sp.make_two_room_plan())
    assert result.status == "COMPLETED" and result.model is not None
    ocr = next(s for s in result.stages if s.name == "ocr")
    assert ocr.status == "degraded"
    assert "secret" not in result.model_dump_json()
    assert "secret" in caplog.text  # the full error goes to the log
    assert len(result.model.rooms) == 2  # rooms still found, just unlabelled
    assert result.model.coordinate_system.mm_per_pixel is None


def test_object_detector_failure_keeps_gap_openings(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_: Any) -> Any:
        raise RuntimeError("no weights")

    monkeypatch.setattr(stages, "get_detector", boom)
    result = analyze_png(sp.make_apartment_plan())
    assert result.status == "COMPLETED" and result.model is not None
    assert next(s for s in result.stages if s.name == "object_detection").status == "degraded"
    assert len(result.model.doors) == 4 and len(result.model.windows) == 3


def test_overlay_failure_keeps_other_artifacts(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_: Any) -> Any:
        raise RuntimeError("draw failed")

    monkeypatch.setattr(stages, "render_overlay", boom)
    result = analyze_png(sp.make_two_room_plan())
    assert result.status == "COMPLETED"
    assert next(s for s in result.stages if s.name == "artifacts").status == "degraded"
    assert {a.kind for a in result.artifacts} == {"preprocessed", "detected_elements", "semantic_model"}


@pytest.mark.parametrize(
    "target,name",
    [("detect_walls", "wall_detection"), ("build_model", "semantic_assembly"), ("preprocess", "preprocess")],
)
def test_critical_failure_stops_with_a_safe_message(monkeypatch: pytest.MonkeyPatch, target: str, name: str) -> None:
    def boom(*_: Any, **__: Any) -> Any:
        raise RuntimeError("cv2 blew up at C:/secret/path/file.py")

    monkeypatch.setattr(stages, target, boom)
    result = analyze_png(sp.make_two_room_plan())
    assert result.status == "FAILED" and result.model is None
    assert result.error == f"Processing failed at stage '{name}'."
    assert "secret" not in result.model_dump_json()
    statuses = {s.name: s.status for s in result.stages}
    assert statuses[name] == "failed"
    order = [s.name for s in result.stages]
    assert all(statuses[n] == "skipped" for n in order[order.index(name) + 1 :])
    assert result.artifacts == []


def test_options_can_skip_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    scripted(monkeypatch, APARTMENT_WORDS)
    result = analyze_png(sp.make_apartment_plan(), AnalyzeOptions(ocr=False, object_detection=False))
    statuses = {s.name: s.status for s in result.stages}
    assert statuses["ocr"] == "skipped" and statuses["object_detection"] == "skipped"
    assert result.model is not None
    assert result.model.stairs == []
    assert all(r.label_text is None for r in result.model.rooms)
    assert not any("OCR is unavailable" in w for w in result.warnings)


def test_max_dimension_option_shrinks_the_coordinate_system() -> None:
    result = analyze_png(sp.make_apartment_plan(), AnalyzeOptions(max_dimension=1000, ocr=False))
    assert result.model is not None
    assert result.model.coordinate_system.image_width == 1000


def test_blank_page_completes_with_warning_not_failure() -> None:
    result = analyze_png(np.full((400, 400), 255, np.uint8))
    assert result.status == "COMPLETED" and result.model is not None
    assert next(s for s in result.stages if s.name == "wall_detection").status == "degraded"
    assert result.model.walls == []
    assert any("No walls" in w for w in result.warnings)


def test_multi_page_pdf_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = pymupdf.open()
    png = sp.to_png(sp.make_two_room_plan())
    for _ in range(3):
        doc.new_page(width=1000, height=600).insert_image(pymupdf.Rect(0, 0, 1000, 600), stream=png)
    result = run_pipeline(doc.tobytes(), "application/pdf", FLOORPLAN_ID, None, SETTINGS)
    assert "Only page 1 of 3 was processed." in result.warnings
    assert result.model is not None and len(result.model.rooms) == 2


def test_auto_without_tesseract_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _: None)
    settings = Settings(environment="test", ocr_provider="auto")
    assert isinstance(get_ocr("auto"), StubOCR)
    result = run_pipeline(sp.to_png(sp.make_two_room_plan()), "image/png", FLOORPLAN_ID, None, settings)
    assert result.status == "COMPLETED"
    assert any("OCR is unavailable" in w for w in result.warnings)


def test_performance_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    scripted(monkeypatch, APARTMENT_WORDS)
    start = time.perf_counter()
    analyze_png(sp.make_apartment_plan())
    assert time.perf_counter() - start < 6.0


def test_jpeg_input_finds_the_same_structure() -> None:
    ok, jpg = cv2.imencode(".jpg", sp.make_apartment_plan(), [cv2.IMWRITE_JPEG_QUALITY, 90])
    assert ok
    result = run_pipeline(jpg.tobytes(), "image/jpeg", FLOORPLAN_ID, AnalyzeOptions(ocr=False), SETTINGS)
    assert result.model is not None
    assert len(result.model.rooms) == 5 and len(result.model.walls) == 10


@needs_tesseract
def test_real_tesseract_reads_the_apartment() -> None:
    settings = Settings(environment="test", ocr_provider="tesseract")
    result = run_pipeline(sp.to_png(sp.make_apartment_plan()), "image/png", FLOORPLAN_ID, None, settings)
    assert result.model is not None
    assert next(s for s in result.stages if s.name == "ocr").status == "ok"
    assert sorted(r.label_text or "" for r in result.model.rooms) == ["BATH", "BEDROOM", "HALL", "KITCHEN", "LIVING"]
    assert {r.room_type for r in result.model.rooms} == {
        RoomType.BATHROOM,
        RoomType.BEDROOM,
        RoomType.HALLWAY,
        RoomType.KITCHEN,
        RoomType.LIVING_ROOM,
    }
    assert result.model.coordinate_system.mm_per_pixel == pytest.approx(10.0, rel=0.05)

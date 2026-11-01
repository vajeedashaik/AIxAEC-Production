import cv2
import numpy as np
import pytest
from aec_contracts import CalibrationSource

from app.ocr.base import OcrWord
from app.ocr.parsing import parse_dimension
from app.vision.calibrate import estimate_scale, read_dimensions
from app.vision.objects import HeuristicObjectDetector, NullObjectDetector, Swing, get_detector, reconcile_openings
from app.vision.preprocess import Preprocessed
from app.vision.walls import Opening, Segment, WallDetection

from .conftest import fixture_model, pre_and_walls, word


def detect(pre: Preprocessed, walls: WallDetection):  # type: ignore[no-untyped-def]
    return HeuristicObjectDetector().detect(pre.gray, pre.fine, walls)


def test_swings_found_and_reconciled_onto_gap_doors(apartment: tuple[Preprocessed, WallDetection]) -> None:
    pre, walls = apartment
    objects = detect(pre, walls)
    doors = [o for o in reconcile_openings(objects.swings, walls.openings, walls.walls) if o.kind == "door"]
    assert len(doors) == 4  # swings don't add doors: each one duplicates a gap
    expected = {
        (round(d["bbox"]["x"] + d["bbox"]["width"] / 2), round(d["bbox"]["y"] + d["bbox"]["height"] / 2)): d["swing"]
        for d in fixture_model("apartment.model.json")["doors"]
    }
    for door in doors:
        centre = ((door.x1 + door.x2) / 2, (door.y1 + door.y2) / 2)
        key = min(expected, key=lambda c: abs(c[0] - centre[0]) + abs(c[1] - centre[1]))
        assert door.swing == expected[key], key


def test_stairs_detected_and_window_glazing_is_not_a_stair(apartment: tuple[Preprocessed, WallDetection]) -> None:
    objects = detect(*apartment)
    assert len(objects.stairs) == 1
    stair = objects.stairs[0]
    assert abs(stair.x - 650) <= 3 and abs(stair.y - 565) <= 3
    assert abs(stair.width - 200) <= 5 and abs(stair.height - 120) <= 5


def test_hatched_room_has_no_false_objects(apartment: tuple[Preprocessed, WallDetection]) -> None:
    objects = detect(*apartment)
    assert objects.columns == []
    # Hatching fills the bath (y > 710); only the bath door's own swing may hinge there.
    assert not [s for s in objects.swings if s.y > 720]


def test_column_detected() -> None:
    img = np.full((800, 1000), 255, np.uint8)
    cv2.rectangle(img, (100, 100), (900, 700), 0, 20)
    cv2.rectangle(img, (480, 380), (530, 430), 0, -1)
    objects = detect(*pre_and_walls(img))
    assert len(objects.columns) == 1
    assert abs(objects.columns[0].x - 480) <= 2 and abs(objects.columns[0].width - 51) <= 2


def _wall() -> Segment:
    return Segment(100, 100, 900, 100, 20)


def test_swing_with_no_wall_at_its_hinge_is_dropped() -> None:
    far = Swing(400, 400, 90, 1, 1)
    assert reconcile_openings([far], [], [_wall()]) == []


def test_swing_on_solid_wall_becomes_a_door() -> None:
    hinge = Swing(300, 110, 90, 1, 1)
    out = reconcile_openings([hinge], [], [_wall()])
    assert [o.kind for o in out] == ["door"]
    assert out[0].swing == "LEFT" and abs(out[0].width - 90) < 1


def test_swing_over_gap_only_sets_handedness() -> None:
    gap = Opening("door", 300, 100, 390, 100, 20)
    out = reconcile_openings([Swing(390, 110, 90, -1, 1)], [gap], [_wall()])
    assert len(out) == 1 and out[0].swing == "RIGHT"


def test_swing_over_window_gap_does_not_turn_it_into_a_door() -> None:
    gap = Opening("window", 300, 100, 390, 100, 20)
    out = reconcile_openings([Swing(390, 110, 90, -1, 1)], [gap], [_wall()])
    assert len(out) == 1 and out[0].kind == "window" and out[0].swing is None


def test_detector_factory() -> None:
    assert isinstance(get_detector("none"), NullObjectDetector)
    assert isinstance(get_detector("heuristic"), HeuristicObjectDetector)


@pytest.mark.parametrize(
    "text,mm",
    [
        ("3600", 3600.0),
        ("100", 100.0),
        ("100000", 100_000.0),
        ("3,600", 3600.0),
        ("3.6 m", 3600.0),
        ("3.6m", 3600.0),
        ("360 cm", 3600.0),
        ("3600 mm", 3600.0),
        ("3600MM", 3600.0),
        ("12'-6\"", 3810.0),
        ("12' 6\"", 3810.0),
        ("12ft 6in", 3810.0),
        ("12'", 3657.6),
        ('6"', 152.4),
        ("12’-6”", 3810.0),
    ],
)
def test_parse_dimension(text: str, mm: float) -> None:
    value = parse_dimension(text)
    assert value == pytest.approx(mm)


@pytest.mark.parametrize("text", ["", "99", "100001", "BEDROOM", "2", "12x4", "0 m", "A3", "-3600", "'", "1.5"])
def test_parse_dimension_rejects(text: str) -> None:
    assert parse_dimension(text) is None


def test_scale_uses_the_bay_not_the_merged_wall(apartment: tuple[Preprocessed, WallDetection]) -> None:
    """The top wall merges to 1200 px, but "3600" labels the kitchen's 360 px bay."""
    cal = estimate_scale([word("3600", 780, 36)], apartment[1].walls)
    assert cal.mm_per_pixel == pytest.approx(10.0, rel=0.05)
    assert cal.source == CalibrationSource.DIMENSION_OCR
    assert cal.confidence == pytest.approx(0.45)
    assert cal.dimensions[0].span_px == pytest.approx(360, abs=5)


def test_no_dimensions_means_no_scale(apartment: tuple[Preprocessed, WallDetection]) -> None:
    cal = estimate_scale([word("KITCHEN", 780, 325)], apartment[1].walls)
    assert cal.mm_per_pixel is None
    assert cal.source == CalibrationSource.UNKNOWN
    assert cal.confidence is None


def test_dimension_far_from_any_wall_is_read_but_not_used(apartment: tuple[Preprocessed, WallDetection]) -> None:
    cal = estimate_scale([word("3600", 700, 1150)], apartment[1].walls)
    assert cal.mm_per_pixel is None
    assert len(cal.dimensions) == 1 and cal.dimensions[0].span_px is None


def test_implausible_ratio_rejected() -> None:
    wall = Segment(0, 100, 1000, 100, 20)
    assert estimate_scale([word("100", 500, 80)], [wall]).mm_per_pixel == pytest.approx(0.1)
    assert estimate_scale([word("100", 500, 80)], [Segment(0, 100, 100000, 100, 20)]).mm_per_pixel is None


def test_median_across_matches_and_confidence_caps(apartment: tuple[Preprocessed, WallDetection]) -> None:
    walls = [
        Segment(0, 100, 1000, 100, 20),
        Segment(0, 400, 1000, 400, 20),
        Segment(0, 700, 1000, 700, 20),
        Segment(0, 1000, 1000, 1000, 20),
    ]
    words = [word("5000", 500, 80), word("5000", 500, 380), word("9000", 500, 680), word("5000", 500, 980)]
    cal = estimate_scale(words, walls)
    assert cal.mm_per_pixel == pytest.approx(5.0)
    assert cal.confidence == pytest.approx(0.8)


def test_split_tokens_rejoin() -> None:
    a = OcrWord("3.6", 100, 100, 30, 12)
    b = OcrWord("m", 134, 100, 12, 12)
    readings = read_dimensions([b, a])
    assert [r.value_mm for r in readings] == [3600.0]
    assert readings[0].text == "3.6 m"


def test_distant_tokens_stay_apart() -> None:
    a = OcrWord("360", 100, 100, 30, 12)
    b = OcrWord("cm", 500, 100, 12, 12)
    assert [r.value_mm for r in read_dimensions([a, b])] == [360.0]

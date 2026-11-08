"""Regressions from measuring the reader on realistic plans: jogged walls, doors at junctions, wide openings, scale."""

import cv2
import numpy as np
import pytest

from app.ocr.base import OcrWord
from app.vision.calibrate import estimate_scale
from app.vision.rooms import detect_rooms
from app.vision.walls import Opening, Segment, _bridge_gaps, _close_doors_at_walls, _on_line_runs, _snap_junctions


def blank(width: int = 800, height: int = 600) -> np.ndarray:
    return np.zeros((height, width), np.uint8)


def test_a_wall_that_jogs_sideways_keeps_both_pieces() -> None:
    centres = np.array([10.0] * 40 + [25.0] * 40)
    assert _on_line_runs(centres, np.ones(80, bool), tol=3.0, min_run=20) == [(0, 40), (40, 80)]


def test_a_stub_past_the_crossing_survives_snapping() -> None:
    side = Segment(100, 0, 100, 200, 20)
    long_stub = next(s for s in _snap_junctions([Segment(0, 100, 122, 100, 20), side]) if s.is_horizontal)
    short_end = next(s for s in _snap_junctions([Segment(0, 100, 108, 100, 20), side]) if s.is_horizontal)
    assert round(long_stub.x2) == 122
    assert round(short_end.x2) == 100


def test_glazed_opening_wider_than_a_door_is_bridged_as_one_wall() -> None:
    fine = blank()
    for y in (95, 105):
        cv2.line(fine, (100, y), (500, y), 255, 1)
    segs, openings = _bridge_gaps([Segment(0, 100, 100, 100, 20), Segment(500, 100, 600, 100, 20)], fine, 200)
    assert len(segs) == 1 and [o.kind for o in openings] == ["window"]


def test_same_wide_gap_with_nothing_in_it_stays_open() -> None:
    segs, openings = _bridge_gaps([Segment(0, 100, 100, 100, 20), Segment(500, 100, 600, 100, 20)], blank(), 200)
    assert len(segs) == 2 and not openings


@pytest.mark.parametrize(("swing_drawn", "reaches_wall"), [(True, True), (False, False)])
def test_door_against_a_side_wall_needs_its_swing(swing_drawn: bool, reaches_wall: bool) -> None:
    fine = blank()
    if swing_drawn:
        cv2.line(fine, (200, 130), (270, 130), 255, 1)  # covers the gap's width, as an arc does
    wall, side = Segment(0, 100, 200, 100, 20), Segment(280, 0, 280, 200, 20)
    segs, openings = _close_doors_at_walls([wall, side], fine)
    end = max(s.x2 for s in segs if s.is_horizontal)
    assert (round(end) == 280) is reaches_wall
    assert [o.kind for o in openings] == (["door"] if swing_drawn else [])


def test_door_opening_keeps_two_rooms_apart() -> None:
    walls = [
        Segment(100, 100, 700, 100, 12),
        Segment(100, 400, 700, 400, 12),
        Segment(100, 100, 100, 400, 12),
        Segment(700, 100, 700, 400, 12),
        Segment(400, 100, 400, 280, 12),
    ]
    door = Opening("door", 400, 280, 400, 400, 12)
    assert len(detect_rooms(walls, (800, 600), [])) == 1
    assert len(detect_rooms(walls, (800, 600), [], [door])) == 2


def test_scale_is_read_from_the_drawn_dimension_line() -> None:
    fine = blank()
    cv2.line(fine, (100, 100), (500, 100), 255, 1)
    calibration = estimate_scale([OcrWord("3600", 280, 55, 40, 30)], [], fine)
    assert calibration.mm_per_pixel == pytest.approx(3600 / 400, rel=0.01)
    assert calibration.dimensions[0].span_px == pytest.approx(400, abs=2)

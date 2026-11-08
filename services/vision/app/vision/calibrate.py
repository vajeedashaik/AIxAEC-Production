"""Scale from OCR dimensions. Never assumes a default: no match means no scale."""

import statistics
from dataclasses import dataclass, field

import numpy as np
from aec_contracts import CalibrationSource

from app.ocr.base import OcrWord
from app.ocr.parsing import parse_dimension

from .decode import Gray
from .walls import Segment

MAX_WALL_DISTANCE_PX = 120.0
MIN_MM_PER_PX = 0.05
MAX_MM_PER_PX = 500.0
LINE_REACH_FACTOR, LINE_MIN_FACTOR = 1.6, 3.0  # in text heights
LINE_CLEARANCE_PX = 5


@dataclass(frozen=True)
class DimensionReading:
    text: str
    value_mm: float
    x: float
    y: float
    span_px: float | None = None
    height: float = 0.0


@dataclass(frozen=True)
class Calibration:
    mm_per_pixel: float | None = None
    confidence: float | None = None
    source: CalibrationSource = CalibrationSource.UNKNOWN
    dimensions: list[DimensionReading] = field(default_factory=list)


def read_dimensions(words: list[OcrWord]) -> list[DimensionReading]:
    """Tesseract splits "3.6 m" and "12ft 6in" in two, so try each word with its right-hand neighbour first."""
    ordered = sorted(words, key=lambda w: (round(w.centre[1] / max(w.height, 1.0)), w.x))
    out = []
    i = 0
    while i < len(ordered):
        word = ordered[i]
        if i + 1 < len(ordered):
            nxt = ordered[i + 1]
            same_line = abs(nxt.centre[1] - word.centre[1]) <= max(word.height, nxt.height) / 2
            if same_line and 0 <= nxt.x - (word.x + word.width) <= 1.5 * max(word.height, nxt.height):
                text = f"{word.text} {nxt.text}"
                value = parse_dimension(text)
                if value is not None:
                    out.append(
                        DimensionReading(
                            text[:80], value, (word.x + nxt.x + nxt.width) / 2, word.centre[1], height=word.height
                        )
                    )
                    i += 2
                    continue
        value = parse_dimension(word.text)
        if value is not None:
            out.append(DimensionReading(word.text[:80], value, *word.centre, height=word.height))
        i += 1
    return out


def wall_span(wall: Segment, x: float, y: float, walls: list[Segment]) -> float:
    """Length of the stretch of `wall` between the junctions either side of (x, y).

    Collinear pieces are merged into one wall, but a dimension describes one bay of it, not the whole façade.
    """
    t = min(max(wall.along(x, y), 0.0), wall.length)
    stops = [0.0, wall.length]
    for other in walls:
        if other is wall:
            continue
        for ex, ey in other.ends:
            if abs(wall.offset(ex, ey)) <= wall.thickness and 0 < wall.along(ex, ey) < wall.length:
                stops.append(wall.along(ex, ey))
    return min(s for s in stops if s >= t) - max(s for s in stops if s <= t)


def _line_run(
    ink: np.ndarray, along: float, across: float, reach: float, min_length: float
) -> tuple[float, float] | None:
    """(distance from the text, length) of the nearest thin horizontal line running past `along`."""
    x, y = round(along), round(across)
    if not 0 <= x < ink.shape[1]:
        return None
    best: tuple[float, float] | None = None
    for r in range(
        max(LINE_CLEARANCE_PX, y - round(reach)), min(ink.shape[0] - LINE_CLEARANCE_PX, y + round(reach) + 1)
    ):
        # Thin means clear ink above and below; that rules out wall faces and the text itself.
        if ink[r - LINE_CLEARANCE_PX, x] or ink[r + LINE_CLEARANCE_PX, x]:
            continue
        row = ink[r - 1 : r + 2].any(axis=0)  # a line can straddle rows after deskew
        if not row[x]:
            continue
        gaps = np.flatnonzero(~row)
        left = int(gaps[gaps < x].max()) + 1 if (gaps < x).any() else 0
        right = int(gaps[gaps > x].min()) if (gaps > x).any() else ink.shape[1]
        if right - left >= min_length and (best is None or abs(r - y) < best[0]):
            best = (float(abs(r - y)), float(right - left))
    return best


def dimension_line_span(fine: Gray, dim: DimensionReading) -> float | None:
    """The drawn dimension line beside the number is what the number actually measures."""
    if dim.height <= 0:
        return None
    reach, min_length = LINE_REACH_FACTOR * dim.height, LINE_MIN_FACTOR * dim.height
    binary = fine > 0
    runs = [_line_run(binary, dim.x, dim.y, reach, min_length), _line_run(binary.T, dim.y, dim.x, reach, min_length)]
    found = [r for r in runs if r is not None]
    return min(found)[1] if found else None


def estimate_scale(words: list[OcrWord], walls: list[Segment], fine: Gray | None = None) -> Calibration:
    readings = []
    ratios = []
    for dim in read_dimensions(words):
        span = dimension_line_span(fine, dim) if fine is not None else None
        if span is None:
            wall = min(walls, key=lambda w: w.distance(dim.x, dim.y), default=None)
            if wall is None or wall.distance(dim.x, dim.y) > MAX_WALL_DISTANCE_PX:
                readings.append(dim)
                continue
            span = wall_span(wall, dim.x, dim.y, walls)
        if span <= 0:
            readings.append(dim)
            continue
        readings.append(DimensionReading(dim.text, dim.value_mm, dim.x, dim.y, span))
        ratio = dim.value_mm / span
        if MIN_MM_PER_PX <= ratio <= MAX_MM_PER_PX:
            ratios.append(ratio)
    if not ratios:
        return Calibration(dimensions=readings)
    return Calibration(
        round(statistics.median(ratios), 4),
        round(min(0.8, 0.3 + 0.15 * len(ratios)), 2),
        CalibrationSource.DIMENSION_OCR,
        readings,
    )

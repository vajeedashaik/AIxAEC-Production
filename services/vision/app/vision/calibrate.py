"""Scale from OCR dimensions. Never assumes a default: no match means no scale."""

import statistics
from dataclasses import dataclass, field

from aec_contracts import CalibrationSource

from app.ocr.base import OcrWord
from app.ocr.parsing import parse_dimension

from .walls import Segment

MAX_WALL_DISTANCE_PX = 120.0
MIN_MM_PER_PX = 0.05
MAX_MM_PER_PX = 500.0


@dataclass(frozen=True)
class DimensionReading:
    text: str
    value_mm: float
    x: float
    y: float
    span_px: float | None = None


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
                    out.append(DimensionReading(text[:80], value, (word.x + nxt.x + nxt.width) / 2, word.centre[1]))
                    i += 2
                    continue
        value = parse_dimension(word.text)
        if value is not None:
            out.append(DimensionReading(word.text[:80], value, *word.centre))
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


def estimate_scale(words: list[OcrWord], walls: list[Segment]) -> Calibration:
    readings = []
    ratios = []
    for dim in read_dimensions(words):
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

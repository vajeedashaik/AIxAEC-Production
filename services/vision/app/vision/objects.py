"""Object detection behind a small interface: door swings, columns, stairs (heuristic) or a YOLO model."""

import math
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Literal, Protocol

import cv2
import numpy as np

from .decode import Gray
from .strokes import Box, compact_blobs, thin_ink
from .walls import BRIDGE_FRACTION, Opening, Segment, WallDetection

SWING_ANGLES = np.radians(np.arange(3, 88, 2))  # dense: hatching can hit a sparse ring by chance, not a dense one
# One quadrant holds the arc; the ring may brush other ink (leaf, hatching) elsewhere.
SWING_MIN_FILL = 0.8
SWING_MAX_OTHER = 0.35
SEARCH_OFFSETS = np.arange(-4, 5)
SEARCH_RADII = np.arange(-3, 4)
HINGE_MARGIN_PX = 6
MIN_TREADS = 4


@dataclass(frozen=True)
class Swing:
    x: float  # hinge
    y: float
    radius: float
    sx: int  # quadrant the arc occupies, as signs in image axes
    sy: int
    score: float = 0.0


@dataclass(frozen=True)
class FurnitureBox:
    box: Box
    category: str | None = None


@dataclass
class Detections:
    swings: list[Swing] = field(default_factory=list)
    columns: list[Box] = field(default_factory=list)
    stairs: list[Box] = field(default_factory=list)
    furniture: list[FurnitureBox] = field(default_factory=list)


class ObjectDetector(Protocol):
    def detect(self, gray: Gray, fine: Gray, walls: WallDetection) -> Detections: ...


def _best_quadrant(ink: Gray, cx: float, cy: float, r: float) -> Swing | None:
    """Search a small neighbourhood: Hough centres are several px off for a 90° arc."""
    h, w = ink.shape
    dx, dy, dr = np.meshgrid(SEARCH_OFFSETS, SEARCH_OFFSETS, SEARCH_RADII, indexing="ij")
    xs0, ys0, rs = cx + dx.ravel(), cy + dy.ravel(), np.maximum(r + dr.ravel(), 1)
    fills = []
    for quadrant in range(4):
        angles = SWING_ANGLES + quadrant * math.pi / 2
        xs = np.rint(xs0[:, None] + rs[:, None] * np.cos(angles)).astype(np.int64)
        ys = np.rint(ys0[:, None] + rs[:, None] * np.sin(angles)).astype(np.int64)
        inside = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
        fills.append(((ink[ys.clip(0, h - 1), xs.clip(0, w - 1)] > 0) & inside).mean(axis=1))
    fill = np.stack(fills, axis=1)
    order = np.sort(fill, axis=1)
    valid = (order[:, 3] >= SWING_MIN_FILL) & (order[:, 2] <= SWING_MAX_OTHER)
    if not valid.any():
        return None
    score = order[:, 3] - order[:, 2]
    i = int(np.argmax(np.where(valid, score, -1.0)))
    q = int(np.argmax(fill[i]))
    sx, sy = ((1, 1), (-1, 1), (-1, -1), (1, -1))[q]
    return Swing(float(xs0[i]), float(ys0[i]), float(rs[i]), sx, sy, float(score[i]))


def detect_swings(thin: Gray, mask: Gray, thickness: float) -> list[Swing]:
    r_min = max(20, round(1.5 * thickness))
    r_max = round(BRIDGE_FRACTION * max(thin.shape))
    blurred = cv2.GaussianBlur(cv2.bitwise_not(thin), (5, 5), 1.0)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1,
        minDist=max(4, r_min // 4),
        param1=100,
        param2=14,
        minRadius=r_min,
        maxRadius=r_max,
    )
    if circles is None:
        return []
    ink = cv2.dilate(thin, np.ones((3, 3), np.uint8))
    # The refinement is costly and hatching yields hundreds of centres: only those near a wall can be a hinge.
    reach = 2 * (SEARCH_OFFSETS[-1] + HINGE_MARGIN_PX) + 1
    near_wall = cv2.dilate(mask, np.ones((reach, reach), np.uint8))
    h, w = thin.shape
    candidates = circles.reshape(-1, circles.shape[-1])[:, :3].tolist()
    found = (
        _best_quadrant(np.asarray(ink, np.uint8), cx, cy, r)
        for cx, cy, r in candidates
        if 0 <= round(cy) < h and 0 <= round(cx) < w and near_wall[round(cy), round(cx)]
    )
    swings: list[Swing] = []
    for s in sorted((s for s in found if s), key=lambda s: (-s.score, s.y, s.x)):
        if all(math.hypot(s.x - o.x, s.y - o.y) > o.radius / 2 for o in swings):
            swings.append(s)
    return sorted(swings, key=lambda s: (s.y, s.x))


def _thin_lines(thin: Gray, thickness: float, horizontal: bool) -> list[tuple[int, int, int]]:
    """Straight axis-aligned thin lines as (position across, start along, end along)."""
    length = max(25, round(1.5 * thickness)) | 1
    # Widen across the line first so a slightly stepped line survives the opening.
    widen, line = ((3, 1), (1, length)) if horizontal else ((1, 3), (length, 1))
    opened = cv2.morphologyEx(cv2.dilate(thin, np.ones(widen, np.uint8)), cv2.MORPH_OPEN, np.ones(line, np.uint8))
    n, _, stats, centroids = cv2.connectedComponentsWithStats(opened, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, _ = (int(v) for v in stats[i])
        if horizontal and h <= 7:
            out.append((round(centroids[i][1]), x, x + w))
        elif not horizontal and w <= 7:
            out.append((round(centroids[i][0]), y, y + h))
    return sorted(out)


def _stair_groups(lines: list[tuple[int, int, int]], thickness: float) -> list[tuple[int, int, int, int]]:
    """Runs of ≥4 evenly spaced parallel lines with matching extents → (pos_lo, pos_hi, start, end)."""
    min_spacing = max(6.0, 0.5 * thickness)  # window glazing is packed tighter than any stair
    groups = []
    used: set[int] = set()
    for i, (_, start, end) in enumerate(lines):
        if i in used:
            continue
        run = [i]
        step: float | None = None
        tolerance = 0.2 * (end - start)
        for j in range(i + 1, len(lines)):
            p, s, e = lines[j]
            if j in used or abs(s - start) > tolerance or abs(e - end) > tolerance:
                continue
            gap = p - lines[run[-1]][0]
            if gap < min_spacing:
                continue
            if step is None:
                step = float(gap)
            elif abs(gap - step) > max(2.0, 0.25 * step):
                break
            run.append(j)
        if len(run) >= MIN_TREADS:
            used.update(run)
            picked = [lines[k] for k in run]
            groups.append((picked[0][0], picked[-1][0], min(p[1] for p in picked), max(p[2] for p in picked)))
    return groups


def detect_stairs(thin: Gray, thickness: float) -> list[Box]:
    out = []
    for lo, hi, start, end in _stair_groups(_thin_lines(thin, thickness, False), thickness):
        out.append(Box(lo, start, hi - lo, end - start))  # vertical treads: the run goes along x
    for lo, hi, start, end in _stair_groups(_thin_lines(thin, thickness, True), thickness):
        out.append(Box(start, lo, end - start, hi - lo))
    return sorted(out, key=lambda b: (b.y, b.x))


class HeuristicObjectDetector:
    def detect(self, gray: Gray, fine: Gray, walls: WallDetection) -> Detections:
        if walls.thickness is None:
            return Detections()
        thin = thin_ink(fine, walls.mask, walls.thickness)
        return Detections(
            swings=detect_swings(thin, walls.mask, walls.thickness),
            columns=compact_blobs(walls.mask, walls.thickness),
            stairs=detect_stairs(thin, walls.thickness),
        )


class NullObjectDetector:
    def detect(self, gray: Gray, fine: Gray, walls: WallDetection) -> Detections:
        return Detections()


class YoloObjectDetector:  # pragma: no cover
    """Optional: needs `ultralytics` (not a dependency) and weights. A missing import degrades the stage."""

    # shortcut: coarse COCO classes → furniture only, train real plan weights to find doors and columns this way.
    FURNITURE = {"chair", "couch", "bed", "dining table", "toilet", "sink", "refrigerator", "oven"}

    def __init__(self, weights: str | None) -> None:
        from ultralytics import YOLO  # type: ignore[import-not-found]

        self.model = YOLO(weights or "yolov8n.pt")

    def detect(self, gray: Gray, fine: Gray, walls: WallDetection) -> Detections:
        result = self.model.predict(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR), verbose=False)[0]
        out = Detections()
        for box, cls in zip(result.boxes.xywh.tolist(), result.boxes.cls.tolist(), strict=True):
            name = result.names[int(cls)]
            if name in self.FURNITURE:
                cx, cy, w, h = box
                out.furniture.append(FurnitureBox(Box(cx - w / 2, cy - h / 2, w, h), name))
        return out


@lru_cache  # YOLO weights take seconds to load; detectors are stateless
def get_detector(name: str, weights: str | None = None) -> ObjectDetector:
    if name == "none":
        return NullObjectDetector()
    if name == "yolo":  # pragma: no cover
        return YoloObjectDetector(weights)
    return HeuristicObjectDetector()


def _overlap_fraction(a: tuple[float, float], b: tuple[float, float]) -> float:
    overlap = min(a[1], b[1]) - max(a[0], b[0])
    return max(0.0, overlap) / max(min(a[1] - a[0], b[1] - b[0]), 1e-6)


def _nearest_wall(x: float, y: float, walls: list[Segment]) -> Segment | None:
    return min(walls, key=lambda w: w.distance(x, y), default=None)


def reconcile_openings(swings: list[Swing], openings: list[Opening], walls: list[Segment]) -> list[Opening]:
    """Drop swings whose hinge isn't on a wall. A swing over a gap only tells us how that door hinges."""
    out = list(openings)
    for swing in swings:
        wall = _nearest_wall(swing.x, swing.y, walls)
        if wall is None or wall.distance(swing.x, swing.y) > wall.thickness / 2 + HINGE_MARGIN_PX:
            continue
        ux, uy = wall.unit
        direction = swing.sx * ux + swing.sy * uy
        hinge_t = wall.along(swing.x, swing.y)
        span = (hinge_t, hinge_t + swing.radius) if direction > 0 else (hinge_t - swing.radius, hinge_t)
        handed: Literal["LEFT", "RIGHT"] = "LEFT" if direction > 0 else "RIGHT"  # hinge at the wall's start / end
        for i, op in enumerate(out):
            ts = sorted((wall.along(op.x1, op.y1), wall.along(op.x2, op.y2)))
            on_wall = wall.distance(op.x1, op.y1) <= wall.thickness and wall.distance(op.x2, op.y2) <= wall.thickness
            if on_wall and _overlap_fraction(span, (ts[0], ts[1])) >= 0.5:
                if op.kind == "door" and op.swing is None:
                    out[i] = replace(op, swing=handed)
                break
        else:
            (x1, y1), (x2, y2) = wall.at(span[0]), wall.at(span[1])
            out.append(Opening("door", x1, y1, x2, y2, wall.thickness, confidence=0.5, swing=handed))
    return out

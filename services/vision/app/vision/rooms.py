"""Rooms are the enclosed free space between walls, with edges on the wall centre-lines."""

import math
import statistics
from dataclasses import dataclass
from itertools import combinations

import cv2
import numpy as np

from app.ocr.base import OcrWord

from .walls import Segment

MIN_AREA_FRACTION = 0.003
MAX_AREA_FRACTION = 0.9
LABEL_MIN_CONFIDENCE = 0.6  # below this Tesseract is mostly reading hatching
Vertex = tuple[float, float]


@dataclass(frozen=True)
class DetectedRoom:
    points: list[Vertex]
    label: str | None = None


def _wall_joints(walls: list[Segment]) -> list[Vertex]:
    joints = [p for w in walls for p in w.ends]
    for a, b in combinations(walls, 2):
        p0, p1 = b.offset(a.x1, a.y1), b.offset(a.x2, a.y2)
        if p0 * p1 < 0:
            x, y = a.at(a.length * p0 / (p0 - p1))
            if 0 <= b.along(x, y) <= b.length:
                joints.append((x, y))
    return joints


def _snap(points: list[Vertex], joints: list[Vertex], reach: float) -> list[Vertex]:
    out: list[Vertex] = []
    for p in points:
        nearest = min(joints, key=lambda j: math.dist(j, p), default=p)
        q = nearest if math.dist(nearest, p) <= reach else p
        if not out or q != out[-1]:
            out.append(q)
    if len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out


def _drop_collinear(points: list[Vertex]) -> list[Vertex]:
    kept = []
    n = len(points)
    for i, (x, y) in enumerate(points):
        ax, ay = points[i - 1]
        bx, by = points[(i + 1) % n]
        # Twice the triangle area over the chord is how far the vertex sits off the straight line.
        off_line = abs((bx - ax) * (y - ay) - (by - ay) * (x - ax)) / max(math.hypot(bx - ax, by - ay), 1e-6)
        if off_line > 1.0:
            kept.append((x, y))
    return kept


def _label(polygon: list[Vertex], words: list[OcrWord]) -> str | None:
    contour = np.array(polygon, np.float32)
    inside = [
        w
        for w in words
        if w.confidence >= LABEL_MIN_CONFIDENCE
        and sum(c.isalpha() for c in w.text) >= 2
        and not any(c.isdigit() for c in w.text)
        and cv2.pointPolygonTest(contour, w.centre, False) >= 0
    ]
    if not inside:
        return None
    line_height = max(statistics.median(w.height for w in inside), 1.0)
    inside.sort(key=lambda w: (round(w.centre[1] / line_height), w.x))  # reading order
    return " ".join(w.text for w in inside)[:80]


def detect_rooms(walls: list[Segment], size: tuple[int, int], words: list[OcrWord]) -> list[DetectedRoom]:
    if not walls:
        return []
    width, height = size
    stroke = max(3, round(statistics.median(w.thickness for w in walls)))
    half = stroke // 2
    canvas = np.zeros((height, width), np.uint8)
    for w in walls:
        cv2.line(canvas, (round(w.x1), round(w.y1)), (round(w.x2), round(w.y2)), 255, stroke)
    closed = cv2.morphologyEx(canvas, cv2.MORPH_CLOSE, np.ones((stroke | 1, stroke | 1), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(cv2.bitwise_not(closed), connectivity=4)
    # Anything reaching the image border is the outside (flooding from border seeds gives the same set).
    exterior = set(np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1])).tolist())
    image_area = width * height
    grow = np.ones((2 * half + 1, 2 * half + 1), np.uint8)
    joints = _wall_joints(walls)
    rooms = []
    for i in range(1, n):  # label 0 is the wall ink
        fraction = stats[i, cv2.CC_STAT_AREA] / image_area
        if i in exterior or not MIN_AREA_FRACTION <= fraction <= MAX_AREA_FRACTION:
            continue
        # Each free-space edge sits half a stroke from its centre-line; grow back to land on it.
        body = cv2.dilate(np.asarray((labels == i) * 255, np.uint8), grow)
        contours, _ = cv2.findContours(body, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contour = max(contours, key=cv2.contourArea)
        approx = cv2.approxPolyDP(contour, 3.0, True).reshape(-1, 2).tolist()
        points = _drop_collinear(_snap([(float(x), float(y)) for x, y in approx], joints, half + 3.0))
        if len(points) >= 3:
            rooms.append(DetectedRoom(points, _label(points, words)))
    return rooms

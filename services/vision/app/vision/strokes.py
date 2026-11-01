"""Stroke-width analysis: how thick are the walls, and which ink belongs to them."""

from dataclasses import dataclass

import cv2
import numpy as np

from .decode import Gray

MIN_WALL_PX = 3


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    width: float
    height: float


def estimate_wall_thickness(binary: Gray) -> float | None:
    """Largest stroke width shared by enough ridge pixels. None for hairline plans (< 3 px)."""
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    ridge = (dist > 0) & (dist >= cv2.dilate(dist, np.ones((3, 3), np.uint8)))
    widths = np.rint(2 * dist[ridge] - 1).astype(np.int64)  # a stroke of width w peaks at (w + 1) / 2
    if widths.size == 0:
        return None
    hist = np.bincount(widths, minlength=3)
    needed = max(30, 0.6 * max(binary.shape))
    for w in range(len(hist) - 1, MIN_WALL_PX - 1, -1):
        window = hist[max(0, w - 1) : w + 2]
        if window.sum() >= needed:
            return float(max(0, w - 1) + int(np.argmax(window)))
    return None


def structural_mask(binary: Gray, thickness: float) -> Gray:
    """Keep strokes near wall width; text, hatching, dimension lines and swings are all thinner."""
    k = max(3, round(0.45 * thickness)) | 1
    kernel = np.ones((k, k), np.uint8)
    opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    return np.asarray(cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel), np.uint8)


def thin_ink(fine: Gray, mask: Gray, thickness: float) -> Gray:
    """Fine ink away from the walls: where swings, treads and glazing live."""
    k = max(3, round(thickness * 0.75))
    return np.asarray(cv2.bitwise_and(fine, cv2.bitwise_not(cv2.dilate(mask, np.ones((k, k), np.uint8)))), np.uint8)


def compact_blobs(mask: Gray, thickness: float) -> list[Box]:
    """Free-standing solid squares between wall width and 4× wall width: columns, not walls."""
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[i])
        if (
            0.7 * thickness <= min(w, h)
            and max(w, h) <= 4 * thickness
            and max(w, h) <= 1.3 * min(w, h)
            and area >= 0.85 * w * h
        ):
            out.append(Box(x, y, w, h))
    return out


def _compact_components(ink: Gray, max_size: float) -> Gray:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    small = np.flatnonzero((stats[:, cv2.CC_STAT_WIDTH] <= max_size) & (stats[:, cv2.CC_STAT_HEIGHT] <= max_size))
    return np.asarray(np.isin(labels, small[small != 0]) * 255, np.uint8)


def text_layer(gray: Gray, fine: Gray, mask: Gray, thickness: float) -> Gray:
    """The plan with only its compact ink left, for OCR. Walls and long lines wreck Tesseract's layout analysis.

    Letters touching hatching join one huge component, so a second pass erases 1 px lines first and recovers them.
    Gray, not binary: thresholding closes the counters of small digits ("3600" reads as "36080").
    """
    ink = thin_ink(fine, mask, thickness * 0.5)
    max_size = max(60.0, 3 * thickness)
    bold = np.asarray(cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)), np.uint8)
    text = cv2.bitwise_or(_compact_components(ink, max_size), _compact_components(bold, max_size))
    keep = cv2.dilate(text, np.ones((3, 3), np.uint8))
    return np.asarray(cv2.GaussianBlur(np.where(keep > 0, gray, 255).astype(np.uint8), (3, 3), 0), np.uint8)

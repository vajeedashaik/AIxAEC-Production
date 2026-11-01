"""Grayscale → denoised, contrast-normalised, deskewed gray plus binary ink masks (ink = 255)."""

import math
from dataclasses import dataclass

import cv2
import numpy as np

from .decode import Gray

DESKEW_MIN_DEG = 0.3
DESKEW_MAX_DEG = 20.0
SOLID_INK = 64  # below this is ink whatever the neighbourhood: stops the local threshold hollowing thick walls


@dataclass(frozen=True)
class Preprocessed:
    gray: Gray
    binary: Gray  # median-blurred: strokes that matter for walls
    fine: Gray  # no median blur, which would erase 1 px lines (glazing, treads, swings)
    deskew_deg: float

    @property
    def size(self) -> tuple[int, int]:
        return self.gray.shape[1], self.gray.shape[0]


def _binarize(gray: Gray) -> tuple[Gray, Gray]:
    block = max(31, max(gray.shape) // 25) | 1  # must span more than a wall or walls come out as outlines
    ink = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, block, 15)
    ink = np.asarray(cv2.bitwise_or(ink, np.asarray((gray < SOLID_INK) * 255, np.uint8)), np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    specks = np.flatnonzero(stats[:, cv2.CC_STAT_AREA] <= 2)
    fine = ink.copy()
    fine[np.isin(labels, specks)] = 0
    return np.asarray(cv2.medianBlur(ink, 3), np.uint8), np.asarray(fine, np.uint8)


def measure_skew(binary: Gray) -> float:
    """Median angle of the long lines, in degrees from the nearest axis. 0.0 when there are none."""
    longest = max(binary.shape)
    edges = cv2.subtract(binary, cv2.erode(binary, np.ones((3, 3), np.uint8)))
    lines = cv2.HoughLinesP(edges, 1, math.pi / 720, threshold=longest // 10, minLineLength=longest // 10, maxLineGap=5)
    if lines is None:
        return 0.0
    angles = []
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        angle = math.degrees(math.atan2(float(y2) - float(y1), float(x2) - float(x1)))
        folded = (angle + 45) % 90 - 45
        if abs(folded) <= DESKEW_MAX_DEG:  # hatching sits near ±45° and must not vote
            angles.append(folded)
    return float(np.median(angles)) if angles else 0.0


def _rotate(gray: Gray, angle: float) -> Gray:
    """Rotate on an expanded canvas so nothing is clipped."""
    h, w = gray.shape
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    nw, nh = round(h * sin + w * cos), round(h * cos + w * sin)
    matrix[0, 2] += nw / 2 - w / 2
    matrix[1, 2] += nh / 2 - h / 2
    return np.asarray(cv2.warpAffine(gray, matrix, (nw, nh), flags=cv2.INTER_LINEAR, borderValue=255), np.uint8)


def preprocess(image: Gray, max_dimension: int) -> Preprocessed:
    h, w = image.shape
    if max(h, w) > max_dimension:
        scale = max_dimension / max(h, w)
        size = (max(1, round(w * scale)), max(1, round(h * scale)))
        image = np.asarray(cv2.resize(image, size, interpolation=cv2.INTER_AREA), np.uint8)
    denoised = cv2.fastNlMeansDenoising(image, None, h=10, templateWindowSize=7, searchWindowSize=21)
    gray = np.asarray(cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(denoised), np.uint8)
    binary, fine = _binarize(gray)
    angle = measure_skew(binary)
    if abs(angle) < DESKEW_MIN_DEG:
        return Preprocessed(gray, binary, fine, 0.0)
    gray = _rotate(gray, angle)
    binary, fine = _binarize(gray)
    return Preprocessed(gray, binary, fine, round(angle, 2))

"""Thickness-aware morphology + Hough wall detector (FULL_PROJECT_CONTEXT §7).

Supports solid / thick-stroke walls. Hairline double-line walls, curved walls and noisy scans are unsupported.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass, replace
from itertools import combinations
from typing import Literal

import cv2
import numpy as np

from .decode import Gray
from .strokes import compact_blobs, estimate_wall_thickness, structural_mask

AXIS_CONFIDENCE = 0.9
DIAGONAL_CONFIDENCE = 0.45
STRAIGHTEN_DEG = 3.0
BRIDGE_FRACTION = 0.14
WIDE_OPENING_FACTOR = 2.0
DOOR_GAP_FACTOR = 6.0  # a door is at most this many wall-widths wide
SWING_COVERAGE = 0.8
TOUCHING_PX = 2.0
THICKNESS_STEP = 1.4  # walls this different in width are different walls, even when collinear


@dataclass(frozen=True)
class Segment:
    x1: float
    y1: float
    x2: float
    y2: float
    thickness: float
    confidence: float = AXIS_CONFIDENCE

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    @property
    def unit(self) -> tuple[float, float]:
        length = self.length or 1.0
        return (self.x2 - self.x1) / length, (self.y2 - self.y1) / length

    @property
    def ends(self) -> tuple[tuple[float, float], tuple[float, float]]:
        return (self.x1, self.y1), (self.x2, self.y2)

    @property
    def angle(self) -> float:
        return math.degrees(math.atan2(self.y2 - self.y1, self.x2 - self.x1)) % 180

    @property
    def is_horizontal(self) -> bool:
        return abs(self.y2 - self.y1) < 1e-6

    @property
    def is_vertical(self) -> bool:
        return abs(self.x2 - self.x1) < 1e-6

    def along(self, x: float, y: float) -> float:
        ux, uy = self.unit
        return (x - self.x1) * ux + (y - self.y1) * uy

    def offset(self, x: float, y: float) -> float:
        ux, uy = self.unit
        return (x - self.x1) * -uy + (y - self.y1) * ux

    def at(self, t: float) -> tuple[float, float]:
        ux, uy = self.unit
        return self.x1 + ux * t, self.y1 + uy * t

    def distance(self, x: float, y: float) -> float:
        t = min(max(self.along(x, y), 0.0), self.length)
        px, py = self.at(t)
        return math.hypot(x - px, y - py)


@dataclass(frozen=True)
class Opening:
    kind: Literal["door", "window"]
    x1: float
    y1: float
    x2: float
    y2: float
    thickness: float
    confidence: float = 0.7
    swing: Literal["LEFT", "RIGHT", "DOUBLE", "SLIDING"] | None = None

    @property
    def width(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)


@dataclass(frozen=True)
class WallDetection:
    walls: list[Segment]
    openings: list[Opening]
    thickness: float | None
    mask: Gray


def _ordered(s: Segment) -> Segment:
    """Start is the top-left end, so equal geometry always gives equal coordinates."""
    if (s.x1, s.y1) > (s.x2, s.y2):
        return replace(s, x1=s.x2, y1=s.y2, x2=s.x1, y2=s.y1)
    return s


def _parallel(a: Segment, b: Segment) -> bool:
    diff = abs(a.angle - b.angle)
    return min(diff, 180 - diff) <= STRAIGHTEN_DEG


def _same_line(a: Segment, b: Segment) -> bool:
    if not _parallel(a, b):
        return False
    base, other = (a, b) if a.length >= b.length else (b, a)
    mx, my = (other.x1 + other.x2) / 2, (other.y1 + other.y2) / 2
    return abs(base.offset(mx, my)) <= max(3.0, min(a.thickness, b.thickness) / 2)


def _gap(a: Segment, b: Segment) -> float:
    """Along-line distance between two collinear segments (negative when they overlap)."""
    ts = sorted(a.along(*p) for p in b.ends)
    return max(ts[0] - a.length, -ts[1])


def _union(a: Segment, b: Segment) -> Segment:
    base = a if a.length >= b.length else b
    ts = [base.along(*p) for p in (*a.ends, *b.ends)]
    (x1, y1), (x2, y2) = base.at(min(ts)), base.at(max(ts))
    return _ordered(replace(base, x1=x1, y1=y1, x2=x2, y2=y2))


def _thickness_runs(counts: np.ndarray, min_run: int) -> list[tuple[int, int]]:
    """Split one straight ink body where its stroke width steps (exterior wall running into an interior one)."""
    n = len(counts)
    lo, hi = np.percentile(counts, [10, 90])
    if hi < THICKNESS_STEP * lo:
        return [(0, n)]
    cuts = [0]
    for c in (np.flatnonzero(np.diff(counts >= (lo + hi) / 2)) + 1).tolist():
        if c - cuts[-1] >= min_run and n - c >= min_run:
            cuts.append(c)
    return list(zip(cuts, [*cuts[1:], n], strict=True))


def _fit_centre_line(
    centres: np.ndarray, remaining: np.ndarray, seed: float, tol: float, min_run: int
) -> tuple[float, np.ndarray] | None:
    """(slope, columns on the line) for the line nearest `seed`, or None if too few columns sit on it."""
    cols = np.arange(len(centres))
    slope, intercept = 0.0, seed
    inliers = remaining
    for _ in range(3):
        inliers = remaining & (np.abs(centres - (slope * cols + intercept)) <= tol)
        if np.count_nonzero(inliers) < min_run:
            return None
        slope, intercept = (float(v) for v in np.polyfit(cols[inliers], centres[inliers], 1))
    return slope, inliers


def _on_line_runs(centres: np.ndarray, valid: np.ndarray, tol: float, min_run: int) -> list[tuple[int, int]]:
    """Column runs whose centre sits on one near-axis line.

    A shallow diagonal survives the axis opening and can join an axis wall's body; its columns drift off the line.
    """
    runs: list[tuple[int, int]] = []
    remaining = valid.copy()
    while np.count_nonzero(remaining) >= min_run:  # a wall that jogs sideways is two lines in one body
        fitted = _fit_centre_line(centres, remaining, float(np.median(centres[remaining])), tol, min_run)
        if fitted is None:  # two equal halves put the median between them, on neither line
            fitted = _fit_centre_line(centres, remaining, float(centres[remaining][0]), tol, min_run)
        if fitted is None:
            return sorted(runs)
        slope, inliers = fitted
        if abs(slope) > math.tan(math.radians(STRAIGHTEN_DEG)):
            return sorted(runs)
        edges = np.diff(np.concatenate(([0], inliers.astype(np.int8), [0])))
        starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
        runs += [(int(a), int(b)) for a, b in zip(starts, ends, strict=True) if b - a >= min_run]
        remaining = remaining & ~inliers
    return sorted(runs)


def _bodies_to_segments(opened: Gray, horizontal: bool, min_length: int) -> list[Segment]:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(opened, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, _ = (int(v) for v in stats[i])
        along_size, across_size = (w, h) if horizontal else (h, w)
        if along_size < min_length or along_size < across_size:
            continue
        ys, xs = np.nonzero(labels[y : y + h, x : x + w] == i)
        along, across = (xs + x, ys + y) if horizontal else (ys + y, xs + x)
        first = int(along.min())
        counts = np.bincount(along - first, minlength=along_size)
        valid = counts > 0
        centres = np.bincount(along - first, weights=across, minlength=along_size) / np.maximum(counts, 1)
        tol = max(2.0, float(np.median(counts[valid])) / 3)
        for run_start, run_end in _on_line_runs(centres, valid, tol, min_length):
            for start, end in _thickness_runs(counts[run_start:run_end], min_length):
                lo, hi = run_start + start, run_start + end
                picked = (along >= first + lo) & (along < first + hi)
                slope, intercept = np.polyfit(along[picked], across[picked], 1)
                a, b = first + lo, first + hi - 1
                ca, cb = float(slope * a + intercept), float(slope * b + intercept)
                thick = float(np.median(counts[lo:hi]))
                seg = Segment(a, ca, b, cb, thick) if horizontal else Segment(ca, a, cb, b, thick)
                out.append(_ordered(seg))
    return out


def _axis_walls(mask: Gray, thickness: float) -> tuple[list[Segment], Gray]:
    # Longer than any wall is wide, short enough to keep stubs by a door. Odd: even kernels shift the result a pixel.
    length = max(3, round(1.5 * thickness)) | 1
    h_mask = np.asarray(cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((1, length), np.uint8)), np.uint8)
    v_mask = np.asarray(cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((length, 1), np.uint8)), np.uint8)
    segs = _bodies_to_segments(h_mask, True, length) + _bodies_to_segments(v_mask, False, length)
    # Ink the accepted walls only, so rejected diagonal columns stay in the residual for Hough.
    axis_ink = np.zeros_like(mask)
    for seg in segs:
        cv2.line(
            axis_ink, (round(seg.x1), round(seg.y1)), (round(seg.x2), round(seg.y2)), 255, max(1, round(seg.thickness))
        )
    return segs, axis_ink


def _diagonal_walls(mask: Gray, axis_ink: Gray, thickness: float) -> list[Segment]:
    k = round(thickness)
    residual = np.asarray(
        cv2.bitwise_and(mask, cv2.bitwise_not(cv2.dilate(axis_ink, np.ones((k, k), np.uint8)))), np.uint8
    )
    core = cv2.erode(residual, np.ones((max(1, k // 3),) * 2, np.uint8))  # reduce the band to its centre line
    lines = cv2.HoughLinesP(core, 1, math.pi / 180, threshold=max(20, 2 * k), minLineLength=3 * k, maxLineGap=k)
    if lines is None:
        return []
    out = []
    for x1, y1, x2, y2 in lines.reshape(-1, 4).tolist():
        seg = _ordered(Segment(x1, y1, x2, y2, thickness, DIAGONAL_CONFIDENCE))
        folded = (seg.angle + 45) % 90 - 45
        if abs(folded) <= STRAIGHTEN_DEG:
            continue  # sliver of an axis wall the opening missed
        # The residual was cut back from the axis walls and the core eroded: give that length back so snap can reach.
        (ax, ay), (bx, by) = seg.at(-thickness / 3), seg.at(seg.length + thickness / 3)
        out.append(_ordered(replace(seg, x1=max(ax, 0), y1=max(ay, 0), x2=max(bx, 0), y2=max(by, 0))))
    # Hough finds several lines inside one band: keep the longest, drop any lying within a wall width of it.
    kept: list[Segment] = []
    for seg in sorted(out, key=lambda s: (-s.length, s.y1, s.x1)):
        if not any(_parallel(seg, k) and max(k.distance(*p) for p in seg.ends) <= thickness for k in kept):
            kept.append(seg)
    return [_recentre(seg, residual) for seg in kept]


def _recentre(seg: Segment, band: Gray) -> Segment:
    """Hough's 1° bins and edge-following leave the line off-centre: least-squares fit it to the band's pixels."""
    ys, xs = np.nonzero(band)
    ux, uy = seg.unit
    along = (xs - seg.x1) * ux + (ys - seg.y1) * uy
    offset = (xs - seg.x1) * -uy + (ys - seg.y1) * ux
    near = (np.abs(offset) <= seg.thickness) & (along >= 0) & (along <= seg.length)
    if np.count_nonzero(near) < 10:
        return seg
    pts = np.stack((xs[near], ys[near]), axis=1).astype(np.float64)
    centre = pts.mean(axis=0)
    direction = np.linalg.svd(pts - centre, full_matrices=False)[2][0]
    ts = [float(np.dot(np.array(p) - centre, direction)) for p in seg.ends]
    (x1, y1), (x2, y2) = (centre + t * direction for t in ts)
    return _ordered(
        replace(seg, x1=max(float(x1), 0), y1=max(float(y1), 0), x2=max(float(x2), 0), y2=max(float(y2), 0))
    )


def _straighten(s: Segment) -> Segment:
    angle = s.angle
    if min(angle, 180 - angle) <= STRAIGHTEN_DEG:
        y = (s.y1 + s.y2) / 2
        return _ordered(replace(s, y1=y, y2=y))
    if abs(angle - 90) <= STRAIGHTEN_DEG:
        x = (s.x1 + s.x2) / 2
        return _ordered(replace(s, x1=x, x2=x))
    return s


def _merge_collinear(segs: list[Segment]) -> list[Segment]:
    segs = sorted(segs, key=lambda s: (s.y1, s.x1, s.y2, s.x2))
    while True:
        for i, j in combinations(range(len(segs)), 2):
            a, b = segs[i], segs[j]
            similar = max(a.thickness, b.thickness) < THICKNESS_STEP * min(a.thickness, b.thickness)
            if similar and _same_line(a, b) and _gap(a, b) <= TOUCHING_PX:
                segs[i] = _union(a, b)
                del segs[j]
                break
        else:
            return segs


def _snap_tolerance(a: Segment, b: Segment) -> float:
    return (a.thickness + b.thickness) / 2 + 3


def _junction_on(point: tuple[float, float], seg: Segment, others: Iterable[Segment]) -> Segment | None:
    """The non-parallel wall this end of `seg` runs into, if any."""
    best, best_dist = None, math.inf
    for other in others:
        if other is seg or _parallel(seg, other):
            continue
        tol = _snap_tolerance(seg, other)
        dist = abs(other.offset(*point))
        if dist <= tol and -tol <= other.along(*point) <= other.length + tol and dist < best_dist:
            best, best_dist = other, dist
    return best


def _crossed(p: tuple[float, float], q: tuple[float, float], others: Iterable[Segment]) -> bool:
    """Does any wall pass through the stretch p–q?"""
    for other in others:
        op, oq = other.offset(*p), other.offset(*q)
        if op * oq < 0:  # strict: the two collinear pieces being bridged sit on the same side
            t = op / (op - oq)
            x, y = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
            if 0 <= other.along(x, y) <= other.length:
                return True
    return False


def _facing_ends(a: Segment, b: Segment) -> tuple[tuple[float, float], tuple[float, float]]:
    return min(((p, q) for p in a.ends for q in b.ends), key=lambda pq: math.dist(*pq))


def _classify_opening(
    fine: Gray, p: tuple[float, float], q: tuple[float, float], thickness: float
) -> Literal["door", "window"]:
    """≥2 thin lines running along the gap is glazing. Anything else is a door."""
    half = round(thickness / 2) + 1
    inset = 3
    if abs(q[1] - p[1]) <= 2:
        c, a, b = round((p[1] + q[1]) / 2), round(min(p[0], q[0])) + inset, round(max(p[0], q[0])) - inset
        band = fine[max(0, c - half) : c + half + 1, max(0, a) : b]
    elif abs(q[0] - p[0]) <= 2:
        c, a, b = round((p[0] + q[0]) / 2), round(min(p[1], q[1])) + inset, round(max(p[1], q[1])) - inset
        band = fine[max(0, a) : b, max(0, c - half) : c + half + 1].T
    else:
        return "door"
    if band.size == 0:
        return "door"
    rows = (band > 0).astype(np.uint8)
    # Tolerate lines that straddle two rows after deskew interpolation.
    rows = np.maximum(rows, np.pad(rows, ((1, 0), (0, 0)))[:-1])
    full = rows.mean(axis=1) >= 0.6
    lines = int(np.count_nonzero(np.diff(np.concatenate(([False], full)).astype(np.int8)) == 1))
    return "window" if lines >= 2 else "door"


def _swing_ink(fine: Gray, p: tuple[float, float], q: tuple[float, float], thickness: float) -> bool:
    """Does a door's arc sweep past this gap? An arc leaves ink over nearly its whole width on one side of the wall."""
    half, reach, inset = round(thickness / 2) + 2, round(math.dist(p, q)), 3
    if abs(q[1] - p[1]) <= 2:
        c, a, b = round((p[1] + q[1]) / 2), round(min(p[0], q[0])) + inset, round(max(p[0], q[0])) - inset
        sides = [fine[c + half : c + half + reach, a:b], fine[max(0, c - half - reach) : max(0, c - half), a:b]]
    elif abs(q[0] - p[0]) <= 2:
        c, a, b = round((p[0] + q[0]) / 2), round(min(p[1], q[1])) + inset, round(max(p[1], q[1])) - inset
        sides = [fine[a:b, c + half : c + half + reach].T, fine[a:b, max(0, c - half - reach) : max(0, c - half)].T]
    else:
        return False
    return any(side.size > 0 and float((side > 0).any(axis=0).mean()) >= SWING_COVERAGE for side in sides)


def _bridge_gaps(segs: list[Segment], fine: Gray, limit: float) -> tuple[list[Segment], list[Opening]]:
    """One pass per line: only neighbouring pieces can share a gap (rescanning all pairs took minutes)."""
    lines: list[list[Segment]] = []
    for seg in sorted(segs, key=lambda s: -s.length):
        home = next((line for line in lines if _same_line(line[0], seg)), None)
        if home is None:
            lines.append([seg])
        else:
            home.append(seg)
    out: list[Segment] = []
    openings: list[Opening] = []
    for line in lines:
        base = line[0]
        pieces = sorted(line, key=lambda s: min(base.along(*p) for p in s.ends))
        current = pieces[0]
        for nxt in pieces[1:]:
            gap = _gap(current, nxt)
            p, q = _facing_ends(current, nxt)
            thick = max(current.thickness, nxt.thickness)
            # Lines running along the gap prove the wall continues, so a garage or sliding door can exceed the limit.
            door_beside_junction = gap <= DOOR_GAP_FACTOR * thick and _swing_ink(fine, p, q, thick)
            glazed_wide = (
                limit < gap <= WIDE_OPENING_FACTOR * limit and _classify_opening(fine, p, q, thick) == "window"
            )
            # A wall ending on a perpendicular wall stopped there on purpose; the stretch beyond is open floor.
            if (
                not (TOUCHING_PX < gap <= limit or glazed_wide)
                or ((_junction_on(p, current, segs) or _junction_on(q, nxt, segs)) and not door_beside_junction)
                or _crossed(p, q, segs)
            ):
                out.append(current)
                current = nxt
                continue
            merged = _union(current, nxt)
            (x1, y1), (x2, y2) = sorted((merged.at(merged.along(*p)), merged.at(merged.along(*q))))
            openings.append(Opening(_classify_opening(fine, p, q, thick), x1, y1, x2, y2, thick))
            current = merged
        out.append(current)
    return out, sorted(openings, key=lambda o: (o.y1, o.x1))


def _ray_hit(
    point: tuple[float, float], direction: tuple[float, float], seg: Segment, segs: list[Segment]
) -> tuple[float, Segment] | None:
    """Nearest wall across this ray: (distance to its centre-line, the wall)."""
    best: tuple[float, Segment] | None = None
    for other in segs:
        if other is seg or _parallel(seg, other):
            continue
        offset = other.offset(*point)
        rate = other.offset(point[0] + direction[0], point[1] + direction[1]) - offset
        if abs(rate) < 1e-9:
            continue
        t = -offset / rate
        x, y = point[0] + direction[0] * t, point[1] + direction[1] * t
        tol = other.thickness
        if t > 0 and -tol <= other.along(x, y) <= other.length + tol and (best is None or t < best[0]):
            best = (t, other)
    return best


def _close_doors_at_walls(segs: list[Segment], fine: Gray) -> tuple[list[Segment], list[Opening]]:
    """A door hung against a side wall leaves a free wall end facing that wall, with no second piece to bridge to."""
    out: list[Segment] = []
    openings: list[Opening] = []
    for s in segs:
        ends = list(s.ends)
        for i, point in enumerate(s.ends):
            if _junction_on(point, s, segs):
                continue
            ox, oy = s.ends[1 - i]
            direction = ((point[0] - ox) / s.length, (point[1] - oy) / s.length)
            hit = _ray_hit(point, direction, s, segs)
            if hit is None:
                continue
            distance, wall = hit
            clear = distance - wall.thickness / 2
            face = (point[0] + direction[0] * clear, point[1] + direction[1] * clear)
            if not TOUCHING_PX < clear <= DOOR_GAP_FACTOR * s.thickness or not _swing_ink(
                fine, point, face, s.thickness
            ):
                continue
            ends[i] = (point[0] + direction[0] * distance, point[1] + direction[1] * distance)
            (x1, y1), (x2, y2) = sorted((point, face))
            openings.append(Opening("door", x1, y1, x2, y2, s.thickness))
        (x1, y1), (x2, y2) = ends
        out.append(_ordered(replace(s, x1=x1, y1=y1, x2=x2, y2=y2)))
    return out, openings


def _inside(point: tuple[float, float], seg: Segment) -> bool:
    return 0 < seg.along(*point) < seg.length


def _snap_junctions(segs: list[Segment]) -> list[Segment]:
    out = []
    for s in segs:
        ends = []
        for point in s.ends:
            other = _junction_on(point, s, segs)
            if other is None:
                ends.append(point)
                continue
            # Slide along our own line to where it crosses the other centre-line.
            op0, op1 = other.offset(s.x1, s.y1), other.offset(s.x2, s.y2)
            denom = op0 - op1
            crossing = point if abs(denom) < 1e-9 else s.at(s.length * op0 / denom)
            # Past the other wall's far face this end is a real stub, often the jamb a door hangs from.
            ends.append(
                point if math.dist(point, crossing) > other.thickness / 2 + 3 and _inside(crossing, s) else crossing
            )
        (x1, y1), (x2, y2) = ends
        out.append(_ordered(replace(s, x1=x1, y1=y1, x2=x2, y2=y2)))
    return out


def detect_walls(binary: Gray, fine: Gray) -> WallDetection:
    thickness = estimate_wall_thickness(binary)
    if thickness is None:
        return WallDetection([], [], None, np.zeros_like(binary))
    mask = structural_mask(binary, thickness)
    wall_ink = mask.copy()
    for box in compact_blobs(mask, thickness):
        x, y, w, h = int(box.x), int(box.y), int(box.width), int(box.height)
        wall_ink[y : y + h, x : x + w] = 0
    axis, axis_ink = _axis_walls(wall_ink, thickness)
    segs = [_straighten(s) for s in axis + _diagonal_walls(wall_ink, axis_ink, thickness)]
    segs = _merge_collinear(segs)
    segs, openings = _bridge_gaps(segs, fine, BRIDGE_FRACTION * max(binary.shape))
    segs, side_doors = _close_doors_at_walls(segs, fine)
    openings = sorted([*openings, *side_doors], key=lambda o: (o.y1, o.x1))
    segs = _snap_junctions(segs)
    segs = [s for s in segs if s.length >= 1.5 * thickness]
    return WallDetection(sorted(segs, key=lambda s: (s.y1, s.x1, s.y2, s.x2)), openings, thickness, mask)

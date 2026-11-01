"""Plain geometry helpers shared by the engine and insights. Coordinates are image px, +y down."""

from collections.abc import Iterable, Sequence
from math import hypot, radians, sin
from typing import Literal
from uuid import UUID

import shapely
from aec_contracts import BBox, CoordinateSystem, Direction, Distance, FloorPlanModel, Point, Room, Wall
from aec_contracts.model import Element
from shapely.geometry import Polygon

from .errors import SemanticError

MAX_ALONG_FRACTION = 0.35  # also the sine of the angle at which a wall stops counting as horizontal/vertical
PARALLEL_SIN = sin(radians(3))
AXIS_ALIGNED_SIN = sin(radians(0.5))
SAME_LINE_PX = 2.0
IMAGE_MARGIN_PX = 6.0
DIRECTION_VECTOR = {Direction.LEFT: (-1.0, 0.0), Direction.RIGHT: (1.0, 0.0),
                    Direction.UP: (0.0, -1.0), Direction.DOWN: (0.0, 1.0)}


def find[E: Element](items: Iterable[E], element_id: UUID | None) -> E:
    return next(i for i in items if i.id == element_id)


def pt(x: float, y: float) -> Point:
    # Unvalidated on purpose: out-of-image results must reach the constraints stage. +0.0 turns -0.0 into 0.0.
    return Point.model_construct(x=round(x, 2) + 0.0, y=round(y, 2) + 0.0)


def bbox(x: float, y: float, width: float, height: float) -> BBox:
    return BBox.model_construct(x=round(x, 2) + 0.0, y=round(y, 2) + 0.0,
                                width=round(width, 2), height=round(height, 2))


def unit(wall: Wall) -> tuple[float, float]:
    length = wall.length_px
    return (wall.end.x - wall.start.x) / length, (wall.end.y - wall.start.y) / length


def midpoint(wall: Wall) -> tuple[float, float]:
    return (wall.start.x + wall.end.x) / 2, (wall.start.y + wall.end.y) / 2


def wall_axis(wall: Wall) -> Literal["horizontal", "vertical", "diagonal"]:
    ux, uy = unit(wall)
    if abs(uy) <= MAX_ALONG_FRACTION:
        return "horizontal"
    return "vertical" if abs(ux) <= MAX_ALONG_FRACTION else "diagonal"


def is_axis_aligned(wall: Wall) -> bool:
    ux, uy = unit(wall)
    return min(abs(ux), abs(uy)) <= AXIS_ALIGNED_SIN


def are_parallel(a: Wall, b: Wall) -> bool:
    ax, ay = unit(a)
    bx, by = unit(b)
    return abs(ax * by - ay * bx) <= PARALLEL_SIN


def tolerance(wall: Wall) -> float:
    return max(6.0, 1.5 * (wall.thickness_px or 0.0))


def distance_to_line(p: Point, wall: Wall) -> float:
    ux, uy = unit(wall)
    return abs((p.x - wall.start.x) * uy - (p.y - wall.start.y) * ux)


def nearest_on_wall(x: float, y: float, wall: Wall) -> tuple[float, float]:
    ux, uy = unit(wall)
    along = min(max((x - wall.start.x) * ux + (y - wall.start.y) * uy, 0.0), wall.length_px)
    return wall.start.x + along * ux, wall.start.y + along * uy


def distance_to_wall(x: float, y: float, wall: Wall) -> float:
    nx, ny = nearest_on_wall(x, y, wall)
    return hypot(x - nx, y - ny)


def signed_area(points: Sequence[Point]) -> float:
    n = len(points)
    return sum(points[i].x * points[(i + 1) % n].y - points[(i + 1) % n].x * points[i].y for i in range(n)) / 2.0


def polygon_of(room: Room) -> Polygon:
    return Polygon([(p.x, p.y) for p in room.polygon])


def to_px(distance: Distance, cs: CoordinateSystem) -> float:
    """Never treat px as mm: mm without a scale is an error, not a guess."""
    if distance.unit == "px":
        return distance.value
    if cs.mm_per_pixel is None:
        raise SemanticError("Set a scale first to use millimetres (select a wall and use Set scale).")
    return distance.value / cs.mm_per_pixel


def room_polygons(model: FloorPlanModel) -> list[Polygon]:
    polygons = [polygon_of(r) for r in model.rooms]
    shapely.prepare(polygons)
    return polygons


def rooms_by_side(model: FloorPlanModel, wall: Wall, polygons: list[Polygon]) -> tuple[list[Room], list[Room]]:
    """Rooms on each side of a wall, probing outward (vision room polygons can stop short of the centre-line)."""
    if not polygons:
        return [], []
    thickness = wall.thickness_px or 0.0
    ux, uy = unit(wall)
    sides: tuple[set[int], set[int]] = (set(), set())
    for t in (0.25, 0.5, 0.75):
        x, y = wall.start.x + t * (wall.end.x - wall.start.x), wall.start.y + t * (wall.end.y - wall.start.y)
        for side, sign in zip(sides, (1.0, -1.0), strict=True):
            for depth in (2.0, thickness / 2 + 2, thickness + 4):
                hits = shapely.contains_xy(polygons, x - sign * uy * depth, y + sign * ux * depth)
                if hits.any():  # the nearest room only: a thick wall must not reach past a narrow closet
                    side.update(int(i) for i in hits.nonzero()[0])
                    break
    return [model.rooms[i] for i in sorted(sides[0])], [model.rooms[i] for i in sorted(sides[1])]

"""Detections → validated FloorPlanModel. Sorted spatially and uuid5-ed, so re-analysis gives stable ids."""

import math
from collections.abc import Sequence
from uuid import UUID, uuid5

import numpy as np
from aec_contracts import (
    BBox,
    Column,
    CoordinateSystem,
    Dimension,
    Door,
    FloorPlanModel,
    Furniture,
    Point,
    Room,
    RoomType,
    Source,
    Stair,
    Wall,
    Window,
    polygon_area,
    room_type_for_text,
)

from .calibrate import Calibration
from .objects import Detections
from .rooms import DetectedRoom
from .strokes import Box
from .walls import Opening, Segment

OPENING_WALL_MAX_PX = 40.0
LINK_NEAR_PX = 12.0
LINK_MIN_PX = 20.0
LINK_MIN_FRACTION = 0.1
LINK_SAMPLE_PX = 4.0
ROOM_CONFIDENCE = 0.8
COLUMN_CONFIDENCE = 0.6
STAIR_CONFIDENCE = 0.6
FURNITURE_CONFIDENCE = 0.5


def _r(v: float) -> float:
    return round(float(v), 2)


def _clamped_box(x: float, y: float, width: float, height: float, size: tuple[int, int]) -> BBox | None:
    x2, y2 = min(x + width, size[0]), min(y + height, size[1])
    x, y = max(x, 0.0), max(y, 0.0)
    if _r(x2 - x) <= 0 or _r(y2 - y) <= 0:
        return None
    return BBox(x=_r(x), y=_r(y), width=_r(x2 - x), height=_r(y2 - y))


def _point(x: float, y: float, size: tuple[int, int]) -> Point:
    return Point(x=_r(min(max(x, 0.0), size[0])), y=_r(min(max(y, 0.0), size[1])))


def _element_id(floorplan_id: UUID, kind: str, index: int) -> UUID:
    return uuid5(floorplan_id, f"{kind}:{index}")


def _opening_box(op: Opening, size: tuple[int, int]) -> BBox | None:
    half = op.thickness / 2
    x1, x2 = sorted((op.x1, op.x2))
    y1, y2 = sorted((op.y1, op.y2))
    return _clamped_box(
        x1 - half if y2 - y1 >= 1 else x1,
        y1 - half if x2 - x1 >= 1 else y1,
        (x2 - x1) + (op.thickness if y2 - y1 >= 1 else 0),
        (y2 - y1) + (op.thickness if x2 - x1 >= 1 else 0),
        size,
    )


def _binding_wall(op: Opening, walls: list[Segment], wall_ids: list[UUID]) -> UUID | None:
    cx, cy = (op.x1 + op.x2) / 2, (op.y1 + op.y2) / 2
    if not walls:
        return None
    i = min(range(len(walls)), key=lambda k: walls[k].distance(cx, cy))
    return wall_ids[i] if walls[i].distance(cx, cy) <= OPENING_WALL_MAX_PX else None


def link_walls_to_rooms(walls: Sequence[Wall], rooms: Sequence[Room]) -> None:
    """A wall joins a room when ≥ max(20 px, 10 % of its length) lies within 12 px of the room boundary."""
    for room in rooms:
        pts = np.array([(p.x, p.y) for p in room.polygon])
        a, b = pts, np.roll(pts, -1, axis=0)
        ab = b - a
        denom = np.maximum((ab**2).sum(axis=1), 1e-9)
        linked = []
        for wall in walls:
            length = wall.length_px
            n = max(2, math.ceil(length / LINK_SAMPLE_PX) + 1)
            ts = np.linspace(0, 1, n)[:, None]
            samples = np.array([wall.start.x, wall.start.y]) * (1 - ts) + np.array([wall.end.x, wall.end.y]) * ts
            # Distance from every sample to every polygon edge.
            rel = samples[:, None, :] - a[None, :, :]
            u = np.clip((rel * ab[None, :, :]).sum(axis=2) / denom, 0, 1)[:, :, None]
            dist = np.linalg.norm(rel - u * ab[None, :, :], axis=2).min(axis=1)
            near_px = np.count_nonzero(dist <= LINK_NEAR_PX) / n * length
            if near_px >= max(LINK_MIN_PX, LINK_MIN_FRACTION * length):
                linked.append(wall.id)
        room.wall_ids = list(dict.fromkeys(room.wall_ids + linked))


def _placed_boxes(boxes: list[Box], size: tuple[int, int]) -> list[BBox]:
    clamped = (_clamped_box(b.x, b.y, b.width, b.height, size) for b in sorted(boxes, key=lambda b: (b.y, b.x)))
    return [b for b in clamped if b is not None]


def _corners(box: BBox, size: tuple[int, int]) -> list[Point]:
    x2, y2 = box.x + box.width, box.y + box.height
    return [_point(x, y, size) for x, y in ((box.x, box.y), (x2, box.y), (x2, y2), (box.x, y2))]


def build_model(
    floorplan_id: UUID,
    size: tuple[int, int],
    segments: list[Segment],
    openings: list[Opening],
    objects: Detections,
    rooms: list[DetectedRoom],
    calibration: Calibration,
) -> FloorPlanModel:
    walls: list[Wall] = []
    kept: list[Segment] = []
    for seg in sorted(segments, key=lambda s: (s.y1, s.x1, s.y2, s.x2)):
        start, end = _point(seg.x1, seg.y1, size), _point(seg.x2, seg.y2, size)
        if start == end:
            continue
        walls.append(
            Wall(
                id=_element_id(floorplan_id, "wall", len(walls)),
                start=start,
                end=end,
                thickness_px=_r(seg.thickness),
                confidence=seg.confidence,
                source=Source.DETECTED,
            )
        )
        kept.append(seg)
    wall_ids = [w.id for w in walls]

    doors: list[Door] = []
    windows: list[Window] = []
    placed = [(found, op) for op in openings if (found := _opening_box(op, size)) is not None]
    for box, op in sorted(placed, key=lambda item: (item[0].y, item[0].x)):
        wall_id = _binding_wall(op, kept, wall_ids)
        width = _r(op.width) if op.width > 0 else None
        if op.kind == "window":
            windows.append(
                Window(
                    id=_element_id(floorplan_id, "window", len(windows)),
                    bbox=box,
                    wall_id=wall_id,
                    width_px=width,
                    confidence=op.confidence,
                )
            )
        else:
            doors.append(
                Door(
                    id=_element_id(floorplan_id, "door", len(doors)),
                    bbox=box,
                    wall_id=wall_id,
                    width_px=width,
                    swing=op.swing,
                    confidence=op.confidence,
                )
            )

    columns = [
        Column(id=_element_id(floorplan_id, "column", i), bbox=box, confidence=COLUMN_CONFIDENCE)
        for i, box in enumerate(_placed_boxes(objects.columns, size))
    ]
    stairs = [
        Stair(
            id=_element_id(floorplan_id, "stair", i), bbox=box, polygon=_corners(box, size), confidence=STAIR_CONFIDENCE
        )
        for i, box in enumerate(_placed_boxes(objects.stairs, size))
    ]
    furniture: list[Furniture] = []
    for item in sorted(objects.furniture, key=lambda f: (f.box.y, f.box.x)):
        clamped = _clamped_box(item.box.x, item.box.y, item.box.width, item.box.height, size)
        if clamped is not None:
            furniture.append(
                Furniture(
                    id=_element_id(floorplan_id, "furniture", len(furniture)),
                    bbox=clamped,
                    category=item.category,
                    confidence=FURNITURE_CONFIDENCE,
                )
            )

    dimensions = [
        Dimension(
            id=_element_id(floorplan_id, "dimension", i),
            text=d.text,
            value_mm=_r(d.value_mm),
            span_px=_r(d.span_px) if d.span_px else None,
            position=_point(d.x, d.y, size),
        )
        for i, d in enumerate(sorted(calibration.dimensions, key=lambda d: (d.y, d.x)))
    ]

    model_rooms: list[Room] = []
    for detected in sorted(rooms, key=lambda r: (min(p[1] for p in r.points), min(p[0] for p in r.points))):
        polygon = [_point(x, y, size) for x, y in detected.points]
        area = polygon_area(polygon)
        if area <= 0:
            continue
        room_type, type_confidence = room_type_for_text(detected.label or "")
        known = room_type != RoomType.UNKNOWN
        model_rooms.append(
            Room(
                id=_element_id(floorplan_id, "room", len(model_rooms)),
                polygon=polygon,
                label_text=detected.label,
                room_type=room_type,
                room_type_source=Source.INFERRED if known else None,
                room_type_confidence=type_confidence if known else None,
                area_px=_r(area),
                confidence=ROOM_CONFIDENCE,
            )
        )
    link_walls_to_rooms(walls, model_rooms)

    cs = CoordinateSystem(
        image_width=size[0],
        image_height=size[1],
        mm_per_pixel=calibration.mm_per_pixel,
        calibration_source=calibration.source,
        calibration_confidence=calibration.confidence,
    )
    return FloorPlanModel(
        id=_element_id(floorplan_id, "model", 0),
        floorplan_id=floorplan_id,
        coordinate_system=cs,
        walls=walls,
        doors=doors,
        windows=windows,
        columns=columns,
        stairs=stairs,
        furniture=furniture,
        dimensions=dimensions,
        rooms=model_rooms,
    )

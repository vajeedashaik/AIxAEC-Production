"""Building Model (CONTRACTS.md §2). Coordinates are image pixels, origin top-left."""

from collections.abc import Sequence
from enum import StrEnum
from itertools import chain
from typing import Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    # serialization-defaults-required only affects the exported JSON Schema: response fields with
    # defaults are always present on the wire, so TS types mark them required.
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


class Source(StrEnum):
    DETECTED = "DETECTED"; INFERRED = "INFERRED"; USER_CONFIRMED = "USER_CONFIRMED"


class RoomType(StrEnum):
    UNKNOWN = "UNKNOWN"; BEDROOM = "BEDROOM"; MASTER_BEDROOM = "MASTER_BEDROOM"; BATHROOM = "BATHROOM"
    KITCHEN = "KITCHEN"; LIVING_ROOM = "LIVING_ROOM"; DINING_ROOM = "DINING_ROOM"; HALLWAY = "HALLWAY"
    CLOSET = "CLOSET"; GARAGE = "GARAGE"; OFFICE = "OFFICE"; LAUNDRY = "LAUNDRY"; BALCONY = "BALCONY"
    STORAGE = "STORAGE"; STAIRWELL = "STAIRWELL"; UTILITY = "UTILITY"; OTHER = "OTHER"


class CalibrationSource(StrEnum):
    UNKNOWN = "UNKNOWN"; ASSUMED_DEFAULT = "ASSUMED_DEFAULT"; DIMENSION_OCR = "DIMENSION_OCR"; MANUAL = "MANUAL"


class Point(Strict):
    x: float = Field(ge=0, allow_inf_nan=False)
    y: float = Field(ge=0, allow_inf_nan=False)


class BBox(Strict):
    x: float = Field(ge=0, allow_inf_nan=False)
    y: float = Field(ge=0, allow_inf_nan=False)
    width: float = Field(gt=0, allow_inf_nan=False)
    height: float = Field(gt=0, allow_inf_nan=False)


class Element(Strict):
    id: UUID = Field(default_factory=uuid4)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: Source = Source.DETECTED


class Wall(Element):
    start: Point
    end: Point
    thickness_px: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _distinct_endpoints(self) -> Self:
        if self.start == self.end:
            raise ValueError("wall start and end must differ")
        return self

    @property
    def length_px(self) -> float:
        return float(((self.end.x - self.start.x) ** 2 + (self.end.y - self.start.y) ** 2) ** 0.5)


class Opening(Element):
    bbox: BBox
    wall_id: UUID | None = None
    width_px: float | None = Field(default=None, gt=0)


class Door(Opening):
    swing: Literal["LEFT", "RIGHT", "DOUBLE", "SLIDING"] | None = None


class Window(Opening):
    pass


class Column(Element):
    bbox: BBox


class Stair(Element):
    bbox: BBox
    polygon: list[Point] | None = None


class Furniture(Element):
    bbox: BBox
    category: str | None = Field(default=None, max_length=60)


class Dimension(Element):
    text: str = Field(max_length=80)
    value_mm: float | None = Field(default=None, gt=0)
    span_px: float | None = Field(default=None, gt=0)
    position: Point | None = None


class Room(Element):
    polygon: list[Point] = Field(min_length=3)
    wall_ids: list[UUID] = Field(default_factory=list)
    label_text: str | None = Field(default=None, max_length=80)
    room_type: RoomType = RoomType.UNKNOWN
    room_type_source: Source | None = None
    room_type_confidence: float | None = Field(default=None, ge=0, le=1)
    area_px: float | None = Field(default=None, gt=0)


class CoordinateSystem(Strict):
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    mm_per_pixel: float | None = Field(default=None, gt=0)
    calibration_source: CalibrationSource = CalibrationSource.UNKNOWN
    calibration_confidence: float | None = Field(default=None, ge=0, le=1)


class ModelSummary(Strict):
    walls: int; doors: int; windows: int; columns: int; stairs: int
    furniture: int; dimensions: int; rooms: int


class FloorPlanModel(Strict):
    schema_version: Literal[1] = 1
    id: UUID = Field(default_factory=uuid4)
    floorplan_id: UUID
    coordinate_system: CoordinateSystem
    walls: list[Wall] = []
    doors: list[Door] = []
    windows: list[Window] = []
    columns: list[Column] = []
    stairs: list[Stair] = []
    furniture: list[Furniture] = []
    dimensions: list[Dimension] = []
    rooms: list[Room] = []

    @model_validator(mode="after")
    def _integrity(self) -> Self:
        seen: set[UUID] = set()
        for el in chain(self.walls, self.doors, self.windows, self.columns, self.stairs,
                        self.furniture, self.dimensions, self.rooms):
            if el.id in seen:
                raise ValueError(f"duplicate element id {el.id}")
            seen.add(el.id)
        wall_ids = {w.id for w in self.walls}
        for room in self.rooms:
            for wid in room.wall_ids:
                if wid not in wall_ids:
                    raise ValueError(f"room {room.id} references unknown wall {wid}")
        for op in chain(self.doors, self.windows):
            if op.wall_id is not None and op.wall_id not in wall_ids:
                raise ValueError(f"opening {op.id} references unknown wall {op.wall_id}")
        return self

    def summary(self) -> ModelSummary:
        return ModelSummary(
            walls=len(self.walls), doors=len(self.doors), windows=len(self.windows),
            columns=len(self.columns), stairs=len(self.stairs), furniture=len(self.furniture),
            dimensions=len(self.dimensions), rooms=len(self.rooms),
        )


def polygon_area(points: Sequence[Point]) -> float:
    """Shoelace area, absolute, in px²."""
    n = len(points)
    s = sum(points[i].x * points[(i + 1) % n].y - points[(i + 1) % n].x * points[i].y for i in range(n))
    return abs(s) / 2.0


class CoordinateTransform:
    def __init__(self, cs: CoordinateSystem) -> None:
        self.mm_per_pixel = cs.mm_per_pixel

    def px_to_mm(self, v: float) -> float | None:
        """None without a scale: never treat px as mm."""
        return None if self.mm_per_pixel is None else v * self.mm_per_pixel

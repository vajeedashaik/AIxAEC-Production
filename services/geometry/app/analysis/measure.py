"""Everything the analyses share: the plan measured in real units. Only ever built when the plan has a scale."""

import heapq
from dataclasses import dataclass
from math import hypot
from uuid import UUID

import shapely
from aec_contracts import Door, FloorPlanModel, Room, RoomType, Wall, Window, polygon_area
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import Polygon

from ..engine.geom import polygon_of, room_polygons, rooms_by_side, unit

DEFAULT_EXTERIOR_MM, DEFAULT_INTERIOR_MM = 230.0, 115.0
HABITABLE = {
    RoomType.BEDROOM,
    RoomType.MASTER_BEDROOM,
    RoomType.LIVING_ROOM,
    RoomType.DINING_ROOM,
    RoomType.OFFICE,
    RoomType.KITCHEN,
}
SLEEPING = {RoomType.BEDROOM, RoomType.MASTER_BEDROOM}


@dataclass(frozen=True)
class WallInfo:
    wall: Wall
    length_m: float
    thickness_m: float
    exterior: bool


@dataclass(frozen=True)
class OpeningInfo:
    element: Door | Window
    width_mm: float
    centre: tuple[float, float]
    rooms: tuple[Room, ...]
    exterior: bool
    wall: WallInfo | None


@dataclass(frozen=True)
class RoomInfo:
    room: Room
    name: str
    area_m2: float
    perimeter_m: float
    min_width_mm: float
    polygon: Polygon


@dataclass(frozen=True)
class Plan:
    model: FloorPlanModel
    mm: float
    walls: list[WallInfo]
    rooms: list[RoomInfo]
    doors: list[OpeningInfo]
    windows: list[OpeningInfo]

    def room(self, room_id: UUID) -> RoomInfo:
        return next(r for r in self.rooms if r.room.id == room_id)

    @property
    def floor_area_m2(self) -> float:
        return sum(r.area_m2 for r in self.rooms)

    def openings_in(self, room_id: UUID, kind: str = "window") -> list[OpeningInfo]:
        items = self.windows if kind == "window" else self.doors
        return [o for o in items if any(r.id == room_id for r in o.rooms)]


def display_name(room: Room) -> str:
    return room.label_text or room.room_type.replace("_", " ").capitalize()


def _min_width_px(polygon: Polygon) -> float:
    box = polygon.minimum_rotated_rectangle
    if not isinstance(box, Polygon):
        return 0.0
    (ax, ay), (bx, by), (cx, cy) = list(box.exterior.coords)[:3]
    return min(hypot(bx - ax, by - ay), hypot(cx - bx, cy - by))


def _rooms_at_opening(
    model: FloorPlanModel,
    polygons: list[Polygon],
    centre: tuple[float, float],
    normal: tuple[float, float],
    thickness: float,
) -> tuple[list[Room], list[Room]]:
    """Rooms on each side of one opening. `rooms_by_side` samples a whole wall, wrong for one spot on a long run."""
    if not polygons:
        return [], []
    sides: tuple[list[Room], list[Room]] = ([], [])
    for side, sign in zip(sides, (1.0, -1.0), strict=True):
        for depth in (2.0, thickness / 2 + 2, thickness + 4, thickness * 2 + 8):
            hits = shapely.contains_xy(
                polygons, centre[0] + sign * normal[0] * depth, centre[1] + sign * normal[1] * depth
            )
            if hits.any():
                side.extend(model.rooms[int(i)] for i in hits.nonzero()[0])
                break
    return sides


def _opening(
    model: FloorPlanModel, polygons: list[Polygon], mm: float, element: Door | Window, walls: dict[UUID, WallInfo]
) -> OpeningInfo:
    box = element.bbox
    centre = (box.x + box.width / 2, box.y + box.height / 2)
    info = walls.get(element.wall_id) if element.wall_id else None
    if info:
        ux, uy = unit(info.wall)
        normal, thickness = (-uy, ux), info.wall.thickness_px or 0.0
    else:
        normal, thickness = ((0.0, 1.0), box.height) if box.width >= box.height else ((1.0, 0.0), box.width)
    one, other = _rooms_at_opening(model, polygons, centre, normal, thickness)
    width_px = element.width_px or max(box.width, box.height)
    return OpeningInfo(
        element=element,
        width_mm=width_px * mm,
        centre=centre,
        rooms=tuple({r.id: r for r in one + other}.values()),
        exterior=bool(one) != bool(other),
        wall=info,
    )


def measure(model: FloorPlanModel) -> Plan:
    mm = model.coordinate_system.mm_per_pixel
    if mm is None:
        raise ValueError("measure() needs a scale")  # callers check first: never treat px as mm
    polygons = room_polygons(model)
    walls = []
    for wall in model.walls:
        one, other = rooms_by_side(model, wall, polygons)
        exterior = not (one and other)
        default = DEFAULT_EXTERIOR_MM if exterior else DEFAULT_INTERIOR_MM
        walls.append(
            WallInfo(
                wall=wall,
                length_m=wall.length_px * mm / 1000,
                exterior=exterior,
                thickness_m=(wall.thickness_px * mm if wall.thickness_px else default) / 1000,
            )
        )
    by_id = {w.wall.id: w for w in walls}
    rooms = []
    for room in model.rooms:
        polygon = polygon_of(room)
        rooms.append(
            RoomInfo(
                room=room,
                name=display_name(room),
                area_m2=polygon_area(room.polygon) * (mm / 1000) ** 2,
                perimeter_m=polygon.exterior.length * mm / 1000,
                min_width_mm=_min_width_px(polygon) * mm,
                polygon=polygon,
            )
        )
    return Plan(
        model=model,
        mm=mm,
        walls=walls,
        rooms=rooms,
        doors=[_opening(model, polygons, mm, d, by_id) for d in model.doors],
        windows=[_opening(model, polygons, mm, w, by_id) for w in model.windows],
    )


def travel_distances_m(plan: Plan) -> dict[UUID, float]:
    """Walking distance from each room's centre to the nearest exterior door. Unreachable rooms are absent."""
    centroids = {r.room.id: (r.polygon.centroid.x, r.polygon.centroid.y) for r in plan.rooms}
    edges: dict[UUID, list[tuple[UUID, float]]] = {i: [] for i in centroids}
    best: dict[UUID, float] = {}
    queue: list[tuple[float, str, UUID]] = []
    for door in plan.doors:
        if door.exterior:
            for room in door.rooms:
                cost = hypot(centroids[room.id][0] - door.centre[0], centroids[room.id][1] - door.centre[1])
                if cost < best.get(room.id, float("inf")):
                    best[room.id] = cost
                    heapq.heappush(queue, (cost, str(room.id), room.id))
        elif len(door.rooms) >= 2:
            for a in door.rooms:
                for b in door.rooms:
                    if a.id != b.id:
                        cost = hypot(centroids[a.id][0] - door.centre[0], centroids[a.id][1] - door.centre[1]) + hypot(
                            centroids[b.id][0] - door.centre[0], centroids[b.id][1] - door.centre[1]
                        )
                        edges[a.id].append((b.id, cost))
    while queue:
        cost, _, room_id = heapq.heappop(queue)
        if cost > best[room_id]:
            continue
        for neighbour, step in edges[room_id]:
            if cost + step < best.get(neighbour, float("inf")):
                best[neighbour] = cost + step
                heapq.heappush(queue, (cost + step, str(neighbour), neighbour))
    return {room_id: cost * plan.mm / 1000 for room_id, cost in best.items()}


def contains(info: RoomInfo, x: float, y: float) -> bool:
    return bool(info.polygon.contains(ShapelyPoint(x, y)))

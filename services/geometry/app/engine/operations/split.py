"""SPLIT_ROOM: one new wall, two rooms and a door between them, as a single atomic edit."""

from statistics import median

from aec_contracts import AddDoor, Distance, Door, FloorPlanModel, Point, Room, Source, Wall, polygon_area
from aec_contracts.commands import SplitRoom
from shapely.errors import GEOSException
from shapely.geometry import LineString, Polygon, box
from shapely.ops import split

from ..errors import GeometryError
from ..geom import find, polygon_of, pt, signed_area, tolerance
from .ids import new_id
from .openings import DEFAULT_MM, DEFAULT_PX, _place

LINKED_LENGTH_PX = 1.0


def _ring(polygon: Polygon, clockwise_like: float) -> list[Point]:
    ring = [pt(x, y) for x, y in polygon.exterior.coords[:-1]]
    if signed_area(ring) * clockwise_like < 0:  # same winding as the original, or the validator calls it inverted
        ring.reverse()
    return ring


def _linked(wall: Wall, polygon: Polygon) -> bool:
    line = LineString([(wall.start.x, wall.start.y), (wall.end.x, wall.end.y)])
    return float(polygon.buffer(tolerance(wall)).intersection(line).length) > LINKED_LENGTH_PX


def split_room(model: FloorPlanModel, command: SplitRoom) -> FloorPlanModel:
    room = find(model.rooms, command.target_id)
    outline = polygon_of(room)
    min_x, min_y, max_x, max_y = outline.bounds
    if command.axis == "VERTICAL":
        x = min_x + command.position * (max_x - min_x)
        cut = LineString([(x, min_y - 1), (x, max_y + 1)])
    else:
        y = min_y + command.position * (max_y - min_y)
        cut = LineString([(min_x - 1, y), (max_x + 1, y)])
    try:
        pieces = [g for g in split(outline, cut).geoms if isinstance(g, Polygon)]
    except GEOSException as exc:
        raise GeometryError("That room's outline is too irregular to split.") from exc
    if len(pieces) != 2:
        raise GeometryError("A straight wall there wouldn't divide the room into exactly two spaces.")

    span = outline.intersection(cut)
    if not isinstance(span, LineString):
        raise GeometryError("A straight wall there wouldn't divide the room into exactly two spaces.")
    for opening in (*model.doors, *model.windows):
        b = opening.bbox
        if span.intersects(box(b.x, b.y, b.x + b.width, b.y + b.height)):
            raise GeometryError("A wall there would run through an existing door or window; pick another position.")
    (ax, ay), (bx, by) = span.coords[0], span.coords[-1]
    thicknesses = [w.thickness_px for w in model.walls if w.thickness_px is not None]
    wall = Wall(
        id=new_id(model, command, "wall"),
        start=pt(ax, ay),
        end=pt(bx, by),
        thickness_px=median(thicknesses) if thicknesses else None,
        confidence=1.0,
        source=Source.USER_CONFIRMED,
    )

    # The piece keeping the original id is the larger one; ties resolve by split order, which is deterministic.
    keep, new = sorted(pieces, key=lambda p: -p.area)
    winding = signed_area(room.polygon)
    existing = [w for w in model.walls if w.id in room.wall_ids]
    new_ring, keep_ring = _ring(new, winding), _ring(keep, winding)
    room.polygon = keep_ring
    room.area_px = round(polygon_area(keep_ring), 2) or None
    room.wall_ids = [*(w.id for w in existing if _linked(w, keep)), wall.id]
    model.walls.append(wall)
    model.rooms.append(
        Room(
            id=new_id(model, command, "room"),
            polygon=new_ring,
            wall_ids=[*(w.id for w in existing if _linked(w, new)), wall.id],
            label_text=command.new_room_name,
            room_type=command.new_room_type,
            room_type_source=Source.USER_CONFIRMED,
            room_type_confidence=1.0,
            area_px=round(polygon_area(new_ring), 2) or None,
            confidence=1.0,
            source=Source.USER_CONFIRMED,
        )
    )

    cs = model.coordinate_system
    width = (
        Distance(value=DEFAULT_MM["door"], unit="mm")
        if cs.mm_per_pixel
        else Distance(value=DEFAULT_PX["door"], unit="px")
    )
    door = AddDoor(operation="ADD_DOOR", target_id=wall.id, position=0.5, width=width)
    model.doors.append(Door.model_validate({**_place(model, door, "door"), "id": new_id(model, command, "door")}))
    return model

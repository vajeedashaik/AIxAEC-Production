"""MOVE_WALL, RESIZE_ROOM, ADD_WALL, DELETE_WALL. Moves and resizes share `_shift_walls`."""

from math import hypot
from statistics import median
from uuid import UUID

from aec_contracts import (
    AddWall,
    DeleteWall,
    Direction,
    FloorPlanModel,
    MoveWall,
    Point,
    ResizeMode,
    ResizeRoom,
    Room,
    Source,
    Wall,
    polygon_area,
)
from shapely import union_all
from shapely.errors import GEOSException
from shapely.geometry import Polygon

from ..errors import ConstraintViolation, GeometryError
from ..geom import (
    DIRECTION_VECTOR,
    MAX_ALONG_FRACTION,
    SAME_LINE_PX,
    are_parallel,
    bbox,
    distance_to_line,
    distance_to_wall,
    find,
    midpoint,
    nearest_on_wall,
    polygon_of,
    pt,
    room_polygons,
    rooms_by_side,
    signed_area,
    to_px,
    tolerance,
    unit,
    wall_axis,
)
from ..resolve import room_name
from .ids import new_id

SAME_POINT_PX = 1.0
SIDE_OVERLAP_FRACTION = 0.25
MERGE_SIMPLIFY_PX = 0.5
MERGE_GAP_MARGIN_PX = 3.0


def _is_continuation(wall: Wall, moved: Wall) -> bool:
    if not are_parallel(wall, moved):
        return False
    if max(distance_to_line(wall.start, moved), distance_to_line(wall.end, moved)) > SAME_LINE_PX:
        return False
    reach = tolerance(moved)
    return (distance_to_wall(wall.start.x, wall.start.y, moved) <= reach
            or distance_to_wall(wall.end.x, wall.end.y, moved) <= reach
            or distance_to_wall(moved.start.x, moved.start.y, wall) <= reach
            or distance_to_wall(moved.end.x, moved.end.y, wall) <= reach)


def _with_continuations(walls: list[Wall], ids: set[UUID]) -> set[UUID]:
    """A straight run is often several detected segments, and moving only one would tear the wall apart."""
    moved = set(ids)
    grew = True
    while grew:
        grew = False
        for wall in walls:
            if wall.id not in moved and any(_is_continuation(wall, m) for m in walls if m.id in moved):
                moved.add(wall.id)
                grew = True
    return moved


def _meet(wall: Wall, moved: Wall, dx: float, dy: float) -> tuple[float, float]:
    """Where `wall`'s own line crosses `moved`'s line after the shift. They are never parallel here."""
    wx, wy = unit(wall)
    mx, my = unit(moved)
    offset_x, offset_y = moved.start.x + dx - wall.start.x, moved.start.y + dy - wall.start.y
    along = (offset_x * my - offset_y * mx) / (wx * my - wy * mx)
    return wall.start.x + along * wx, wall.start.y + along * wy


def _reprojected_ends(wall: Wall, moved: list[Wall], dx: float, dy: float) -> dict[str, tuple[float, float]]:
    """Which end of `wall` meets a moved wall, end-on or as a T, and where it now lands."""
    best: dict[str, tuple[float, tuple[float, float]]] = {}
    for m in moved:
        if are_parallel(wall, m):
            continue
        d_start = distance_to_wall(wall.start.x, wall.start.y, m)
        d_end = distance_to_wall(wall.end.x, wall.end.y, m)
        attr, distance = ("start", d_start) if d_start <= d_end else ("end", d_end)
        if distance <= tolerance(m) and (attr not in best or distance < best[attr][0]):
            best[attr] = (distance, _meet(wall, m, dx, dy))
    return {attr: landing for attr, (_, landing) in best.items()}


def _move_corner(p: Point, endpoint_moves: list[tuple[Point, Point]], moved: list[Wall], dx: float, dy: float) -> Point:
    nearest = min(endpoint_moves, key=lambda move: hypot(p.x - move[0].x, p.y - move[0].y))
    if hypot(p.x - nearest[0].x, p.y - nearest[0].y) <= SAME_POINT_PX:
        return nearest[1]
    # Vision room corners can sit off the centre-line, inside the wall's thickness.
    if any(distance_to_wall(p.x, p.y, m) <= tolerance(m) for m in moved):
        return pt(p.x + dx, p.y + dy)
    return p


def _shift_walls(model: FloorPlanModel, ids: set[UUID], dx: float, dy: float) -> None:
    moved_ids = _with_continuations(model.walls, ids)
    moved = [w.model_copy() for w in model.walls if w.id in moved_ids]  # the old lines, untouched by the loop below
    endpoint_moves: list[tuple[Point, Point]] = []
    for wall in model.walls:
        if wall.id in moved_ids:
            start, end = pt(wall.start.x + dx, wall.start.y + dy), pt(wall.end.x + dx, wall.end.y + dy)
            endpoint_moves += [(wall.start, start), (wall.end, end)]
            wall.start, wall.end = start, end
        else:
            for attr, (x, y) in _reprojected_ends(wall, moved, dx, dy).items():
                endpoint_moves.append((getattr(wall, attr), pt(x, y)))
                setattr(wall, attr, pt(x, y))
    for opening in (*model.doors, *model.windows):
        if opening.wall_id in moved_ids:
            box = opening.bbox
            opening.bbox = bbox(box.x + dx, box.y + dy, box.width, box.height)
    for room in model.rooms:
        polygon = [_move_corner(p, endpoint_moves, moved, dx, dy) for p in room.polygon]
        if polygon != room.polygon:
            room.polygon = polygon
            room.area_px = round(polygon_area(polygon), 2) or None


def move_wall(model: FloorPlanModel, command: MoveWall) -> FloorPlanModel:
    wall = find(model.walls, command.target_id)
    distance = to_px(command.distance, model.coordinate_system)
    vx, vy = DIRECTION_VECTOR[command.direction]
    ux, uy = unit(wall)
    along = (vx * ux + vy * uy) * distance
    if abs(along) > MAX_ALONG_FRACTION * distance:
        axis = wall_axis(wall)
        raise GeometryError({
            "horizontal": "This wall is horizontal; move it up or down.",
            "vertical": "This wall is vertical; move it left or right.",
        }.get(axis, f"This wall runs diagonally, so it can't move {command.direction.value.lower()}: "
                    "it can only move across its length."))
    _shift_walls(model, {wall.id}, vx * distance - along * ux, vy * distance - along * uy)
    return model


def _side_walls(model: FloorPlanModel, room: Room, side: Direction) -> list[Wall]:
    xs, ys = [p.x for p in room.polygon], [p.y for p in room.polygon]
    horizontal = side in (Direction.UP, Direction.DOWN)
    across, along = (ys, xs) if horizontal else (xs, ys)
    edge = min(across) if side in (Direction.UP, Direction.LEFT) else max(across)
    low, high = min(along), max(along)
    found = []
    for wall in model.walls:
        if wall_axis(wall) != ("horizontal" if horizontal else "vertical"):
            continue
        if abs(midpoint(wall)[1 if horizontal else 0] - edge) > tolerance(wall):
            continue
        a, b = (wall.start.x, wall.end.x) if horizontal else (wall.start.y, wall.end.y)
        a, b = min(a, b), max(a, b)
        if min(b, high) - max(a, low) > SIDE_OVERLAP_FRACTION * (b - a):
            found.append(wall)
    return found


def resize_room(model: FloorPlanModel, command: ResizeRoom) -> FloorPlanModel:
    room = find(model.rooms, command.target_id)
    walls = _side_walls(model, room, command.direction)
    if not walls:
        raise GeometryError(f"The {command.direction.value.lower()} side of {room_name(room)} isn't formed by "
                            "walls that can move, so it can't be resized that way.")
    distance = to_px(command.distance, model.coordinate_system)
    if command.mode is ResizeMode.CONTRACT:
        distance = -distance
    vx, vy = DIRECTION_VECTOR[command.direction]
    _shift_walls(model, {w.id for w in walls}, vx * distance, vy * distance)
    return model


def _snap(p: Point, walls: list[Wall]) -> Point:
    best: tuple[float, float] | None = None
    best_distance = float("inf")
    for wall in walls:
        distance = distance_to_wall(p.x, p.y, wall)
        if distance <= tolerance(wall) and distance < best_distance:
            best, best_distance = nearest_on_wall(p.x, p.y, wall), distance
    return pt(*best) if best else p


def add_wall(model: FloorPlanModel, command: AddWall) -> FloorPlanModel:
    start, end = _snap(command.start, model.walls), _snap(command.end, model.walls)
    if hypot(end.x - start.x, end.y - start.y) < 1:
        raise GeometryError("Both ends of that wall snap to the same point on an existing wall; draw it longer.")
    thicknesses = [w.thickness_px for w in model.walls if w.thickness_px is not None]
    thickness = command.thickness_px or (median(thicknesses) if thicknesses else None)
    model.walls.append(Wall(id=new_id(model, command), start=start, end=end, thickness_px=thickness,
                            confidence=1.0, source=Source.USER_CONFIRMED))
    return model


def _merged_ring(rooms: list[Room], wall: Wall) -> list[Point]:
    polygons = [polygon_of(r) for r in rooms]
    try:
        merged = union_all(polygons)
        if not isinstance(merged, Polygon):
            # Rooms detected inside the wall's faces don't touch; close the gap the wall leaves.
            gap = (wall.thickness_px or 0.0) / 2 + MERGE_GAP_MARGIN_PX
            merged = union_all([p.buffer(gap, join_style="mitre") for p in polygons]).buffer(-gap, join_style="mitre")
        merged = merged.simplify(MERGE_SIMPLIFY_PX)
    except GEOSException as exc:
        raise GeometryError("Those rooms' outlines are too irregular to merge; fix them first.") from exc
    if not isinstance(merged, Polygon):
        raise GeometryError("The rooms on either side of that wall don't form one space, so it can't be deleted.")
    if merged.interiors:
        raise GeometryError("Deleting that wall would leave a room with a hole in it, which isn't supported.")
    return [pt(x, y) for x, y in merged.exterior.coords[:-1]]


def delete_wall(model: FloorPlanModel, command: DeleteWall) -> FloorPlanModel:
    wall = find(model.walls, command.target_id)
    one_side, other_side = rooms_by_side(model, wall, room_polygons(model))
    if bool(one_side) != bool(other_side):
        raise ConstraintViolation("Exterior walls can't be deleted.")
    # The same room on both sides means a partition inside it: nothing to merge.
    to_merge = [r for r in model.rooms if r in one_side or r in other_side]
    if len(to_merge) > 1:
        survivor = max(to_merge, key=lambda r: polygon_area(r.polygon))  # max keeps the first on a tie
        ring = _merged_ring(to_merge, wall)
        if signed_area(ring) * signed_area(survivor.polygon) < 0:
            ring.reverse()
        survivor.polygon = ring
        survivor.area_px = round(polygon_area(ring), 2) or None
        survivor.wall_ids = list(dict.fromkeys(i for r in [survivor, *to_merge] for i in r.wall_ids))
        model.rooms = [r for r in model.rooms if r is survivor or r not in to_merge]
    model.walls = [w for w in model.walls if w.id != wall.id]
    model.doors = [d for d in model.doors if d.wall_id != wall.id]
    model.windows = [w for w in model.windows if w.wall_id != wall.id]
    for room in model.rooms:
        room.wall_ids = [i for i in room.wall_ids if i != wall.id]
    return model

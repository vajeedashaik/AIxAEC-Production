"""Constraint validator. Scope: geometric consistency, not building-code or structural compliance.

With `before`, only what the edit changed is judged, so pre-existing imperfections never block an unrelated edit.
"""

from itertools import chain
from uuid import UUID

from aec_contracts import FloorPlanModel, Point, ValidationIssue, Wall

from .geom import (
    IMAGE_MARGIN_PX,
    are_parallel,
    distance_to_wall,
    find,
    is_axis_aligned,
    midpoint,
    polygon_of,
    signed_area,
    unit,
)
from .resolve import room_name

MIN_ROOM_AREA_PX2 = 1.0
MIN_AREA_FRACTION = 0.2
OPENING_REACH_PX = 30.0
TOUCH_PX = 1.0


def _outside(p: Point, model: FloorPlanModel) -> bool:
    cs = model.coordinate_system
    return not (-IMAGE_MARGIN_PX <= p.x <= cs.image_width + IMAGE_MARGIN_PX
                and -IMAGE_MARGIN_PX <= p.y <= cs.image_height + IMAGE_MARGIN_PX)


def _across(wall: Wall, x: float, y: float) -> float:
    """Signed distance from the wall's line."""
    ux, uy = unit(wall)
    return (x - wall.start.x) * uy - (y - wall.start.y) * ux


def _along_overlap(a: Wall, b: Wall) -> float:
    ux, uy = unit(a)
    a_low, a_high = sorted(p.x * ux + p.y * uy for p in (a.start, a.end))
    b_low, b_high = sorted(p.x * ux + p.y * uy for p in (b.start, b.end))
    return min(a_high, b_high) - max(a_low, b_low)


def _hits_parallel_wall(wall: Wall, old: Wall, after: FloorPlanModel, before_walls: dict[UUID, Wall]) -> bool:
    if abs(_across(old, *midpoint(wall))) <= TOUCH_PX:  # slid along its own line: not a sideways move
        return False
    for other in after.walls:
        other_old = before_walls.get(other.id)
        if other.id == wall.id or other_old is None or not are_parallel(wall, other):
            continue
        if _along_overlap(wall, other) <= TOUCH_PX:
            continue
        was, now = _across(old, *midpoint(other_old)), _across(wall, *midpoint(other))
        if abs(was) > TOUCH_PX and (abs(now) <= TOUCH_PX or was * now < 0):
            return True
    return False


def validate_model(model: FloorPlanModel, before: FloorPlanModel | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    def issue(code: str, message: str, element_id: object = None) -> None:
        issues.append(ValidationIssue.model_validate({"code": code, "message": message, "element_id": element_id}))

    seen = set()
    for element in chain(model.walls, model.doors, model.windows, model.columns, model.stairs, model.furniture,
                         model.dimensions, model.rooms):
        if element.id in seen:
            issue("duplicate_id", "Two elements share one id.", element.id)
        seen.add(element.id)

    walls_before = {w.id: w for w in before.walls} if before else {}
    changed_walls = {w.id for w in model.walls if before is None or w != walls_before.get(w.id)}

    for wall in model.walls:
        if wall.id not in changed_walls:
            continue
        if _outside(wall.start, model) or _outside(wall.end, model):
            issue("out_of_bounds", "That would put a wall outside the image.", wall.id)
        old = walls_before.get(wall.id)
        if old is None:
            continue
        if is_axis_aligned(old) and not is_axis_aligned(wall):
            issue("wall_not_axis_aligned", "That would knock a straight wall off the horizontal or vertical.", wall.id)
        if _hits_parallel_wall(wall, old, model, walls_before):
            issue("wall_collision", "That would move the wall onto or through a parallel wall.", wall.id)
    for wall in model.walls:  # after the checks above: a neighbour flips because the moved wall went through a wall
        old = walls_before.get(wall.id)
        if old is not None and wall.id in changed_walls:
            ou, nu = unit(old), unit(wall)
            if ou[0] * nu[0] + ou[1] * nu[1] <= 0:
                issue("wall_flipped", "That would reverse a connected wall; try a shorter move.", wall.id)

    rooms_before = {r.id: r for r in before.rooms} if before else {}
    for room in model.rooms:
        room_old = rooms_before.get(room.id)
        if before and room_old is not None and room_old.polygon == room.polygon:
            continue
        name = room.label_text or room_name(room)
        if any(_outside(p, model) for p in room.polygon):
            issue("out_of_bounds", f"That would put a corner of {name} outside the image.", room.id)
        if len(room.polygon) < 3 or not polygon_of(room).is_valid:
            issue("room_invalid", f"That would leave {name} with an outline that crosses itself.", room.id)
            continue
        area = signed_area(room.polygon)
        if abs(area) < MIN_ROOM_AREA_PX2:
            issue("room_too_small", f"That would shrink {name} to almost nothing.", room.id)
        elif room_old is not None:
            old_area = signed_area(room_old.polygon)
            if area * old_area < 0:
                issue("room_inverted", f"That would turn {name} inside out.", room.id)
            elif abs(area) < MIN_AREA_FRACTION * abs(old_area):
                issue("room_crushed", f"That would crush {name} to under 20 % of its area.", room.id)

    openings_before = {o.id: o for o in chain(before.doors, before.windows)} if before else {}
    wall_ids = {w.id for w in model.walls}
    for opening in chain(model.doors, model.windows):
        if opening.wall_id is None:
            continue
        if opening.wall_id not in wall_ids:
            issue("opening_orphan", "An opening refers to a wall that no longer exists.", opening.id)
            continue
        if before and opening == openings_before.get(opening.id) and opening.wall_id not in changed_walls:
            continue
        cx, cy = opening.bbox.x + opening.bbox.width / 2, opening.bbox.y + opening.bbox.height / 2
        if distance_to_wall(cx, cy, find(model.walls, opening.wall_id)) > OPENING_REACH_PX:
            issue("opening_detached", "That would leave an opening off the end of its wall.", opening.id)
    return issues

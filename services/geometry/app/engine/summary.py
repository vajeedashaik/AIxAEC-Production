"""One human sentence describing an applied change."""

from aec_contracts import (
    AddDoor,
    AddWall,
    AddWindow,
    Command,
    DeleteDoor,
    DeleteWall,
    DeleteWindow,
    Direction,
    Distance,
    FloorPlanModel,
    MoveWall,
    RenameRoom,
    ResizeMode,
    ResizeRoom,
    Room,
    polygon_area,
)

from .geom import find

RESIZED_MIN_PX2 = 0.5
_SIDE_NAME = {Direction.UP: "top", Direction.DOWN: "bottom", Direction.LEFT: "left", Direction.RIGHT: "right"}


def _distance(d: Distance) -> str:
    return f"{d.value:.10g} {d.unit}"


def _name(room: Room) -> str:
    return room.label_text or "room"


def _resized(before: FloorPlanModel, after: FloorPlanModel) -> str:
    old = {r.id: polygon_area(r.polygon) for r in before.rooms}
    n = sum(1 for r in after.rooms if r.id in old and abs(polygon_area(r.polygon) - old[r.id]) > RESIZED_MIN_PX2)
    return f"; {n} room{'' if n == 1 else 's'} resized" if n else ""


def _opening_width(after: FloorPlanModel, command: AddDoor | AddWindow) -> str:
    if command.width is not None:
        return _distance(command.width)
    added = after.doors[-1] if isinstance(command, AddDoor) else after.windows[-1]
    return f"{added.width_px:.0f} px"


def build_summary(before: FloorPlanModel, after: FloorPlanModel, command: Command) -> str:
    if isinstance(command, MoveWall):
        direction = command.direction.value.lower()
        return f"Moved wall {_distance(command.distance)} {direction}{_resized(before, after)}."
    if isinstance(command, ResizeRoom):
        name = _name(find(before.rooms, command.target_id))
        if command.mode is ResizeMode.EXPAND:
            direction = command.direction.value.lower()
            return f"Expanded {name} {_distance(command.distance)} {direction}{_resized(before, after)}."
        side = _SIDE_NAME[command.direction]
        return f"Contracted {name} {_distance(command.distance)} from the {side}{_resized(before, after)}."
    if isinstance(command, AddWall):
        return f"Added a wall, {after.walls[-1].length_px:.0f} px long."
    if isinstance(command, DeleteWall):
        remaining = {r.id for r in after.rooms}
        gone = [r for r in before.rooms if r.id not in remaining]
        if not gone:
            return "Deleted wall."
        # The union can equal the survivor's outline when a room sat inside it, so the polygon may not have changed.
        survivor = next((r for r in after.rooms if r.polygon != find(before.rooms, r.id).polygon), None)
        merged = [r for r in before.rooms if r in gone or (survivor and r.id == survivor.id)]
        into = f" into {_name(survivor)}" if survivor else ""
        return f"Deleted wall; merged {' and '.join(_name(r) for r in merged)}{into}."
    if isinstance(command, AddDoor):
        return f"Added a door, {_opening_width(after, command)} wide."
    if isinstance(command, AddWindow):
        return f"Added a window, {_opening_width(after, command)} wide."
    if isinstance(command, DeleteDoor):
        return "Deleted door."
    if isinstance(command, DeleteWindow):
        return "Deleted window."
    if isinstance(command, RenameRoom):
        return f'Renamed {_name(find(before.rooms, command.target_id))} to "{command.name}".'
    return f"Set scale to {after.coordinate_system.mm_per_pixel:.4g} mm per pixel."

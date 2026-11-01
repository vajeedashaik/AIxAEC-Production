"""ADD_DOOR, ADD_WINDOW, DELETE_DOOR, DELETE_WINDOW."""

from aec_contracts import AddDoor, AddWindow, DeleteDoor, DeleteWindow, Door, FloorPlanModel, Source, Wall, Window
from aec_contracts.model import Opening

from ..errors import GeometryError
from ..geom import bbox, find, to_px, unit
from .ids import new_id

DEFAULT_MM = {"door": 900.0, "window": 1200.0}
DEFAULT_PX = {"door": 40.0, "window": 48.0}
MIN_WIDTH_PX = 4.0
MAX_WALL_FRACTION = 0.9
THICKNESS_WHEN_UNKNOWN_PX = 10.0


def _width_px(model: FloorPlanModel, command: AddDoor | AddWindow, kind: str) -> float:
    cs = model.coordinate_system
    if command.width is not None:
        return to_px(command.width, cs)
    return DEFAULT_MM[kind] / cs.mm_per_pixel if cs.mm_per_pixel else DEFAULT_PX[kind]


def _place(model: FloorPlanModel, command: AddDoor | AddWindow, kind: str) -> dict[str, object]:
    wall = find(model.walls, command.target_id)
    width = _width_px(model, command, kind)
    if width < MIN_WIDTH_PX:
        raise GeometryError(f"A {kind} must be at least {MIN_WIDTH_PX:g} px wide.")
    if width > MAX_WALL_FRACTION * wall.length_px:
        raise GeometryError(f"That {kind} would take more than 90 % of the wall ({wall.length_px:.0f} px long).")
    half = width / 2
    along = min(max(command.position * wall.length_px, half), wall.length_px - half)
    ux, uy = unit(wall)
    for other in (*model.doors, *model.windows):
        if other.wall_id == wall.id and abs(along - _centre_along(other, wall)) < half + _half_width(other):
            raise GeometryError("That spot overlaps an existing opening on this wall; pick another position.")
    x, y = wall.start.x + along * ux, wall.start.y + along * uy
    thickness = wall.thickness_px or THICKNESS_WHEN_UNKNOWN_PX
    # The rectangle's bounding box at any wall angle; a horizontal wall gives width × thickness.
    w, h = abs(ux) * width + abs(uy) * thickness, abs(uy) * width + abs(ux) * thickness
    box = bbox(max(x - w / 2, 0.0), max(y - h / 2, 0.0), w, h)
    return {"id": new_id(model, command), "bbox": box, "wall_id": wall.id, "width_px": round(width, 2),
            "confidence": 1.0, "source": Source.USER_CONFIRMED}


def _centre_along(opening: Opening, wall: Wall) -> float:
    ux, uy = unit(wall)
    cx, cy = opening.bbox.x + opening.bbox.width / 2, opening.bbox.y + opening.bbox.height / 2
    return (cx - wall.start.x) * ux + (cy - wall.start.y) * uy


def _half_width(opening: Opening) -> float:
    return (opening.width_px or max(opening.bbox.width, opening.bbox.height)) / 2


def add_door(model: FloorPlanModel, command: AddDoor) -> FloorPlanModel:
    model.doors.append(Door.model_validate(_place(model, command, "door")))
    return model


def add_window(model: FloorPlanModel, command: AddWindow) -> FloorPlanModel:
    model.windows.append(Window.model_validate(_place(model, command, "window")))
    return model


def delete_door(model: FloorPlanModel, command: DeleteDoor) -> FloorPlanModel:
    model.doors = [d for d in model.doors if d.id != command.target_id]
    return model


def delete_window(model: FloorPlanModel, command: DeleteWindow) -> FloorPlanModel:
    model.windows = [w for w in model.windows if w.id != command.target_id]
    return model

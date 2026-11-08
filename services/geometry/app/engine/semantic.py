"""Semantic validation: is this resolved command meaningful for this plan, before any geometry runs?"""

from math import hypot, isfinite

from aec_contracts import AddDoor, AddWall, AddWindow, FloorPlanModel, MoveWall, ResizeRoom, SetScale
from aec_contracts.commands import EngineCommand

from .errors import SemanticError
from .geom import IMAGE_MARGIN_PX, find, to_px

MOVE_LIMIT_FACTOR = 3
MIN_MM_PER_PX, MAX_MM_PER_PX = 0.05, 500.0


def check_semantics(model: FloorPlanModel, command: EngineCommand) -> None:
    cs = model.coordinate_system
    if isinstance(command, MoveWall | ResizeRoom):
        limit = MOVE_LIMIT_FACTOR * max(cs.image_width, cs.image_height)
        if to_px(command.distance, cs) > limit:
            raise SemanticError(f"That's too far: the limit is {limit} px, three times the image's larger side.")
    elif isinstance(command, AddDoor | AddWindow):
        if command.width is not None:
            span = find(model.walls, command.target_id).length_px
            width = to_px(command.width, cs)
            if width > span:
                raise SemanticError(f"That opening is {width:.0f} px wide, wider than the wall ({span:.0f} px).")
    elif isinstance(command, AddWall):
        for p in (command.start, command.end):
            if p.x > cs.image_width + IMAGE_MARGIN_PX or p.y > cs.image_height + IMAGE_MARGIN_PX:
                raise SemanticError(f"({p.x:g}, {p.y:g}) is outside the image "
                                    f"({cs.image_width} × {cs.image_height} px).")
        if hypot(command.end.x - command.start.x, command.end.y - command.start.y) < 1:
            raise SemanticError("That wall is too short: it must be at least 1 px long.")
        # JSON can carry Infinity, and the contract's gt=0 lets it through.
        if command.thickness_px is not None and (
                not isfinite(command.thickness_px) or command.thickness_px > max(cs.image_width, cs.image_height)):
            raise SemanticError("That wall thickness is larger than the image.")
    elif isinstance(command, SetScale):
        ratio = command.length_mm / find(model.walls, command.target_id).length_px
        if not MIN_MM_PER_PX <= ratio <= MAX_MM_PER_PX:
            raise SemanticError(f"That gives {ratio:.3g} mm/px; a scale must be between {MIN_MM_PER_PX} and "
                                f"{MAX_MM_PER_PX:g} mm/px, so check the length and the wall.")

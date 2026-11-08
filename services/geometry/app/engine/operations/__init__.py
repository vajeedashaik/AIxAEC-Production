"""The operations. Each mutates the deep copy `apply_operation` hands it, so the public call stays pure."""

from collections.abc import Callable
from typing import Any

from aec_contracts import FloorPlanModel
from aec_contracts.commands import EngineCommand

from .metadata import rename_room, set_scale
from .openings import add_door, add_window, delete_door, delete_window
from .split import split_room
from .walls import add_wall, delete_wall, move_wall, resize_room

_OPERATIONS: dict[str, Callable[[FloorPlanModel, Any], FloorPlanModel]] = {
    "MOVE_WALL": move_wall, "ADD_WALL": add_wall, "DELETE_WALL": delete_wall, "RESIZE_ROOM": resize_room,
    "ADD_DOOR": add_door, "ADD_WINDOW": add_window, "DELETE_DOOR": delete_door, "DELETE_WINDOW": delete_window,
    "RENAME_ROOM": rename_room, "SET_SCALE": set_scale, "SPLIT_ROOM": split_room,
}


def apply_operation(model: FloorPlanModel, command: EngineCommand) -> FloorPlanModel:
    return _OPERATIONS[command.operation](model.model_copy(deep=True), command)

"""Structured edit commands (CONTRACTS.md §3). The LLM produces dicts; these validate them."""

from enum import StrEnum
from typing import Annotated, Literal, Self, get_args
from uuid import UUID

from pydantic import Field, TypeAdapter, model_validator

from .model import Point, RoomType, Strict


class Direction(StrEnum):  LEFT = "LEFT"; RIGHT = "RIGHT"; UP = "UP"; DOWN = "DOWN"
class ResizeMode(StrEnum): EXPAND = "EXPAND"; CONTRACT = "CONTRACT"


class Distance(Strict):
    value: float = Field(gt=0, allow_inf_nan=False)
    unit: Literal["mm", "px"]


class Targeted(Strict):
    target_id: UUID | None = None
    target_query: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _exactly_one_target(self) -> Self:
        if (self.target_id is None) == (self.target_query is None):
            raise ValueError("exactly one of target_id / target_query must be set")
        return self


class MoveWall(Targeted):    operation: Literal["MOVE_WALL"];    direction: Direction; distance: Distance
class DeleteWall(Targeted):  operation: Literal["DELETE_WALL"]
class ResizeRoom(Targeted):  operation: Literal["RESIZE_ROOM"];  direction: Direction; distance: Distance; mode: ResizeMode  # noqa: E501
class AddDoor(Targeted):     operation: Literal["ADD_DOOR"];     position: float = Field(default=0.5, ge=0, le=1); width: Distance | None = None  # noqa: E501
class AddWindow(Targeted):   operation: Literal["ADD_WINDOW"];   position: float = Field(default=0.5, ge=0, le=1); width: Distance | None = None  # noqa: E501
class DeleteDoor(Targeted):  operation: Literal["DELETE_DOOR"]
class DeleteWindow(Targeted):operation: Literal["DELETE_WINDOW"]
class RenameRoom(Targeted):  operation: Literal["RENAME_ROOM"];  name: str = Field(min_length=1, max_length=80); room_type: RoomType | None = None  # noqa: E501
class SetScale(Targeted):    operation: Literal["SET_SCALE"];    length_mm: float = Field(gt=0, le=1_000_000)


class AddWall(Strict):  # untargeted
    operation: Literal["ADD_WALL"]
    start: Point; end: Point
    thickness_px: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _distinct_endpoints(self) -> Self:
        if self.start == self.end:
            raise ValueError("wall start and end must differ")
        return self


_COMMAND_TYPES = (MoveWall, AddWall, DeleteWall, ResizeRoom, AddDoor, AddWindow,
                  DeleteDoor, DeleteWindow, RenameRoom, SetScale)

Command = Annotated[
    MoveWall | AddWall | DeleteWall | ResizeRoom | AddDoor | AddWindow
    | DeleteDoor | DeleteWindow | RenameRoom | SetScale,
    Field(discriminator="operation"),
]
COMMAND_ADAPTER: TypeAdapter[Command] = TypeAdapter(Command)
OPERATIONS: tuple[str, ...] = tuple(get_args(t.model_fields["operation"].annotation)[0] for t in _COMMAND_TYPES)

TARGET_KIND: dict[str, Literal["wall", "room", "door", "window"]] = {
    "MOVE_WALL": "wall", "DELETE_WALL": "wall", "ADD_DOOR": "wall", "ADD_WINDOW": "wall", "SET_SCALE": "wall",
    "RESIZE_ROOM": "room", "RENAME_ROOM": "room", "DELETE_DOOR": "door", "DELETE_WINDOW": "window",
}

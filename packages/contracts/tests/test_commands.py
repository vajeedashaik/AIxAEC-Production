import uuid
from typing import Any

import pytest
from conftest import load
from pydantic import ValidationError

from aec_contracts import (
    COMMAND_ADAPTER,
    OPERATIONS,
    TARGET_KIND,
    AddDoor,
    AddWall,
    CommandRequest,
    MoveWall,
    RenameRoom,
)

TID = str(uuid.uuid4())
ONE_OF_EACH: list[dict[str, Any]] = [
    {"operation": "MOVE_WALL", "target_id": TID, "direction": "LEFT", "distance": {"value": 300, "unit": "mm"}},
    {"operation": "ADD_WALL", "start": {"x": 0, "y": 0}, "end": {"x": 10, "y": 0}},
    {"operation": "DELETE_WALL", "target_query": "wall between kitchen and living room"},
    {"operation": "RESIZE_ROOM", "target_query": "kitchen", "direction": "UP",
     "distance": {"value": 20, "unit": "px"}, "mode": "EXPAND"},
    {"operation": "ADD_DOOR", "target_id": TID, "position": 0.3, "width": {"value": 900, "unit": "mm"}},
    {"operation": "ADD_WINDOW", "target_id": TID},
    {"operation": "DELETE_DOOR", "target_query": "bathroom door"},
    {"operation": "DELETE_WINDOW", "target_id": TID},
    {"operation": "RENAME_ROOM", "target_query": "bedroom", "name": "Guest", "room_type": "BEDROOM"},
    {"operation": "SET_SCALE", "target_id": TID, "length_mm": 3600},
]


def test_operations_order_and_target_kind() -> None:
    assert OPERATIONS == ("MOVE_WALL", "ADD_WALL", "DELETE_WALL", "RESIZE_ROOM", "ADD_DOOR", "ADD_WINDOW",
                          "DELETE_DOOR", "DELETE_WINDOW", "RENAME_ROOM", "SET_SCALE")
    assert set(TARGET_KIND) == set(OPERATIONS) - {"ADD_WALL"}


@pytest.mark.parametrize("raw", ONE_OF_EACH, ids=lambda r: r["operation"])
def test_discriminated_union_parses_every_operation(raw: dict[str, Any]) -> None:
    cmd = COMMAND_ADAPTER.validate_python(raw)
    assert cmd.operation == raw["operation"]
    assert type(cmd).__name__.upper().replace("_", "") == raw["operation"].replace("_", "")
    assert COMMAND_ADAPTER.validate_json(COMMAND_ADAPTER.dump_json(cmd)) == cmd


def test_defaults() -> None:
    door = COMMAND_ADAPTER.validate_python({"operation": "ADD_DOOR", "target_query": "x"})
    assert isinstance(door, AddDoor) and door.position == 0.5 and door.width is None


def test_unknown_operation_rejected() -> None:
    with pytest.raises(ValidationError):
        COMMAND_ADAPTER.validate_python({"operation": "EXPLODE", "target_query": "x"})


@pytest.mark.parametrize("raw", ONE_OF_EACH, ids=lambda r: r["operation"])
def test_extra_forbidden(raw: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        COMMAND_ADAPTER.validate_python({**raw, "coordinates": [1, 2]})


@pytest.mark.parametrize("target", [{}, {"target_id": TID, "target_query": "kitchen"}])
def test_targeted_requires_exactly_one(target: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="exactly one of target_id / target_query"):
        COMMAND_ADAPTER.validate_python({"operation": "DELETE_WALL", **target})


def test_targeted_positive_cases() -> None:
    assert MoveWall.model_validate(ONE_OF_EACH[0]).target_id == uuid.UUID(TID)
    assert RenameRoom.model_validate(ONE_OF_EACH[8]).target_query == "bedroom"


@pytest.mark.parametrize("bad", [
    {"distance": {"value": 0, "unit": "mm"}},
    {"distance": {"value": -5, "unit": "mm"}},
    {"distance": {"value": 5, "unit": "cm"}},
    {"distance": {"value": float("inf"), "unit": "mm"}},
    {"direction": "NORTH"},
])
def test_move_wall_bounds(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        COMMAND_ADAPTER.validate_python({**ONE_OF_EACH[0], **bad})


def test_bounds_on_other_operations() -> None:
    with pytest.raises(ValidationError):
        COMMAND_ADAPTER.validate_python({**ONE_OF_EACH[4], "position": 1.5})
    with pytest.raises(ValidationError):
        COMMAND_ADAPTER.validate_python({**ONE_OF_EACH[9], "length_mm": 0})
    with pytest.raises(ValidationError):
        COMMAND_ADAPTER.validate_python({**ONE_OF_EACH[8], "name": ""})
    with pytest.raises(ValidationError):
        AddWall.model_validate({"operation": "ADD_WALL", "start": {"x": 1, "y": 1}, "end": {"x": 1, "y": 1}})


def test_command_request_exactly_one() -> None:
    CommandRequest(instruction="move it")
    CommandRequest(command={"operation": "DELETE_WALL", "target_query": "x"}, expected_version=3)
    with pytest.raises(ValidationError, match="exactly one of instruction / command"):
        CommandRequest()
    with pytest.raises(ValidationError, match="exactly one of instruction / command"):
        CommandRequest(instruction="a", command={})
    with pytest.raises(ValidationError):
        CommandRequest(instruction="")


def test_command_examples_fixture() -> None:
    data = load("commands.examples.json")
    cases = data["cases"]
    assert len(cases) >= 40
    parsed = [c for c in cases if c["expected"] == "PARSED"]
    assert {c["expected_command"]["operation"] for c in parsed} == set(OPERATIONS)
    for c in cases:
        assert c["brief_fixture"] in {"apartment", "apartment.unscaled", "two_room"}
        load(f"{c['brief_fixture']}.model.json")
        if c["expected"] == "PARSED":
            COMMAND_ADAPTER.validate_python(c["expected_command"])
        else:
            assert c["expected"] == "UNKNOWN" and c["expected_command"] is None
    units = {c["expected_command"].get("distance", c["expected_command"].get("width") or {}).get("unit")
             for c in parsed}
    assert {"mm", "px"} <= units
    text = " ".join(c["instruction"].lower() for c in cases)
    for word in ("cm", " m ", "north", "south", "east", "west", "left", "right", "up", "down", "between",
                 "%", "900 wide"):
        assert word in text, word

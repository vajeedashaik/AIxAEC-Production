import json
from pathlib import Path
from typing import Any

import pytest
from aec_contracts import COMMAND_ADAPTER

from app.rules import parse_rules

FIXTURES = Path(__file__).parents[3] / "packages/contracts/fixtures/commands.examples.json"
CASES: list[dict[str, Any]] = json.loads(FIXTURES.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["instruction"] for c in CASES])
def test_fixture_case(case: dict[str, Any]) -> None:
    assert parse_rules(case["instruction"]) == case["expected_command"]


def _move(text: str) -> dict[str, Any]:
    cmd = parse_rules(text)
    assert cmd is not None and cmd["operation"] == "MOVE_WALL", text
    return cmd


@pytest.mark.parametrize("phrase,value,unit", [
    ("300 mm", 300, "mm"), ("300mm", 300, "mm"), ("300 millimetres", 300, "mm"), ("300 millimeters", 300, "mm"),
    ("30 cm", 300, "mm"), ("30 centimetres", 300, "mm"), ("1.5 m", 1500, "mm"), ("1.5 metres", 1500, "mm"),
    ("1.1 meters", 1100, "mm"), ("40 px", 40, "px"), ("40 pixels", 40, "px"), ("1 pixel", 1, "px"),
    ("1,200 mm", 1200, "mm"), (".5 m", 500, "mm"),
    ("three metres", 3000, "mm"), ("twenty cm", 200, "mm"), ("one point five metres", 1500, "mm"),
    ("eleven px", 11, "px"), ("seventeen mm", 17, "mm"),
])
def test_units_and_number_words(phrase: str, value: float, unit: str) -> None:
    cmd = _move(f"move the shared wall {phrase} left")
    assert cmd["distance"] == {"value": value, "unit": unit}


@pytest.mark.parametrize("phrase", ["twenty five mm", "three hundred mm", "300", "300 ft", "0 mm", "- 300 mm",
                                    "minus 300 mm", "300 mm 400 mm"])
def test_distance_never_guessed(phrase: str) -> None:
    assert parse_rules(f"move the shared wall {phrase} left") is None


@pytest.mark.parametrize("phrase,direction", [
    ("left", "LEFT"), ("right", "RIGHT"), ("up", "UP"), ("down", "DOWN"), ("north", "UP"), ("south", "DOWN"),
    ("east", "RIGHT"), ("west", "LEFT"), ("top", "UP"), ("bottom", "DOWN"), ("to the left", "LEFT"),
    ("towards the north", "UP"), ("toward the east", "RIGHT"), ("downwards", "DOWN"), ("upward", "UP"),
    ("towards the top", "UP"),
])
def test_direction_synonyms(phrase: str, direction: str) -> None:
    assert _move(f"move the shared wall 10 mm {phrase}")["direction"] == direction


@pytest.mark.parametrize("text", [
    "move the shared wall 10 mm towards the kitchen",  # needs geometry to know which way that is
    "move the shared wall 10 mm left right",
    "move the wall between the left bedroom and the kitchen 10 mm",
    "move the wall between the kitchen 10 mm left",
])
def test_ambiguous_direction_is_unknown(text: str) -> None:
    assert parse_rules(text) is None


def test_room_names_containing_directions_keep_their_meaning() -> None:
    cmd = _move("move the wall between the north bedroom and the kitchen 10 mm left")
    assert cmd["target_query"] == "wall between north bedroom and kitchen" and cmd["direction"] == "LEFT"


@pytest.mark.parametrize("text,target", [
    ("move the kitchen wall 10 mm left", "kitchen wall"),
    ("move the wall of the kitchen 10 mm left", "kitchen wall"),
    ("move the living room kitchen wall 10 mm left", "wall between living room and kitchen"),
    ("move the gym/sauna wall 10 mm left", "wall between gym and sauna"),
    ("move the en-suite wall 10 mm left", "en-suite wall"),
    ("please move the top wall of the kitchen 10 mm left.", "top wall of kitchen"),
    ("can you move the wall 10 mm left", "wall"),
])
def test_wall_targets(text: str, target: str) -> None:
    assert _move(text)["target_query"] == target


def test_resize_phrasings() -> None:
    assert parse_rules("make the kitchen bigger by 500 mm to the right") == {
        "operation": "RESIZE_ROOM", "target_query": "kitchen", "direction": "RIGHT",
        "distance": {"value": 500, "unit": "mm"}, "mode": "EXPAND"}
    assert parse_rules("shrink the kitchen by half a metre to the right") is None
    cmd = parse_rules("make the kitchen 200 mm smaller on the left")
    assert cmd is not None and cmd["mode"] == "CONTRACT" and cmd["direction"] == "LEFT"


@pytest.mark.parametrize("text", [
    "make it bigger by 500 mm to the right",
    "make the kitchen and hall bigger by 500 mm to the right",
    "make the wall 300 mm longer to the right",
    "make the kitchen 300 mm bigger and smaller to the right",
])
def test_resize_rejects(text: str) -> None:
    assert parse_rules(text) is None


@pytest.mark.parametrize("text,position,width", [
    ("add a door to the kitchen wall at 30 %", 0.3, None),
    ("add a door to the kitchen wall at 30 percent", 0.3, None),
    ("add a door halfway along the kitchen wall", 0.5, None),
    ("add a door 900 wide on the kitchen wall", 0.5, {"value": 900, "unit": "mm"}),
    ("add a door 90 cm wide on the kitchen wall", 0.5, {"value": 900, "unit": "mm"}),
])
def test_add_door_phrasings(text: str, position: float, width: dict[str, Any] | None) -> None:
    cmd = parse_rules(text)
    assert cmd is not None and cmd["operation"] == "ADD_DOOR" and cmd["target_query"] == "kitchen wall"
    assert cmd["position"] == position and cmd.get("width") == width


@pytest.mark.parametrize("text", [
    "add a door at 150% of the kitchen wall",
    "add a door at thirty percent of the kitchen wall",
    "add a door at 20% and 40% of the kitchen wall",
    "add a 900 door on the kitchen wall",
    "add two doors to the kitchen wall",
    "add a door",
    "add a door and a window to the kitchen wall",
])
def test_add_door_rejects(text: str) -> None:
    assert parse_rules(text) is None


@pytest.mark.parametrize("text,target,name,room_type", [
    ("rename the kitchen as Pantry", "kitchen", "Pantry", "STORAGE"),
    ("rename room 3 to kitchen", "room 3", "Kitchen", "KITCHEN"),
    ("rename the room kitchen as pantry", "kitchen", "Pantry", "STORAGE"),
    ("call the kitchen as Cook's Place", "kitchen", "Cook's Place", None),
    ("label the hall as bob's room", "hall", "Bob's Room", None),
    ("name the bedroom to 'guest room'", "bedroom", "guest room", None),
    ('call the office "Room Two"', "office", "Room Two", None),
    ("rename the den to Studio Two", "den", "Studio Two", None),  # number words in a name stay words
])
def test_rename_phrasings(text: str, target: str, name: str, room_type: str | None) -> None:
    cmd = parse_rules(text)
    assert cmd is not None and cmd["operation"] == "RENAME_ROOM"
    assert (cmd["target_query"], cmd["name"], cmd.get("room_type")) == (target, name, room_type)


@pytest.mark.parametrize("text,target,length", [
    ("this wall is 3.6 m", "this wall", 3600),
    ("set the scale: wall between kitchen and bedroom is 3600 mm", "wall between kitchen and bedroom", 3600),
    ("the kitchen wall is 3,600 mm long", "kitchen wall", 3600),
    ("the shared wall measures three metres", "shared wall", 3000),
])
def test_set_scale_phrasings(text: str, target: str, length: float) -> None:
    assert parse_rules(text) == {"operation": "SET_SCALE", "target_query": target, "length_mm": length}


@pytest.mark.parametrize("text", [
    "this wall is 300 px",  # px must never become mm
    "what if this wall is 3 m",
    "move the wall is 3 m",
    "add a wall from (1, 2) to (1, 2)",  # zero length
    "add a wall from (-1, 2) to (3, 4)",
    "draw a 10 mm thick wall from 1,2 to 3,4",
    "draw a " + "9" * 400 + " px thick wall from 1,2 to 3,4",  # inf isn't serialisable
    "move the door between the kitchen and the hall 10 mm left",
    "delete the kitchen",
    "delete every door",
    "delete the door and the window",
    "move the shared wall 10 mm left and delete the kitchen door",
    "move the shared wall 10 mm left, then add a door to it",
    "rename it to Kitchen",
    "rename the bedroom",
    "hello there",
])
def test_nonsense_is_unknown(text: str) -> None:
    assert parse_rules(text) is None


@pytest.mark.parametrize("case", [c for c in CASES if c["expected"] == "PARSED"], ids=lambda c: c["instruction"])
def test_every_output_is_contract_valid(case: dict[str, Any]) -> None:
    COMMAND_ADAPTER.validate_python(parse_rules(case["instruction"]))

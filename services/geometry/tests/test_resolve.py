import json
from typing import Any
from uuid import UUID

import pytest
from aec_contracts import FloorPlanModel

from .conftest import FIXTURES, applied, clarified, el, load, rejected, room, run, wid

SCALE = {"operation": "SET_SCALE", "length_mm": 4500}
DELETE_DOOR = {"operation": "DELETE_DOOR"}
DELETE_WINDOW = {"operation": "DELETE_WINDOW"}
RENAME = {"operation": "RENAME_ROOM", "name": "X"}


def target(model: FloorPlanModel, base: dict[str, Any], **kw: Any) -> UUID | None:
    return applied(model, **base, **kw).command.target_id  # type: ignore[union-attr]


def unlink(model: FloorPlanModel, label: str, keep: list[str]) -> FloorPlanModel:
    room(model, label).wall_ids = [wid(model, p) for p in keep]
    return model


@pytest.mark.parametrize("query,label", [
    ("kitchen", "KITCHEN"), ("the KITCHEN", "KITCHEN"), ("living room", "LIVING"), ("lounge", "LIVING"),
    ("toilet", "BATH"), ("bathroom", "BATH"), ("corridor", "HALL"), ("hallway", "HALL"), ("bedroom", "BEDROOM"),
])
def test_room_by_label_or_synonym(apartment: FloorPlanModel, query: str, label: str) -> None:
    result = applied(apartment, **RENAME, target_query=query)
    assert result.command.target_id == room(apartment, label).id  # type: ignore[union-attr]
    assert result.command.target_query is None  # type: ignore[union-attr]


@pytest.mark.parametrize("query", ["garage", "x", "asdf qwerty"])
def test_room_no_match(apartment: FloorPlanModel, query: str) -> None:
    assert query in rejected(apartment, "entity_resolution", **RENAME, target_query=query)


def test_room_several_matches_clarifies(apartment: FloorPlanModel) -> None:
    room(apartment, "BEDROOM").label_text = "KITCHEN 2"
    result = clarified(apartment, **RENAME, target_query="kitchen")
    assert result.question == "Which room do you mean?"
    assert {c.kind for c in result.candidates} == {"room"} and len(result.candidates) == 2
    assert result.candidates[0].x == pytest.approx(780)


def test_specific_label_beats_generic(apartment: FloorPlanModel) -> None:
    room(apartment, "KITCHEN").label_text = "MASTER BEDROOM"
    assert target(apartment, RENAME, target_query="master bedroom") == room(apartment, "MASTER BEDROOM").id
    assert len(clarified(apartment, **RENAME, target_query="bedroom").candidates) == 2


@pytest.mark.parametrize("query,expected", [
    ("wall between kitchen and living room", "260db342"),
    ("the wall between the living room and the kitchen", "260db342"),
    ("wall between hall and bath", "cac36134"),
    ("wall between kitchen and bedroom", "19dadcef"),
    ("north wall of kitchen", "f1d5effe"),
    ("kitchen's north wall", "f1d5effe"),
    ("top wall of the bathroom", "cac36134"),
    ("east wall of bedroom", "b8d3af23"),
    ("west wall of kitchen", "260db342"),
    ("north kitchen wall", "f1d5effe"),
    ("south wall of bathroom", "07d7ef81"),
])
def test_wall_resolves(apartment: FloorPlanModel, query: str, expected: str) -> None:
    assert target(apartment, SCALE, target_query=query) == wid(apartment, expected)


def test_between_rooms_sharing_no_wall(apartment: FloorPlanModel) -> None:
    assert rejected(apartment, "entity_resolution", **SCALE,
                    target_query="wall between living and bath") == "Those rooms don't share a wall."


def test_between_unknown_room(apartment: FloorPlanModel) -> None:
    assert "garage" in rejected(apartment, "entity_resolution", **SCALE, target_query="wall between garage and bath")


def test_between_prefers_the_wall_that_separates_them(apartment: FloorPlanModel) -> None:
    # Linked to both rooms (as vision does for merged collinear walls), but only 260db342 has one room on each side.
    room(apartment, "LIVING").wall_ids.append(wid(apartment, "19dadcef"))
    assert target(apartment, SCALE, target_query="wall between kitchen and living") == wid(apartment, "260db342")


def test_between_several_shared_walls_none_separating_clarifies(apartment: FloorPlanModel) -> None:
    room(apartment, "LIVING").wall_ids += [wid(apartment, "19dadcef"), wid(apartment, "f1d5effe")]
    room(apartment, "KITCHEN").wall_ids.remove(wid(apartment, "260db342"))
    assert len(clarified(apartment, **SCALE, target_query="wall between kitchen and living").candidates) == 2


def test_room_walls_clarify_with_human_labels(apartment: FloorPlanModel) -> None:
    result = clarified(apartment, **SCALE, target_query="kitchen wall")
    assert result.question == "Which kitchen wall do you mean?"
    assert len(result.candidates) == 4
    shared = next(c for c in result.candidates if c.id == wid(apartment, "260db342"))
    assert shared.label == "vertical wall, 450 px long (living ↔ kitchen)"
    assert (shared.x, shared.y, shared.kind) == (600, 325, "wall")
    assert any(c.label.startswith("horizontal wall, 360 px long") for c in result.candidates)


def test_room_with_no_walls(apartment: FloorPlanModel) -> None:
    unlink(apartment, "KITCHEN", [])
    assert rejected(apartment, "entity_resolution", **SCALE, target_query="kitchen wall") == \
        "No walls are linked to kitchen."


def test_room_with_one_wall_resolves(apartment: FloorPlanModel) -> None:
    unlink(apartment, "KITCHEN", ["260db342"])
    assert target(apartment, SCALE, target_query="kitchen wall") == wid(apartment, "260db342")


def test_orientation_ties_clarify(apartment: FloorPlanModel) -> None:
    assert len(clarified(apartment, **SCALE, target_query="north wall of hallway").candidates) == 3
    assert len(clarified(apartment, **SCALE, target_query="south wall of hall").candidates) == 2


def test_orientation_with_no_such_wall(apartment: FloorPlanModel) -> None:
    unlink(apartment, "KITCHEN", ["260db342", "19dadcef"])
    assert "no north wall" in rejected(apartment, "entity_resolution", **SCALE, target_query="north wall of kitchen")


def test_orientation_word_inside_a_label_is_kept(apartment: FloorPlanModel) -> None:
    room(apartment, "BEDROOM").label_text = "EAST WING"
    assert target(apartment, RENAME, target_query="east wing") == room(apartment, "EAST WING").id
    assert target(apartment, SCALE, target_query="north wall of east wing") == wid(apartment, "60973af4")


def test_single_wall_model_resolves_trivially(two_room: FloorPlanModel) -> None:
    two_room.walls, two_room.rooms = two_room.walls[:1], []
    assert target(two_room, SCALE, target_query="whatever this says") == two_room.walls[0].id


def test_no_walls_at_all(two_room: FloorPlanModel) -> None:
    two_room.walls, two_room.rooms = [], []
    assert "no walls" in rejected(two_room, "entity_resolution", **SCALE, target_query="the wall")


def test_shared_wall(two_room: FloorPlanModel, apartment: FloorPlanModel) -> None:
    assert str(target(two_room, SCALE, target_query="shared wall")).startswith("5b0e4ca9")
    # A merged exterior wall linked to both rooms is still not the one they share.
    outer = next(w.id for w in two_room.walls if not str(w.id).startswith("5b0e4ca9"))
    for r in two_room.rooms:
        r.wall_ids.append(outer)
    assert str(target(two_room, SCALE, target_query="shared wall")).startswith("5b0e4ca9")
    two_room.rooms[0].wall_ids.remove(outer)
    assert len(clarified(apartment, **SCALE, target_query="shared wall").candidates) == 6
    two_room.rooms = []
    assert "share" in rejected(two_room, "entity_resolution", **SCALE, target_query="shared wall")


def test_bare_wall_clarifies_over_all_walls(apartment: FloorPlanModel) -> None:
    assert len(clarified(apartment, **SCALE, target_query="the wall").candidates) == 17


@pytest.mark.parametrize("base,query,expected", [
    (DELETE_DOOR, "bathroom door", "d50b70b9"),
    (DELETE_DOOR, "bedroom door", "0f201baf"),
    (DELETE_DOOR, "door between bedroom and hallway", "0f201baf"),
    (DELETE_WINDOW, "kitchen window", "37a46186"),
    (DELETE_WINDOW, "bedroom window", "3be54df3"),
    (DELETE_WINDOW, "north window of kitchen", "37a46186"),
])
def test_opening_resolves_via_room(apartment: FloorPlanModel, base: dict[str, Any], query: str, expected: str) -> None:
    assert str(target(apartment, base, target_query=query)).startswith(expected)


def test_opening_clarifies_with_human_labels(apartment: FloorPlanModel) -> None:
    result = clarified(apartment, **DELETE_DOOR, target_query="hall door")
    assert result.question == "Which door do you mean?"
    assert len(result.candidates) == 4
    door = next(c for c in result.candidates if str(c.id).startswith("d50b70b9"))
    assert door.label == "door at (1130, 700) in hall / bath"
    assert (door.x, door.y, door.kind) == (1130, 700, "door")


@pytest.mark.parametrize("query", ["door", "the front door", "main door"])
def test_opening_without_room_phrase(apartment: FloorPlanModel, query: str) -> None:
    assert len(clarified(apartment, **DELETE_DOOR, target_query=query).candidates) == 4
    apartment.doors = apartment.doors[:1]
    assert target(apartment, DELETE_DOOR, target_query=query) == apartment.doors[0].id


def test_opening_refusals(apartment: FloorPlanModel) -> None:
    assert "kitchen" in rejected(apartment, "entity_resolution", **DELETE_DOOR, target_query="kitchen door")
    assert "garage" in rejected(apartment, "entity_resolution", **DELETE_DOOR, target_query="garage door")
    assert "share" in rejected(apartment, "entity_resolution", **DELETE_DOOR,
                               target_query="door between living and bath")
    apartment.doors = []
    assert "no doors" in rejected(apartment, "entity_resolution", **DELETE_DOOR, target_query="door")


def test_explicit_id_is_kind_checked(apartment: FloorPlanModel) -> None:
    door = el(apartment.doors, "d50b70b9").id
    assert "door, not a wall" in rejected(apartment, "entity_resolution", **SCALE, target_id=str(door))
    assert "wall, not a room" in rejected(apartment, "entity_resolution", **RENAME,
                                          target_id=str(wid(apartment, "260db342")))
    assert "No wall" in rejected(apartment, "entity_resolution", **SCALE,
                                 target_id="00000000-0000-4000-8000-000000000000")


def test_clarification_candidate_can_be_sent_back() -> None:
    model = load("apartment")
    pick = clarified(model, **SCALE, target_query="kitchen wall").candidates[0]
    assert target(model, SCALE, target_id=str(pick.id)) == pick.id


EXAMPLES = json.loads((FIXTURES / "commands.examples.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", [c for c in EXAMPLES if c.get("expected_command")], ids=lambda c: c["instruction"])
def test_every_parser_example_is_understood(case: dict[str, Any]) -> None:
    """What the language service is specified to emit must resolve here; the plan may still refuse it, sensibly."""
    result = run(load(case["brief_fixture"].removesuffix(".model.json")), **case["expected_command"])
    assert result.status != "REJECTED" or result.stage == "geometry", result

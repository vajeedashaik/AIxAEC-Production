import pytest
from aec_contracts import FloorPlanModel

from .conftest import applied, rejected, wid

LIVING_KITCHEN, HALL_EAST = "260db342", "c60f8fe0"


@pytest.mark.parametrize("command", [
    {"operation": "NOPE"},
    {"target_query": "kitchen"},
    {"operation": "MOVE_WALL", "target_query": "x", "direction": "LEFT"},
    {"operation": "MOVE_WALL", "target_query": "x", "direction": "SIDEWAYS", "distance": {"value": 1, "unit": "px"}},
    {"operation": "MOVE_WALL", "target_query": "x", "direction": "LEFT", "distance": {"value": -1, "unit": "px"}},
    {"operation": "MOVE_WALL", "target_query": "x", "direction": "LEFT", "distance": {"value": 1, "unit": "ft"}},
    {"operation": "DELETE_WALL"},
    {"operation": "DELETE_WALL", "target_query": "x", "target_id": "260db342-ed25-4198-9c8d-81a9e520ad2a"},
    {"operation": "DELETE_WALL", "target_query": "x", "extra": 1},
    {"operation": "ADD_WALL", "start": {"x": -1, "y": 0}, "end": {"x": 5, "y": 5}},
    {"operation": "ADD_WALL", "start": {"x": 5, "y": 5}, "end": {"x": 5, "y": 5}},
])
def test_bad_commands_fail_schema_in_one_plain_sentence(apartment: FloorPlanModel, command: dict[str, object]) -> None:
    detail = rejected(apartment, "schema", **command)
    assert "pydantic" not in detail.lower() and "Value error" not in detail
    assert detail.endswith(".")


def test_mm_needs_a_scale(unscaled: FloorPlanModel) -> None:
    wall = str(wid(unscaled, LIVING_KITCHEN))
    message = "Set a scale first to use millimetres (select a wall and use Set scale)"
    distance = {"value": 300, "unit": "mm"}
    assert message in rejected(unscaled, "semantic_validation", operation="MOVE_WALL", target_id=wall,
                               direction="LEFT", distance=distance)
    assert message in rejected(unscaled, "semantic_validation", operation="RESIZE_ROOM", target_query="kitchen",
                               direction="LEFT", distance=distance, mode="EXPAND")
    assert message in rejected(unscaled, "semantic_validation", operation="ADD_DOOR", target_id=wall, width=distance)
    assert message in rejected(unscaled, "semantic_validation", operation="ADD_WINDOW", target_id=wall, width=distance)


def test_px_still_works_without_a_scale(unscaled: FloorPlanModel) -> None:
    applied(unscaled, operation="MOVE_WALL", target_id=str(wid(unscaled, LIVING_KITCHEN)),
            direction="LEFT", distance={"value": 30, "unit": "px"})


@pytest.mark.parametrize("distance", [{"value": 4801, "unit": "px"}, {"value": 48010, "unit": "mm"}])
def test_huge_moves_are_rejected(apartment: FloorPlanModel, distance: dict[str, object]) -> None:
    wall = str(wid(apartment, LIVING_KITCHEN))
    assert "too far" in rejected(apartment, "semantic_validation", operation="MOVE_WALL", target_id=wall,
                                 direction="LEFT", distance=distance)
    assert "too far" in rejected(apartment, "semantic_validation", operation="RESIZE_ROOM", target_query="kitchen",
                                 direction="LEFT", distance=distance, mode="CONTRACT")


def test_opening_wider_than_its_wall(apartment: FloorPlanModel) -> None:
    wall = str(wid(apartment, HALL_EAST))
    assert "wider than the wall" in rejected(apartment, "semantic_validation", operation="ADD_DOOR", target_id=wall,
                                             width={"value": 151, "unit": "px"})


def test_add_wall_bounds_and_length(apartment: FloorPlanModel) -> None:
    far = {"x": 1607, "y": 10}
    assert "outside the image" in rejected(apartment, "semantic_validation", operation="ADD_WALL",
                                           start={"x": 1100, "y": 300}, end=far)
    assert "too short" in rejected(apartment, "semantic_validation", operation="ADD_WALL",
                                   start={"x": 10, "y": 10}, end={"x": 10.5, "y": 10})
    applied(apartment, operation="ADD_WALL", start={"x": 1400, "y": 10}, end={"x": 1606, "y": 10})


def test_add_wall_thickness_must_be_sane(apartment: FloorPlanModel) -> None:
    assert "thickness" in rejected(apartment, "semantic_validation", operation="ADD_WALL",
                                   start={"x": 1400, "y": 10}, end={"x": 1500, "y": 10}, thickness_px=float("inf"))


@pytest.mark.parametrize("length_mm", [1, 450_000])
def test_set_scale_ratio_bounds(apartment: FloorPlanModel, length_mm: float) -> None:
    wall = str(wid(apartment, LIVING_KITCHEN))  # 450 px long
    assert "mm/px" in rejected(apartment, "semantic_validation", operation="SET_SCALE", target_id=wall,
                               length_mm=length_mm)

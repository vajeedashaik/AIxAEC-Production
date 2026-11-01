import json
from typing import Any

import pytest
from aec_contracts import FloorPlanModel, Point, Room, RoomType, Source, Wall, polygon_area

from app.engine.geom import signed_area

from .conftest import FIXTURES, applied, el, pts, rejected, room, wid

LIVING_KITCHEN, KITCHEN_BED, LIVING_HALL, HALL_BATH = "260db342", "19dadcef", "afdd271c", "cac36134"
HALL_EAST, TOP_LIVING, TOP_KITCHEN, TOP_BED, BATH_SOUTH = "c60f8fe0", "c2b9546e", "f1d5effe", "60973af4", "07d7ef81"
TWO_SHARED, TWO_TOP = "5b0e4ca9", "52d65a1b"


def move(model: FloorPlanModel, prefix: str, direction: str, px: float) -> dict[str, Any]:
    return {"operation": "MOVE_WALL", "target_id": str(wid(model, prefix)), "direction": direction,
            "distance": {"value": px, "unit": "px"}}


def resize(label: str, direction: str, px: float, mode: str) -> dict[str, Any]:
    return {"operation": "RESIZE_ROOM", "target_query": label, "direction": direction,
            "distance": {"value": px, "unit": "px"}, "mode": mode}


def add_stub(model: FloorPlanModel, start: tuple[float, float], end: tuple[float, float]) -> Wall:
    wall = Wall(start=Point(x=start[0], y=start[1]), end=Point(x=end[0], y=end[1]), thickness_px=10)
    model.walls.append(wall)
    return wall


def ends(wall: Wall) -> tuple[tuple[float, float], tuple[float, float]]:
    return (wall.start.x, wall.start.y), (wall.end.x, wall.end.y)


# --- MOVE_WALL ---------------------------------------------------------------------------------------------------

def test_move_matches_the_api_fixture(apartment: FloorPlanModel) -> None:
    expected = json.loads((FIXTURES / "api" / "commands.apply.json").read_text(encoding="utf-8"))
    result = applied(apartment, operation="MOVE_WALL", target_query="wall between kitchen and living room",
                     direction="LEFT", distance={"value": 300, "unit": "mm"})
    assert result.summary == expected["summary"] == "Moved wall 300 mm left; 2 rooms resized."
    assert result.changes.model_dump(mode="json") == expected["changes"]
    assert result.command.model_dump(mode="json") == expected["command"]


def test_move_corners_and_areas_follow(apartment: FloorPlanModel) -> None:
    after = applied(apartment, **move(apartment, LIVING_KITCHEN, "LEFT", 30)).model
    assert ends(el(after.walls, LIVING_KITCHEN)) == ((570, 100), (570, 550))
    assert el(after.walls, TOP_LIVING).end == Point(x=570, y=100)
    assert el(after.walls, TOP_KITCHEN).start == Point(x=570, y=100)
    assert pts(room(after, "LIVING").polygon) == [(100, 100), (570, 100), (570, 550), (100, 550)]
    assert room(after, "LIVING").area_px == 470 * 450
    assert room(after, "KITCHEN").area_px == 390 * 450
    hall = room(after, "HALL")
    assert (570, 550) in pts(hall.polygon) and hall.area_px == 180000


def test_move_t_junction_reprojects(two_room: FloorPlanModel) -> None:
    straight = add_stub(two_room, (300, 100), (300, 300))
    near_miss = add_stub(two_room, (200, 110), (200, 300))  # 10 px short of the wall: still within tolerance
    slanted = add_stub(two_room, (400, 100), (450, 300))
    after = applied(two_room, **move(two_room, TWO_TOP, "UP", 20)).model
    assert ends(el(after.walls, str(straight.id))) == ((300, 80), (300, 300))
    assert ends(el(after.walls, str(near_miss.id))) == ((200, 80), (200, 300))
    assert ends(el(after.walls, str(slanted.id))) == ((395, 80), (450, 300))


def test_move_translates_collinear_continuations(apartment: FloorPlanModel) -> None:
    result = applied(apartment, **move(apartment, TOP_LIVING, "UP", 20))
    after = result.model
    for prefix in (TOP_LIVING, TOP_KITCHEN, TOP_BED):
        assert {el(after.walls, prefix).start.y, el(after.walls, prefix).end.y} == {80}
    assert el(after.windows, "37a46186").bbox.y == 70  # a window on the continuation goes with it
    assert el(after.walls, LIVING_KITCHEN).start == Point(x=600, y=80)
    assert result.summary == "Moved wall 20 px up; 3 rooms resized."


def test_move_carries_openings(apartment: FloorPlanModel) -> None:
    result = applied(apartment, **move(apartment, HALL_BATH, "DOWN", 20))
    door = el(result.model.doors, "d50b70b9")
    assert (door.bbox.x, door.bbox.y) == (1095, 715)
    assert door.id in result.changes.modified
    assert el(result.model.doors, "e19b04c4") == el(apartment.doors, "e19b04c4")


def test_move_slightly_slanted_wall_goes_perpendicular(two_room: FloorPlanModel) -> None:
    wall = add_stub(two_room, (200, 200), (300, 210))
    after = el(applied(two_room, **move(two_room, str(wall.id), "UP", 50)).model.walls, str(wall.id))
    (x0, y0), _ = ends(after)
    assert (x0 - 200) * 100 + (y0 - 200) * 10 == pytest.approx(0, abs=1)  # no travel along the wall
    assert y0 < 200


@pytest.mark.parametrize("prefix,direction,hint", [
    (LIVING_KITCHEN, "UP", "This wall is vertical; move it left or right."),
    (LIVING_KITCHEN, "DOWN", "This wall is vertical; move it left or right."),
    (TOP_LIVING, "LEFT", "This wall is horizontal; move it up or down."),
])
def test_move_along_the_wall_is_refused(apartment: FloorPlanModel, prefix: str, direction: str, hint: str) -> None:
    assert rejected(apartment, "geometry", **move(apartment, prefix, direction, 30)) == hint


def test_move_diagonal_wall_is_refused_with_a_hint(two_room: FloorPlanModel) -> None:
    wall = add_stub(two_room, (200, 200), (300, 300))
    assert "diagonal" in rejected(two_room, "geometry", **move(two_room, str(wall.id), "UP", 30))


def test_move_collision_with_parallel_wall(apartment: FloorPlanModel) -> None:
    assert "parallel" in rejected(apartment, "constraints", **move(apartment, LIVING_KITCHEN, "RIGHT", 400))


def test_move_onto_a_parallel_wall_is_refused(apartment: FloorPlanModel) -> None:
    assert "collapse" in rejected(apartment, "constraints", **move(apartment, LIVING_KITCHEN, "RIGHT", 360))


def test_move_crushed_room(apartment: FloorPlanModel) -> None:
    assert "KITCHEN" in rejected(apartment, "constraints", **move(apartment, LIVING_KITCHEN, "RIGHT", 300))
    applied(apartment, **move(apartment, LIVING_KITCHEN, "RIGHT", 200))


def test_move_stranding_an_opening_is_refused(apartment: FloorPlanModel) -> None:
    # The kitchen window is centred at x=780: a 210+ px move shortens its wall past it, under the crush limit.
    assert "opening" in rejected(apartment, "constraints", **move(apartment, LIVING_KITCHEN, "RIGHT", 280))


def test_move_off_the_image(apartment: FloorPlanModel) -> None:
    assert "outside the image" in rejected(apartment, "constraints", **move(apartment, TOP_LIVING, "UP", 150))


def test_move_flipping_a_connected_wall(two_room: FloorPlanModel) -> None:
    add_stub(two_room, (300, 100), (300, 130))
    assert "reverse" in rejected(two_room, "constraints", **move(two_room, TWO_TOP, "DOWN", 50))


# --- RESIZE_ROOM -------------------------------------------------------------------------------------------------

def test_resize_expand(apartment: FloorPlanModel) -> None:
    result = applied(apartment, **resize("bathroom", "DOWN", 20, "EXPAND"))
    assert room(result.model, "BATH").area_px == 340 * 220
    assert el(result.model.walls, BATH_SOUTH).start.y == 920
    assert result.summary == "Expanded BATH 20 px down; 1 room resized."


def test_resize_contract(apartment: FloorPlanModel) -> None:
    result = applied(apartment, **resize("living room", "LEFT", 30, "CONTRACT"))
    assert room(result.model, "LIVING").area_px == 470 * 450
    assert result.summary == "Contracted LIVING 30 px from the left; 2 rooms resized."  # the hall shares that wall


def test_resize_contract_names_the_side(apartment: FloorPlanModel) -> None:
    assert "from the bottom" in applied(apartment, **resize("hall", "DOWN", 10, "CONTRACT")).summary


def test_resize_side_made_of_several_walls(apartment: FloorPlanModel) -> None:
    after = applied(apartment, **resize("hall", "DOWN", 10, "EXPAND")).model
    assert el(after.walls, HALL_BATH).start.y == 710 and el(after.walls, "b3d8c88a").start.y == 710
    assert room(after, "HALL").area_px == 1200 * 160


def test_resize_refuses_side_without_walls(apartment: FloorPlanModel) -> None:
    gone = wid(apartment, KITCHEN_BED)
    apartment.walls = [w for w in apartment.walls if w.id != gone]
    for r in apartment.rooms:
        r.wall_ids = [i for i in r.wall_ids if i != gone]
    assert "isn't formed" in rejected(apartment, "geometry", **resize("kitchen", "RIGHT", 10, "EXPAND"))


def test_resize_crushed(apartment: FloorPlanModel) -> None:
    assert "BATH" in rejected(apartment, "constraints", **resize("bath", "UP", 180, "CONTRACT"))


def test_resize_diagonal_side_refused(two_room: FloorPlanModel) -> None:
    two_room.walls = []
    for r in two_room.rooms:
        r.wall_ids = []
    add_stub(two_room, (850, 250), (950, 350))  # centred on the side, but diagonal
    assert "isn't formed" in rejected(two_room, "geometry", **resize("office", "RIGHT", 10, "EXPAND"))


# --- ADD_WALL ----------------------------------------------------------------------------------------------------

def test_add_wall_snaps_and_defaults_thickness(apartment: FloorPlanModel) -> None:
    result = applied(apartment, operation="ADD_WALL", start={"x": 605, "y": 300}, end={"x": 955, "y": 300})
    wall = next(w for w in result.model.walls if w.id == result.changes.added[0])
    assert ends(wall) == ((600, 300), (960, 300))
    assert wall.thickness_px == 20 and wall.source is Source.USER_CONFIRMED
    assert result.changes.modified == [] and result.changes.removed == []
    assert result.summary == "Added a wall, 360 px long."
    assert wall.id.version == 4


def test_add_wall_keeps_given_thickness_and_free_ends(apartment: FloorPlanModel) -> None:
    result = applied(apartment, operation="ADD_WALL", start={"x": 200, "y": 300}, end={"x": 300, "y": 300},
                     thickness_px=7)
    wall = next(w for w in result.model.walls if w.id == result.changes.added[0])
    assert ends(wall) == ((200, 300), (300, 300)) and wall.thickness_px == 7


def test_add_wall_with_no_existing_walls(two_room: FloorPlanModel) -> None:
    two_room.walls, two_room.rooms = [], []
    after = applied(two_room, operation="ADD_WALL", start={"x": 1, "y": 1}, end={"x": 9, "y": 1}).model
    assert after.walls[0].thickness_px is None


def test_add_wall_collapsing_on_snap(apartment: FloorPlanModel) -> None:
    assert "same point" in rejected(apartment, "geometry", operation="ADD_WALL",
                                    start={"x": 601, "y": 300}, end={"x": 603, "y": 300})


# --- DELETE_WALL -------------------------------------------------------------------------------------------------

def test_delete_wall_merges(two_room: FloorPlanModel) -> None:
    shared = wid(two_room, TWO_SHARED)
    winding = signed_area(two_room.rooms[0].polygon)
    result = applied(two_room, operation="DELETE_WALL", target_query="shared wall")
    assert len(result.model.rooms) == 1 and len(result.model.walls) == 6
    merged = result.model.rooms[0]
    assert merged.label_text == "BEDROOM" and merged.room_type is RoomType.BEDROOM
    assert merged.area_px == 320000
    assert len(merged.polygon) == 4
    assert signed_area(merged.polygon) * winding > 0
    assert len(merged.wall_ids) == 6 and shared not in merged.wall_ids
    assert result.changes.removed == [shared, two_room.rooms[1].id]
    assert result.changes.modified == [merged.id]
    assert result.summary == "Deleted wall; merged BEDROOM and OFFICE into BEDROOM."


def test_delete_wall_larger_room_survives_and_openings_go(apartment: FloorPlanModel) -> None:
    door = el(apartment.doors, "e19b04c4").id
    result = applied(apartment, operation="DELETE_WALL", target_id=str(wid(apartment, LIVING_HALL)))
    assert {r.label_text for r in result.model.rooms} == {"LIVING", "KITCHEN", "BEDROOM", "BATH"}
    living = room(result.model, "LIVING")
    assert living.area_px == 405000
    assert wid(apartment, HALL_BATH) in living.wall_ids and wid(apartment, LIVING_HALL) not in living.wall_ids
    assert door in result.changes.removed and door not in {d.id for d in result.model.doors}


def test_delete_wall_cleans_other_rooms_wall_ids(apartment: FloorPlanModel) -> None:
    wall = wid(apartment, LIVING_HALL)
    room(apartment, "BATH").wall_ids.append(wall)
    after = applied(apartment, operation="DELETE_WALL", target_id=str(wall)).model
    assert wall not in room(after, "BATH").wall_ids


def test_delete_exterior_wall_refused(two_room: FloorPlanModel) -> None:
    assert rejected(two_room, "constraints", operation="DELETE_WALL", target_id=str(wid(two_room, TWO_TOP))) == \
        "Exterior walls can't be deleted."


def test_delete_merges_rooms_inset_from_the_wall(two_room: FloorPlanModel) -> None:
    for r, (x0, x1) in zip(two_room.rooms, ((105, 495), (505, 895)), strict=True):
        r.polygon = [Point(x=x0, y=105), Point(x=x1, y=105), Point(x=x1, y=495), Point(x=x0, y=495)]
    merged = applied(two_room, operation="DELETE_WALL", target_id=str(wid(two_room, TWO_SHARED))).model.rooms[0]
    assert polygon_area(merged.polygon) == pytest.approx(790 * 390, rel=0.01)


def test_delete_refuses_a_merge_that_would_enclose_a_hole(two_room: FloorPlanModel) -> None:
    left = [(0, 0), (50, 0), (50, 10), (10, 10), (10, 90), (50, 90), (50, 100), (0, 100)]
    right = [(100 - x, y) for x, y in left]
    two_room.rooms = [Room(polygon=[Point(x=x, y=y) for x, y in shape], label_text=name)
                      for shape, name in ((left, "A"), (right, "B"))]
    wall = add_stub(two_room, (50, 0), (50, 10))
    assert "hole" in rejected(two_room, "geometry", operation="DELETE_WALL", target_id=str(wall.id))


def test_delete_merge_when_one_room_sits_inside_the_other(two_room: FloorPlanModel) -> None:
    two_room.rooms[1].polygon = [Point(x=200, y=200), Point(x=400, y=200), Point(x=400, y=400), Point(x=200, y=400)]
    wall = add_stub(two_room, (200, 200), (200, 400))
    result = applied(two_room, operation="DELETE_WALL", target_id=str(wall.id))
    assert [r.label_text for r in result.model.rooms] == ["BEDROOM"]
    assert result.summary.startswith("Deleted wall; merged")


def test_delete_freestanding_and_inner_walls(two_room: FloorPlanModel) -> None:
    outside = add_stub(two_room, (950, 100), (950, 300))
    inner = add_stub(two_room, (200, 200), (300, 200))
    for wall in (outside, inner):
        result = applied(two_room, operation="DELETE_WALL", target_id=str(wall.id))
        assert result.changes.removed == [wall.id] and result.changes.modified == []
        assert result.summary == "Deleted wall."


# --- ADD_DOOR / ADD_WINDOW ---------------------------------------------------------------------------------------

def test_add_door_default_scaled(apartment: FloorPlanModel) -> None:
    wall = wid(apartment, LIVING_KITCHEN)
    result = applied(apartment, operation="ADD_DOOR", target_id=str(wall))
    door = next(d for d in result.model.doors if d.id == result.changes.added[0])
    assert door.bbox.model_dump() == {"x": 595, "y": 280, "width": 10, "height": 90}
    assert door.wall_id == wall and door.width_px == 90 and door.source is Source.USER_CONFIRMED
    assert result.summary == "Added a door, 90 px wide."


def test_add_window_default_and_units(apartment: FloorPlanModel) -> None:
    wall = str(wid(apartment, "e1c29267"))
    result = applied(apartment, operation="ADD_WINDOW", target_id=wall)
    window = next(w for w in result.model.windows if w.id == result.changes.added[0])
    assert window.bbox.model_dump() == {"x": 720, "y": 545, "width": 120, "height": 10}
    result = applied(apartment, operation="ADD_WINDOW", target_id=wall, width={"value": 800, "unit": "mm"})
    assert next(w for w in result.model.windows if w.id == result.changes.added[0]).width_px == 80


def test_add_opening_defaults_unscaled(unscaled: FloorPlanModel) -> None:
    wall = wid(unscaled, LIVING_KITCHEN)
    door = applied(unscaled, operation="ADD_DOOR", target_id=str(wall)).model.doors[-1]
    window = applied(unscaled, operation="ADD_WINDOW", target_id=str(wall)).model.windows[-1]
    assert (door.wall_id, door.width_px, window.wall_id, window.width_px) == (wall, 40, wall, 48)


@pytest.mark.parametrize("position,y", [(0, 100), (1, 460), (0.3, 190)])
def test_add_door_position_is_clamped_onto_the_wall(apartment: FloorPlanModel, position: float, y: float) -> None:
    result = applied(apartment, operation="ADD_DOOR", target_id=str(wid(apartment, LIVING_KITCHEN)), position=position)
    assert result.model.doors[-1].bbox.y == y


def test_add_opening_on_a_wall_with_no_thickness(two_room: FloorPlanModel) -> None:
    two_room.walls[0].thickness_px = None
    result = applied(two_room, operation="ADD_DOOR", target_id=str(two_room.walls[0].id))
    assert result.model.doors[0].bbox.height == 10


def test_add_opening_refusals(apartment: FloorPlanModel) -> None:
    short = str(wid(apartment, HALL_EAST))  # 150 px
    assert "90 %" in rejected(apartment, "geometry", operation="ADD_DOOR", target_id=short,
                              width={"value": 140, "unit": "px"})
    assert "at least 4 px" in rejected(apartment, "geometry", operation="ADD_WINDOW", target_id=short,
                                       width={"value": 3, "unit": "px"})
    busy = str(wid(apartment, LIVING_HALL))  # door centred at x=350, 90 wide
    assert "overlaps" in rejected(apartment, "geometry", operation="ADD_DOOR", target_id=busy, position=0.5)
    assert "overlaps" in rejected(apartment, "geometry", operation="ADD_WINDOW", target_id=busy, position=0.45)
    applied(apartment, operation="ADD_DOOR", target_id=busy, position=0.1)


# --- DELETE_DOOR / DELETE_WINDOW, RENAME_ROOM, SET_SCALE ---------------------------------------------------------

def test_delete_openings(apartment: FloorPlanModel) -> None:
    result = applied(apartment, operation="DELETE_DOOR", target_query="bathroom door")
    assert len(result.model.doors) == 3 and result.summary == "Deleted door."
    assert str(result.changes.removed[0]).startswith("d50b70b9")
    result = applied(apartment, operation="DELETE_WINDOW", target_query="kitchen window")
    assert len(result.model.windows) == 2 and result.summary == "Deleted window."


@pytest.mark.parametrize("name,given,expected", [
    ("Guest Room", None, RoomType.BEDROOM),
    ("Lounge", "LIVING_ROOM", RoomType.LIVING_ROOM),
    ("Lounge", "OTHER", RoomType.OTHER),
    ("Zorblax", None, RoomType.UNKNOWN),
])
def test_rename_room(apartment: FloorPlanModel, name: str, given: str | None, expected: RoomType) -> None:
    command: dict[str, Any] = {"operation": "RENAME_ROOM", "target_query": "kitchen", "name": name}
    if given:
        command["room_type"] = given
    result = applied(apartment, **command)
    renamed = room(result.model, name)
    assert renamed.room_type is expected and renamed.room_type_source is Source.USER_CONFIRMED
    assert renamed.room_type_confidence == 1.0 and renamed.confidence == 1.0
    assert renamed.polygon == room(apartment, "KITCHEN").polygon
    assert result.changes.modified == [renamed.id]
    assert result.summary == f'Renamed KITCHEN to "{name}".'


def test_set_scale(unscaled: FloorPlanModel) -> None:
    result = applied(unscaled, operation="SET_SCALE", target_query="wall between kitchen and living", length_mm=3600)
    cs = result.model.coordinate_system
    assert cs.mm_per_pixel == 8.0 and cs.calibration_source == "MANUAL" and cs.calibration_confidence == 1.0
    assert result.changes.model_dump() == {"added": [], "modified": [], "removed": []}
    assert result.summary == "Set scale to 8 mm per pixel."
    assert result.model.walls == unscaled.walls

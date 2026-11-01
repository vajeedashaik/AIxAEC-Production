from uuid import uuid4

from aec_contracts import FloorPlanModel, Point

from app.engine.constraints import validate_model

from .conftest import applied, el, load, room, wid


def codes(model: FloorPlanModel, before: FloorPlanModel | None = None) -> list[str]:
    return [i.code for i in validate_model(model, before)]


def edited() -> tuple[FloorPlanModel, FloorPlanModel]:
    before = load("apartment")
    return before.model_copy(deep=True), before


def test_fixtures_are_clean() -> None:
    for name in ("apartment", "apartment.unscaled", "two_room"):
        assert codes(load(name)) == []


def test_duplicate_ids() -> None:
    model = load("two_room")
    model.walls[1].id = model.walls[0].id
    assert "duplicate_id" in codes(model)


def test_out_of_bounds_tolerance() -> None:
    model = load("two_room")
    model.walls[0].end = Point(x=1006, y=100)
    assert codes(model) == []
    model.walls[0].end = Point(x=1006.5, y=100)
    assert codes(model) == ["out_of_bounds"]
    model = load("two_room")
    model.rooms[0].polygon[0] = Point(x=10, y=606.5)
    assert "out_of_bounds" in codes(model)


def test_room_ring_problems() -> None:
    model = load("two_room")
    p = model.rooms[0].polygon
    p[1], p[2] = p[2], p[1]  # bow-tie
    assert "room_invalid" in codes(model)
    model = load("two_room")
    model.rooms[0].polygon = [Point(x=1, y=1), Point(x=1.5, y=1), Point(x=1.5, y=1.5)]
    assert codes(model) == ["room_too_small"]


def test_room_inverted_and_crushed_compare_with_before() -> None:
    after, before = edited()
    room(after, "BATH").polygon.reverse()
    assert codes(after, before) == ["room_inverted"]
    after, before = edited()
    bath = room(after, "BATH")
    bath.polygon = [Point(x=p.x, y=700 + (p.y - 700) * 0.19) for p in bath.polygon]
    assert codes(after, before) == ["room_crushed"]
    bath.polygon = [Point(x=p.x, y=700 + (p.y - 700) * 0.21 / 0.19) for p in bath.polygon]
    assert codes(after, before) == []


def test_axis_aligned_wall_stays_axis_aligned() -> None:
    after, before = edited()
    el(after.walls, "260db342").end = Point(x=610, y=550)
    assert "wall_not_axis_aligned" in codes(after, before)


def test_already_touching_parallel_walls_do_not_collide() -> None:
    after, before = edited()
    extra = el(before.walls, "260db342").model_copy(update={"id": uuid4()})
    before.walls.append(extra)  # coincident with the wall that then moves away
    after.walls.append(extra)
    moved = el(after.walls, "260db342")
    moved.start, moved.end = Point(x=590, y=100), Point(x=590, y=550)
    assert "wall_collision" not in codes(after, before)


def test_opening_detached_only_when_judged() -> None:
    after, before = edited()
    door = el(after.doors, "e19b04c4")
    door.bbox.y = 400  # 150 px off its wall
    assert codes(after, before) == ["opening_detached"]
    # Already detached before the edit and untouched: an unrelated edit is not blocked.
    assert codes(after.model_copy(deep=True), after) == []
    door.bbox.y = 525
    assert codes(after, before) == []
    assert codes(after) == []


def test_opening_orphan() -> None:
    model = load("apartment")
    model.walls = [w for w in model.walls if w.id != wid(model, "afdd271c")]
    assert "opening_orphan" in codes(model)


def test_preexisting_imperfections_do_not_block_unrelated_edits() -> None:
    model = load("apartment")
    p = room(model, "BATH").polygon
    p[1], p[2] = p[2], p[1]
    el(model.doors, "e19b04c4").bbox.y = 400
    model.walls.append(el(model.walls, "260db342").model_copy(update={"id": uuid4(), "end": Point(x=1700, y=550)}))
    assert {"room_invalid", "opening_detached", "out_of_bounds"} <= set(codes(model))
    applied(model, operation="RENAME_ROOM", target_query="kitchen", name="Galley")
    applied(model, operation="SET_SCALE", target_query="north wall of kitchen", length_mm=3600)

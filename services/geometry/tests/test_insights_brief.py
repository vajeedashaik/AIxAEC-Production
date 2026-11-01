import pytest
from aec_contracts import FloorPlanModel, RoomType

from app.brief import build_brief
from app.insights import build_insights

from .conftest import room


def test_two_room_hand_computed(two_room: FloorPlanModel) -> None:
    room(two_room, "OFFICE").area_px = 1  # a stale stored value must be ignored
    i = build_insights(two_room)
    assert i.counts.walls == 7 and i.counts.rooms == 2
    assert i.total_area_px == 320000 and i.average_room_area_px == 160000
    assert i.largest_room is not None and i.largest_room.label == "BEDROOM" and i.largest_room.area_px == 160000
    assert i.smallest_room is not None and i.smallest_room.label == "BEDROOM"
    assert (i.total_wall_length_px, i.exterior_wall_length_px, i.interior_wall_length_px) == (2800, 2400, 400)
    assert i.rooms_by_type == {RoomType.BEDROOM: 1, RoomType.OFFICE: 1}
    assert i.metric is not None
    assert i.metric.total_area_m2 == 32 and i.metric.average_room_area_m2 == 16
    assert i.metric.total_wall_length_m == 28
    assert i.metric.exterior_wall_length_m == 24 and i.metric.interior_wall_length_m == 4


def test_apartment_hand_computed(apartment: FloorPlanModel) -> None:
    i = build_insights(apartment)
    assert i.total_area_px == 225000 + 162000 + 153000 + 180000 + 68000
    assert i.largest_room is not None and i.largest_room.label == "LIVING"
    assert i.smallest_room is not None and i.smallest_room.label == "BATH"
    assert i.total_wall_length_px == 6440 and i.interior_wall_length_px == 2440
    assert i.rooms_by_type[RoomType.HALLWAY] == 1


def test_metric_is_null_without_scale(unscaled: FloorPlanModel) -> None:
    assert build_insights(unscaled).metric is None


def test_no_rooms(two_room: FloorPlanModel) -> None:
    two_room.rooms = []
    i = build_insights(two_room)
    assert i.largest_room is None and i.smallest_room is None and i.average_room_area_px == 0
    assert i.exterior_wall_length_px == 2800 and i.interior_wall_length_px == 0


def test_insights_survive_a_broken_polygon(two_room: FloorPlanModel) -> None:
    p = two_room.rooms[0].polygon
    p[1], p[2] = p[2], p[1]
    assert build_insights(two_room).total_wall_length_px == pytest.approx(2800)


def test_brief_has_no_coordinates_or_ids(apartment: FloorPlanModel) -> None:
    brief = build_brief(apartment)
    assert brief.counts.walls == 17 and brief.has_scale and (brief.image_width, brief.image_height) == (1600, 1200)
    assert brief.rooms[0].label == "LIVING" and brief.rooms[0].room_type is RoomType.LIVING_ROOM
    assert brief.rooms[3].wall_count == 7
    text = brief.model_dump_json()
    assert '"x"' not in text and "polygon" not in text and '"id"' not in text
    assert str(apartment.id) not in text and str(apartment.rooms[0].id) not in text
    assert str(apartment.floorplan_id) not in text


def test_brief_without_scale(unscaled: FloorPlanModel) -> None:
    assert build_brief(unscaled).has_scale is False

import copy
import uuid
from typing import Any

import pytest
from conftest import FIXTURES, load
from pydantic import ValidationError

from aec_contracts import CoordinateSystem, CoordinateTransform, FloorPlanModel, Point, Wall, polygon_area

MODEL_FIXTURES = ["apartment.model.json", "apartment.unscaled.model.json", "two_room.model.json"]


@pytest.mark.parametrize("name", MODEL_FIXTURES)
def test_fixture_round_trip(name: str) -> None:
    raw = load(name)
    model = FloorPlanModel.model_validate(raw)
    again = FloorPlanModel.model_validate_json(model.model_dump_json())
    assert again == model
    assert model.model_dump(mode="json") == raw


@pytest.mark.parametrize("builder", ["build_models", "build_api_examples"])
def test_fixtures_are_regenerated(builder: str, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Committed JSON must equal what the builder scripts produce."""
    import importlib

    mod = importlib.import_module(builder)
    if builder == "build_models":
        assert mod.apartment(True) == load("apartment.model.json")
        assert mod.apartment(False) == load("apartment.unscaled.model.json")
        assert mod.two_room() == load("two_room.model.json")
    else:
        monkeypatch.setattr(mod, "OUT", tmp_path)
        mod.main()
        for f in tmp_path.iterdir():
            assert f.read_text(encoding="utf-8") == (FIXTURES / "api" / f.name).read_text(encoding="utf-8"), f.name


def test_unscaled_is_same_geometry(apartment: dict[str, Any]) -> None:
    unscaled = load("apartment.unscaled.model.json")
    assert unscaled["coordinate_system"]["mm_per_pixel"] is None
    assert {k: v for k, v in unscaled.items() if k != "coordinate_system"} == \
           {k: v for k, v in apartment.items() if k != "coordinate_system"}


def _on_segment(p: Point, w: Wall) -> bool:
    (x1, y1), (x2, y2) = (w.start.x, w.start.y), (w.end.x, w.end.y)
    cross = (x2 - x1) * (p.y - y1) - (y2 - y1) * (p.x - x1)
    return abs(cross) < 1e-6 and min(x1, x2) - 1e-6 <= p.x <= max(x1, x2) + 1e-6 \
        and min(y1, y2) - 1e-6 <= p.y <= max(y1, y2) + 1e-6


@pytest.mark.parametrize("name", MODEL_FIXTURES)
def test_geometry_is_honest(name: str) -> None:
    m = FloorPlanModel.model_validate(load(name))
    walls = {w.id: w for w in m.walls}
    for room in m.rooms:
        poly = room.polygon
        edges = [(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly))]
        assert len(edges) == len(room.wall_ids), room.label_text
        for (a, b), wid in zip(edges, room.wall_ids, strict=True):
            w = walls[wid]
            assert {(a.x, a.y), (b.x, b.y)} == {(w.start.x, w.start.y), (w.end.x, w.end.y)}, room.label_text
        assert room.area_px == polygon_area(poly)
    for op in [*m.doors, *m.windows]:
        assert op.wall_id is not None
        w = walls[op.wall_id]
        centre = Point(x=op.bbox.x + op.bbox.width / 2, y=op.bbox.y + op.bbox.height / 2)
        assert _on_segment(centre, w)
        assert op.width_px == max(op.bbox.width, op.bbox.height)
    # every wall bounds one (exterior) or two (interior) rooms
    uses = [sum(w.id in r.wall_ids for r in m.rooms) for w in m.walls]
    assert set(uses) <= {1, 2}


def test_apartment_contents(apartment: dict[str, Any]) -> None:
    m = FloorPlanModel.model_validate(apartment)
    s = m.summary()
    assert (s.rooms, s.doors, s.windows, s.columns, s.stairs, s.dimensions) == (5, 4, 3, 1, 1, 3)
    assert 14 <= s.walls <= 18
    assert m.coordinate_system.mm_per_pixel == 10.0
    assert {r.room_type for r in m.rooms} == {"LIVING_ROOM", "KITCHEN", "BEDROOM", "BATHROOM", "HALLWAY"}


def test_wall_start_must_differ_from_end() -> None:
    Wall(start=Point(x=0, y=0), end=Point(x=1, y=0))
    with pytest.raises(ValidationError, match="start and end must differ"):
        Wall(start=Point(x=5, y=5), end=Point(x=5, y=5))


def test_wall_length_not_serialised() -> None:
    w = Wall(start=Point(x=0, y=0), end=Point(x=3, y=4))
    assert w.length_px == 5
    assert "length_px" not in w.model_dump()


def test_point_rejects_negative_and_nan() -> None:
    with pytest.raises(ValidationError):
        Point(x=-1, y=0)
    with pytest.raises(ValidationError):
        Point(x=float("nan"), y=0)


def test_unknown_wall_reference_rejected(apartment: dict[str, Any]) -> None:
    bad = copy.deepcopy(apartment)
    bad["rooms"][0]["wall_ids"][0] = str(uuid.uuid4())
    with pytest.raises(ValidationError, match="unknown wall"):
        FloorPlanModel.model_validate(bad)
    bad = copy.deepcopy(apartment)
    bad["doors"][0]["wall_id"] = str(uuid.uuid4())
    with pytest.raises(ValidationError, match="unknown wall"):
        FloorPlanModel.model_validate(bad)


def test_duplicate_ids_rejected_across_lists(apartment: dict[str, Any]) -> None:
    bad = copy.deepcopy(apartment)
    bad["windows"][0]["id"] = bad["doors"][0]["id"]
    with pytest.raises(ValidationError, match="duplicate element id"):
        FloorPlanModel.model_validate(bad)


def test_extra_fields_forbidden(apartment: dict[str, Any]) -> None:
    for path in (lambda d: d, lambda d: d["walls"][0], lambda d: d["coordinate_system"]):
        bad = copy.deepcopy(apartment)
        path(bad)["sneaky"] = 1
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            FloorPlanModel.model_validate(bad)


def test_room_polygon_needs_three_points(apartment: dict[str, Any]) -> None:
    bad = copy.deepcopy(apartment)
    bad["rooms"][0]["polygon"] = bad["rooms"][0]["polygon"][:2]
    with pytest.raises(ValidationError):
        FloorPlanModel.model_validate(bad)


def test_polygon_area_and_transform() -> None:
    square = [Point(x=0, y=0), Point(x=10, y=0), Point(x=10, y=10), Point(x=0, y=10)]
    assert polygon_area(square) == 100
    assert polygon_area(list(reversed(square))) == 100
    assert CoordinateTransform(CoordinateSystem(image_width=1, image_height=1)).px_to_mm(5) is None
    assert CoordinateTransform(CoordinateSystem(image_width=1, image_height=1, mm_per_pixel=10)).px_to_mm(5) == 50

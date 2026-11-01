from typing import Any

from aec_contracts import ExecuteApplied, ExecuteRejected, FloorPlanModel, polygon_area
from hypothesis import given, settings
from hypothesis import strategies as st

from app.engine.constraints import validate_model
from app.engine.execute import execute

from .conftest import load

APARTMENT = load("apartment")
DISTANCE = st.floats(min_value=1, max_value=500, allow_nan=False).map(lambda v: {"value": round(v, 2), "unit": "px"})
DIRECTION = st.sampled_from(["LEFT", "RIGHT", "UP", "DOWN"])
MOVE = st.builds(lambda w, d, v: {"operation": "MOVE_WALL", "target_id": str(w.id), "direction": d, "distance": v},
                 st.sampled_from(APARTMENT.walls), DIRECTION, DISTANCE)
RESIZE = st.builds(lambda r, d, v, m: {"operation": "RESIZE_ROOM", "target_id": str(r.id), "direction": d,
                                       "distance": v, "mode": m},
                   st.sampled_from(APARTMENT.rooms), DIRECTION, DISTANCE, st.sampled_from(["EXPAND", "CONTRACT"]))


@settings(max_examples=120, deadline=None, database=None)
@given(st.lists(st.one_of(MOVE, RESIZE), min_size=1, max_size=8))
def test_random_edit_sequences_never_produce_an_invalid_model(commands: list[dict[str, Any]]) -> None:
    model: FloorPlanModel = APARTMENT
    for command in commands:
        before = model.model_dump_json()
        result = execute(model, command)
        assert model.model_dump_json() == before
        if isinstance(result, ExecuteRejected):
            assert result.stage in ("geometry", "constraints") and result.detail
            continue
        assert isinstance(result, ExecuteApplied)
        assert result.model_dump_json() == execute(model, command).model_dump_json()
        model = FloorPlanModel.model_validate(result.model.model_dump())
        assert validate_model(model) == []
        for room in model.rooms:
            assert room.area_px is not None and abs(room.area_px - polygon_area(room.polygon)) < 0.01

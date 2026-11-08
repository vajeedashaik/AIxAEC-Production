"""Building intelligence on the apartment fixture: hand-checked arithmetic, honest refusals, engine-backed options."""

from typing import Any

import pytest
from aec_contracts import ExecuteApplied, ExecuteRejected, FloorPlanModel, RoomType, polygon_area
from aec_contracts.analysis import CostRates

from app.analysis import build_analysis
from app.analysis.compliance import build_compliance
from app.analysis.cost import build_estimate
from app.analysis.layouts import suggest_layouts
from app.analysis.measure import contains, measure, travel_distances_m
from app.analysis.qa import answer_question, money, plan_facts
from app.analysis.takeoff import build_takeoff, quantity
from app.engine.execute import execute
from app.insights import build_insights


def _room(model: FloorPlanModel, kind: RoomType) -> Any:
    return next(r for r in model.rooms if r.room_type == kind)


def test_no_scale_means_no_numbers(unscaled: FloorPlanModel) -> None:
    result = build_analysis(unscaled)
    assert result.needs_scale and result.takeoff is None and result.estimate is None
    assert "scale" in suggest_layouts(unscaled, "make the kitchen larger").answer.lower()


def test_takeoff_agrees_with_insights(apartment: FloorPlanModel) -> None:
    takeoff = build_takeoff(measure(apartment))
    metric = build_insights(apartment).metric
    assert metric is not None
    assert quantity(takeoff, "WL-03") == pytest.approx(metric.total_wall_length_m, abs=0.02)
    assert quantity(takeoff, "WL-01") == pytest.approx(metric.exterior_wall_length_m, abs=0.02)
    assert quantity(takeoff, "FA-01") == pytest.approx(metric.total_area_m2, abs=0.02)
    assert quantity(takeoff, "OP-01") == len(apartment.doors)
    assert quantity(takeoff, "OP-02") == len(apartment.windows)
    assert quantity(takeoff, "CO-04") == pytest.approx(
        quantity(takeoff, "CO-01") + quantity(takeoff, "CO-02") + quantity(takeoff, "CO-03"), abs=0.02
    )
    assert quantity(takeoff, "MA-02") > 0 and quantity(takeoff, "ST-01") > 0 and quantity(takeoff, "PA-03") > 0


def test_takeoff_scales_with_rooms_and_quantity_is_deterministic(apartment: FloorPlanModel) -> None:
    assert build_takeoff(measure(apartment)) == build_takeoff(measure(apartment))


def test_estimate_arithmetic_and_rate_override(apartment: FloorPlanModel) -> None:
    plan = measure(apartment)
    takeoff = build_takeoff(plan)
    base = build_estimate(plan, takeoff, None)
    assert sum(line.amount for line in base.lines) + base.labour_cost + base.contingency == pytest.approx(
        base.construction_cost, abs=0.05
    )
    assert base.tile_count == int(quantity(takeoff, "TI-03") + quantity(takeoff, "TI-04"))
    free = build_estimate(plan, takeoff, CostRates(currency="INR", concrete_per_m3=0))
    assert free.currency == "INR"
    assert free.construction_cost < base.construction_cost


def test_compliance_flags_a_narrow_corridor_and_a_small_bedroom(apartment: FloorPlanModel) -> None:
    report = build_compliance(measure(apartment))
    assert report.passed + report.warnings + report.failed == len(report.checks)
    assert {c.category for c in report.checks} >= {
        "Room size",
        "Door width",
        "Window placement",
        "Emergency exits",
        "Fire safety",
    }
    assert "not a certified" in report.disclaimer

    tiny = apartment.model_copy(deep=True)
    tiny.coordinate_system.mm_per_pixel = 1.0  # everything shrinks to a tenth
    failing = build_compliance(measure(tiny))
    assert any(c.category == "Room size" and c.status == "FAIL" for c in failing.checks)


def test_no_exterior_door_fails_the_exit_check(apartment: FloorPlanModel) -> None:
    sealed = apartment.model_copy(deep=True)
    sealed.doors = []
    report = build_compliance(measure(sealed))
    exit_check = next(c for c in report.checks if c.category == "Emergency exits")
    assert exit_check.status == "FAIL"
    assert not travel_distances_m(measure(sealed))
    assert not any(c.rule == "Door route to an exit" for c in report.checks)  # one failure, not a pass per room


def test_interior_places_furniture_inside_rooms_and_gives_all_themes(apartment: FloorPlanModel) -> None:
    result = build_analysis(apartment)
    assert result.interior is not None
    assert {t.name for t in result.interior.themes} == {"Modern", "Minimalist", "Industrial", "Luxury", "Scandinavian"}
    assert result.interior.lighting and all(r.fixtures >= 1 for r in result.interior.lighting)
    plan = measure(apartment)
    for item in result.interior.furniture:
        x, y = item.bbox.x + item.bbox.width / 2, item.bbox.y + item.bbox.height / 2
        assert any(contains(r, x, y) for r in plan.rooms), item.category


def test_tall_furniture_keeps_windows_clear(apartment: FloorPlanModel) -> None:
    result = build_analysis(apartment)
    assert result.interior is not None
    wardrobe = next(f for f in result.interior.furniture if f.category == "Wardrobe")
    window = next(w for w in measure(apartment).windows if w.rooms[0].room_type == RoomType.BEDROOM)
    half = window.width_mm / 10 / 2
    clear = (
        wardrobe.bbox.y + wardrobe.bbox.height <= window.centre[1] - half or wardrobe.bbox.y >= window.centre[1] + half
    )
    assert clear or wardrobe.bbox.x + wardrobe.bbox.width < window.centre[0] - half


def test_an_empty_scaled_plan_does_not_crash(apartment: FloorPlanModel) -> None:
    empty = apartment.model_copy(deep=True)
    empty.rooms, empty.walls, empty.doors, empty.windows, empty.columns, empty.stairs = [], [], [], [], [], []
    result = build_analysis(empty)
    assert result.estimate is not None and result.estimate.cost_per_m2 == 0
    assert answer_question(empty, "which room is the largest?").status == "ANSWERED"
    assert not suggest_layouts(empty, "add a bedroom").feasible


def test_structural_commands_all_apply(apartment: FloorPlanModel) -> None:
    result = build_analysis(apartment)
    assert result.structural is not None
    for s in result.structural.suggestions:
        if s.command is not None:
            outcome = execute(apartment, s.command.model_dump(mode="json"), dry_run=True)
            assert isinstance(outcome, ExecuteApplied), s.title


@pytest.mark.parametrize(
    "question",
    [
        "how many bedrooms are there?",
        "How many doors?",
        "What is the total wall length?",
        "Which room has the largest area?",
        "Where are emergency exits?",
    ],
)
def test_chatbot_answers_the_brief(apartment: FloorPlanModel, question: str) -> None:
    assert answer_question(apartment, question).status == "ANSWERED"


def test_chatbot_counts_master_bedrooms_as_bedrooms(apartment: FloorPlanModel) -> None:
    n = sum(r.room_type in (RoomType.BEDROOM, RoomType.MASTER_BEDROOM) for r in apartment.rooms)
    assert f"{n} bedroom" in answer_question(apartment, "how many bedrooms?").answer


def test_chatbot_largest_room_matches_polygons(apartment: FloorPlanModel) -> None:
    largest = max(apartment.rooms, key=lambda r: polygon_area(r.polygon))
    assert answer_question(apartment, "which room is the biggest?").element_ids == [largest.id]


def test_chatbot_refuses_what_it_cant_derive(apartment: FloorPlanModel, unscaled: FloorPlanModel) -> None:
    assert answer_question(apartment, "who designed this?").status == "UNKNOWN"
    assert answer_question(apartment, "which is the largest door?").status == "UNKNOWN"
    assert "scale" in answer_question(unscaled, "what is the total wall length?").answer


def test_facts_have_no_coordinates_or_ids(apartment: FloorPlanModel) -> None:
    text = str(plan_facts(apartment))
    assert str(apartment.rooms[0].id) not in text and "polygon" not in text


def _apply_all(model: FloorPlanModel, goal: str) -> None:
    result = suggest_layouts(model, goal)
    assert result.feasible and result.options and len(result.options) <= 3
    scores = [o.score for o in result.options]
    assert scores == sorted(scores, reverse=True)
    for option in result.options:
        assert isinstance(execute(model, option.command.model_dump(mode="json"), dry_run=True), ExecuteApplied), (
            option.title
        )


def test_make_kitchen_larger_returns_engine_valid_options(apartment: FloorPlanModel) -> None:
    _apply_all(apartment, "Make kitchen larger.")
    for option in suggest_layouts(apartment, "make kitchen larger").options:
        assert option.target_area_after_m2 is not None and option.target_area_before_m2 is not None
        assert option.target_area_after_m2 > option.target_area_before_m2


def test_goal_outside_the_vocabulary_explains_itself(apartment: FloorPlanModel) -> None:
    result = suggest_layouts(apartment, "paint it blue")
    assert not result.feasible and "bedroom" in result.answer


def test_missing_parking_is_stated_not_invented(apartment: FloorPlanModel) -> None:
    result = suggest_layouts(apartment, "Increase parking.")
    assert not result.feasible and "parking" in result.answer.lower()


def _split(model: FloorPlanModel, room: Any, **extra: Any) -> dict[str, Any]:
    return {
        "operation": "SPLIT_ROOM",
        "target_id": str(room.id),
        "axis": "VERTICAL",
        "position": 0.5,
        "new_room_name": "Study",
        "new_room_type": "OFFICE",
        **extra,
    }


def test_split_room_creates_a_room_a_wall_and_a_door(apartment: FloorPlanModel) -> None:
    living = _room(apartment, RoomType.LIVING_ROOM)
    result = execute(apartment, _split(apartment, living, position=0.7), dry_run=True)  # clear of its openings
    assert isinstance(result, ExecuteApplied), result
    after = result.model
    assert (len(after.rooms), len(after.walls), len(after.doors)) == (
        len(apartment.rooms) + 1,
        len(apartment.walls) + 1,
        len(apartment.doors) + 1,
    )
    study = next(r for r in after.rooms if r.label_text == "Study")
    kept = next(r for r in after.rooms if r.id == living.id)
    assert polygon_area(study.polygon) + polygon_area(kept.polygon) == pytest.approx(
        polygon_area(living.polygon), rel=1e-3
    )
    assert after.walls[-1].id in study.wall_ids and after.walls[-1].id in kept.wall_ids
    assert after.doors[-1].wall_id == after.walls[-1].id
    assert len(result.changes.added) == 3


def test_split_is_not_reachable_through_the_language_contract() -> None:
    from aec_contracts import COMMAND_ADAPTER, OPERATIONS
    from pydantic import ValidationError

    assert "SPLIT_ROOM" not in OPERATIONS
    with pytest.raises(ValidationError):
        COMMAND_ADAPTER.validate_python(
            {"operation": "SPLIT_ROOM", "target_query": "kitchen", "axis": "VERTICAL", "new_room_name": "x"}
        )


def test_split_cannot_run_through_a_door_or_window(apartment: FloorPlanModel) -> None:
    living = _room(apartment, RoomType.LIVING_ROOM)  # the midline at x=350 crosses its window and door
    result = execute(apartment, _split(apartment, living))
    assert isinstance(result, ExecuteRejected) and "door or window" in result.detail


def test_bedroom_goal_refuses_when_nothing_works(apartment: FloorPlanModel) -> None:
    result = suggest_layouts(apartment, "Can this house have another bedroom?")
    assert not result.feasible and not result.options and "m²" in result.answer


def test_bedroom_goal_prefers_converting_a_spare_room(apartment: FloorPlanModel) -> None:
    spare = apartment.model_copy(deep=True)
    _room(spare, RoomType.LIVING_ROOM).room_type = RoomType.OFFICE
    _apply_all(spare, "Can this house have another bedroom?")
    best = suggest_layouts(spare, "another bedroom").options[0]
    assert best.command.operation == "RENAME_ROOM" and best.new_compliance_failures == 0


def test_bedroom_goal_can_split_a_large_room(apartment: FloorPlanModel) -> None:
    large = apartment.model_copy(deep=True)
    large.coordinate_system.mm_per_pixel = 20.0  # same plan, twice the size
    _apply_all(large, "add a bedroom")
    assert suggest_layouts(large, "add a bedroom").options[0].command.operation == "SPLIT_ROOM"


def test_fix_it_windows_avoid_existing_openings(apartment: FloorPlanModel) -> None:
    result = build_analysis(apartment)
    assert result.structural is not None
    assert [s for s in result.structural.suggestions if s.category == "Lighting improvement" and s.command]


def test_split_outside_limits_is_rejected_at_schema(apartment: FloorPlanModel) -> None:
    living = _room(apartment, RoomType.LIVING_ROOM)
    result = execute(apartment, _split(apartment, living, position=0.05))
    assert isinstance(result, ExecuteRejected) and result.stage == "schema"


@pytest.mark.parametrize(
    ("amount", "currency", "expected"),
    [
        (2408253.43, "INR", "INR 24,08,253"),
        (999, "INR", "INR 999"),
        (1000, "INR", "INR 1,000"),
        (100000, "INR", "INR 1,00,000"),
        (12345678, "INR", "INR 1,23,45,678"),
        (2408253, "USD", "USD 2,408,253"),
    ],
)
def test_money_grouping(amount: float, currency: str, expected: str) -> None:
    assert money(amount, currency) == expected


def test_absurd_rates_are_refused_before_they_can_overflow() -> None:
    from pydantic import ValidationError

    for field in ("concrete_per_m3", "steel_per_kg", "plumbing_fixture_each"):
        with pytest.raises(ValidationError):
            CostRates(**{field: 1e308})
    assert CostRates(concrete_per_m3=999_999_999).concrete_per_m3 == 999_999_999

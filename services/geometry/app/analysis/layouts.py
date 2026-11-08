"""Layout suggestions: generate candidate edits, run each through the real engine, keep and rank what survives."""

import re
from collections.abc import Callable
from typing import Any, NamedTuple
from uuid import UUID

from aec_contracts import ExecuteApplied, FloorPlanModel, RoomType, polygon_area
from aec_contracts.analysis import LayoutOption, LayoutSuggestions
from aec_contracts.commands import ENGINE_COMMAND_ADAPTER
from aec_contracts.lexicon import ROOM_SYNONYMS

from ..engine.execute import execute
from .compliance import ROOM_MINIMUMS, build_compliance
from .measure import Plan, RoomInfo, display_name, measure

EXPAND_STEPS_MM = (300, 600, 900)
SIDE_NAME = {"LEFT": "left", "RIGHT": "right", "UP": "top", "DOWN": "bottom"}
SPLIT_POSITIONS = (0.5, 0.4, 0.6)
MAX_OPTIONS = 3
PENALTY_PER_FAILURE = 5.0
NEEDS_SCALE = "Layout suggestions need real measurements. Set a scale first (select a wall and use Set scale)."
HELP = (
    'I can suggest layouts for goals like "Can this house have another bedroom?", "Increase parking" or '
    '"Make the kitchen larger".'
)
BEDROOM_DONORS = (
    RoomType.OFFICE,
    RoomType.STORAGE,
    RoomType.UTILITY,
    RoomType.DINING_ROOM,
    RoomType.OTHER,
    RoomType.UNKNOWN,
)
SPLIT_DONORS = (
    RoomType.LIVING_ROOM,
    RoomType.DINING_ROOM,
    RoomType.MASTER_BEDROOM,
    RoomType.BEDROOM,
    RoomType.OFFICE,
    RoomType.OTHER,
    RoomType.UNKNOWN,
)
PARKING_DONORS = (RoomType.STORAGE, RoomType.UTILITY, RoomType.OTHER, RoomType.UNKNOWN)
PARKING_MIN_M2, PARKING_MIN_WIDTH_MM = 13.0, 2700.0
_SYNONYMS = sorted(ROOM_SYNONYMS, key=len, reverse=True)


class Tried(NamedTuple):
    option: LayoutOption
    key: str  # at most one option per key, so the choices are really different


def _evaluate(
    plan: Plan,
    failures: int,
    raw: dict[str, Any],
    title: str,
    rationale: str,
    target: RoomInfo | None,
    base_score: float = 0.0,
    key: str = "",
    accept: Callable[[Plan], bool] | None = None,
) -> Tried | None:
    result = execute(plan.model, raw, dry_run=True)
    if not isinstance(result, ExecuteApplied):
        return None
    after = measure(result.model)
    if accept and not accept(after):
        return None
    new_failures = max(build_compliance(after).failed - failures, 0)
    before_m2 = after_m2 = None
    gain = 0.0
    if target is not None:
        before_m2 = round(target.area_m2, 2)
        after_m2 = round(after.room(target.room.id).area_m2, 2)
        gain = after_m2 - before_m2
    lost = 0.0
    if target is not None:
        others = (r for r in plan.rooms if r.room.id != target.room.id)
        lost = sum(max(r.area_m2 - after.room(r.room.id).area_m2, 0.0) for r in others)
    score = round(base_score + gain - 0.5 * lost - PENALTY_PER_FAILURE * new_failures, 2)
    taken = f"Takes {lost:.1f} m² from neighbouring rooms. " if lost >= 0.05 else ""
    note = taken + (
        "No new compliance failures."
        if not new_failures
        else f"Adds {new_failures} compliance failure{'' if new_failures == 1 else 's'}."
    )
    return Tried(
        LayoutOption(
            title=title,
            rationale=f"{rationale} {note}",
            command=ENGINE_COMMAND_ADAPTER.validate_python(raw),
            target_area_before_m2=before_m2,
            target_area_after_m2=after_m2,
            new_compliance_failures=new_failures,
            score=score,
        ),
        key or title,
    )


def _best(tried: list[Tried | None]) -> list[LayoutOption]:
    ranked = sorted((t for t in tried if t), key=lambda t: -t.option.score)
    seen: set[str] = set()
    out = []
    for t in ranked:
        if t.key not in seen:
            seen.add(t.key)
            out.append(t.option)
    return out[:MAX_OPTIONS]


def _expand(plan: Plan, failures: int, room: RoomInfo) -> list[LayoutOption]:
    tried = []
    for direction in ("LEFT", "RIGHT", "UP", "DOWN"):
        for step in EXPAND_STEPS_MM:
            raw = {
                "operation": "RESIZE_ROOM",
                "target_id": str(room.room.id),
                "direction": direction,
                "mode": "EXPAND",
                "distance": {"value": step, "unit": "mm"},
            }
            tried.append(
                _evaluate(
                    plan,
                    failures,
                    raw,
                    f"Extend {room.name} {step} mm {direction.lower()}",
                    f"Moves the {SIDE_NAME[direction]} side of {room.name} out by {step} mm.",
                    room,
                    key=direction,
                )
            )
    return _best(tried)


def _convert(plan: Plan, failures: int, room: RoomInfo, name: str, kind: RoomType, score: float) -> Tried | None:
    raw = {"operation": "RENAME_ROOM", "target_id": str(room.room.id), "name": name, "room_type": kind.value}
    return _evaluate(
        plan,
        failures,
        raw,
        f"Convert {room.name} into {name}",
        f"Reuses {room.name} ({room.area_m2:.1f} m²) with no wall changes.",
        room,
        base_score=score,
        key=f"convert:{room.room.id}",
    )


def _bedroom(plan: Plan, failures: int) -> LayoutSuggestions:
    min_area, min_width = ROOM_MINIMUMS[RoomType.BEDROOM]
    number = sum(r.room.room_type in (RoomType.BEDROOM, RoomType.MASTER_BEDROOM) for r in plan.rooms) + 1
    name = f"Bedroom {number}"
    tried: list[Tried | None] = []
    for room in plan.rooms:
        kind = room.room.room_type
        if kind in BEDROOM_DONORS and room.area_m2 >= min_area and room.min_width_mm >= min_width:
            tried.append(_convert(plan, failures, room, name, RoomType.BEDROOM, 10.0))
        if kind not in SPLIT_DONORS or room.area_m2 < 2 * min_area:
            continue
        keep_min = ROOM_MINIMUMS.get(kind, (min_area, min_width))[0]

        def both_usable(after: Plan, room_id: UUID = room.room.id, keep: float = keep_min) -> bool:
            new_room, kept = after.rooms[-1], after.room(room_id)
            return new_room.area_m2 >= min_area and new_room.min_width_mm >= min_width and kept.area_m2 >= keep

        for axis in ("VERTICAL", "HORIZONTAL"):
            for position in SPLIT_POSITIONS:
                raw = {
                    "operation": "SPLIT_ROOM",
                    "target_id": str(room.room.id),
                    "axis": axis,
                    "position": position,
                    "new_room_name": name,
                    "new_room_type": RoomType.BEDROOM.value,
                }
                tried.append(
                    _evaluate(
                        plan,
                        failures,
                        raw,
                        f"Split {room.name} to create {name}",
                        f"Adds a {axis.lower()} wall and a door inside {room.name}.",
                        None,
                        base_score=5.0,
                        key=f"split:{room.room.id}",
                        accept=both_usable,
                    )
                )
    options = _best(tried)
    if not options:
        return LayoutSuggestions(
            feasible=False,
            options=[],
            answer=(
                f"Not within the current footprint: a bedroom needs at least {min_area:g} m² and "
                f"{min_width / 1000:g} m width, and no "
                "room can give that up while staying usable."
            ),
        )
    ways = f"{len(options)} way{'' if len(options) == 1 else 's'}"
    if all(o.new_compliance_failures for o in options):
        return LayoutSuggestions(
            feasible=True,
            options=options,
            answer=f"Only with compromises: {ways} to add {name}, each adding compliance failures.",
        )
    return LayoutSuggestions(
        feasible=True, options=options, answer=f"Yes. Here {'is' if len(options) == 1 else 'are'} {ways} to add {name}."
    )


def _parking(plan: Plan, failures: int) -> LayoutSuggestions:
    garages = [r for r in plan.rooms if r.room.room_type == RoomType.GARAGE]
    if garages:
        options = _expand(plan, failures, max(garages, key=lambda r: r.area_m2))
        if options:
            return LayoutSuggestions(
                feasible=True, options=options, answer=f"Here are {len(options)} ways to enlarge the parking area."
            )
        return LayoutSuggestions(
            feasible=False, options=[], answer="The garage walls can't move without breaking the plan."
        )
    tried = [
        _convert(plan, failures, r, "Garage", RoomType.GARAGE, 5.0)
        for r in plan.rooms
        if r.room.room_type in PARKING_DONORS
        and r.area_m2 >= PARKING_MIN_M2
        and r.min_width_mm >= PARKING_MIN_WIDTH_MM
        and any(o.exterior for o in plan.openings_in(r.room.id, "door"))
    ]
    options = _best(tried)
    if options:
        return LayoutSuggestions(
            feasible=True, options=options, answer="This plan has no parking, but these rooms could become a garage."
        )
    return LayoutSuggestions(
        feasible=False,
        options=[],
        answer=(
            "This plan has no parking, and no room is large enough with an outside door to convert. "
            "The site outside the building "
            "isn't part of this model, so I can't lay out new parking there."
        ),
    )


def _named_room(text: str) -> RoomType | None:
    for phrase in _SYNONYMS:
        if re.search(rf"\b{re.escape(phrase)}\b", text):
            return ROOM_SYNONYMS[phrase]
    return None


def suggest_layouts(model: FloorPlanModel, goal: str) -> LayoutSuggestions:
    if model.coordinate_system.mm_per_pixel is None:
        return LayoutSuggestions(feasible=False, options=[], answer=NEEDS_SCALE)
    text = " ".join(goal.lower().split())
    plan = measure(model)
    failures = build_compliance(plan).failed
    grows = re.search(r"\b(larger|bigger|expand|enlarge|extend|increase|wider|more space)\b", text)
    if re.search(r"\b(parking|garage|carport)\b", text) and (grows or "more" in text or "add" in text):
        return _parking(plan, failures)
    if re.search(r"\b(another|extra|additional|new|add|one more|second|third)\b", text) and re.search(
        r"\b(bed ?rooms?|guest room)\b", text
    ):
        return _bedroom(plan, failures)
    if grows and (kind := _named_room(text)):
        rooms = [r for r in plan.rooms if r.room.room_type == kind]
        if not rooms:
            return LayoutSuggestions(
                feasible=False, options=[], answer=f"This plan has no {kind.replace('_', ' ').lower()}."
            )
        room = max(rooms, key=lambda r: polygon_area(r.room.polygon))
        options = _expand(plan, failures, room)
        if not options:
            return LayoutSuggestions(
                feasible=False, options=[], answer=f"{display_name(room.room)} can't grow without breaking the plan."
            )
        return LayoutSuggestions(
            feasible=True,
            options=options,
            answer=f"Here are {len(options)} ways to make {display_name(room.room)} larger.",
        )
    return LayoutSuggestions(feasible=False, options=[], answer=HELP)

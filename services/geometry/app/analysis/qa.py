"""Blueprint chatbot: rules answer from the structured model; unknown questions reach the LLM with `facts` only."""

import re
from typing import Any
from uuid import UUID

from aec_contracts import FloorPlanModel, RoomType, polygon_area
from aec_contracts.analysis import Answer
from aec_contracts.lexicon import ROOM_SYNONYMS

from ..insights import build_insights
from .compliance import build_compliance
from .cost import build_estimate
from .measure import Plan, display_name, measure
from .takeoff import build_takeoff

UNKNOWN = "I can't answer that from this plan's data."
NEEDS_SCALE = "That needs real measurements, and this plan has no scale yet. Select a wall and use Set scale."

_ELEMENTS = {
    "door": "doors",
    "window": "windows",
    "wall": "walls",
    "column": "columns",
    "stair": "stairs",
    "room": "rooms",
}
_MATERIALS: tuple[tuple[str, str, str], ...] = (
    (r"\bbricks?\b", "MA-02", "bricks"),
    (r"\bconcrete\b", "CO-04", "m³ of concrete"),
    (r"\bsteel\b", "ST-01", "kg of steel"),
    (r"\bpaint\b", "PA-03", "litres of paint"),
    (r"\b(?:floor )?tiles?\b", "TI-03", "floor tiles"),
)
_SYNONYM_PATTERN = sorted(ROOM_SYNONYMS, key=len, reverse=True)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _room_phrase(text: str) -> tuple[str, RoomType] | None:
    for phrase in _SYNONYM_PATTERN:
        if re.search(rf"\b{re.escape(phrase)}(?:s|es)?\b", text):
            return phrase, ROOM_SYNONYMS[phrase]
    return None


def _rooms_of(model: FloorPlanModel, kind: RoomType) -> list[Any]:
    """ "Bedroom" counts master bedrooms too: people mean both when they ask how many bedrooms there are."""
    kinds = {RoomType.BEDROOM, RoomType.MASTER_BEDROOM} if kind == RoomType.BEDROOM else {kind}
    return [r for r in model.rooms if r.room_type in kinds]


def _ok(answer: str, ids: list[UUID] | None = None) -> Answer:
    return Answer(status="ANSWERED", answer=answer, element_ids=ids or [])


def _where(plan: Plan, x: float, y: float) -> str:
    cs = plan.model.coordinate_system
    ns = "north" if y < cs.image_height / 3 else "south" if y > 2 * cs.image_height / 3 else ""
    ew = "west" if x < cs.image_width / 3 else "east" if x > 2 * cs.image_width / 3 else ""
    return f"{ns}{ew}" if ns and ew else ns or ew or "central"


def _exits(plan: Plan) -> Answer:
    doors = [d for d in plan.doors if d.exterior]
    if not doors:
        return _ok("I found no exterior doors on this plan, so it has no marked exit.")
    parts = []
    for d in doors:
        room = display_name(d.rooms[0]) if d.rooms else "the plan edge"
        parts.append(f"{room} ({_where(plan, *d.centre)} side)")
    return _ok(
        f"{_plural(len(doors), 'exit door')}: {', '.join(parts)}. Exits are exterior doors detected on the plan.",
        [d.element.id for d in doors],
    )


def _measured(model: FloorPlanModel, text: str) -> Answer | None:
    """Questions that need a scale. None means the question isn't one of these."""
    wants_cost = re.search(r"\b(cost|price|budget|expensive)\b", text)
    wants_compliance = re.search(r"\b(compl(?:y|iant|iance)|violations?|building code|code check|regulations?)\b", text)
    wants_exit = re.search(r"\b(emergency exits?|exits?|escape)\b", text)
    material = next((m for m in _MATERIALS if re.search(m[0], text)), None)
    wants_wall_length = "wall" in text and re.search(r"\b(length|long)\b", text)
    wants_area = re.search(r"\b(area|size|big|square|m2|sqm)\b", text)
    if not (wants_cost or wants_compliance or wants_exit or material or wants_wall_length or wants_area):
        return None
    if model.coordinate_system.mm_per_pixel is None:
        return _ok(NEEDS_SCALE)
    plan = measure(model)
    if wants_exit:
        return _exits(plan)
    if wants_compliance:
        report = build_compliance(plan)
        worst = [c for c in report.checks if c.status == "FAIL"][:3]
        lead = f"{report.failed} failed, {report.warnings} warnings, {report.passed} passed on the indicative checks."
        detail = " ".join(f"{c.subject}: {c.rule.lower()} is {c.measured}, needs {c.required}." for c in worst)
        return _ok(f"{lead} {detail}".strip(), [c.element_id for c in worst if c.element_id])
    takeoff = build_takeoff(plan)
    if wants_cost:
        e = build_estimate(plan, takeoff, None)
        return _ok(
            f"About {e.currency} {e.construction_cost:,.0f} at the default India rates. "
            "Set local rates in Analyze > Cost."
        )
    if material:
        qty = next(i.quantity for i in takeoff.items if i.code == material[1])
        return _ok(f"About {qty:,.0f} {material[2]}. See Analyze > Takeoff for how it's derived.")
    metric = build_insights(model).metric
    assert metric is not None  # a scale is set
    if wants_wall_length:
        if "exterior" in text or "external" in text or "outer" in text:
            return _ok(f"The exterior wall length is {metric.exterior_wall_length_m} m.")
        if "interior" in text or "internal" in text or "inner" in text:
            return _ok(f"The interior wall length is {metric.interior_wall_length_m} m.")
        return _ok(
            f"The total wall length is {metric.total_wall_length_m} m "
            f"({metric.exterior_wall_length_m} m exterior, {metric.interior_wall_length_m} m interior)."
        )
    if found := _room_phrase(text):
        rooms = _rooms_of(model, found[1])
        if rooms:
            parts = [f"{r.name} is {r.area_m2:.2f} m²" for r in plan.rooms if r.room.id in {x.id for x in rooms}]
            return _ok("; ".join(parts) + ".", [r.id for r in rooms])
        return _ok(f"This plan has no {found[0]}.")
    return _ok(f"The total floor area is {metric.total_area_m2} m².")


def answer_question(model: FloorPlanModel, question: str) -> Answer:
    text = " ".join(question.lower().split())
    m = re.search(r"\b(largest|biggest|smallest)\b", text)
    if m and not re.search(r"\b(door|window|wall|column|stair)s?\b", text):
        if not model.rooms:
            return _ok("This plan has no rooms yet.")
        pick = (max if m[1] != "smallest" else min)(model.rooms, key=lambda r: polygon_area(r.polygon))
        mm = model.coordinate_system.mm_per_pixel
        size = (
            f"{polygon_area(pick.polygon) * (mm / 1000) ** 2:.2f} m²"
            if mm
            else f"{polygon_area(pick.polygon):,.0f} px²"
        )
        return _ok(f"{display_name(pick)} is the {m[1]} room, at {size}.", [pick.id])
    if re.search(r"\b(how many|number of|count of)\b", text):
        found = _room_phrase(text)
        if found:
            rooms = _rooms_of(model, found[1])
            return _ok(
                f"This plan has {_plural(len(rooms), found[0])}"
                + (f": {', '.join(display_name(r) for r in rooms)}." if rooms else "."),
                [r.id for r in rooms],
            )
        for word, attr in _ELEMENTS.items():
            if re.search(rf"\b{word}s?\b", text):
                items = getattr(model, attr)
                return _ok(f"This plan has {_plural(len(items), word)}.", [i.id for i in items])
    if re.search(r"\b(list|what|which) (?:the |all )?rooms\b", text):
        return _ok(
            ", ".join(display_name(r) for r in model.rooms) + "." if model.rooms else "This plan has no rooms yet.",
            [r.id for r in model.rooms],
        )
    return _measured(model, text) or Answer(status="UNKNOWN", answer=UNKNOWN)


def plan_facts(model: FloorPlanModel) -> dict[str, Any]:
    """The only plan data the LLM ever sees: no coordinates and no ids."""
    facts: dict[str, Any] = {
        "counts": model.summary().model_dump(),
        "has_scale": model.coordinate_system.mm_per_pixel is not None,
    }
    if model.coordinate_system.mm_per_pixel is None:
        facts["rooms"] = [{"name": display_name(r), "type": r.room_type} for r in model.rooms]
        return facts
    plan = measure(model)
    takeoff = build_takeoff(plan)
    facts["rooms"] = [
        {
            "name": r.name,
            "type": r.room.room_type,
            "area_m2": round(r.area_m2, 2),
            "min_width_mm": round(r.min_width_mm),
            "windows": len(plan.openings_in(r.room.id)),
            "doors": len(plan.openings_in(r.room.id, "door")),
        }
        for r in plan.rooms
    ]
    facts["quantities"] = {i.description: f"{i.quantity} {i.unit}" for i in takeoff.items}
    report = build_compliance(plan)
    facts["compliance"] = {
        "passed": report.passed,
        "warnings": report.warnings,
        "failed": report.failed,
        "failures": [
            f"{c.subject}: {c.rule} ({c.measured}, needs {c.required})" for c in report.checks if c.status == "FAIL"
        ][:20],
    }
    return facts

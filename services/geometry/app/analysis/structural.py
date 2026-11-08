"""Advisory structural and spatial suggestions. Any attached command has already passed the engine."""

from typing import Any
from uuid import UUID

from aec_contracts import ExecuteApplied, RoomType
from aec_contracts.analysis import StructuralReport, StructuralSuggestion
from aec_contracts.commands import ENGINE_COMMAND_ADAPTER

from ..engine.execute import execute
from ..engine.geom import are_parallel, distance_to_line, distance_to_wall, is_axis_aligned, midpoint, unit, wall_axis
from .compliance import GLAZING_RATIO
from .measure import HABITABLE, Plan, RoomInfo, WallInfo, contains
from .takeoff import WINDOW_HEIGHT_M

DISCLAIMER = (
    "Early-stage advice from plan geometry only. Loads and soil are unknown here: a structural engineer must "
    "check anything before it is built."
)
MAX_SPAN_MM, MAX_WALL_RUN_MM = 5000.0, 6000.0
ALIGN_MIN_MM, ALIGN_MAX_MM, ALIGN_GAP_MM = 50.0, 300.0, 300.0
COLUMN_ALIGN_MIN_MM, COLUMN_ALIGN_MAX_MM = 100.0, 400.0
HALLWAY_SHARE, NARROW_RATIO = 0.15, 2.5
MIN_WALL_FOR_WINDOW_MM = 1500.0
WINDOW_SIZES_MM, WINDOW_SPOTS = (1200.0, 800.0), (0.5, 0.2, 0.8)


def _viable(plan: Plan, raw: dict[str, Any]) -> Any:
    """The command only if the engine would apply it today, so a suggestion never offers a dead button."""
    result = execute(plan.model, raw, dry_run=True)
    return ENGINE_COMMAND_ADAPTER.validate_python(raw) if isinstance(result, ExecuteApplied) else None


def _exterior_wall(plan: Plan, room: RoomInfo) -> WallInfo | None:
    ids = set(room.room.wall_ids)
    options = [w for w in plan.walls if w.wall.id in ids and w.exterior and w.length_m * 1000 >= MIN_WALL_FOR_WINDOW_MM]
    return max(options, key=lambda w: w.length_m, default=None)


def _add_window(plan: Plan, room: RoomInfo, wall: WallInfo) -> Any:
    """The first size and spot the engine accepts, measured along the room: a long wall run can span several rooms."""
    w = wall.wall
    ux, uy = unit(w)
    spots = [(p[0] - w.start.x) * ux + (p[1] - w.start.y) * uy for p in room.polygon.exterior.coords]
    low, high = max(min(spots), 0.0), min(max(spots), w.length_px)
    for width_mm in WINDOW_SIZES_MM:
        for fraction in WINDOW_SPOTS:
            position = round((low + fraction * (high - low)) / w.length_px, 3)
            command = _viable(
                plan,
                {
                    "operation": "ADD_WINDOW",
                    "target_id": str(w.id),
                    "position": position,
                    "width": {"value": width_mm, "unit": "mm"},
                },
            )
            if command is not None:
                return command
    return None


def build_structural(plan: Plan) -> StructuralReport:
    out: list[StructuralSuggestion] = []

    def add(category: Any, title: str, detail: str, element_id: UUID | None = None, command: Any = None) -> None:
        out.append(
            StructuralSuggestion(category=category, title=title, detail=detail, element_id=element_id, command=command)
        )

    columns = plan.model.columns
    for room in plan.rooms:
        has_column = any(contains(room, c.bbox.x + c.bbox.width / 2, c.bbox.y + c.bbox.height / 2) for c in columns)
        if room.min_width_mm > MAX_SPAN_MM and not has_column:
            add(
                "Column placement",
                f"Long clear span in {room.name}",
                f"The shorter span is {room.min_width_mm / 1000:.1f} m, above the usual "
                f"{MAX_SPAN_MM / 1000:g} m for a simple slab. "
                "Consider a column or a deeper beam.",
                room.room.id,
            )
    for wall in plan.walls:
        if wall.length_m * 1000 > MAX_WALL_RUN_MM:
            add(
                "Column placement",
                f"Unbroken {wall.length_m:.1f} m wall",
                f"Runs over {MAX_WALL_RUN_MM / 1000:g} m usually want an intermediate column or pier.",
                wall.wall.id,
            )
    mm = plan.mm
    for i, column in enumerate(columns):
        for other in columns[i + 1 :]:
            dx, dy = abs(column.bbox.x - other.bbox.x) * mm, abs(column.bbox.y - other.bbox.y) * mm
            if COLUMN_ALIGN_MIN_MM <= dx <= COLUMN_ALIGN_MAX_MM or COLUMN_ALIGN_MIN_MM <= dy <= COLUMN_ALIGN_MAX_MM:
                add(
                    "Column placement",
                    "Columns slightly off grid",
                    f"Two columns sit {min(v for v in (dx, dy) if v >= COLUMN_ALIGN_MIN_MM):.0f} mm out of line. "
                    "Aligning them "
                    "lets beams run straight.",
                    column.id,
                )

    seen: set[UUID] = set()
    aligned = [w for w in plan.walls if is_axis_aligned(w.wall)]
    for i, first in enumerate(aligned):
        for second in aligned[i + 1 :]:
            a, b = first.wall, second.wall
            if not are_parallel(a, b) or {a.id, b.id} & seen:
                continue
            offset = max(distance_to_line(b.start, a), distance_to_line(b.end, a)) * mm
            near = min(distance_to_wall(p.x, p.y, a) for p in (b.start, b.end))
            reach = (offset**2 + (ALIGN_GAP_MM**2)) ** 0.5 / mm
            if not ALIGN_MIN_MM <= offset <= ALIGN_MAX_MM or near > reach:
                continue
            seen |= {a.id, b.id}
            shorter = b if b.length_px <= a.length_px else a
            longer = a if shorter is b else b
            mid_short, mid_long = midpoint(shorter), midpoint(longer)
            direction = (
                ("DOWN" if mid_long[1] > mid_short[1] else "UP")
                if wall_axis(shorter) == "horizontal"
                else ("RIGHT" if mid_long[0] > mid_short[0] else "LEFT")
            )
            command = _viable(
                plan,
                {
                    "operation": "MOVE_WALL",
                    "target_id": str(shorter.id),
                    "direction": direction,
                    "distance": {"value": round(offset), "unit": "mm"},
                },
            )
            add(
                "Wall alignment",
                "Nearly aligned walls",
                f"Two walls miss each other by {offset:.0f} mm. Lining them up simplifies framing and loads.",
                shorter.id,
                command,
            )

    floor = plan.floor_area_m2
    hall = sum(r.area_m2 for r in plan.rooms if r.room.room_type == RoomType.HALLWAY)
    if floor and hall / floor > HALLWAY_SHARE:
        add(
            "Space optimization",
            "A lot of floor goes to circulation",
            f"Hallways take {hall / floor:.0%} of the floor. Under {HALLWAY_SHARE:.0%} leaves more usable room area.",
        )
    for room in plan.rooms:
        if room.room.room_type in HABITABLE and room.min_width_mm:
            long_side = room.polygon.minimum_rotated_rectangle.length / 2 * mm - room.min_width_mm
            if long_side / room.min_width_mm > NARROW_RATIO:
                add(
                    "Space optimization",
                    f"{room.name} is long and narrow",
                    f"It is {long_side / room.min_width_mm:.1f} times longer than wide, which limits furniture.",
                    room.room.id,
                )

    for room in plan.rooms:
        if room.room.room_type not in HABITABLE:
            continue
        windows = [w for w in plan.openings_in(room.room.id) if w.exterior]
        outer = _exterior_wall(plan, room)
        if not windows:
            detail = "No exterior window, so there is no natural airflow."
            if outer is None:
                add(
                    "Natural ventilation",
                    f"{room.name} has no outside air",
                    f"{detail} It has no exterior wall: consider a shaft or vent.",
                    room.room.id,
                )
            else:
                add(
                    "Natural ventilation",
                    f"Add a window to {room.name}",
                    detail,
                    room.room.id,
                    _add_window(plan, room, outer),
                )
            continue
        if len({o.wall.wall.id for o in windows if o.wall}) == 1 and len(windows) == 1 and room.area_m2 > 12:
            add(
                "Natural ventilation",
                f"Single-sided ventilation in {room.name}",
                "Openings on two walls would allow cross-ventilation.",
                room.room.id,
            )
        glazed = sum(w.width_mm / 1000 * WINDOW_HEIGHT_M for w in windows)
        if glazed < room.area_m2 * GLAZING_RATIO:
            add(
                "Lighting improvement",
                f"More daylight for {room.name}",
                f"Glazing is {glazed:.2f} m² against a target of {room.area_m2 * GLAZING_RATIO:.2f} m².",
                room.room.id,
                _add_window(plan, room, outer) if outer else None,
            )

    return StructuralReport(disclaimer=DISCLAIMER, suggestions=out)

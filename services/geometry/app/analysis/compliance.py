"""Building-code checks based on NBC India 2016. Thresholds are constants, so a bylaw's values can replace them."""

from uuid import UUID

from aec_contracts import RoomType
from aec_contracts.analysis import ComplianceCategory, ComplianceCheck, ComplianceReport

from .measure import HABITABLE, SLEEPING, Plan, travel_distances_m
from .takeoff import WINDOW_HEIGHT_M

PROFILE = "NBC India 2016, residential (indicative)"
DISCLAIMER = (
    "Thresholds follow published summaries of the National Building Code of India 2016. This is not a certified "
    "code review: confirm every result against the NBC text and your state or municipal building bylaws."
)

# type: (minimum area m², minimum width mm). Habitable, kitchen and bathroom values: NBC 2016 Part 3 as summarised.
ROOM_MINIMUMS: dict[RoomType, tuple[float, float]] = {
    RoomType.BEDROOM: (9.5, 2400),
    RoomType.MASTER_BEDROOM: (9.5, 2400),
    RoomType.LIVING_ROOM: (9.5, 2400),
    RoomType.DINING_ROOM: (7.5, 2100),
    RoomType.OFFICE: (7.5, 2100),
    RoomType.KITCHEN: (5.0, 1800),
    RoomType.BATHROOM: (1.8, 1200),
    RoomType.LAUNDRY: (1.8, 1200),
}
# Corridor, internal door, glazing and accessibility values are common Indian practice, not confirmed clause by clause.
CORRIDOR_MIN_MM, CORRIDOR_ACCESSIBLE_MM = 1000.0, 1200.0
DOOR_MIN_MM, DOOR_BATH_MIN_MM, DOOR_ACCESSIBLE_MM, EXIT_DOOR_MIN_MM = 800.0, 700.0, 900.0, 1000.0
TURNING_CIRCLE_MM = 1500.0
GLAZING_RATIO = 0.10
LARGE_FLOOR_M2 = 150.0
MAX_TRAVEL_M = 22.5  # NBC Part 4, residential without sprinklers
STAIR_MIN_MM = 1000.0
ESCAPE_WINDOW_MIN_MM = 600.0


def build_compliance(plan: Plan) -> ComplianceReport:
    checks: list[ComplianceCheck] = []

    def check(
        category: ComplianceCategory,
        rule: str,
        ok: bool,
        subject: str,
        measured: str,
        required: str,
        element_id: UUID | None = None,
        severity: str = "FAIL",
    ) -> None:
        checks.append(
            ComplianceCheck.model_validate(
                {
                    "category": category,
                    "rule": rule,
                    "status": "PASS" if ok else severity,
                    "subject": subject,
                    "measured": measured,
                    "required": required,
                    "element_id": element_id,
                }
            )
        )

    exits = [d for d in plan.doors if d.exterior]

    for r in plan.rooms:
        rid, kind = r.room.id, r.room.room_type
        if kind == RoomType.HALLWAY:
            check(
                "Corridor width",
                "Minimum clear corridor width",
                r.min_width_mm >= CORRIDOR_MIN_MM,
                r.name,
                f"{r.min_width_mm:.0f} mm",
                f"≥ {CORRIDOR_MIN_MM:.0f} mm",
                rid,
            )
            check(
                "Accessibility",
                "Wheelchair-passable corridor",
                r.min_width_mm >= CORRIDOR_ACCESSIBLE_MM,
                r.name,
                f"{r.min_width_mm:.0f} mm",
                f"≥ {CORRIDOR_ACCESSIBLE_MM:.0f} mm",
                rid,
                "WARN",
            )
        if minimum := ROOM_MINIMUMS.get(kind):
            area, width = minimum
            check(
                "Room size",
                "Minimum floor area",
                r.area_m2 >= area,
                r.name,
                f"{r.area_m2:.2f} m²",
                f"≥ {area:g} m²",
                rid,
            )
            check(
                "Room size",
                "Minimum room width",
                r.min_width_mm >= width,
                r.name,
                f"{r.min_width_mm:.0f} mm",
                f"≥ {width:.0f} mm",
                rid,
            )
        if kind == RoomType.BATHROOM:
            check(
                "Accessibility",
                "Wheelchair turning space",
                r.min_width_mm >= TURNING_CIRCLE_MM,
                r.name,
                f"{r.min_width_mm:.0f} mm",
                f"≥ {TURNING_CIRCLE_MM:.0f} mm",
                rid,
                "WARN",
            )
        if kind in HABITABLE:
            windows = plan.openings_in(rid)
            outside = [w for w in windows if w.exterior]
            check(
                "Window placement",
                "Window on an exterior wall",
                bool(outside),
                r.name,
                f"{len(outside)} exterior window{'' if len(outside) == 1 else 's'}",
                "≥ 1",
                rid,
            )
            glazed = sum(w.width_mm / 1000 * WINDOW_HEIGHT_M for w in outside)
            needed = r.area_m2 * GLAZING_RATIO
            check(
                "Window placement",
                "Glazing for daylight",
                glazed >= needed,
                r.name,
                f"{glazed:.2f} m²",
                f"≥ {needed:.2f} m² ({GLAZING_RATIO:.0%} of floor)",
                rid,
                "WARN",
            )
        if kind in SLEEPING:
            escape = any(w.exterior and w.width_mm >= ESCAPE_WINDOW_MIN_MM for w in plan.openings_in(rid)) or any(
                d.exterior for d in plan.openings_in(rid, "door")
            )
            check(
                "Fire safety",
                "Escape window or exterior door from sleeping room",
                escape,
                r.name,
                "Present" if escape else "None",
                f"Exterior door or window ≥ {ESCAPE_WINDOW_MIN_MM:.0f} mm wide",
                rid,
            )

    for door in plan.doors:
        bath = any(r.room_type == RoomType.BATHROOM for r in door.rooms)
        door_min = EXIT_DOOR_MIN_MM if door.exterior else DOOR_BATH_MIN_MM if bath else DOOR_MIN_MM
        subject = " / ".join(r.label_text or r.room_type.replace("_", " ").capitalize() for r in door.rooms) or "Door"
        rule = "Exit door clear width" if door.exterior else "Internal door clear width"
        check(
            "Door width",
            rule,
            door.width_mm >= door_min,
            subject,
            f"{door.width_mm:.0f} mm",
            f"≥ {door_min:.0f} mm",
            door.element.id,
        )
        check(
            "Accessibility",
            "Wheelchair-passable door",
            door.width_mm >= DOOR_ACCESSIBLE_MM,
            subject,
            f"{door.width_mm:.0f} mm",
            f"≥ {DOOR_ACCESSIBLE_MM:.0f} mm",
            door.element.id,
            "WARN",
        )

    floor = plan.floor_area_m2
    check(
        "Emergency exits",
        "At least one exit to the outside",
        bool(exits),
        "Whole plan",
        f"{len(exits)} exit door(s)",
        "≥ 1",
    )
    if floor > LARGE_FLOOR_M2:
        check(
            "Emergency exits",
            "Second exit on a large floor plate",
            len(exits) >= 2,
            "Whole plan",
            f"{len(exits)} exit door(s)",
            f"≥ 2 above {LARGE_FLOOR_M2:g} m²",
            severity="WARN",
        )

    distances = travel_distances_m(plan)
    for r in plan.rooms if exits else []:  # no exit at all is already reported once, above
        if r.room.id not in distances:
            check(
                "Fire safety",
                "Door route to an exit",
                False,
                r.name,
                "No route through doors",
                "A connected route",
                r.room.id,
            )
        else:
            check(
                "Fire safety",
                "Travel distance to exit",
                distances[r.room.id] <= MAX_TRAVEL_M,
                r.name,
                f"{distances[r.room.id]:.1f} m",
                f"≤ {MAX_TRAVEL_M:g} m",
                r.room.id,
            )
    for stair in plan.model.stairs:
        width = min(stair.bbox.width, stair.bbox.height) * plan.mm
        check(
            "Fire safety",
            "Stair clear width",
            width >= STAIR_MIN_MM,
            "Stair",
            f"{width:.0f} mm",
            f"≥ {STAIR_MIN_MM:.0f} mm",
            stair.id,
        )

    return ComplianceReport(
        profile=PROFILE,
        disclaimer=DISCLAIMER,
        checks=checks,
        passed=sum(c.status == "PASS" for c in checks),
        warnings=sum(c.status == "WARN" for c in checks),
        failed=sum(c.status == "FAIL" for c in checks),
    )

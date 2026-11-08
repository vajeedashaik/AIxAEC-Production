"""Cost estimate: takeoff quantities × editable rates. Default rates are placeholders until the user sets local ones."""

from math import ceil
from typing import Any

from aec_contracts import RoomType
from aec_contracts.analysis import Assumption, CostEstimate, CostLine, CostRates, Takeoff

from .measure import Plan
from .takeoff import quantity

SOCKETS: dict[RoomType, int] = {
    RoomType.LIVING_ROOM: 6,
    RoomType.MASTER_BEDROOM: 6,
    RoomType.BEDROOM: 5,
    RoomType.KITCHEN: 8,
    RoomType.OFFICE: 6,
    RoomType.DINING_ROOM: 3,
    RoomType.BATHROOM: 2,
    RoomType.LAUNDRY: 3,
    RoomType.GARAGE: 3,
    RoomType.UTILITY: 3,
}
DEFAULT_SOCKETS = 2
FIXTURES: dict[RoomType, int] = {RoomType.BATHROOM: 3, RoomType.KITCHEN: 2, RoomType.LAUNDRY: 2}
M2_PER_LIGHT = 9.0


def electrical_points(plan: Plan) -> int:
    return sum(ceil(r.area_m2 / M2_PER_LIGHT) + SOCKETS.get(r.room.room_type, DEFAULT_SOCKETS) for r in plan.rooms)


def plumbing_fixtures(plan: Plan) -> int:
    return sum(FIXTURES.get(r.room.room_type, 0) for r in plan.rooms)


def build_estimate(plan: Plan, takeoff: Takeoff, rates: CostRates | None) -> CostEstimate:
    r = rates or CostRates()

    def q(code: str) -> float:
        return quantity(takeoff, code)

    painted = q("PA-01") + q("PA-02")
    points, fixtures = electrical_points(plan), plumbing_fixtures(plan)
    tile_count = int(q("TI-03") + q("TI-04"))
    specs: list[tuple[Any, str, float, str, float]] = [
        ("Structure", "Concrete", q("CO-04"), "m³", r.concrete_per_m3),
        ("Structure", "Reinforcement steel", q("ST-01"), "kg", r.steel_per_kg),
        ("Structure", "Bricks", q("MA-02"), "nr", r.brick_each),
        ("Openings", "Doors", q("OP-01"), "nr", r.door_each),
        ("Openings", "Windows", q("OP-02"), "nr", r.window_each),
        ("Painting", "Paint", q("PA-03"), "L", r.paint_per_litre),
        ("Painting", "Painting labour", painted, "m²", r.painting_labour_per_m2),
        ("Flooring", "Floor tiles", q("TI-01"), "m²", r.floor_tile_per_m2),
        ("Flooring", "Wall tiles", q("TI-02"), "m²", r.wall_tile_per_m2),
        ("Flooring", "Other flooring", q("FL-01"), "m²", r.flooring_per_m2),
        ("Electrical", "Lighting and socket points", points, "nr", r.electrical_point_each),
        ("Plumbing", "Plumbing fixtures", fixtures, "nr", r.plumbing_fixture_each),
    ]
    lines = [
        CostLine(category=c, description=d, quantity=round(n, 2), unit=u, rate=rate, amount=round(n * rate, 2))
        for c, d, n, u, rate in specs
    ]

    def total(*categories: str) -> float:
        return round(sum(line.amount for line in lines if line.category in categories), 2)

    material = total("Structure", "Openings")
    painting, flooring, electrical, plumbing = (
        total("Painting"),
        total("Flooring"),
        total("Electrical"),
        total("Plumbing"),
    )
    labour = round((material + flooring) * r.labour_percent / 100, 2)
    subtotal = material + painting + flooring + electrical + plumbing + labour
    contingency = round(subtotal * r.contingency_percent / 100, 2)
    construction = round(subtotal + contingency, 2)
    floor = q("FA-01")
    return CostEstimate(
        currency=r.currency,
        rates=r,
        lines=lines,
        material_cost=material,
        painting_cost=painting,
        flooring_cost=flooring,
        electrical_cost=electrical,
        plumbing_cost=plumbing,
        labour_cost=labour,
        contingency=contingency,
        construction_cost=construction,
        cost_per_m2=round(construction / floor, 2) if floor else 0.0,
        tile_count=tile_count,
        assumptions=[
            Assumption(label="Rates", value="Rough India averages: replace them with current local prices"),
            Assumption(
                label="Labour",
                value=f"{r.labour_percent:g}% of structure, openings and flooring; painting labour is its own line",
            ),
            Assumption(label="Electrical", value="One light per 9 m² plus sockets by room type"),
            Assumption(label="Plumbing", value="Bathroom 3 fixtures, kitchen 2, laundry 2"),
        ],
    )

"""Quantity takeoff and Bill of Quantities. Geometry comes from the model; build-ups are stated assumptions."""

from math import ceil

from aec_contracts import RoomType
from aec_contracts.analysis import Assumption, BoqItem, Takeoff

from .measure import OpeningInfo, Plan

WALL_HEIGHT_M, DOOR_HEIGHT_M, WINDOW_HEIGHT_M = 3.0, 2.1, 1.2
SLAB_M, LINTEL_DEPTH_M, LINTEL_BEARING_M = 0.15, 0.15, 0.15
BRICKS_PER_M3, WASTE = 500, 1.05
PAINT_COATS, PAINT_COVERAGE_M2_PER_L = 2, 10.0
FLOOR_TILE_M2, WALL_TILE_M2, TILE_WASTE = 0.36, 0.09, 1.10
BATH_TILE_HEIGHT_M = 2.1
STEEL_KG_PER_M3 = {"slab": 80.0, "column": 160.0, "lintel": 100.0}
TILED_FLOORS = {RoomType.BATHROOM, RoomType.KITCHEN, RoomType.LAUNDRY, RoomType.BALCONY}
DEFAULT_COLUMN_M = 0.3

ASSUMPTIONS = [
    ("Wall height", f"{WALL_HEIGHT_M:g} m"),
    ("Door height", f"{DOOR_HEIGHT_M:g} m"),
    ("Window height", f"{WINDOW_HEIGHT_M:g} m"),
    ("Slab thickness", f"{SLAB_M * 1000:.0f} mm"),
    ("Wall thickness when not detected", "230 mm exterior, 115 mm interior"),
    ("Bricks", f"{BRICKS_PER_M3} per m³ including mortar, plus {WASTE - 1:.0%} waste"),
    ("Paint", f"{PAINT_COATS} coats at {PAINT_COVERAGE_M2_PER_L:g} m² per litre"),
    ("Tiles", f"600 × 600 mm floor, 300 × 300 mm wall, plus {TILE_WASTE - 1:.0%} waste"),
    ("Steel", "80 kg/m³ slab, 160 kg/m³ columns, 100 kg/m³ lintels"),
    ("Excluded", "Foundations, roof finishes and external works"),
]


def _opening_area(o: OpeningInfo, height: float) -> float:
    return o.width_mm / 1000 * height


def build_takeoff(plan: Plan) -> Takeoff:
    exterior_m = sum(w.length_m for w in plan.walls if w.exterior)
    interior_m = sum(w.length_m for w in plan.walls if not w.exterior)
    floor_m2 = plan.floor_area_m2

    openings = [(o, DOOR_HEIGHT_M) for o in plan.doors] + [(o, WINDOW_HEIGHT_M) for o in plan.windows]
    gross_m3 = sum(w.length_m * WALL_HEIGHT_M * w.thickness_m for w in plan.walls)
    opening_m3 = sum(_opening_area(o, h) * (o.wall.thickness_m if o.wall else 0.23) for o, h in openings)
    brick_m3 = max(gross_m3 - opening_m3, 0.0)
    bricks = ceil(brick_m3 * BRICKS_PER_M3 * WASTE)

    wall_footprint_m2 = sum(w.length_m * w.thickness_m for w in plan.walls)
    slab_m3 = (floor_m2 + wall_footprint_m2) * SLAB_M
    mm_m = plan.mm / 1000
    column_m3 = sum(c.bbox.width * mm_m * c.bbox.height * mm_m * WALL_HEIGHT_M for c in plan.model.columns)
    lintel_m3 = sum(
        (o.width_mm / 1000 + 2 * LINTEL_BEARING_M) * (o.wall.thickness_m if o.wall else 0.23) * LINTEL_DEPTH_M
        for o, _ in openings
    )
    concrete_m3 = slab_m3 + column_m3 + lintel_m3
    steel_kg = (
        slab_m3 * STEEL_KG_PER_M3["slab"]
        + column_m3 * STEEL_KG_PER_M3["column"]
        + lintel_m3 * STEEL_KG_PER_M3["lintel"]
    )

    # Interior faces: both sides of partitions, one side of exterior walls, plus ceilings. Exterior doors and windows
    # are deducted once per face they cut.
    interior_faces = sum(_opening_area(o, h) * (1 if o.exterior else 2) for o, h in openings)
    bath = [r for r in plan.rooms if r.room.room_type == RoomType.BATHROOM]
    wall_tile_m2 = sum(r.perimeter_m for r in bath) * BATH_TILE_HEIGHT_M
    paint_interior_m2 = (
        max((2 * interior_m + exterior_m) * WALL_HEIGHT_M - interior_faces - wall_tile_m2, 0.0) + floor_m2
    )
    paint_exterior_m2 = max(
        exterior_m * WALL_HEIGHT_M - sum(_opening_area(o, h) for o, h in openings if o.exterior), 0.0
    )
    paint_l = (paint_interior_m2 + paint_exterior_m2) * PAINT_COATS / PAINT_COVERAGE_M2_PER_L

    tiled_m2 = sum(r.area_m2 for r in plan.rooms if r.room.room_type in TILED_FLOORS)
    floor_tiles = ceil(tiled_m2 / FLOOR_TILE_M2 * TILE_WASTE)
    wall_tiles = ceil(wall_tile_m2 / WALL_TILE_M2 * TILE_WASTE)

    def item(code: str, category: str, description: str, unit: str, quantity: float, basis: str) -> BoqItem:
        return BoqItem(
            code=code, category=category, description=description, unit=unit, quantity=round(quantity, 2), basis=basis
        )

    return Takeoff(
        assumptions=[Assumption(label=a, value=b) for a, b in ASSUMPTIONS],
        items=[
            item("WL-01", "Walls", "Exterior wall length", "m", exterior_m, "Sum of exterior wall centre-lines"),
            item("WL-02", "Walls", "Interior wall length", "m", interior_m, "Sum of interior wall centre-lines"),
            item("WL-03", "Walls", "Total wall length", "m", exterior_m + interior_m, "Exterior + interior"),
            item("FA-01", "Floor", "Floor area", "m²", floor_m2, "Sum of room polygons"),
            item("OP-01", "Openings", "Doors", "nr", len(plan.doors), "Counted from the model"),
            item("OP-02", "Openings", "Windows", "nr", len(plan.windows), "Counted from the model"),
            item("MA-01", "Masonry", "Brickwork", "m³", brick_m3, "Wall volume less openings"),
            item("MA-02", "Masonry", "Bricks", "nr", bricks, "Brickwork × bricks per m³ + waste"),
            item("CO-01", "Concrete", "RCC floor slab", "m³", slab_m3, "(Floor + wall footprint) × slab thickness"),
            item("CO-02", "Concrete", "RCC columns", "m³", column_m3, "Detected column sections × wall height"),
            item("CO-03", "Concrete", "RCC lintels", "m³", lintel_m3, "Opening span + bearing × wall × depth"),
            item("CO-04", "Concrete", "Total concrete", "m³", concrete_m3, "Slab + columns + lintels"),
            item("ST-01", "Steel", "Reinforcement steel", "kg", steel_kg, "Concrete volumes × steel ratios"),
            item(
                "PA-01",
                "Paint",
                "Interior paint area",
                "m²",
                paint_interior_m2,
                "Wall faces + ceilings − openings − tiled walls",
            ),
            item("PA-02", "Paint", "Exterior paint area", "m²", paint_exterior_m2, "Exterior wall face − openings"),
            item("PA-03", "Paint", "Paint", "L", paint_l, "Painted area × coats ÷ coverage"),
            item("TI-01", "Tiles", "Floor tile area", "m²", tiled_m2, "Bathrooms, kitchens, laundries, balconies"),
            item("TI-02", "Tiles", "Wall tile area", "m²", wall_tile_m2, "Bathroom perimeters × tile height"),
            item("TI-03", "Tiles", "Floor tiles", "nr", floor_tiles, "Area ÷ tile size + waste"),
            item("TI-04", "Tiles", "Wall tiles", "nr", wall_tiles, "Area ÷ tile size + waste"),
            item("FL-01", "Floor", "Other flooring", "m²", floor_m2 - tiled_m2, "Floor area − tiled floors"),
        ],
    )


def quantity(takeoff: Takeoff, code: str) -> float:
    return next(i.quantity for i in takeoff.items if i.code == code)

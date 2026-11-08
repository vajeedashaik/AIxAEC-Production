"""Interior designer: deterministic furniture placement, lighting and theme finishes."""

from dataclasses import dataclass
from math import ceil
from uuid import NAMESPACE_URL, uuid5

from aec_contracts import BBox, RoomType
from aec_contracts.analysis import (
    FurniturePlacement,
    InteriorPlan,
    InteriorTheme,
    RoomFinish,
    RoomLighting,
    ThemeSwatch,
)
from shapely.geometry import Polygon, box

from .measure import Plan, RoomInfo

WALL_CLEARANCE_MM = 50.0
WALKWAY_MM = 300.0
STEP_MM = 200.0
LUMENS_PER_FIXTURE = 800
UTILISATION = 0.6


@dataclass(frozen=True)
class Item:
    category: str
    width_mm: float
    depth_mm: float
    centre: bool = False  # stands in the middle of the room instead of against a wall
    gap_mm: float = WALKWAY_MM
    tall: bool = False  # must not stand in front of a window


CATALOG: dict[RoomType, tuple[Item, ...]] = {
    RoomType.MASTER_BEDROOM: (
        Item("King bed", 1800, 2000),
        Item("Nightstand", 500, 400, gap_mm=0),
        Item("Wardrobe", 1800, 600, tall=True),
    ),
    RoomType.BEDROOM: (
        Item("Queen bed", 1500, 2000),
        Item("Nightstand", 500, 400, gap_mm=0),
        Item("Wardrobe", 1200, 600, tall=True),
    ),
    RoomType.LIVING_ROOM: (
        Item("Sofa", 2200, 900),
        Item("TV unit", 1800, 400),
        Item("Coffee table", 1200, 600, centre=True),
    ),
    RoomType.DINING_ROOM: (Item("Dining table", 1600, 900, centre=True), Item("Sideboard", 1400, 450)),
    RoomType.KITCHEN: (Item("Counter", 2400, 600), Item("Fridge", 700, 700, tall=True)),
    RoomType.BATHROOM: (Item("Shower", 900, 900), Item("Toilet", 400, 700), Item("Basin", 600, 500)),
    RoomType.OFFICE: (Item("Desk", 1400, 700), Item("Bookshelf", 1000, 350, tall=True)),
    RoomType.LAUNDRY: (Item("Washer", 600, 600), Item("Dryer", 600, 600, gap_mm=0)),
    RoomType.GARAGE: (Item("Car bay", 2500, 5000, centre=True),),
    RoomType.BALCONY: (Item("Outdoor seat", 1200, 600),),
}
# type: (lux, fixture, colour temperature K)
LIGHTING: dict[RoomType, tuple[int, str, int]] = {
    RoomType.LIVING_ROOM: (150, "Dimmable downlights and a floor lamp", 2700),
    RoomType.DINING_ROOM: (200, "Pendant over the table", 2700),
    RoomType.BEDROOM: (100, "Ceiling light and bedside lamps", 2700),
    RoomType.MASTER_BEDROOM: (100, "Ceiling light and bedside lamps", 2700),
    RoomType.KITCHEN: (300, "Downlights and under-cabinet strips", 4000),
    RoomType.BATHROOM: (200, "Moisture-rated downlights and a mirror light", 4000),
    RoomType.OFFICE: (500, "Even ceiling panels and a task lamp", 4000),
    RoomType.HALLWAY: (100, "Low-glare downlights", 3000),
    RoomType.GARAGE: (100, "Linear battens", 4000),
    RoomType.LAUNDRY: (200, "Linear battens", 4000),
}
DEFAULT_LIGHTING = (100, "Ceiling light", 3000)

_ZONES: dict[RoomType, str] = {
    RoomType.BATHROOM: "wet",
    RoomType.LAUNDRY: "wet",
    RoomType.KITCHEN: "kitchen",
    RoomType.BEDROOM: "bed",
    RoomType.MASTER_BEDROOM: "bed",
    RoomType.LIVING_ROOM: "living",
    RoomType.DINING_ROOM: "living",
    RoomType.OFFICE: "living",
    RoomType.HALLWAY: "living",
}
_THEMES: tuple[dict[str, object], ...] = (
    {
        "name": "Modern",
        "summary": "Clean lines, neutral walls and one strong contrast.",
        "palette": [("Warm white", "#F2F0EB"), ("Graphite", "#3A3D42"), ("Oak", "#B48A5E")],
        "materials": ["Large-format porcelain", "Matte lacquer", "Black steel"],
        "lighting": "Recessed 3000 K with hidden linear strips",
        "finishes": {
            "living": "Oak-look plank floor, matte white walls",
            "bed": "Oak floor, graphite feature wall",
            "kitchen": "Handleless graphite cabinets, quartz counter",
            "wet": "Large grey porcelain, black fittings",
        },
    },
    {
        "name": "Minimalist",
        "summary": "Very little on show, soft tones and hidden storage.",
        "palette": [("Chalk", "#F5F4F0"), ("Stone", "#D8D4CC"), ("Ash", "#9A958C")],
        "materials": ["Microcement", "Pale ash veneer", "Linen"],
        "lighting": "Soft indirect 2700 K, no visible fittings",
        "finishes": {
            "living": "Pale microcement floor, flush storage",
            "bed": "Pale ash floor, full-height wardrobes",
            "kitchen": "Flat ash fronts, stone counter",
            "wet": "Microcement walls, frameless glass",
        },
    },
    {
        "name": "Industrial",
        "summary": "Raw materials, exposed services and dark metal.",
        "palette": [("Concrete", "#8C8C88"), ("Brick", "#8A4B38"), ("Iron", "#2B2B2B")],
        "materials": ["Polished concrete", "Exposed brick", "Blackened steel"],
        "lighting": "Track lights and caged pendants at 3000 K",
        "finishes": {
            "living": "Polished concrete, one exposed brick wall",
            "bed": "Dark timber floor, concrete-look wall",
            "kitchen": "Steel counter, open shelving",
            "wet": "Metro tile, black pipework",
        },
    },
    {
        "name": "Luxury",
        "summary": "Rich materials, layered light and fine detail.",
        "palette": [("Ivory", "#EFE7D8"), ("Emerald", "#1F4D40"), ("Brass", "#B08D57")],
        "materials": ["Marble", "Walnut", "Brushed brass"],
        "lighting": "Chandelier and dimmable layered 2700 K",
        "finishes": {
            "living": "Herringbone walnut, marble fireplace wall",
            "bed": "Walnut floor, upholstered headboard wall",
            "kitchen": "Marble counter, brass hardware",
            "wet": "Book-matched marble, brass fittings",
        },
    },
    {
        "name": "Scandinavian",
        "summary": "Light timber, soft white and natural textures.",
        "palette": [("Snow", "#F7F6F2"), ("Birch", "#D9C4A0"), ("Fjord", "#6E8894")],
        "materials": ["Birch", "Wool", "Painted panelling"],
        "lighting": "Warm 2700 K pendants, daylight kept open",
        "finishes": {
            "living": "Birch floor, white walls, wool textiles",
            "bed": "Birch floor, soft blue accent wall",
            "kitchen": "White fronts, birch counter",
            "wet": "Matte white tile, birch vanity",
        },
    },
)


def _place(
    room: RoomInfo,
    usable: Polygon,
    item: Item,
    placed: list[Polygon],
    blocked: list[Polygon],
    windows: list[Polygon],
    mm: float,
) -> Polygon | None:
    min_x, min_y, max_x, max_y = usable.bounds
    w, d = item.width_mm / mm, item.depth_mm / mm
    gap, step = item.gap_mm / mm, STEP_MM / mm

    def free(candidate: Polygon) -> bool:
        grown = candidate.buffer(gap) if gap else candidate
        return (
            bool(usable.contains(candidate))
            and not any(grown.intersects(p) for p in placed)
            and not any(candidate.intersects(b) for b in blocked)
            and not (item.tall and any(candidate.intersects(w) for w in windows))
        )

    if item.centre:
        cx, cy = room.polygon.centroid.x, room.polygon.centroid.y
        for cw, cd in ((w, d), (d, w)):
            candidate = box(cx - cw / 2, cy - cd / 2, cx + cw / 2, cy + cd / 2)
            if free(candidate):
                return candidate
        return None

    span_x, span_y = max_x - min_x, max_y - min_y
    sides = [("top", span_x), ("bottom", span_x), ("left", span_y), ("right", span_y)]
    for side, length in sorted(sides, key=lambda s: -s[1]):  # stable sort: longest wall first, ties in fixed order
        along = w
        if along > length:
            continue
        count = int((length - along) / step) + 1
        slots = sorted(range(count), key=lambda i: abs(i - (count - 1) / 2))  # centred first
        for slot in slots:
            offset = slot * step + ((length - along) - (count - 1) * step) / 2
            if side in ("top", "bottom"):
                x, y = min_x + offset, min_y if side == "top" else max_y - d
                candidate = box(x, y, x + w, y + d)
            else:
                x, y = min_x if side == "left" else max_x - d, min_y + offset
                candidate = box(x, y, x + d, y + w)
            if free(candidate):
                return candidate
    return None


def build_interior(plan: Plan) -> InteriorPlan:
    mm = plan.mm
    furniture: list[FurniturePlacement] = []
    notes: list[str] = []
    for room in plan.rooms:
        items = CATALOG.get(room.room.room_type, ())
        if not items:
            continue
        usable = room.polygon.buffer(-WALL_CLEARANCE_MM / mm)
        if not isinstance(usable, Polygon) or usable.is_empty:
            continue
        windows = []
        for window in plan.openings_in(room.room.id):
            half = window.width_mm / mm / 2
            windows.append(
                box(window.centre[0] - half, window.centre[1] - half, window.centre[0] + half, window.centre[1] + half)
            )
        blocked = []
        for door in plan.openings_in(room.room.id, "door"):
            half = door.width_mm / mm / 2 + WALKWAY_MM / mm  # keep the swing and the approach clear
            blocked.append(
                box(door.centre[0] - half, door.centre[1] - half, door.centre[0] + half, door.centre[1] + half)
            )
        placed: list[Polygon] = []
        for item in items:
            spot = _place(room, usable, item, placed, blocked, windows, mm)
            if spot is None:
                notes.append(f"{item.category} doesn't fit in {room.name} with clearances kept.")
                continue
            placed.append(spot)
            x0, y0, x1, y1 = spot.bounds
            furniture.append(
                FurniturePlacement(
                    id=uuid5(NAMESPACE_URL, f"{room.room.id}/{item.category}"),
                    category=item.category,
                    bbox=BBox(x=round(x0, 2), y=round(y0, 2), width=round(x1 - x0, 2), height=round(y1 - y0, 2)),
                )
            )

    lighting = []
    for room in plan.rooms:
        lux, fixture, kelvin = LIGHTING.get(room.room.room_type, DEFAULT_LIGHTING)
        lumens = round(lux * room.area_m2 / UTILISATION)
        windows = [w for w in plan.openings_in(room.room.id) if w.exterior]
        lighting.append(
            RoomLighting(
                room_id=room.room.id,
                room=room.name,
                target_lux=lux,
                lumens=lumens,
                fixtures=max(1, ceil(lumens / LUMENS_PER_FIXTURE)),
                fixture=fixture,
                colour_temperature_k=kelvin,
                daylight=f"{len(windows)} exterior window{'' if len(windows) == 1 else 's'}"
                if windows
                else "No daylight: consider a lightwell or borrowed light",
            )
        )

    themes = []
    for theme in _THEMES:
        finishes: dict[str, str] = theme["finishes"]  # type: ignore[assignment]
        themes.append(
            InteriorTheme.model_validate(
                {
                    "name": theme["name"],
                    "summary": theme["summary"],
                    "lighting": theme["lighting"],
                    "materials": theme["materials"],
                    "palette": [ThemeSwatch(name=n, hex=h) for n, h in theme["palette"]],  # type: ignore[attr-defined]
                    "room_finishes": [
                        RoomFinish(room=r.name, finish=finishes[_ZONES[r.room.room_type]])
                        for r in plan.rooms
                        if r.room.room_type in _ZONES
                    ],
                }
            )
        )
    return InteriorPlan(furniture=furniture, lighting=lighting, themes=themes, notes=notes)

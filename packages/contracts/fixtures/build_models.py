"""Writes apartment.model.json, apartment.unscaled.model.json and two_room.model.json.

The layout is hand-designed on a grid (px, 1 px = 10 mm). Walls are split at every junction so each
room edge is exactly one wall. Ids are deterministic UUID v4s. Run: `uv run python fixtures/build_models.py`.

Apartment (centre-lines):
    x: 100 ─ 600 ─ 960 ─ 1300      y: 100 ─ 550 ─ 700 ─ 900
    ┌─────────┬───────┬───────┐ 100
    │ LIVING  │KITCHEN│BEDROOM│
    ├─────────┴───────┴───────┤ 550
    │ HALL                    │
    └─────────────────┬───────┤ 700
                      │ BATH  │
                      └───────┘ 900
"""

import json
import random
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
EXT, INT = 20.0, 10.0  # wall thickness px


class Ids:
    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)

    def __call__(self) -> str:
        return str(uuid.UUID(int=self._rng.getrandbits(128), version=4))


def pt(x: float, y: float) -> dict[str, float]:
    return {"x": x, "y": y}


def wall(ids: Ids, a: tuple[float, float], b: tuple[float, float], t: float) -> dict[str, Any]:
    return {"id": ids(), "confidence": 0.97, "source": "DETECTED", "start": pt(*a), "end": pt(*b),
            "thickness_px": t}


def on_wall(w: dict[str, Any], centre: float, width: float) -> dict[str, float]:
    """BBox of an opening of `width` centred at `centre` along an axis-aligned wall."""
    s, e, t = w["start"], w["end"], w["thickness_px"]
    if s["y"] == e["y"]:
        return {"x": centre - width / 2, "y": s["y"] - t / 2, "width": width, "height": t}
    return {"x": s["x"] - t / 2, "y": centre - width / 2, "width": t, "height": width}


def room(ids: Ids, poly: list[tuple[float, float]], walls: list[dict[str, Any]], label: str, rtype: str,
         area: float) -> dict[str, Any]:
    return {"id": ids(), "confidence": 0.93, "source": "DETECTED", "polygon": [pt(*p) for p in poly],
            "wall_ids": [w["id"] for w in walls], "label_text": label, "room_type": rtype,
            "room_type_source": "INFERRED", "room_type_confidence": 0.95, "area_px": area}


def apartment(scaled: bool) -> dict[str, Any]:
    ids = Ids(1001)
    w = {
        # exterior, clockwise from the north-west corner
        "n_living": wall(ids, (100, 100), (600, 100), EXT),
        "n_kitchen": wall(ids, (600, 100), (960, 100), EXT),
        "n_bed": wall(ids, (960, 100), (1300, 100), EXT),
        "e_bed": wall(ids, (1300, 100), (1300, 550), EXT),
        "e_hall": wall(ids, (1300, 550), (1300, 700), EXT),
        "e_bath": wall(ids, (1300, 700), (1300, 900), EXT),
        "s_bath": wall(ids, (1300, 900), (960, 900), EXT),
        "w_bath": wall(ids, (960, 900), (960, 700), EXT),
        "s_hall": wall(ids, (960, 700), (100, 700), EXT),
        "w_hall": wall(ids, (100, 700), (100, 550), EXT),
        "w_living": wall(ids, (100, 550), (100, 100), EXT),
        # interior
        "living_kitchen": wall(ids, (600, 100), (600, 550), INT),
        "kitchen_bed": wall(ids, (960, 100), (960, 550), INT),
        "living_hall": wall(ids, (100, 550), (600, 550), INT),
        "kitchen_hall": wall(ids, (600, 550), (960, 550), INT),
        "bed_hall": wall(ids, (960, 550), (1300, 550), INT),
        "hall_bath": wall(ids, (960, 700), (1300, 700), INT),
    }
    rooms = [
        room(ids, [(100, 100), (600, 100), (600, 550), (100, 550)],
             [w["n_living"], w["living_kitchen"], w["living_hall"], w["w_living"]], "LIVING", "LIVING_ROOM",
             500 * 450),
        room(ids, [(600, 100), (960, 100), (960, 550), (600, 550)],
             [w["n_kitchen"], w["kitchen_bed"], w["kitchen_hall"], w["living_kitchen"]], "KITCHEN", "KITCHEN",
             360 * 450),
        room(ids, [(960, 100), (1300, 100), (1300, 550), (960, 550)],
             [w["n_bed"], w["e_bed"], w["bed_hall"], w["kitchen_bed"]], "BEDROOM", "BEDROOM", 340 * 450),
        room(ids, [(100, 550), (600, 550), (960, 550), (1300, 550), (1300, 700), (960, 700), (100, 700)],
             [w["living_hall"], w["kitchen_hall"], w["bed_hall"], w["e_hall"], w["hall_bath"], w["s_hall"],
              w["w_hall"]], "HALL", "HALLWAY", 1200 * 150),
        room(ids, [(960, 700), (1300, 700), (1300, 900), (960, 900)],
             [w["hall_bath"], w["e_bath"], w["s_bath"], w["w_bath"]], "BATH", "BATHROOM", 340 * 200),
    ]

    def door(host: str, centre: float, width: float, swing: str) -> dict[str, Any]:
        return {"id": ids(), "confidence": 0.9, "source": "DETECTED", "bbox": on_wall(w[host], centre, width),
                "wall_id": w[host]["id"], "width_px": width, "swing": swing}

    def window(host: str, centre: float, width: float) -> dict[str, Any]:
        return {"id": ids(), "confidence": 0.88, "source": "DETECTED", "bbox": on_wall(w[host], centre, width),
                "wall_id": w[host]["id"], "width_px": width}

    doors = [
        door("w_hall", 625, 90, "RIGHT"),       # entrance
        door("living_hall", 350, 90, "LEFT"),
        door("bed_hall", 1130, 90, "RIGHT"),
        door("hall_bath", 1130, 70, "LEFT"),
    ]
    windows = [window("n_living", 350, 150), window("n_kitchen", 780, 120), window("e_bed", 325, 150)]
    dims = [
        {"text": "12000", "value_mm": 12000.0, "span_px": 1200.0, "position": pt(700, 50)},
        {"text": "4500", "value_mm": 4500.0, "span_px": 450.0, "position": pt(50, 325)},
        {"text": "3600", "value_mm": 3600.0, "span_px": 360.0, "position": pt(780, 70)},
    ]
    model: dict[str, Any] = {
        "schema_version": 1,
        "id": ids(),
        "floorplan_id": ids(),
        "coordinate_system": {
            "image_width": 1600, "image_height": 1200,
            "mm_per_pixel": 10.0 if scaled else None,
            "calibration_source": "DIMENSION_OCR" if scaled else "UNKNOWN",
            "calibration_confidence": 0.9 if scaled else None,
        },
        "walls": list(w.values()),
        "doors": doors,
        "windows": windows,
        "columns": [{"id": ids(), "confidence": 0.8, "source": "DETECTED",
                     "bbox": {"x": 588, "y": 538, "width": 24, "height": 24}}],
        "stairs": [{"id": ids(), "confidence": 0.85, "source": "DETECTED",
                    "bbox": {"x": 650, "y": 565, "width": 200, "height": 120},
                    "polygon": [pt(650, 565), pt(850, 565), pt(850, 685), pt(650, 685)]}],
        "furniture": [],
        "dimensions": [{"id": ids(), "confidence": 0.9, "source": "DETECTED", **d} for d in dims],
        "rooms": rooms,
    }
    return model


def two_room() -> dict[str, Any]:
    ids = Ids(2002)
    w = {
        "n_a": wall(ids, (100, 100), (500, 100), EXT),
        "n_b": wall(ids, (500, 100), (900, 100), EXT),
        "e_b": wall(ids, (900, 100), (900, 500), EXT),
        "s_b": wall(ids, (900, 500), (500, 500), EXT),
        "s_a": wall(ids, (500, 500), (100, 500), EXT),
        "w_a": wall(ids, (100, 500), (100, 100), EXT),
        "shared": wall(ids, (500, 100), (500, 500), INT),
    }
    rooms = [
        room(ids, [(100, 100), (500, 100), (500, 500), (100, 500)], [w["n_a"], w["shared"], w["s_a"], w["w_a"]],
             "BEDROOM", "BEDROOM", 400 * 400),
        room(ids, [(500, 100), (900, 100), (900, 500), (500, 500)], [w["n_b"], w["e_b"], w["s_b"], w["shared"]],
             "OFFICE", "OFFICE", 400 * 400),
    ]
    return {
        "schema_version": 1, "id": ids(), "floorplan_id": ids(),
        "coordinate_system": {"image_width": 1000, "image_height": 600, "mm_per_pixel": 10.0,
                              "calibration_source": "MANUAL", "calibration_confidence": 1.0},
        "walls": list(w.values()), "doors": [], "windows": [], "columns": [], "stairs": [], "furniture": [],
        "dimensions": [], "rooms": rooms,
    }


if __name__ == "__main__":
    for name, data in [("apartment.model.json", apartment(True)), ("apartment.unscaled.model.json", apartment(False)),
                       ("two_room.model.json", two_room())]:
        (HERE / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print("wrote", name)

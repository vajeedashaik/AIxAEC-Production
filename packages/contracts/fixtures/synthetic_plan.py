"""Deterministic synthetic floor-plan PNGs for vision tests (NumPy + OpenCV).

Each image is drawn from the matching fixture model, so the expected answer is the JSON next to it:
    make_apartment_plan() ↔ apartment.model.json      make_two_room_plan() ↔ two_room.model.json

Features: solid walls (exterior 20 px, interior 10 px), door gaps with leaf + quarter-circle swing,
windows as double thin lines, a stair with 8 parallel treads, room-label text, one dimension string
("3600", along the kitchen's north wall) and hatching in the bathroom. Fixed seeds; identical bytes per run.

CLI: `uv run python fixtures/synthetic_plan.py <out_dir>` writes apartment.png and two_room.png.
"""

import json
import math
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

HERE = Path(__file__).parent
INK = 0
PAPER = 255
Image = NDArray[np.uint8]


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((HERE / name).read_text(encoding="utf-8"))
    return data


def _p(d: dict[str, float]) -> tuple[int, int]:
    return round(d["x"]), round(d["y"])


def _draw_walls(img: Image, model: dict[str, Any]) -> None:
    for w in model["walls"]:
        (x1, y1), (x2, y2), h = _p(w["start"]), _p(w["end"]), round(w["thickness_px"] / 2)
        # Square caps: extend each rectangle by half the thickness so corners close.
        cv2.rectangle(img, (min(x1, x2) - h, min(y1, y2) - h), (max(x1, x2) + h, max(y1, y2) + h), INK, -1)


def _bbox(b: dict[str, float]) -> tuple[int, int, int, int]:
    return round(b["x"]), round(b["y"]), round(b["x"] + b["width"]), round(b["y"] + b["height"])


def _draw_door(img: Image, door: dict[str, Any]) -> None:
    x1, y1, x2, y2 = _bbox(door["bbox"])
    cv2.rectangle(img, (x1, y1), (x2, y2), PAPER, -1)  # gap in the wall
    horizontal = (x2 - x1) > (y2 - y1)
    width = (x2 - x1) if horizontal else (y2 - y1)
    if horizontal:
        hinge = (x1, y2) if door["swing"] != "RIGHT" else (x2, y2)
        leaf_end = (hinge[0], hinge[1] + width)
        start = 0 if door["swing"] != "RIGHT" else 90
    else:
        hinge = (x2, y1) if door["swing"] != "RIGHT" else (x2, y2)
        leaf_end = (hinge[0] + width, hinge[1])
        start = 0 if door["swing"] != "RIGHT" else 270
    cv2.line(img, hinge, leaf_end, INK, 2, cv2.LINE_AA)
    cv2.ellipse(img, hinge, (width, width), 0, start, start + 90, INK, 1, cv2.LINE_AA)


def _draw_window(img: Image, win: dict[str, Any]) -> None:
    x1, y1, x2, y2 = _bbox(win["bbox"])
    cv2.rectangle(img, (x1, y1), (x2, y2), PAPER, -1)
    cv2.rectangle(img, (x1, y1), (x2, y2), INK, 1)  # jambs
    if (x2 - x1) > (y2 - y1):
        for y in (y1 + (y2 - y1) // 3, y1 + 2 * (y2 - y1) // 3):
            cv2.line(img, (x1, y), (x2, y), INK, 1)
    else:
        for x in (x1 + (x2 - x1) // 3, x1 + 2 * (x2 - x1) // 3):
            cv2.line(img, (x, y1), (x, y2), INK, 1)


def _draw_stair(img: Image, stair: dict[str, Any]) -> None:
    x1, y1, x2, y2 = _bbox(stair["bbox"])
    cv2.rectangle(img, (x1, y1), (x2, y2), INK, 2)
    for i in range(1, 9):  # 8 treads
        x = x1 + i * (x2 - x1) // 9
        cv2.line(img, (x, y1), (x, y2), INK, 1)
    cv2.arrowedLine(img, (x1 + 10, (y1 + y2) // 2), (x2 - 10, (y1 + y2) // 2), INK, 1, tipLength=0.05)


def _draw_hatch(img: Image, room: dict[str, Any], spacing: int = 14) -> None:
    pts = np.array([_p(p) for p in room["polygon"]], dtype=np.int32)
    mask = np.zeros_like(img)
    cv2.fillPoly(mask, [pts], 255)
    mask = cv2.erode(mask, np.ones((25, 25), np.uint8))  # keep hatching clear of the walls
    layer = np.full_like(img, PAPER)
    h, w = img.shape
    for c in range(-h, w, spacing):
        cv2.line(layer, (c, 0), (c + h, h), INK, 1)
    img[(mask > 0) & (layer == INK)] = INK


def _label(img: Image, text: str, centre: tuple[int, int], scale: float = 0.9) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(text, font, scale, 2)
    cv2.putText(img, text, (centre[0] - tw // 2, centre[1] + th // 2), font, scale, INK, 2, cv2.LINE_AA)


def _centroid(poly: list[dict[str, float]]) -> tuple[int, int]:
    return round(sum(p["x"] for p in poly) / len(poly)), round(sum(p["y"] for p in poly) / len(poly))


def _dimension(img: Image, a: tuple[int, int], b: tuple[int, int], text: str) -> None:
    """Horizontal dimension line with ticks, text centred above."""
    cv2.line(img, a, b, INK, 1)
    for x, y in (a, b):
        cv2.line(img, (x - 6, y + 6), (x + 6, y - 6), INK, 1)
        cv2.line(img, (x, y - 10), (x, y + 10), INK, 1)
    _label(img, text, ((a[0] + b[0]) // 2, a[1] - 14), 0.6)


def _noise(img: Image, seed: int) -> None:
    rng = np.random.default_rng(seed)
    n = img.size // 2000
    ys, xs = rng.integers(0, img.shape[0], n), rng.integers(0, img.shape[1], n)
    img[ys, xs] = rng.choice(np.array([INK, 200], dtype=np.uint8), n)


def _render(model: dict[str, Any], seed: int, extras: bool) -> Image:
    cs = model["coordinate_system"]
    img = np.full((cs["image_height"], cs["image_width"]), PAPER, dtype=np.uint8)
    _draw_walls(img, model)
    for d in model["doors"]:
        _draw_door(img, d)
    for win in model["windows"]:
        _draw_window(img, win)
    for s in model["stairs"]:
        _draw_stair(img, s)
    for r in model["rooms"]:
        if extras and r["room_type"] == "BATHROOM":
            _draw_hatch(img, r)
        cx, cy = _centroid(r["polygon"])
        _label(img, r["label_text"], (cx - 240, cy + 10) if r["room_type"] == "HALLWAY" else (cx, cy))
    if extras:
        _dimension(img, (600, 50), (960, 50), "3600")
    _noise(img, seed)
    assert math.isfinite(float(img.mean()))
    return img


def make_apartment_plan() -> Image:
    """≈1600×1200 grayscale apartment matching apartment.model.json."""
    return _render(_load("apartment.model.json"), seed=7, extras=True)


def make_two_room_plan() -> Image:
    """1000×600 grayscale plan matching two_room.model.json."""
    return _render(_load("two_room.model.json"), seed=11, extras=False)


def to_png(img: Image) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return bytes(buf.tobytes())


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    (out / "apartment.png").write_bytes(to_png(make_apartment_plan()))
    (out / "two_room.png").write_bytes(to_png(make_two_room_plan()))
    print("wrote", out / "apartment.png", out / "two_room.png")

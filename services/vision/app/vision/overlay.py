"""Debug artifacts: the model drawn over the plan, and PNG encoding that stays under the size budget."""

import cv2
import numpy as np
from aec_contracts import FloorPlanModel

MAX_PNG_BYTES = 2 * 1024 * 1024

WALL = (0, 0, 220)
DOOR = (0, 160, 0)
WINDOW = (220, 120, 0)
ROOM = (200, 0, 200)
OBJECT = (0, 160, 220)


def encode_png(img: np.ndarray) -> bytes:
    """Scans don't compress: posterise first, then halve, rather than ship a huge artifact."""
    for attempt in range(4):
        ok, buf = cv2.imencode(".png", img, [cv2.IMWRITE_PNG_COMPRESSION, 9])
        if not ok:
            raise ValueError("PNG encoding failed")
        if buf.size <= MAX_PNG_BYTES:
            break
        if attempt == 0:
            img = np.bitwise_and(img, 0xF0)
        else:
            img = cv2.resize(img, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    return bytes(buf.tobytes())


def render_overlay(gray: np.ndarray, model: FloorPlanModel) -> np.ndarray:
    canvas = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    for room in model.rooms:
        pts = np.array([(round(p.x), round(p.y)) for p in room.polygon], np.int32)
        cv2.polylines(canvas, [pts], True, ROOM, 2)
    for wall in model.walls:
        cv2.line(canvas, (round(wall.start.x), round(wall.start.y)), (round(wall.end.x), round(wall.end.y)), WALL, 3)
    for color, elements in (
        (DOOR, model.doors),
        (WINDOW, model.windows),
        (OBJECT, model.columns),
        (OBJECT, model.stairs),
        (OBJECT, model.furniture),
    ):
        for el in elements:
            b = el.bbox
            cv2.rectangle(canvas, (round(b.x), round(b.y)), (round(b.x + b.width), round(b.y + b.height)), color, 2)
    return canvas

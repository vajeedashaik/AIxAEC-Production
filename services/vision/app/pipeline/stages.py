"""The 8 stages. Each one reads and fills a shared context and returns its report detail."""

import base64
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Literal
from uuid import UUID

from aec_contracts import AnalyzeOptions, ArtifactPayload, FloorPlanModel

from app.config import Settings
from app.ocr.base import OcrWord
from app.ocr.factory import get_ocr
from app.vision.assemble import build_model
from app.vision.calibrate import Calibration, estimate_scale
from app.vision.decode import decode_image
from app.vision.objects import Detections, get_detector, reconcile_openings
from app.vision.overlay import encode_png, render_overlay
from app.vision.preprocess import Preprocessed, preprocess
from app.vision.rooms import DetectedRoom, detect_rooms
from app.vision.strokes import text_layer
from app.vision.walls import Opening, WallDetection, detect_walls

Detail = dict[str, int | float | str | bool | None]


class StageDegraded(Exception):
    """The stage produced a usable (possibly empty) result, but the user should know it is thin."""

    def __init__(self, message: str, detail: Detail | None = None) -> None:
        super().__init__(message)
        self.message, self.detail = message, detail or {}


@dataclass
class Context:
    data: bytes
    content_type: str | None
    floorplan_id: UUID
    options: AnalyzeOptions
    settings: Settings
    warnings: list[str] = field(default_factory=list)
    pre: Preprocessed | None = None
    detection: WallDetection | None = None
    openings: list[Opening] = field(default_factory=list)
    words: list[OcrWord] = field(default_factory=list)
    objects: Detections = field(default_factory=Detections)
    rooms: list[DetectedRoom] = field(default_factory=list)
    calibration: Calibration = field(default_factory=Calibration)
    model: FloorPlanModel | None = None
    artifacts: list[ArtifactPayload] = field(default_factory=list)


def _pre(ctx: Context) -> Preprocessed:
    assert ctx.pre is not None  # preprocess is critical: later stages don't run without it
    return ctx.pre


def _detection(ctx: Context) -> WallDetection:
    assert ctx.detection is not None  # wall_detection is critical too
    return ctx.detection


def run_preprocess(ctx: Context) -> Detail:
    max_dimension = min(ctx.settings.image_max_dimension, ctx.options.max_dimension)
    decoded = decode_image(
        ctx.data, ctx.content_type, max_dimension=max_dimension, max_pixels=ctx.settings.max_image_pixels
    )
    if decoded.page_count > 1:
        ctx.warnings.append(f"Only page 1 of {decoded.page_count} was processed.")
    ctx.pre = preprocess(decoded.image, max_dimension)
    width, height = ctx.pre.size
    return {"width": width, "height": height, "pages": decoded.page_count, "deskew_deg": ctx.pre.deskew_deg}


def run_wall_detection(ctx: Context) -> Detail:
    pre = _pre(ctx)
    result = detect_walls(pre.binary, pre.fine)
    ctx.detection = result
    ctx.openings = list(result.openings)
    detail: Detail = {
        "walls": len(result.walls),
        "gap_openings": len(result.openings),
        "thickness_px": result.thickness,
    }
    if not result.walls:
        ctx.warnings.append("No walls were detected. Thin double-line, curved or noisy drawings are not supported.")
        raise StageDegraded("No walls were detected.", detail)
    return detail


def run_ocr(ctx: Context) -> Detail:
    ocr = get_ocr(ctx.settings.ocr_provider, ctx.settings.tesseract_cmd)
    pre, detection = _pre(ctx), _detection(ctx)
    image = pre.gray
    if detection.thickness is not None:
        image = text_layer(pre.gray, pre.fine, detection.mask, detection.thickness)
    ctx.words = ocr.recognize(image)
    if ocr.name == "stub":
        ctx.warnings.append("OCR is unavailable, so room labels and the drawing scale could not be read.")
    return {"provider": ocr.name, "words": len(ctx.words)}


def run_object_detection(ctx: Context) -> Detail:
    pre = _pre(ctx)
    detector = get_detector(ctx.settings.object_detector, ctx.settings.yolo_weights_path)
    detection = _detection(ctx)
    ctx.objects = detector.detect(pre.gray, pre.fine, detection)
    ctx.openings = reconcile_openings(ctx.objects.swings, detection.openings, detection.walls)
    return {
        "swings": len(ctx.objects.swings),
        "columns": len(ctx.objects.columns),
        "stairs": len(ctx.objects.stairs),
        "furniture": len(ctx.objects.furniture),
        "openings": len(ctx.openings),
    }


def run_room_detection(ctx: Context) -> Detail:
    walls = _detection(ctx).walls
    ctx.rooms = detect_rooms(walls, _pre(ctx).size, ctx.words)
    detail: Detail = {"rooms": len(ctx.rooms), "labelled": sum(r.label is not None for r in ctx.rooms)}
    if walls and not ctx.rooms:
        ctx.warnings.append("No enclosed rooms were found. The walls may not form closed outlines.")
        raise StageDegraded("No enclosed rooms were found.", detail)
    return detail


def run_calibration(ctx: Context) -> Detail:
    ctx.calibration = estimate_scale(ctx.words, _detection(ctx).walls)
    return {
        "mm_per_pixel": ctx.calibration.mm_per_pixel,
        "source": str(ctx.calibration.source),
        "dimensions": len(ctx.calibration.dimensions),
    }


def run_semantic_assembly(ctx: Context) -> Detail:
    ctx.model = build_model(
        ctx.floorplan_id, _pre(ctx).size, _detection(ctx).walls, ctx.openings, ctx.objects, ctx.rooms, ctx.calibration
    )
    return dict(ctx.model.summary().model_dump())


def _artifact(
    kind: Literal["preprocessed", "walls_overlay", "detected_elements", "semantic_model"],
    content_type: Literal["image/png", "application/json"],
    data: bytes,
) -> ArtifactPayload:
    return ArtifactPayload(kind=kind, content_type=content_type, data_base64=base64.b64encode(data).decode("ascii"))


def run_artifacts(ctx: Context) -> Detail:
    pre = _pre(ctx)
    assert ctx.model is not None  # semantic_assembly is critical
    detection = _detection(ctx)
    raw = {
        "thickness_px": detection.thickness,
        "walls": [asdict(w) for w in detection.walls],
        "openings": [asdict(o) for o in ctx.openings],
        "swings": [asdict(s) for s in ctx.objects.swings],
        "columns": [asdict(c) for c in ctx.objects.columns],
        "stairs": [asdict(s) for s in ctx.objects.stairs],
        "furniture": [asdict(f) for f in ctx.objects.furniture],
        "ocr_words": [asdict(w) for w in ctx.words],
        "rooms": [asdict(r) for r in ctx.rooms],
    }
    ctx.artifacts = [
        _artifact("preprocessed", "image/png", encode_png(pre.gray)),
        _artifact("detected_elements", "application/json", json.dumps(raw, sort_keys=True).encode()),
        _artifact("semantic_model", "application/json", ctx.model.model_dump_json().encode()),
    ]
    # Last and best-effort: everything above is already kept if drawing the overlay fails.
    ctx.artifacts.insert(1, _artifact("walls_overlay", "image/png", encode_png(render_overlay(pre.gray, ctx.model))))
    return {"artifacts": len(ctx.artifacts)}


STAGES: dict[str, Callable[[Context], Detail]] = {
    "preprocess": run_preprocess,
    "wall_detection": run_wall_detection,
    "ocr": run_ocr,
    "object_detection": run_object_detection,
    "room_detection": run_room_detection,
    "calibration": run_calibration,
    "semantic_assembly": run_semantic_assembly,
    "artifacts": run_artifacts,
}

"""Runs the stages with graceful degradation. Callable without HTTP."""

import logging
import time
from collections.abc import Callable
from functools import partial
from typing import Literal, cast
from uuid import UUID

from aec_contracts import AnalyzeOptions, AnalyzeResult, StageReport
from aec_contracts.vision import CRITICAL_STAGES, STAGE_NAMES, StageName

from app.config import Settings, get_settings
from app.errors import ServiceError

from .stages import STAGES, Context, Detail, StageDegraded

log = logging.getLogger("vision.pipeline")
StageStatus = Literal["ok", "degraded", "failed", "skipped"]


def run_stage(name: StageName, fn: Callable[[], Detail]) -> StageReport:
    """Bad input (ServiceError) propagates to the caller; anything else becomes the stage's status."""
    start = time.perf_counter()
    status: StageStatus = "ok"
    error: str | None = None
    detail: Detail = {}
    try:
        detail = fn()
    except ServiceError:
        raise
    except StageDegraded as exc:
        status, error, detail = "degraded", exc.message, exc.detail
    except Exception:
        # Exception text can hold paths and internals: full error to the log, generic text to the client.
        log.exception("stage failed", extra={"fields": {"stage": name}})
        status = "failed" if name in CRITICAL_STAGES else "degraded"
        error = f"Stage '{name}' failed." if status == "failed" else f"Stage '{name}' failed; continuing without it."
    duration_ms = round((time.perf_counter() - start) * 1000)
    log.info("stage", extra={"fields": {"stage": name, "status": status, "duration_ms": duration_ms}})
    return StageReport(name=name, status=status, duration_ms=duration_ms, error=error, detail=detail)


def run_pipeline(
    data: bytes,
    content_type: str | None,
    floorplan_id: UUID,
    options: AnalyzeOptions | None = None,
    settings: Settings | None = None,
) -> AnalyzeResult:
    """Raises ServiceError (415/422) for undecodable input. Every other outcome is an AnalyzeResult."""
    options = options or AnalyzeOptions()
    ctx = Context(data, content_type, floorplan_id, options, settings or get_settings())
    disabled = {"ocr": not options.ocr, "object_detection": not options.object_detection}
    reports: list[StageReport] = []
    failed_at: str | None = None
    for raw_name in STAGE_NAMES:
        name = cast(StageName, raw_name)
        if failed_at is not None or disabled.get(name):
            reports.append(StageReport(name=name, status="skipped", duration_ms=0))
            continue
        report = run_stage(name, partial(STAGES[name], ctx))
        reports.append(report)
        if report.status == "failed":
            failed_at = name
    if failed_at is not None:
        return AnalyzeResult(
            status="FAILED",
            model=None,
            stages=reports,
            warnings=ctx.warnings,
            error=f"Processing failed at stage '{failed_at}'.",
        )
    return AnalyzeResult(
        status="COMPLETED", model=ctx.model, stages=reports, artifacts=ctx.artifacts, warnings=ctx.warnings
    )

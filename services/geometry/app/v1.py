"""Geometry routes (CONTRACTS.md §6). Validated envelope in, deterministic result out."""

import hmac
import logging
from typing import Annotated, Any

from aec_contracts import ErrorCode, ExecuteRequest, ExecuteResult, Insights, ModelRequest, PlanBrief, ValidateResult
from aec_contracts.analysis import Analysis, AnalysisRequest, Answer, LayoutRequest, LayoutSuggestions, QuestionRequest
from fastapi import APIRouter, Depends, Header

from .analysis import build_analysis
from .analysis.layouts import suggest_layouts
from .analysis.qa import answer_question, plan_facts
from .brief import build_brief
from .config import Settings, get_settings
from .engine.constraints import validate_model
from .engine.execute import execute as run_execute
from .errors import ServiceError
from .insights import build_insights

log = logging.getLogger("geometry")


def require_internal_token(
    settings: Annotated[Settings, Depends(get_settings)],
    x_internal_token: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.internal_service_token.get_secret_value()
    if x_internal_token is None or not hmac.compare_digest(x_internal_token.encode(), expected.encode()):
        raise ServiceError(401, ErrorCode.UNAUTHORIZED)


router = APIRouter(prefix="/v1", dependencies=[Depends(require_internal_token)])


@router.post("/commands/execute", response_model=ExecuteResult)
def execute(body: ExecuteRequest) -> ExecuteResult:
    result = run_execute(body.model, body.command, body.dry_run)
    log.info("execute", extra={"fields": {"operation": str(body.command.get("operation"))[:40],
                                          "status": result.status, "dry_run": body.dry_run}})
    return result


@router.post("/models/insights", response_model=Insights)
def insights(body: ModelRequest) -> Insights:
    return build_insights(body.model)


@router.post("/models/brief", response_model=PlanBrief)
def brief(body: ModelRequest) -> PlanBrief:
    return build_brief(body.model)


@router.post("/models/analysis", response_model=Analysis)
def analysis(body: AnalysisRequest) -> Analysis:
    return build_analysis(body.model, body.rates)


@router.post("/models/answer", response_model=Answer)
def answer(body: QuestionRequest) -> Answer:
    return answer_question(body.model, body.question)


@router.post("/models/facts")
def facts(body: ModelRequest) -> dict[str, Any]:
    return plan_facts(body.model)


@router.post("/models/layouts", response_model=LayoutSuggestions)
def layouts(body: LayoutRequest) -> LayoutSuggestions:
    return suggest_layouts(body.model, body.goal)


@router.post("/models/validate", response_model=ValidateResult)
def validate(body: ModelRequest) -> ValidateResult:
    issues = validate_model(body.model)
    return ValidateResult(valid=not issues, issues=issues)

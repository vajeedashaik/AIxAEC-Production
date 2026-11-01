"""Geometry routes (CONTRACTS.md §6). P0 stub: contract wired, returns 501."""

import hmac
from typing import Annotated

from aec_contracts import ErrorCode, ExecuteRequest, ExecuteResult, Insights, ModelRequest, PlanBrief, ValidateResult
from fastapi import APIRouter, Depends, Header

from .config import Settings, get_settings
from .errors import NotImplementedYet, ServiceError


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
    raise NotImplementedYet()


@router.post("/models/insights", response_model=Insights)
def insights(body: ModelRequest) -> Insights:
    raise NotImplementedYet()


@router.post("/models/brief", response_model=PlanBrief)
def brief(body: ModelRequest) -> PlanBrief:
    raise NotImplementedYet()


@router.post("/models/validate", response_model=ValidateResult)
def validate(body: ModelRequest) -> ValidateResult:
    raise NotImplementedYet()

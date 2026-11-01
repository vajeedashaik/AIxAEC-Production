"""Smoke test against a running OmniRoute: uv run pytest -m live (needs LLM_API_KEY and LLM_MODEL set)."""

import pytest
from aec_contracts import COMMAND_ADAPTER, ModelSummary, PlanBrief

from app.config import Settings
from app.llm import LlmClient, LlmParser


@pytest.mark.live
def test_live_gateway_parses_a_command() -> None:
    settings = Settings(environment="test")
    if not (settings.llm_api_key and settings.llm_model):
        pytest.skip("LLM_API_KEY and LLM_MODEL aren't set")
    counts = ModelSummary(walls=0, doors=0, windows=0, columns=0, stairs=0, furniture=0, dimensions=0, rooms=0)
    brief = PlanBrief(rooms=[], counts=counts, has_scale=True, image_width=10, image_height=10)
    result = LlmParser(LlmClient(settings)).parse("tear out the partition between the kitchen and the hall", brief)
    assert result.status == "PARSED", result.detail
    COMMAND_ADAPTER.validate_python(result.command)

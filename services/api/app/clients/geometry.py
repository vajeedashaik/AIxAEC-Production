from typing import Any

from aec_contracts import EXECUTE_RESULT_ADAPTER, ExecuteResult, FloorPlanModel, Insights, PlanBrief
from aec_contracts.analysis import Analysis, Answer, CostRates, LayoutSuggestions

from .base import ServiceClient


def _body(model: FloorPlanModel) -> dict[str, Any]:
    return {"model": model.model_dump(mode="json")}


class GeometryClient(ServiceClient):
    def brief(self, model: FloorPlanModel) -> PlanBrief:
        return self.post("/v1/models/brief", PlanBrief.model_validate, json=_body(model))

    def insights(self, model: FloorPlanModel) -> Insights:
        return self.post("/v1/models/insights", Insights.model_validate, json=_body(model))

    def analysis(self, model: FloorPlanModel, rates: CostRates | None) -> Analysis:
        return self.post("/v1/models/analysis", Analysis.model_validate,
                         json={**_body(model), "rates": rates.model_dump(mode="json") if rates else None})

    def answer(self, model: FloorPlanModel, question: str) -> Answer:
        return self.post("/v1/models/answer", Answer.model_validate, json={**_body(model), "question": question})

    def facts(self, model: FloorPlanModel) -> dict[str, Any]:
        return self.post("/v1/models/facts", dict, json=_body(model))

    def layouts(self, model: FloorPlanModel, goal: str) -> LayoutSuggestions:
        return self.post("/v1/models/layouts", LayoutSuggestions.model_validate, json={**_body(model), "goal": goal})

    def execute(self, model: FloorPlanModel, command: dict[str, Any], dry_run: bool) -> ExecuteResult:
        return self.post("/v1/commands/execute", EXECUTE_RESULT_ADAPTER.validate_python,
                         json={**_body(model), "command": command, "dry_run": dry_run})

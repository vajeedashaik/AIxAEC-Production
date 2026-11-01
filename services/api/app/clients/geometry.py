from typing import Any

from aec_contracts import EXECUTE_RESULT_ADAPTER, ExecuteResult, FloorPlanModel, Insights, PlanBrief

from .base import ServiceClient


def _body(model: FloorPlanModel) -> dict[str, Any]:
    return {"model": model.model_dump(mode="json")}


class GeometryClient(ServiceClient):
    def brief(self, model: FloorPlanModel) -> PlanBrief:
        return self.post("/v1/models/brief", PlanBrief.model_validate, json=_body(model))

    def insights(self, model: FloorPlanModel) -> Insights:
        return self.post("/v1/models/insights", Insights.model_validate, json=_body(model))

    def execute(self, model: FloorPlanModel, command: dict[str, Any], dry_run: bool) -> ExecuteResult:
        return self.post("/v1/commands/execute", EXECUTE_RESULT_ADAPTER.validate_python,
                         json={**_body(model), "command": command, "dry_run": dry_run})

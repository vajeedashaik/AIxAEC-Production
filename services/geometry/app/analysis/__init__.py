"""Building intelligence: pure functions of a validated model. No LLM, no I/O."""

from aec_contracts import FloorPlanModel
from aec_contracts.analysis import Analysis, CostRates

from .compliance import build_compliance
from .cost import build_estimate
from .interior import build_interior
from .measure import measure
from .structural import build_structural
from .takeoff import build_takeoff


def build_analysis(model: FloorPlanModel, rates: CostRates | None = None) -> Analysis:
    if model.coordinate_system.mm_per_pixel is None:
        return Analysis(needs_scale=True)
    plan = measure(model)
    takeoff = build_takeoff(plan)
    return Analysis(
        needs_scale=False,
        takeoff=takeoff,
        compliance=build_compliance(plan),
        estimate=build_estimate(plan, takeoff, rates),
        interior=build_interior(plan),
        structural=build_structural(plan),
    )

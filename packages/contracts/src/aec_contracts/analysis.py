"""Building intelligence DTOs (CONTRACTS.md §6a). Every quantity is computed deterministically by geometry."""

from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from .commands import EngineCommand
from .model import BBox, FloorPlanModel, Strict


class Assumption(Strict):
    label: str
    value: str


# --- quantity takeoff ---

class BoqItem(Strict):
    code: str
    category: str
    description: str
    unit: str
    quantity: float
    basis: str  # how the number was derived


class Takeoff(Strict):
    items: list[BoqItem]
    assumptions: list[Assumption]


# --- cost ---

MAX_RATE = 1_000_000_000  # an absurd rate would overflow the totals


class CostRates(Strict):
    currency: str = Field(default="INR", min_length=1, max_length=8)
    concrete_per_m3: float = Field(default=7000, ge=0, le=MAX_RATE, allow_inf_nan=False)
    steel_per_kg: float = Field(default=70, ge=0, le=MAX_RATE, allow_inf_nan=False)
    brick_each: float = Field(default=9, ge=0, le=MAX_RATE, allow_inf_nan=False)
    door_each: float = Field(default=12000, ge=0, le=MAX_RATE, allow_inf_nan=False)
    window_each: float = Field(default=15000, ge=0, le=MAX_RATE, allow_inf_nan=False)
    paint_per_litre: float = Field(default=320, ge=0, le=MAX_RATE, allow_inf_nan=False)
    painting_labour_per_m2: float = Field(default=120, ge=0, le=MAX_RATE, allow_inf_nan=False)
    floor_tile_per_m2: float = Field(default=1000, ge=0, le=MAX_RATE, allow_inf_nan=False)
    wall_tile_per_m2: float = Field(default=1000, ge=0, le=MAX_RATE, allow_inf_nan=False)
    flooring_per_m2: float = Field(default=1300, ge=0, le=MAX_RATE, allow_inf_nan=False)
    electrical_point_each: float = Field(default=1500, ge=0, le=MAX_RATE, allow_inf_nan=False)
    plumbing_fixture_each: float = Field(default=9000, ge=0, le=MAX_RATE, allow_inf_nan=False)
    labour_percent: float = Field(default=35, ge=0, le=500, allow_inf_nan=False)
    contingency_percent: float = Field(default=10, ge=0, le=100, allow_inf_nan=False)


class CostLine(Strict):
    category: Literal["Structure", "Openings", "Painting", "Flooring", "Electrical", "Plumbing"]
    description: str
    quantity: float
    unit: str
    rate: float
    amount: float


class CostEstimate(Strict):
    currency: str
    rates: CostRates
    lines: list[CostLine]
    material_cost: float
    painting_cost: float
    flooring_cost: float
    electrical_cost: float
    plumbing_cost: float
    labour_cost: float
    contingency: float
    construction_cost: float
    cost_per_m2: float
    tile_count: int
    assumptions: list[Assumption]


# --- compliance ---

ComplianceCategory = Literal["Corridor width", "Room size", "Accessibility", "Emergency exits", "Door width",
                             "Window placement", "Fire safety"]


class ComplianceCheck(Strict):
    category: ComplianceCategory
    rule: str
    status: Literal["PASS", "WARN", "FAIL"]
    subject: str
    measured: str
    required: str
    element_id: UUID | None = None


class ComplianceReport(Strict):
    profile: str
    disclaimer: str
    passed: int
    warnings: int
    failed: int
    checks: list[ComplianceCheck]


# --- interior ---

class FurniturePlacement(Strict):
    id: UUID
    category: str = Field(max_length=60)
    bbox: BBox


class RoomLighting(Strict):
    room_id: UUID
    room: str
    target_lux: int
    lumens: int
    fixtures: int
    fixture: str
    colour_temperature_k: int
    daylight: str


class ThemeSwatch(Strict):
    name: str
    hex: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class RoomFinish(Strict):
    room: str
    finish: str


class InteriorTheme(Strict):
    name: Literal["Modern", "Minimalist", "Industrial", "Luxury", "Scandinavian"]
    summary: str
    palette: list[ThemeSwatch]
    materials: list[str]
    lighting: str
    room_finishes: list[RoomFinish]


class InteriorPlan(Strict):
    furniture: list[FurniturePlacement]
    lighting: list[RoomLighting]
    themes: list[InteriorTheme]
    notes: list[str]


# --- structural ---

class StructuralSuggestion(Strict):
    category: Literal["Column placement", "Wall alignment", "Space optimization", "Natural ventilation",
                      "Lighting improvement"]
    title: str
    detail: str
    element_id: UUID | None = None
    command: EngineCommand | None = None  # previewable through the normal command flow


class StructuralReport(Strict):
    disclaimer: str
    suggestions: list[StructuralSuggestion]


# --- envelopes ---

class Analysis(Strict):
    needs_scale: bool
    takeoff: Takeoff | None = None
    compliance: ComplianceReport | None = None
    estimate: CostEstimate | None = None
    interior: InteriorPlan | None = None
    structural: StructuralReport | None = None


class Answer(Strict):
    status: Literal["ANSWERED", "UNKNOWN"]
    answer: str
    element_ids: list[UUID] = []  # highlighted on the plan
    source: Literal["rules", "llm"] = "rules"


class LayoutOption(Strict):
    title: str
    rationale: str
    command: EngineCommand
    target_area_before_m2: float | None = None
    target_area_after_m2: float | None = None
    new_compliance_failures: int
    score: float


class LayoutSuggestions(Strict):
    feasible: bool
    answer: str
    options: list[LayoutOption]


# --- geometry service requests ---

class AnalysisRequest(Strict):
    model: FloorPlanModel
    rates: CostRates | None = None


class QuestionRequest(Strict):
    model: FloorPlanModel
    question: str = Field(min_length=1, max_length=500)


class LayoutRequest(Strict):
    model: FloorPlanModel
    goal: str = Field(min_length=1, max_length=300)


# --- language service ---

class AnswerRequest(Strict):
    question: str = Field(min_length=1, max_length=500)
    facts: dict[str, Any]  # no coordinates and no ids


class AnswerResult(Strict):
    status: Literal["ANSWERED", "UNKNOWN", "ERROR"]
    answer: str | None = Field(default=None, max_length=1000)
    model: str | None = None


# --- public API ---

class AnalysisQuery(Strict):
    version: int | None = Field(default=None, ge=1)
    rates: CostRates | None = None


class AskRequest(Strict):
    question: str = Field(min_length=1, max_length=500)
    version: int | None = Field(default=None, ge=1)


class LayoutGoal(Strict):
    goal: str = Field(min_length=1, max_length=300)

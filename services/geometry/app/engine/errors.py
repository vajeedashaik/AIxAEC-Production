"""Typed pipeline failures. Each carries the stage reported to the client (RejectStage)."""

from aec_contracts import Candidate
from aec_contracts.results import RejectStage


class EngineError(Exception):
    stage: RejectStage

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class SchemaError(EngineError):
    stage = "schema"


class ResolutionError(EngineError):
    stage = "entity_resolution"


class SemanticError(EngineError):
    stage = "semantic_validation"


class GeometryError(EngineError):
    stage = "geometry"


class ConstraintViolation(EngineError):
    stage = "constraints"


class ClarificationNeeded(Exception):
    """Not a failure: we refuse to guess and ask instead."""

    stage: RejectStage = "entity_resolution"

    def __init__(self, question: str, candidates: list[Candidate]) -> None:
        super().__init__(question)
        self.question, self.candidates = question, candidates

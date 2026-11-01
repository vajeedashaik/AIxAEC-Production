"""Shared result types (CONTRACTS.md §4)."""

from typing import Literal
from uuid import UUID

from .model import Strict

ElementKind = Literal["wall", "room", "door", "window", "column", "stair", "furniture", "dimension"]


class Candidate(Strict):
    id: UUID
    kind: ElementKind
    label: str            # human description, e.g. "horizontal wall, 240 px long" / "door at (410, 88)"
    x: float; y: float    # anchor point for UI highlighting


class ChangeSet(Strict):
    added: list[UUID] = []
    modified: list[UUID] = []
    removed: list[UUID] = []


RejectStage = Literal["parse", "schema", "entity_resolution", "semantic_validation", "geometry", "constraints"]

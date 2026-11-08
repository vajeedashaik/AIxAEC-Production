"""Ids for new elements: v4-shaped but derived from the input, because the engine may not use randomness."""

from hashlib import sha256
from uuid import UUID

from aec_contracts import FloorPlanModel
from aec_contracts.commands import EngineCommand


def new_id(model: FloorPlanModel, command: EngineCommand, salt: str = "") -> UUID:
    seed = model.model_dump_json() + command.model_dump_json() + salt  # salt: one command, several new elements
    return UUID(bytes=sha256(seed.encode()).digest()[:16], version=4)

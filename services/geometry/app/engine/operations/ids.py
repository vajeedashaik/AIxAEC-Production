"""Ids for new elements: v4-shaped but derived from the input, because the engine may not use randomness."""

from hashlib import sha256
from uuid import UUID

from aec_contracts import Command, FloorPlanModel


def new_id(model: FloorPlanModel, command: Command) -> UUID:
    seed = model.model_dump_json() + command.model_dump_json()
    return UUID(bytes=sha256(seed.encode()).digest()[:16], version=4)

"""Writes JSON Schema for every public and inter-service model into packages/contracts/schema/.

- schema/<Name>.json: one standalone schema per model.
- schema/bundle.json: every model under $defs (input for apps/web TS generation).
Requests are exported in validation mode (fields with defaults optional), responses in serialization mode
(fields always present on the wire are required). Run: `uv run python scripts/export_schema.py`.
"""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, RootModel
from pydantic.json_schema import JsonSchemaMode, models_json_schema

import aec_contracts as c

OUT = Path(__file__).resolve().parent.parent / "schema"


class Command(RootModel[c.Command]):
    """Any of the 10 structured edit commands, discriminated by `operation`."""


class ProjectPage(c.Page[c.Project]):
    pass


REQUESTS: list[type[BaseModel]] = [
    c.ProjectCreate, c.ProjectUpdate, c.CommandRequest, Command,
    c.ExecuteRequest, c.ModelRequest, c.ParseRequest, c.ClassifyRoomsRequest, c.AnalyzeOptions,
]
RESPONSES: list[type[BaseModel]] = [
    c.FloorPlanModel, c.ModelSummary, c.ErrorEnvelope, c.Candidate, c.ChangeSet,
    # public
    c.Me, c.Project, ProjectPage, c.Job, c.FloorPlan, c.ModelEnvelope, c.Artifact, c.CommandResponse,
    c.VersionInfo, c.EditLogEntry, c.History,
    # vision
    c.StageReport, c.ArtifactPayload, c.AnalyzeResult,
    # geometry
    c.ExecuteApplied, c.ExecuteClarification, c.ExecuteRejected, c.Insights, c.PlanBrief, c.ValidateResult,
    # language
    c.ParseResult, c.ClassifyRoomsResult, c.TranscribeResult,
]


def build() -> dict[str, dict[str, Any]]:
    files: dict[str, dict[str, Any]] = {}
    pairs: list[tuple[type[BaseModel], JsonSchemaMode]] = [(m, "validation") for m in REQUESTS]
    pairs += [(m, "serialization") for m in RESPONSES]
    for model, mode in pairs:
        files[f"{model.__name__}.json"] = model.model_json_schema(mode=mode)
    _, bundle = models_json_schema(pairs, title="AEC contracts")
    files["bundle.json"] = bundle
    return files


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    for name, schema in build().items():
        (OUT / name).write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {len(list(OUT.glob('*.json')))} schemas to {OUT}")


if __name__ == "__main__":
    main()

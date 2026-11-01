# Contracts: the frozen interface between all phases

> **P0 materialises this document into code** at `packages/contracts` (Python package `aec_contracts`), JSON Schema (`packages/contracts/schema/*.json`) and TypeScript (`apps/web/src/contracts/generated.ts`).
> After P0 is merged, **no parallel phase edits contracts**. If you find a gap, follow §12 (change requests).
> The Python below is normative: field names, types, bounds and enum values are binding. Docstrings and helper code are up to P0.

---

## 1. Global conventions

- **Coordinates:** image pixels, origin top-left, +x right, +y down. Floats, rounded to 2 dp on output.
- **Units:** `mm_per_pixel` is optional. Never convert px→mm without it. Metric fields are `null` when there is no scale.
- **IDs:** UUID v4 strings. Element IDs are stable across versions unless the element is deleted.
- **Timestamps:** ISO-8601 UTC with `Z` (e.g. `2026-11-01T10:15:00.123Z`).
- **JSON style:** `snake_case` keys everywhere, including TypeScript types (no camelCase mapping layer).
- **Strictness:** every Pydantic model sets `model_config = ConfigDict(extra="forbid")`.
- **Error envelope (every service, every non-2xx):**
  ```json
  { "error": { "code": "stale_model", "message": "The plan changed since you loaded it.", "details": {} } }
  ```
- **Health:** every service exposes `GET /healthz` → `{"status":"ok","service":"<name>","version":"<semver>"}` (no auth) and `GET /readyz` (dependencies checked).
- **Internal auth:** every `/v1/*` route on vision, geometry and language requires the header `X-Internal-Token: <INTERNAL_SERVICE_TOKEN>`. If it's missing or wrong, return `401 {"error":{"code":"unauthorized"}}`.
- **Request ID:** callers send `X-Request-ID`. Services echo it and include it in every log line.

### Error codes (closed set)

| code | HTTP | meaning |
|---|---|---|
| `unauthorized` | 401 | missing/invalid token |
| `forbidden` | 403 | authenticated but not allowed |
| `not_found` | 404 | resource does not exist **or is not yours** (never leak existence) |
| `validation_error` | 422 | request body/params invalid |
| `conflict` | 409 | generic state conflict (e.g. nothing to undo) |
| `stale_model` | 409 | `expected_version` ≠ HEAD |
| `model_not_ready` | 409 | no model yet / processing in progress |
| `already_processing` | 409 | a live job exists |
| `quota_exceeded` | 409 | project/floorplan quota hit |
| `payload_too_large` | 413 | upload/audio too big |
| `unsupported_media_type` | 415 | bad file type |
| `rate_limited` | 429 | includes `Retry-After` header |
| `upstream_unavailable` | 502 / 503 | an internal service or provider failed |
| `internal_error` | 500 | unexpected (never include stack traces) |

---

## 2. Building Model: `aec_contracts.model`

```python
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Source(StrEnum):
    DETECTED = "DETECTED"; INFERRED = "INFERRED"; USER_CONFIRMED = "USER_CONFIRMED"

class RoomType(StrEnum):
    UNKNOWN = "UNKNOWN"; BEDROOM = "BEDROOM"; MASTER_BEDROOM = "MASTER_BEDROOM"; BATHROOM = "BATHROOM"
    KITCHEN = "KITCHEN"; LIVING_ROOM = "LIVING_ROOM"; DINING_ROOM = "DINING_ROOM"; HALLWAY = "HALLWAY"
    CLOSET = "CLOSET"; GARAGE = "GARAGE"; OFFICE = "OFFICE"; LAUNDRY = "LAUNDRY"; BALCONY = "BALCONY"
    STORAGE = "STORAGE"; STAIRWELL = "STAIRWELL"; UTILITY = "UTILITY"; OTHER = "OTHER"

class CalibrationSource(StrEnum):
    UNKNOWN = "UNKNOWN"; ASSUMED_DEFAULT = "ASSUMED_DEFAULT"; DIMENSION_OCR = "DIMENSION_OCR"; MANUAL = "MANUAL"

class Point(Strict):
    x: float = Field(ge=0, allow_inf_nan=False)
    y: float = Field(ge=0, allow_inf_nan=False)

class BBox(Strict):
    x: float = Field(ge=0, allow_inf_nan=False)
    y: float = Field(ge=0, allow_inf_nan=False)
    width: float = Field(gt=0, allow_inf_nan=False)
    height: float = Field(gt=0, allow_inf_nan=False)

class Element(Strict):
    id: UUID = Field(default_factory=uuid4)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: Source = Source.DETECTED

class Wall(Element):
    start: Point
    end: Point
    thickness_px: float | None = Field(default=None, gt=0)
    # validator: start != end ; helper property length_px (not serialised)

class Opening(Element):
    bbox: BBox
    wall_id: UUID | None = None
    width_px: float | None = Field(default=None, gt=0)

class Door(Opening):
    swing: Literal["LEFT", "RIGHT", "DOUBLE", "SLIDING"] | None = None

class Window(Opening):
    pass

class Column(Element):
    bbox: BBox

class Stair(Element):
    bbox: BBox
    polygon: list[Point] | None = None

class Furniture(Element):
    bbox: BBox
    category: str | None = Field(default=None, max_length=60)

class Dimension(Element):
    text: str = Field(max_length=80)
    value_mm: float | None = Field(default=None, gt=0)
    span_px: float | None = Field(default=None, gt=0)
    position: Point | None = None

class Room(Element):
    polygon: list[Point] = Field(min_length=3)
    wall_ids: list[UUID] = Field(default_factory=list)
    label_text: str | None = Field(default=None, max_length=80)
    room_type: RoomType = RoomType.UNKNOWN
    room_type_source: Source | None = None
    room_type_confidence: float | None = Field(default=None, ge=0, le=1)
    area_px: float | None = Field(default=None, gt=0)

class CoordinateSystem(Strict):
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    mm_per_pixel: float | None = Field(default=None, gt=0)
    calibration_source: CalibrationSource = CalibrationSource.UNKNOWN
    calibration_confidence: float | None = Field(default=None, ge=0, le=1)

class FloorPlanModel(Strict):
    schema_version: Literal[1] = 1
    id: UUID = Field(default_factory=uuid4)
    floorplan_id: UUID
    coordinate_system: CoordinateSystem
    walls: list[Wall] = []
    doors: list[Door] = []
    windows: list[Window] = []
    columns: list[Column] = []
    stairs: list[Stair] = []
    furniture: list[Furniture] = []
    dimensions: list[Dimension] = []
    rooms: list[Room] = []
    # model_validator: every Room.wall_ids entry and every Door/Window.wall_id
    # must reference an existing wall id; all element ids unique across lists.
    # method summary() -> ModelSummary
```

```python
class ModelSummary(Strict):
    walls: int; doors: int; windows: int; columns: int; stairs: int
    furniture: int; dimensions: int; rooms: int
```

Helper (pure functions, also in `aec_contracts.model`): `polygon_area(points) -> float` (shoelace, absolute) and `CoordinateTransform(cs).px_to_mm(v) -> float | None`.

---

## 3. Commands: `aec_contracts.commands`

```python
class Direction(StrEnum):  LEFT = "LEFT"; RIGHT = "RIGHT"; UP = "UP"; DOWN = "DOWN"
class ResizeMode(StrEnum): EXPAND = "EXPAND"; CONTRACT = "CONTRACT"

class Distance(Strict):
    value: float = Field(gt=0, allow_inf_nan=False)
    unit: Literal["mm", "px"]

class Targeted(Strict):
    target_id: UUID | None = None
    target_query: str | None = Field(default=None, min_length=1, max_length=200)
    # model_validator: exactly one of target_id / target_query is set

class MoveWall(Targeted):    operation: Literal["MOVE_WALL"];    direction: Direction; distance: Distance
class DeleteWall(Targeted):  operation: Literal["DELETE_WALL"]
class ResizeRoom(Targeted):  operation: Literal["RESIZE_ROOM"];  direction: Direction; distance: Distance; mode: ResizeMode
class AddDoor(Targeted):     operation: Literal["ADD_DOOR"];     position: float = Field(default=0.5, ge=0, le=1); width: Distance | None = None
class AddWindow(Targeted):   operation: Literal["ADD_WINDOW"];   position: float = Field(default=0.5, ge=0, le=1); width: Distance | None = None
class DeleteDoor(Targeted):  operation: Literal["DELETE_DOOR"]
class DeleteWindow(Targeted):operation: Literal["DELETE_WINDOW"]
class RenameRoom(Targeted):  operation: Literal["RENAME_ROOM"];  name: str = Field(min_length=1, max_length=80); room_type: RoomType | None = None
class SetScale(Targeted):    operation: Literal["SET_SCALE"];    length_mm: float = Field(gt=0, le=1_000_000)

class AddWall(Strict):       # untargeted
    operation: Literal["ADD_WALL"]
    start: Point; end: Point
    thickness_px: float | None = Field(default=None, gt=0)

Command = Annotated[
    MoveWall | AddWall | DeleteWall | ResizeRoom | AddDoor | AddWindow
    | DeleteDoor | DeleteWindow | RenameRoom | SetScale,
    Field(discriminator="operation"),
]
COMMAND_ADAPTER: TypeAdapter[Command] = TypeAdapter(Command)
OPERATIONS: tuple[str, ...]  # the 10 literals, in the order above

TARGET_KIND: dict[str, Literal["wall", "room", "door", "window"]] = {
    "MOVE_WALL": "wall", "DELETE_WALL": "wall", "ADD_DOOR": "wall", "ADD_WINDOW": "wall", "SET_SCALE": "wall",
    "RESIZE_ROOM": "room", "RENAME_ROOM": "room", "DELETE_DOOR": "door", "DELETE_WINDOW": "window",
}
```

---

## 4. Shared result types: `aec_contracts.results`

```python
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
```

---

## 5. Vision service API (`services/vision`, :8001)

### `POST /v1/analyze`, multipart/form-data
| field | type | notes |
|---|---|---|
| `file` | binary | PNG / JPG / PDF, already validated by the API (vision re-checks cheaply) |
| `floorplan_id` | UUID string | copied into the model |
| `options` | JSON string, optional | `{"ocr": true, "object_detection": true, "max_dimension": 2400}` |

**200** → `AnalyzeResult` (`aec_contracts.vision`):
```python
StageName = Literal["preprocess", "wall_detection", "ocr", "object_detection",
                    "room_detection", "calibration", "semantic_assembly", "artifacts"]
CRITICAL_STAGES = ("preprocess", "wall_detection", "semantic_assembly")

class StageReport(Strict):
    name: StageName
    status: Literal["ok", "degraded", "failed", "skipped"]
    duration_ms: int = Field(ge=0)
    error: str | None = Field(default=None, max_length=500)   # user-safe text only
    detail: dict[str, int | float | str | bool | None] = {}   # e.g. {"walls": 14, "deskew_deg": 0.8}

ArtifactKind = Literal["preprocessed", "walls_overlay", "detected_elements", "semantic_model"]

class ArtifactPayload(Strict):
    kind: ArtifactKind
    content_type: Literal["image/png", "application/json"]
    data_base64: str

class AnalyzeResult(Strict):
    status: Literal["COMPLETED", "FAILED"]
    model: FloorPlanModel | None          # None iff FAILED
    stages: list[StageReport]             # always all 8, in order (skipped after a critical failure)
    artifacts: list[ArtifactPayload] = []
    warnings: list[str] = []              # e.g. "Only page 1 of 3 was processed."
    error: str | None = None              # "Processing failed at stage 'wall_detection'."
```
A `FAILED` analysis still returns **200**. Non-2xx is reserved for transport/auth/validation errors (`415`, `413`, `422`).

---

## 6. Geometry service API (`services/geometry`, :8002)

### `POST /v1/commands/execute`
```python
class ExecuteRequest(Strict):
    model: FloorPlanModel
    command: dict          # raw/untrusted; geometry validates with COMMAND_ADAPTER (stage "schema")
    dry_run: bool = False  # identical computation; caller decides whether to persist

class ExecuteApplied(Strict):
    status: Literal["APPLIED"]
    command: Command        # resolved: target_id set, target_query cleared
    model: FloorPlanModel   # the new candidate model (validated)
    changes: ChangeSet
    summary: str            # "Moved wall 300 mm left; 2 rooms resized."

class ExecuteClarification(Strict):
    status: Literal["CLARIFICATION"]
    question: str           # "Which wall do you mean?"
    candidates: list[Candidate] = Field(min_length=2)

class ExecuteRejected(Strict):
    status: Literal["REJECTED"]
    stage: RejectStage
    detail: str             # plain English, actionable ("Set a scale first to use millimetres.")

ExecuteResult = Annotated[ExecuteApplied | ExecuteClarification | ExecuteRejected, Field(discriminator="status")]
```
Always **200** for a well-formed request. `422` only if the envelope (not the command) is malformed.

### `POST /v1/models/insights`: body `{"model": FloorPlanModel}` → `Insights`
```python
class RoomRef(Strict): id: UUID; label: str | None; area_px: float
class MetricInsights(Strict):
    total_area_m2: float; average_room_area_m2: float
    total_wall_length_m: float; exterior_wall_length_m: float; interior_wall_length_m: float
class Insights(Strict):
    counts: ModelSummary
    total_area_px: float; average_room_area_px: float
    largest_room: RoomRef | None; smallest_room: RoomRef | None
    total_wall_length_px: float; exterior_wall_length_px: float; interior_wall_length_px: float
    rooms_by_type: dict[RoomType, int]
    metric: MetricInsights | None        # only when mm_per_pixel is set
```

### `POST /v1/models/brief`: body `{"model": FloorPlanModel}` → `PlanBrief`
```python
class RoomBrief(Strict): label: str | None; room_type: RoomType; wall_count: int
class PlanBrief(Strict):
    rooms: list[RoomBrief]; counts: ModelSummary; has_scale: bool
    image_width: int; image_height: int
```
**No coordinates and no ids.** This is the only plan context an LLM ever sees.

### `POST /v1/models/validate`: body `{"model": FloorPlanModel}` → `{"valid": bool, "issues": [{"code": str, "message": str, "element_id": UUID | null}]}`

---

## 7. Language service API (`services/language`, :8003)

### `POST /v1/commands/parse`
```python
class ParseRequest(Strict):
    instruction: str = Field(min_length=1, max_length=500)
    brief: PlanBrief

class ParseResult(Strict):
    status: Literal["PARSED", "UNKNOWN", "ERROR"]
    command: dict | None = None        # raw, UNTRUSTED. Must be re-validated downstream.
    provider: Literal["rules", "llm"]
    model: str | None = None           # LLM model id actually used
    detail: str | None = None          # user-safe reason for UNKNOWN / ERROR
```

### `POST /v1/rooms/classify`
```python
class ClassifyRoomsRequest(Strict): labels: list[str] = Field(max_length=200)
class RoomClassification(Strict):
    label: str; room_type: RoomType; confidence: float = Field(ge=0, le=1)
    source: Literal["rules", "llm"]
class ClassifyRoomsResult(Strict): results: list[RoomClassification]   # same order as input
```

### `POST /v1/speech/transcribe`, multipart: `audio` (binary), `language` (default `en`)
Accepted content types: `audio/webm`, `audio/ogg`, `audio/wav`, `audio/x-wav`, `audio/mp4`, `audio/mpeg`, `audio/flac`. Max 10 MiB / 60 s.
```python
class TranscribeResult(Strict):
    text: str = Field(max_length=500); language: str; duration_ms: int
    provider: Literal["whisper", "stub"]
```

---

## 8. Public API (`services/api`, :8000), used by `apps/web`

Auth: `Authorization: Bearer <Clerk session token>` on every `/v1/*` route. Everything is **owner-scoped**: another user's resource → `404 not_found`.

DTOs live in `aec_contracts.public`:

```python
JobStatus = Literal["PENDING", "PROCESSING", "COMPLETED", "FAILED"]

class Me(Strict): id: UUID; clerk_user_id: str; email: str | None; display_name: str | None; created_at: datetime

class ProjectCreate(Strict): name: str = Field(min_length=1, max_length=200); description: str | None = Field(default=None, max_length=2000)
class ProjectUpdate(Strict): name: str | None = Field(default=None, min_length=1, max_length=200); description: str | None = Field(default=None, max_length=2000)
class Project(Strict):
    id: UUID; name: str; description: str | None
    floorplan_count: int; thumbnail_url: str | None        # signed URL of latest preprocessed artifact
    created_at: datetime; updated_at: datetime

class Page[T](Strict): items: list[T]; total: int; limit: int; offset: int

class Job(Strict):
    id: UUID; floorplan_id: UUID; status: JobStatus; attempts: int
    stages: list[StageReport]; error_message: str | None
    created_at: datetime; started_at: datetime | None; finished_at: datetime | None

class FloorPlan(Strict):
    id: UUID; project_id: UUID; version: int
    original_filename: str; content_type: str; size_bytes: int
    status: JobStatus; current_model_version: int | None
    download_url: str | None; latest_job: Job | None
    warnings: list[str] = []; created_at: datetime

class ModelEnvelope(Strict):
    floorplan_id: UUID; version: int; model: FloorPlanModel; summary: ModelSummary; insights: Insights

class Artifact(Strict): id: UUID; job_id: UUID; kind: ArtifactKind; content_type: str; size_bytes: int; url: str

class CommandRequest(Strict):
    instruction: str | None = Field(default=None, min_length=1, max_length=500)
    command: dict | None = None            # structured (from point-and-click / clarification pick)
    expected_version: int | None = None
    # validator: exactly one of instruction / command

class CommandResponse(Strict):
    status: Literal["APPLIED", "PREVIEW", "CLARIFICATION", "REJECTED"]
    version: int | None = None             # HEAD after the call (APPLIED) or base version (PREVIEW)
    model: FloorPlanModel | None = None    # APPLIED: new HEAD; PREVIEW: candidate (not persisted)
    changes: ChangeSet | None = None
    command: Command | None = None         # resolved command
    summary: str | None = None
    question: str | None = None
    candidates: list[Candidate] = []
    stage: RejectStage | None = None
    detail: str | None = None
    transcript: str | None = None          # voice routes only
    edit_id: UUID | None = None

class VersionInfo(Strict):
    version: int; origin: Literal["PROCESSING", "EDIT"]; parent_version: int | None
    discarded: bool; is_head: bool; created_at: datetime; edit_id: UUID | None

class EditLogEntry(Strict):
    id: UUID; instruction: str | None; operation: str | None
    status: Literal["APPLIED", "REJECTED", "CLARIFICATION", "UNDO", "REDO"]
    stage: RejectStage | None; error: str | None
    parent_version: int | None; result_version: int | None; created_at: datetime

class History(Strict):
    head_version: int | None; can_undo: bool; can_redo: bool
    versions: list[VersionInfo]; edits: list[EditLogEntry]
```

| Method & path | Request | Success |
|---|---|---|
| `GET /healthz` | | 200 |
| `GET /v1/me` | | `Me` (provisions the user on first call) |
| `GET /v1/projects?limit=20&offset=0` | | `Page[Project]` (limit ≤ 100) |
| `POST /v1/projects` | `ProjectCreate` | 201 `Project` |
| `GET /v1/projects/{project_id}` | | `Project` |
| `PATCH /v1/projects/{project_id}` | `ProjectUpdate` | `Project` |
| `DELETE /v1/projects/{project_id}` | | 204 |
| `GET /v1/projects/{project_id}/floorplans` | | `list[FloorPlan]` (newest first) |
| `POST /v1/projects/{project_id}/floorplans` | multipart `file` | 201 `FloorPlan` (job `PENDING`, auto-enqueued unless `?process=false`) |
| `GET /v1/floorplans/{floorplan_id}` | | `FloorPlan` |
| `DELETE /v1/floorplans/{floorplan_id}` | | 204 |
| `POST /v1/floorplans/{floorplan_id}/process` | | 202 `Job` (409 `already_processing`) |
| `GET /v1/floorplans/{floorplan_id}/job` | | `Job` (latest) |
| `GET /v1/floorplans/{floorplan_id}/model` | `?version=` optional | `ModelEnvelope` (409 `model_not_ready`) |
| `GET /v1/floorplans/{floorplan_id}/artifacts` | | `list[Artifact]` |
| `POST /v1/floorplans/{floorplan_id}/commands/interpret` | `CommandRequest` | `CommandResponse` (`PREVIEW`/`CLARIFICATION`/`REJECTED`, never persisted, not audited) |
| `POST /v1/floorplans/{floorplan_id}/commands` | `CommandRequest` | `CommandResponse` (`APPLIED`/`CLARIFICATION`/`REJECTED`, always audited) |
| `POST /v1/floorplans/{floorplan_id}/commands/voice` | multipart `audio`, form `expected_version?`, `dry_run?` | `CommandResponse` with `transcript` |
| `POST /v1/floorplans/{floorplan_id}/model/undo?expected_version=N` | | `CommandResponse` (`APPLIED`, model = new HEAD) |
| `POST /v1/floorplans/{floorplan_id}/model/redo?expected_version=N` | | `CommandResponse` |
| `GET /v1/floorplans/{floorplan_id}/history` | | `History` |

---

## 9. Database schema (Supabase Postgres), owned by P3

```sql
create extension if not exists pgcrypto;
create type job_status   as enum ('PENDING','PROCESSING','COMPLETED','FAILED');
create type model_origin as enum ('PROCESSING','EDIT');
create type edit_status  as enum ('APPLIED','REJECTED','CLARIFICATION','UNDO','REDO');

create table users (
  id uuid primary key default gen_random_uuid(),
  clerk_user_id text not null unique,
  email text unique, display_name text,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table projects (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references users(id) on delete cascade,
  name varchar(200) not null, description varchar(2000),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index on projects(owner_id, created_at desc);
create table floorplans (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  version int not null, original_filename varchar(255) not null,
  storage_key text not null unique, content_type text not null,
  size_bytes bigint not null, checksum_sha256 char(64) not null,
  status job_status not null default 'PENDING',
  current_model_version int, warnings jsonb not null default '[]',
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique (project_id, version)
);
create table processing_jobs (
  id uuid primary key default gen_random_uuid(),
  floorplan_id uuid not null references floorplans(id) on delete cascade,
  status job_status not null default 'PENDING',
  attempts int not null default 0, stages jsonb not null default '[]',
  error_message varchar(500), started_at timestamptz, finished_at timestamptz, heartbeat_at timestamptz,
  created_at timestamptz not null default clock_timestamp(), updated_at timestamptz not null default now()
);
create index on processing_jobs(status, created_at);
create index on processing_jobs(floorplan_id, created_at desc);
create table model_edits (
  id uuid primary key default gen_random_uuid(),
  floorplan_id uuid not null references floorplans(id) on delete cascade,
  user_id uuid references users(id) on delete set null,
  instruction varchar(500), command jsonb, operation text,
  status edit_status not null, stage text, error varchar(500), clarification jsonb,
  parent_version int, result_version int,
  created_at timestamptz not null default clock_timestamp()
);
create table building_models (
  id uuid primary key default gen_random_uuid(),
  floorplan_id uuid not null references floorplans(id) on delete cascade,
  job_id uuid references processing_jobs(id) on delete set null,
  edit_id uuid references model_edits(id) on delete set null,
  version int not null, origin model_origin not null, parent_version int,
  discarded boolean not null default false, data jsonb not null,
  created_at timestamptz not null default clock_timestamp(),
  unique (floorplan_id, version)
);
create table processing_artifacts (
  id uuid primary key default gen_random_uuid(),
  floorplan_id uuid not null references floorplans(id) on delete cascade,
  job_id uuid not null references processing_jobs(id) on delete cascade,
  kind text not null, storage_key text not null unique,
  content_type text not null, size_bytes bigint not null,
  created_at timestamptz not null default now()
);
-- RLS ON for every table with NO policies: anon/authenticated roles get nothing.
-- services/api connects as the postgres role (bypasses RLS) via the connection string.
```

**Storage:** private buckets `floorplans` and `artifacts`.
Keys: `{project_id}/{floorplan_id}/source.{ext}` and `{project_id}/{floorplan_id}/{job_id}/{kind}.{png|json}`.

---

## 10. Environment variables

| Service | Variable | Default / example |
|---|---|---|
| all python | `ENVIRONMENT` | `development` (`test`, `production`) |
| all python | `LOG_LEVEL` / `LOG_FORMAT` | `INFO` / `json` |
| all python | `INTERNAL_SERVICE_TOKEN` | dev: `dev-internal-token-change-me` (prod: ≥32 chars, startup refuses the default) |
| api | `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres` |
| api | `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | `http://127.0.0.1:54321` / from `supabase status` |
| api | `CLERK_ISSUER` | `https://<your-app>.clerk.accounts.dev` |
| api | `CLERK_JWKS_URL` | `${CLERK_ISSUER}/.well-known/jwks.json` |
| api | `CLERK_AUTHORIZED_PARTIES` | `["http://localhost:3000","http://localhost:3001"]` |
| api | `CLERK_SECRET_KEY` | for fetching email/name on first provision (optional) |
| api | `VISION_URL` / `GEOMETRY_URL` / `LANGUAGE_URL` | `http://127.0.0.1:8001` / `:8002` / `:8003` |
| api | `CORS_ORIGINS` | `["http://localhost:3000","http://localhost:3001"]` |
| api | `MAX_UPLOAD_BYTES` / `MAX_AUDIO_BYTES` | `26214400` / `10485760` |
| api | `MAX_PROJECTS_PER_USER` / `MAX_FLOORPLANS_PER_PROJECT` | `200` / `100` |
| api | `PROCESSING_MAX_ATTEMPTS` / `PROCESSING_STALE_SECONDS` / `WORKER_POLL_SECONDS` | `3` / `600` / `2` |
| api | `RATE_LIMIT_READ_PER_MINUTE` / `RATE_LIMIT_WRITE_PER_MINUTE` | `300` / `90` |
| vision | `OCR_PROVIDER` / `TESSERACT_CMD` | `auto` (`stub`, `tesseract`) / unset |
| vision | `OBJECT_DETECTOR` / `YOLO_WEIGHTS_PATH` | `heuristic` (`none`, `yolo`) / unset |
| vision | `IMAGE_MAX_DIMENSION` / `MAX_IMAGE_PIXELS` | `2400` / `64000000` |
| language | `COMMAND_PARSER` | `hybrid` (`rules`, `llm`) |
| language | `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | `http://127.0.0.1:20128/v1` / OmniRoute key / an OmniRoute combo name |
| language | `LLM_TIMEOUT_SECONDS` | `20` |
| language | `STT_PROVIDER` / `WHISPER_MODEL` / `WHISPER_COMPUTE_TYPE` | `whisper` (`stub`) / `base.en` / `int8` |
| web | `NEXT_PUBLIC_API_URL` | `http://localhost:8000` |
| web | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` / `CLERK_SECRET_KEY` | from Clerk dashboard (keyless mode works without them in dev) |
| web | `NEXT_PUBLIC_API_MOCKING` | `off` (`on` = MSW mocks from fixtures) |

---

## 11. Fixtures (`packages/contracts/fixtures`), created by P0, read-only for everyone

| File | Content |
|---|---|
| `apartment.model.json` | Hand-authored valid `FloorPlanModel`: 5 labelled rooms (living, kitchen, bedroom, bathroom, hallway), ~16 walls with `wall_ids` linked, 4 doors, 3 windows, 1 column, 1 stair, 3 dimensions, `mm_per_pixel = 10.0` |
| `apartment.unscaled.model.json` | Same, with `mm_per_pixel = null` |
| `two_room.model.json` | Minimal two rooms sharing one interior wall (for merge-on-delete tests) |
| `synthetic_plan.py` | Deterministic generator (NumPy/OpenCV) for PNGs: `make_two_room_plan()`, `make_apartment_plan()` (thick walls, door gaps + swings, window glazing, stair treads, text labels, a dimension string, hatching) |
| `commands.examples.json` | ≥40 `{instruction, brief_fixture, expected_command}` triples covering all 10 operations, units, directions, ambiguity |
| `api/*.json` | One example response per public endpoint (used by MSW and by contract tests) |

---

## 12. Contract change requests

1. **Never edit `packages/contracts` or `apps/web/src/contracts` in a parallel phase.**
2. Append the request to **your own** `HANDOFF.md` (path in OWNERSHIP.md) under `## Contract change requests`. Include the exact field or shape, why it's needed, and the blast radius.
3. Work around it locally behind an adapter in your own folder and mark it `# CONTRACT-GAP:` / `// CONTRACT-GAP:` so P7 can find it with grep.
4. P7 applies the accepted changes, regenerates the TS types and removes the workarounds.

# AEC AI Platform — Full Project Context

> **Archive.** This file describes the predecessor codebase (`CSPM`) and is kept because phase prompts cite its section numbers. For the current project, see [PROJECT_SOURCE_OF_TRUTH.md](PROJECT_SOURCE_OF_TRUTH.md).

> One-file, code-verified reference for the whole repository (folder name: `CSPM`; product name: **AEC AI Platform**).
> Generated 2026-11-01 from a full read of the source tree, not just the existing docs. Where the older docs disagree with the code, **the code wins** and the drift is listed in §21.
>
> Verified at generation time (run locally, offline): backend `pytest` → **354 passed**; frontend `vitest run` → **88 passed (15 files)**. `ruff` / `black` / `mypy` / `tsc` / `eslint` / `next build` were **not** re-run for this document.

---

## Table of contents

1. [What this project is](#1-what-this-project-is)
2. [Non-negotiable design rules](#2-non-negotiable-design-rules)
3. [Repository layout](#3-repository-layout)
4. [Tech stack & pinned versions](#4-tech-stack--pinned-versions)
5. [High-level architecture](#5-high-level-architecture)
6. [Domain model (the Building Model)](#6-domain-model-the-building-model)
7. [Computer-vision pipeline (floor plan → model)](#7-computer-vision-pipeline-floor-plan--model)
8. [AI editing pipeline (command → new version)](#8-ai-editing-pipeline-command--new-version)
9. [Geometry engine](#9-geometry-engine)
10. [Versioning, undo/redo, audit log](#10-versioning-undoredo-audit-log)
11. [Authentication & identity](#11-authentication--identity)
12. [Storage, queues, voice, OCR, AI providers](#12-storage-queues-voice-ocr-ai-providers)
13. [Database schema & migrations](#13-database-schema--migrations)
14. [HTTP API reference](#14-http-api-reference)
15. [Configuration (every environment variable)](#15-configuration-every-environment-variable)
16. [Security, resilience, observability](#16-security-resilience-observability)
17. [Frontend (Next.js)](#17-frontend-nextjs)
18. [Testing & CI](#18-testing--ci)
19. [Deployment, cloud state & cost](#19-deployment-cloud-state--cost)
20. [Phase history & feature status](#20-phase-history--feature-status)
21. [Known limitations, gaps, and doc drift](#21-known-limitations-gaps-and-doc-drift)
22. [How to run everything](#22-how-to-run-everything)
23. [Documentation map](#23-documentation-map)
24. [Glossary & gotchas](#24-glossary--gotchas)

---

## 1. What this project is

An **AI-native SaaS for Architecture, Engineering & Construction (AEC)**. A user uploads a floor plan (PNG / JPG / PDF). Computer vision converts it into a **structured, typed Building Model** (walls, rooms, doors, windows, columns, stairs, furniture, dimensions). The user then edits that model with **typed or spoken natural-language commands** ("move the wall between the kitchen and the living room 300 mm left", "add a window to the bedroom"). An LLM (or an offline rule grammar) only *interprets language into a structured command*; a **deterministic Shapely-based geometry engine** performs every change, validates it, and writes a new immutable version (with undo/redo and an audit trail).

It is developed by a student (git user `vajeedashaik`) under the project charter in `CLAUDE.md` / `claude.md`: build a *production-oriented* platform, not a disposable demo, while keeping cloud cost near zero. The long-term vision (quantity takeoff, cost estimation, code compliance, BIM interop, collaboration) is **not built**; Phases 0–6 plus a production-readiness hardening pass are.

The product pipeline:

```
Floor-plan image/PDF
  → Computer Vision (OpenCV; optional OCR/YOLO)
  → Semantic Building Model (Pydantic, stored as versioned JSON)
  → Natural-language / voice instruction
  → Structured Command (typed, discriminated union)
  → Schema validation → Entity resolution → Semantic validation
  → Geometry engine (Shapely, deterministic) → Constraint validation
  → New Building Model version (atomic, audited)
  → Renderer (deterministic TypeScript SVG scene)
```

---

## 2. Non-negotiable design rules

From `CLAUDE.md` (root; the identical lower-case `claude.md` also exists) — these govern every design choice:

| Rule | Meaning in the code |
|---|---|
| **A floor plan is a structured model, not an image** | The `FloorPlanModel` JSON is canonical; the original image is never re-edited. |
| **The LLM never edits geometry** | LLM output is a command dict only; it is re-validated as untrusted input. The geometry engine is the *only* writer of coordinates. |
| **AI output is untrusted** | `parse → schema → resolve → semantic → geometry → constraints → transaction`. `extra="forbid"` on every command model. |
| **Don't guess on ambiguity** | `ClarificationRequired` with described candidates instead of picking a target. |
| **Pixels ≠ millimetres** | Geometry is stored in image pixels. `mm_per_pixel` is optional. `mm` commands are *rejected* without a calibrated scale; pixels are never silently treated as mm. |
| **Geometry integrity** | Validate → propose → validate → commit-or-rollback. A failed edit never corrupts the stored model. |
| **Append-only versions** | `building_models` rows are never overwritten; undo/redo move a HEAD pointer. |
| **Async jobs with explicit states** | `PENDING / PROCESSING / COMPLETED / FAILED` on `processing_jobs` (the source of truth). |
| **Cloud behind interfaces** | `AuthService`, `StorageService`, `QueueService`, `OCRService`, `SemanticInterpreter`, `CommandParser`, `SpeechService`, `MetricsSink`, `ObjectDetector`, `WallDetector`. Env var selects the provider; missing SDK/key falls back to the offline default without crashing. |
| **Cost** | Serverless / scale-to-zero, offline-by-default, mocks in tests. RDS is the only standing cost. |
| **Honest status labels** | `NOT_STARTED / IN_PROGRESS / IMPLEMENTED / TESTED / VERIFIED`. **Nothing is marked VERIFIED** (that requires a human/real-system run). |
| **Modular monolith** | One FastAPI app. `services/*` dirs are README-only placeholders by design (D1). |

Architecture mantra: *AI interprets. Structured commands describe intent. Validation checks intent. Geometry computes changes. The Building Model stores truth. The renderer displays truth.*

---

## 3. Repository layout

```
CSPM/
├─ CLAUDE.md / claude.md        project charter (identical content; 35 sections)
├─ README.md                    STALE (says "Phase 3", "68 tests")
├─ PROJECT_OVERVIEW.md          Phases 0–6 summary + manual-work checklist
├─ context.md                   2026-08-31 session handoff (bugs found/fixed, AWS state)
├─ final.md                     click-by-click from-scratch setup (803 lines)
├─ SETUP_GUIDE.md               AWS-oriented setup guide (1165 lines)
├─ SETUP_PROGRESS.md            live AWS setup checklist, resource IDs, teardown commands
├─ Review-1.md                  module inventory ranked for a review/demo
├─ DEMO_SCRIPT.md / VIDEO_SCRIPT.md   live demo + narrated-video scripts
├─ AWS_MIGRATION_PLAN.md        PLAN ONLY (not executed): drop GCP/Azure → Textract/Bedrock/Transcribe
├─ phase0.md … phase6.md        the original per-phase prompts given to Claude
├─ docker-compose.yml           postgres + migrate (one-shot) + api + web (bound to 127.0.0.1)
├─ .env / .env.example          root env for compose (.env is gitignored; contains real values — not read here)
├─ .github/workflows/ci.yml     API job, web job, Postgres-migrations job
├─ apps/
│  ├─ api/                      FastAPI backend (~12.6k LOC Python excluding tests)
│  │  ├─ app/                   see §5 & below
│  │  ├─ alembic/versions/      0001, 0002, 0003, 0004
│  │  ├─ tests/                 43 test modules + fixtures/
│  │  ├─ Dockerfile             python:3.12-slim, non-root uid 10001, tesseract-ocr, healthcheck
│  │  ├─ Dockerfile.lambda      public.ecr.aws/lambda/python:3.12, handler app.lambda_handler.handler
│  │  └─ pyproject.toml, requirements*.txt, alembic.ini, .env.example
│  └─ web/                      Next.js 16 / React 19 / Tailwind 4 frontend (~8.5k LOC TS/TSX/CSS)
├─ docs/                        ARCHITECTURE, FEATURE_STATUS, DECISIONS (D1–D30), HUMAN_TASKS, TESTING,
│                               COMMAND_SYSTEM, GEOMETRY_ENGINE, MULTI_CLOUD_ARCHITECTURE, CLOUD_SERVICES,
│                               COST_OPTIMIZATION, AWS/GCP/AZURE/AI_SETUP, DEMO_RUNBOOK, PRODUCTION_READINESS
├─ services/{vision-worker,geometry-engine,rendering-engine}/   README-only placeholders
├─ packages/schemas/            README-only placeholder
├─ infrastructure/{aws,gcp,azure}/   README-only (no IaC exists)
└─ tests/                       README-only (root cross-service tests, future)
```

### Backend `apps/api/app/` module map

| Path | Role |
|---|---|
| `main.py` | App factory: middleware stack, CORS, exception handlers, routers. |
| `core/config.py` | `Settings` (pydantic-settings), all env vars, prod/staging guards, Secrets-Manager DB URL. |
| `api/deps.py` | DI: DB session, services, `get_current_user` (user id **only** from verified token `sub`). |
| `api/middleware.py` | `SafeErrorMiddleware`, `SecurityHeadersMiddleware`, `MaxBodySizeMiddleware`. |
| `api/rate_limit.py` | `RateLimiter` (per IP+bucket), `LoginThrottle` (per account), `RateLimitMiddleware`. |
| `api/routes/` | `health`, `auth`, `projects`, `floorplans`, `processing`, `editing`, `storage`. |
| `domain/building/` | `model.py` (typed model), `coordinates.py`, `enums.py`, `relationships.py` (wall↔room link), `insights.py` (analytics). |
| `domain/commands/models.py` | The 10-operation typed command union. |
| `domain/enums.py` | `ProcessingStatus`. |
| `db/` | `base.py`, `types.py` (`UTCDateTime`, PG enum), `session.py`, `models/*`. |
| `repositories/` | Thin owner-scoped data access (user, project, floorplan, job, model, edit, artifact). |
| `schemas/` | Pydantic request/response models. |
| `services/auth/` | `base`, `local`, `cognito`, `entra`, `composite`, `factory`. |
| `services/storage/` | `base`, `local`, `s3`, `factory`. |
| `services/queue/` | `base`, `inline`, `local` (thread), `sqs`, `factory`. |
| `services/ocr/` | `stub`, `tesseract`, `google_vision`, `parsing` (dimension parser), `factory`. |
| `services/vision/` | `images` (decode/probe), `preprocess`, `strokes`, `walls`, `rooms`, `objects`, `objects_factory`. |
| `services/processing/` | `pipeline` (`run_pipeline`), `stages` (`run_stage`), `assemble`, `calibrate`, `overlay`, `deps`. |
| `services/semantic/` | `rules`, `room_labels` (lexicon), `ai` + `ai_providers`, `factory`. |
| `services/editing/` | `pipeline` (`EditPipeline`), `rules` (offline grammar), `ai_providers` (LLM), `mock`, `entity_resolution`, `semantic_validation`, `context`, `errors`, `factory`. |
| `services/geometry/` | `operations`, `constraints`, `engine`, `errors`. |
| `services/speech/` | `stub`, `google_speech`, `base`, `factory`. |
| `services/resilience.py` | `call_with_retry`, `CircuitBreaker`. |
| `services/upload_validation.py` | Extension + MIME + magic-byte + size checks. |
| `observability/` | JSON logging + secret redaction; CloudWatch-EMF metrics sink. |
| `worker.py`, `lambda_handler.py` | Two interchangeable processing entrypoints (SQS long-poll / AWS Lambda). |

---

## 4. Tech stack & pinned versions

| Layer | Choice (pinned) |
|---|---|
| Backend | Python ≥3.11 (Docker 3.12; dev box uses 3.13), FastAPI 0.143.5, Starlette 1.8.0, Uvicorn 0.34.0, Pydantic 2.10.4, pydantic-settings 2.7.1, SQLAlchemy 2.0.36, Alembic 1.14.0, `psycopg[binary]` 3.2.3 |
| Auth libs | PyJWT[crypto] 2.15.1, argon2-cffi 23.1.0, boto3 1.35.90 |
| CV / geometry | numpy 2.1.3, opencv-python-headless 4.10.0.84, Pillow 13.0.0, shapely 2.0.6, pytesseract 0.3.13, PyMuPDF 1.24.13 |
| Optional (lazy, **not** in requirements) | `ultralytics` (YOLO), `google-cloud-vision`, `google-cloud-speech`, `google-generativeai`, `anthropic`, `openai` |
| DB | PostgreSQL 16 (prod/compose); SQLite in-memory for tests and quick dev |
| Frontend | Next.js 16.4.2 (App Router), React 19.2.8, TypeScript 5, Tailwind CSS 4, lucide-react, clsx, tailwind-merge |
| Frontend tests | Vitest 2, Testing Library, jsdom |
| Tooling | pytest 8.3.4, httpx, ruff 0.8.4, black 24.10 (line 100), mypy 1.14, moto[s3], boto3-stubs; eslint 9, tsc |
| Container | API: python:3.12-slim (non-root, healthcheck); Lambda: `public.ecr.aws/lambda/python:3.12`; Web: node:22-slim multi-stage (non-root `node`) |

mypy has a scoped relaxation (`call-overload`, `assignment`) for `app.services.vision.*`, `processing.overlay`, `processing.pipeline` because of OpenCV stub false positives (D14).

---

## 5. High-level architecture

```
Browser (Next.js :3000) ──Bearer token──► FastAPI (:8000) ──► PostgreSQL
                                           │
   AuthService      local (dev) | Cognito (prod)  [+ Entra SSO via CompositeAuthService]
   StorageService   local signed-URL FS | S3 (SSE-S3, presigned GET)
   QueueService     inline | local thread (dev default) | SQS
        └─ run_pipeline (8 CV stages) ← also invoked by app.worker (SQS poller) or app.lambda_handler (Lambda)
   OCRService       auto (tesseract if on PATH else stub) | stub | tesseract | google_vision
   ObjectDetector   none | heuristic (default) | yolo
   SemanticInterp.  rules (default) | claude | openai | gemini     (label text → RoomType ONLY)
   CommandParser    rules (default) | mock | claude | openai | gemini
   SpeechService    stub (default) | google
   GeometryEngine   deterministic Shapely/NumPy — the ONLY thing that changes geometry
   MetricsSink      logging (CloudWatch EMF over stdout) | none
   RateLimiter      in-process fixed window + per-account login lockout
```

**Multi-cloud intent** (charter): AWS = core infra (S3, SQS, RDS, Lambda, CloudWatch, Cognito); GCP = AI/processing (Speech-to-Text, Vision OCR, Vertex/Gemini, Cloud Run); Azure = enterprise identity (Entra ID SSO, additive). **Actual live state** (see §19): AWS-only is deployed; GCP and Azure code exists but was never connected to real accounts. `AWS_MIGRATION_PLAN.md` proposes removing GCP/Azure entirely — **not executed**.

Middleware order (outermost → innermost), from `main.py`: CORS → SecurityHeaders → MaxBodySize → RateLimit → SafeError → routes. SafeError sits *inside* CORS so even a 500 carries CORS headers.

---

## 6. Domain model (the Building Model)

`app/domain/building/model.py` — Pydantic v2. Persisted as one JSON document per version in `building_models.data`.

| Type | Fields (besides `id: UUID`, `confidence: 0–1?`, `source: DETECTED|INFERRED|USER_CONFIRMED`) |
|---|---|
| `Point` | `x ≥ 0`, `y ≥ 0` (image px, origin top-left) |
| `BBox` | `x,y ≥ 0`, `width,height > 0`, finite |
| `Wall` | `start`, `end` (must differ), `thickness_px > 0?`, `length_px` property |
| `Opening` → `Door`, `Window` | `bbox`, `wall_id?`, `width_px?`; Door also `swing?` |
| `Column` | `bbox` |
| `Stair` | `bbox`, `polygon?` |
| `Furniture` | `bbox`, `category?` |
| `Dimension` | `text`, `value_mm?`, `span_px?`, `position?` |
| `Room` | `polygon (≥3 pts)`, `wall_ids`, `label_text?`, `room_type`, `room_type_source?`, `room_type_confidence?`, `area_px? (>0)` |
| `FloorPlanModel` | `id`, `floorplan_id`, `coordinate_system`, lists of all of the above; **validator** enforces `Room.wall_ids` and opening `wall_id` reference existing walls. `.summary()` → counts. |
| `Building` | wrapper with `floor_plans` (defined but not used by the API yet) |

`RoomType` enum: UNKNOWN, BEDROOM, MASTER_BEDROOM, BATHROOM, KITCHEN, LIVING_ROOM, DINING_ROOM, HALLWAY, CLOSET, GARAGE, OFFICE, LAUNDRY, BALCONY, STORAGE, STAIRWELL, UTILITY, OTHER.
`CalibrationSource` enum: UNKNOWN, ASSUMED_DEFAULT, DIMENSION_OCR, MANUAL.

**`CoordinateSystem`**: `image_width/height`, `mm_per_pixel?`, `calibration_source`, `calibration_confidence?`. `CoordinateTransform` converts px↔mm and returns `None` when no scale exists.

**Wall↔room linking** (`relationships.py::link_walls_to_rooms`): a wall is linked to a room when ≥ max(20 px, 10 % of wall length) of it lies within 12 px of the room boundary (sampled along the wall). Runs at the end of `build_floorplan_model`; populates `Room.wall_ids` (existing ids preserved, deduped).

**Insights** (`insights.py`, pure/deterministic, no LLM): counts of every element; total/average floor area (shoelace on polygons — not the stored `area_px`), largest/smallest room, total wall length, **exterior wall length** (a wall is *interior* only when rooms lie on **both** sides of it; otherwise exterior), rooms-by-type. Metric (m / m²) values only when `mm_per_pixel` is set.

---

## 7. Computer-vision pipeline (floor plan → model)

Entry: `services/processing/pipeline.py::run_pipeline(session_factory, job_id)` — owns its own DB session; safe to call repeatedly.

### Job lifecycle & reliability

1. Skip if job missing, or already `COMPLETED`/`FAILED`.
2. If `attempts >= PROCESSING_MAX_ATTEMPTS` (default 3) → fail with "giving up" (poison-job guard).
3. **Atomic claim** `ProcessingJobRepository.try_claim`: a single conditional `UPDATE … WHERE status=PENDING OR (PROCESSING AND started_at null/older than PROCESSING_STALE_SECONDS)`; increments `attempts`. Only one runner wins; others no-op (this makes SQS redelivery / double clicks / multiple replicas safe).
4. Mirrors status onto `FloorPlan.status`.
5. Any unexpected exception → rollback → job `FAILED` (never stuck in `PROCESSING`).
6. `POST /floorplans/{id}/process` additionally takes a row lock, fails *stale* active jobs (so a dead worker can't block retry), returns `already_running` for a live one, and on enqueue failure marks the job `FAILED` + 503.

### The 8 stages (each wrapped by `run_stage`)

`run_stage` records `{name, status ok|degraded|failed, duration_ms, error, detail}`; a non-critical failure → `degraded` and the pipeline continues; a **critical** failure raises `StageFailed` → job `FAILED` with a user-safe message (`Processing failed at stage 'X'.`).

| # | Stage | Critical | What it does |
|---|---|---|---|
| 1 | `preprocess` | ✅ | `decode_image` (PNG/JPG via OpenCV; **PDF page 1** via PyMuPDF rasterised directly at working resolution) → downscale so longest edge ≤ `IMAGE_MAX_DIMENSION` (2400) → grayscale → `fastNlMeansDenoising` → CLAHE → Gaussian adaptive threshold (inverted: ink=255) → median blur → **deskew** (median Hough-line angle, applied if \|angle\| ≥ 0.3°). |
| 2 | `wall_detection` | ✅ | `HoughWallDetector.detect_full` (class name historical; see below). Returns walls **and** door/window openings found as wall gaps. |
| 3 | `ocr` | – | `OCRService.recognize(grayscale)` → word boxes. |
| 4 | `object_detection` | – | `ObjectDetector.detect(gray, binary)`; results are combined with the wall-gap openings. |
| 5 | `room_detection` | – | Deterministic rasterise-walls → flood exterior → enclosed components (§below). |
| 6 | `calibration` | – | `estimate_scale`: for each OCR word parsed as a dimension, find the nearest wall within 120 px; ratio `value_mm / wall_px`, accepted if 0.05–500 mm/px; **median** across matches; confidence `min(0.8, 0.3+0.15n)`. No match ⇒ `mm_per_pixel=None`. |
| 7 | `semantic_assembly` | ✅ | `build_floorplan_model`: walls → clamped to image; `reconcile_openings`; rooms typed by `SemanticInterpreter`; objects normalised to Door/Window/Column/Stair/Furniture (opening bound to nearest wall within 40 px); OCR dimensions → `Dimension`; build `CoordinateSystem`; `link_walls_to_rooms`. |
| 8 | `artifacts` | – | Stored via `StorageService` + indexed in `processing_artifacts`: `preprocessed` (PNG), `walls_overlay` (PNG, best-effort), `detected_elements` (JSON), `semantic_model` (JSON). Key: `projects/{pid}/floorplans/{fpid}/artifacts/{jobid}/{kind}.{ext}`. |

After the stages: a **new `BuildingModel` row** (`origin=PROCESSING`, `parent_version = previous HEAD`) is appended and `floorplan.current_model_version` points at it. Re-processing therefore *branches from* the edited model, so **Undo restores the user's edits** (R2).

### Wall detector (`vision/walls.py` + `strokes.py`)

1. `estimate_wall_thickness` — distance-transform ridge; largest stroke width shared by ≥ max(30, 0.6×image length) ridge pixels. `None` for hairline-drawn plans (<3 px).
2. `structural_mask` — morphological open (kernel ≈0.45×thickness) + close; removes text, hatching, dimension lines, furniture outlines, stair treads and door swings (all thin).
3. **Axis walls**: horizontal/vertical line-openings; each connected body → one centre-line (least-squares fit, so slightly rotated scans work). Residual (diagonals) → probabilistic Hough, collinear merge, lower confidence 0.45.
4. Straighten (≤3° → exactly axis-aligned), merge overlapping same-line segments, **bridge gaps** (collinear segments separated by ≤14 % of the longest side become ONE continuous wall and the gap is emitted as an opening), **snap junctions** (each end moves onto the centre-line of the wall it meets), drop short segments.
5. `_classify_opening`: a gap whose band shows ≥2 thin parallel lines (glazing) → `window`, else `door`.

Limitation: supports **solid / thick-stroke** walls. Walls drawn as two hairlines, curved walls, and degraded scans are unsupported (need a learned detector).

### Room detection (`vision/rooms.py`)

Draw walls into a mask (stroke = median thickness), morphological close, invert, flood-fill the exterior from border seeds, take 4-connected enclosed components between 0.3 % and 90 % of the image, dilate by half a stroke so edges land on wall **centre-lines**, `approxPolyDP`, **snap vertices to wall joints** (endpoints + pairwise centre-line intersections), drop collinear vertices. Label = words (without digits) whose centres lie inside, joined in reading order.

### Object detection (`vision/objects.py`)

- `HeuristicObjectDetector` (default): **door swings** (Hough circles on thin ink + validation that ink occupies exactly one quadrant and one bounding radius), **columns** (compact solid squares ~ wall-width to 4×), **stairs** (≥4 evenly spaced parallel thin lines).
- `NullObjectDetector`; `YoloObjectDetector` (optional ultralytics; coarse COCO→architecture label map; `# pragma: no cover`).
- `reconcile_openings` drops door swings whose hinge isn't on a wall and swings duplicated by a gap-opening.

### OCR & semantics

- `ocr/parsing.py::parse_dimension`: `"3600"` (100–100 000 treated as mm), `"3.6 m"`, `"360 cm"`, `"3600 mm"`, `12'-6"`, `12ft 6in`.
- `semantic/room_labels.py`: ordered regex lexicon (master bed, bath/WC, kitchen, living, dining, hall, garage, office, laundry, balcony, storage, stair, utility…). `AIInterpreter` calls an LLM **only for labels the rules left `UNKNOWN`**, validates output to the `RoomType` enum, falls back to rules on any failure.

---

## 8. AI editing pipeline (command → new version)

`services/editing/pipeline.py::EditPipeline` with `interpret()` (dry-run, no mutation, no audit row) and `execute()` (mutating, always audits).

### Commands (`domain/commands/models.py`)

Discriminated union on `operation`, all models `extra="forbid"`. Targeted ops require **exactly one** of `target_id` (UUID) or `target_query` (≤200 chars, resolved later).

| Operation | Fields |
|---|---|
| `MOVE_WALL` | target, `direction` LEFT/RIGHT/UP/DOWN, `distance {value>0, unit mm|px}` |
| `ADD_WALL` | `start`,`end` (px, ≥0), `thickness_px?` — untargeted |
| `DELETE_WALL` | target |
| `RESIZE_ROOM` | target (room), `direction` (which side), `distance`, `mode` EXPAND/CONTRACT |
| `ADD_DOOR` / `ADD_WINDOW` | target (a **wall**), `position` 0–1 (default 0.5), `width?` |
| `DELETE_DOOR` / `DELETE_WINDOW` | target |
| `RENAME_ROOM` | target (room), `name` (1–80), `room_type?` (must be a `RoomType`) — metadata only |
| `SET_SCALE` | target (wall), `length_mm` (0–1 000 000] — calibrates `mm_per_pixel` |

### Stages (each has its own error class with a `.stage` string returned to the client)

1. **parse** (`CommandParseError`) — `CommandParser.parse(instruction, plan_context)`. The context is a *compact read-only brief* (room labels/types/wall counts, element counts, `has_scale`); the parser never receives geometry.
   - **Rules parser** (default, offline, regex): handlers tried in order `rename → add_wall (explicit coords only) → move → resize → add door/window → delete`. Understands mm/cm/m/px, left/right/up/down/top/bottom/north/south/east/west, "at N %", "N wide".
   - **LLM parsers** (`claude` default model string `claude-opus-5`, `openai` `gpt-4o-mini`, `gemini` `gemini-1.5-flash`; override with `COMMAND_AI_MODEL`): system prompt demands one JSON object, forbids inventing ids/coordinates; `{"operation":"UNKNOWN"}` for non-edit text. Wrapped in a latency timer and `ai.error` metric; any failure → `CommandParseError`.
2. **schema** (`CommandSchemaError`) — `COMMAND_ADAPTER.validate_python(raw)`.
3. **entity_resolution** (`EntityResolutionError` / `ClarificationRequired`) — see below.
4. **semantic_validation** (`CommandValidationError`) — `mm` rejected with no scale; moves/resizes larger than 3× the image's larger dimension rejected; opening width in (0, span]; `ADD_WALL` endpoints within image (+6 px margin) and length ≥1; `SET_SCALE` ratio must be 0.05–500 mm/px.
5. **geometry** (`GeometryError`) and 6. **constraints** (`ConstraintViolation`) — §9.
7. **persist** — compare-and-swap HEAD, append version (§10).
8. **audit** — `building_model_edits` row for every attempt.

### Entity resolution (`entity_resolution.py`)

Operation→target kind: wall (MOVE_WALL, DELETE_WALL, ADD_DOOR, ADD_WINDOW, SET_SCALE), room (RESIZE_ROOM, RENAME_ROOM), door, window.
- Explicit `target_id` is only kind-checked against the model.
- Rooms: match by label substring (either direction) or synonym → room type (`master bedroom`, `living room`, `lounge`, `toilet`, `corridor`, …). Multiple → clarification.
- Walls: `"between X and Y"` → intersection of both rooms' `wall_ids` (0 → error; 1 → resolved; >1 → clarification). A room reference → that room's walls (0 → "No walls are linked…", 1 → resolved, >1 → clarification). A single-wall model resolves trivially.
- Doors/windows: via the room's walls; if no room phrase and exactly one exists, that one; else clarification.
- Clarification responses carry `candidate_details [{id, kind, label, x, y}]` (e.g. `"horizontal wall, 240 px long"`, `"door at (410, 88)"`) so the UI can show buttons and re-send the chosen id.

### Outcomes

`EditOutcome.status`: `APPLIED` (new version + full model), `CLARIFICATION`, `REJECTED` (+`stage`, `detail`). `StaleModelError` is raised through to the API as **409 `{"code":"stale_model"}`**.

---

## 9. Geometry engine

`services/geometry/` — `GeometryEngine.apply(model, command)` = dispatch table → candidate (deep copy) → **Pydantic re-validation of the whole model** → `validate_model(candidate, before=model)`. Any failure raises; nothing is persisted. All operations are pure functions of `(model, command)` and deterministic (asserted byte-identical in tests).

### Operations (current behaviour — differs from `docs/GEOMETRY_ENGINE.md`, see §21)

- **MOVE_WALL**: a wall moves **sideways only** (perpendicular to its length). If more than 35 % of the requested move is *along* the wall, it is refused with a plain-English hint ("move it up or down"). Walls meeting the moved wall — at an end **or** in a T-junction (within `max(6, 1.5×thickness)` px) — have that end re-projected onto the moved wall's new line (collinear continuations just translate); room corners on the wall follow; attached doors/windows move; every room's `area_px` is recomputed.
- **RESIZE_ROOM**: finds the walls forming the chosen side of the room (within tolerance of the room's extreme edge and overlapping its span by >25 % of their length) and shifts them via the same `_shift_walls`; refuses if the side isn't formed by a movable wall.
- **ADD_WALL**: endpoints snap onto existing wall centre-lines when within tolerance; thickness defaults to the median existing thickness; `source=USER_CONFIRMED`.
- **DELETE_WALL**: determines which rooms lie on each side. Rooms on **both** sides → they are **merged** (Shapely union, simplified, winding preserved, surviving label/type kept, `wall_ids` merged). A wall with a room on one side only (exterior boundary) → **refused** (`ConstraintViolation`). Openings on it are deleted; `wall_ids` cleaned.
- **ADD_DOOR / ADD_WINDOW**: width from command or default (900 mm / 1200 mm if scaled, else 40 / 48 px), min 4 px, rejected if >90 % of the wall; centre clamped so the whole opening stays on the wall; overlap with existing openings rejected; bbox axis-aligned with wall thickness.
- **DELETE_DOOR / DELETE_WINDOW**: removal.
- **RENAME_ROOM**: sets label; type = given or `room_type_for_text(name)` or UNKNOWN; marks `USER_CONFIRMED`, confidence 1.0.
- **SET_SCALE**: `mm_per_pixel = length_mm / wall.length_px`, `MANUAL`, confidence 1.0.

### Constraint validator (`constraints.py`) — compares to the *previous* model so pre-existing imperfections never block an unrelated edit

1. Unique element ids. 2. Walls/room vertices within image bounds (±6 px). 3. Rooms: ≥3 corners, simple ring, valid, area ≥1 px², **not inverted** (signed-area sign flip), **not crushed** below 20 % of former area. 4. A wall that was axis-aligned (≤0.5°) must stay axis-aligned. 5. A moved wall must not land on/through a **parallel** wall (unless they already touched). 6. Doors/windows must still reference an existing wall and lie within 30 px of it — only judged if the opening or its wall changed.

Explicit scope statement (repeated in code and docs): this is *geometric consistency*, **not** building-code or structural compliance.

---

## 10. Versioning, undo/redo, audit log

- `building_models` is **append-only**, `UNIQUE(floorplan_id, version)`. Columns: `origin` (`PROCESSING|EDIT`), `parent_version`, `discarded`, `edit_id`.
- `floorplans.current_model_version` is the **HEAD pointer**. `get_head` returns it (falls back to max version for pre-Phase-4 plans). Don't use `get_latest_for_floorplan` for "current".
- **Undo** → HEAD := `head.parent_version`. **Redo** → HEAD := the non-discarded child whose `parent_version == head`. Both write audit rows; neither copies data.
- A fresh edit while HEAD is behind marks every later non-discarded version `discarded` (kept for audit, excluded from redo). Version numbers can therefore have gaps.
- **Concurrency**: `_lock` takes `SELECT … FOR UPDATE` on the floor plan (real on Postgres); `expected_version` (optimistic) → `StaleModelError` if HEAD moved; the HEAD swap is a **compare-and-swap UPDATE**; a unique-violation on version → `StaleModelError`. Verified live: 6 parallel edits → 1×200, 5×409.
- **Audit table** `building_model_edits`: user, timestamp, instruction, resolved command JSON, operation, `status` (`APPLIED|REJECTED|CLARIFICATION|UNDO|REDO`), `stage`, `error` (≤500), `clarification`, `parent_version`, `result_version`. No secrets.
- Atomicity: any rejection → `session.rollback()`, then an audit row is committed; the stored model is untouched.

---

## 11. Authentication & identity

`AuthService` ABC (`register, login, logout, verify_token, get_profile` + optional `refresh, resend_confirmation, forgot_password, reset_password`). Exceptions: `AuthError` → `UserAlreadyExistsError`, `InvalidCredentialsError`, `UserNotConfirmedError`, `InvalidCodeError`, `UnsupportedOperationError`, `InvalidTokenError`.

| Provider | Notes |
|---|---|
| **local** (dev/test only) | Argon2id hashes in `local_credentials`; HS256 JWT (`iss=aec-local-auth`) with `jti`; access TTL `LOCAL_JWT_TTL_SECONDS` (3600), refresh 7 days; **logout revokes** the `jti` (process-local deny-list); password reset codes are 6-digit, 15-min TTL, 5 attempts, **written to the server log** (no email channel); dummy-hash verification on unknown email (no timing enumeration). |
| **cognito** (production) | `sign_up` / `confirm_sign_up` / `initiate_auth(USER_PASSWORD_AUTH)` / `REFRESH_TOKEN_AUTH` / forgot/confirm-forgot / `global_sign_out`. `verify_token` is **offline** against the pool JWKS (RS256, issuer, `token_use=access`, `client_id`), `leeway=30` s (added after a real 9-second clock-skew bug). Optional `SECRET_HASH` when the app client has a secret. Challenges (MFA, NEW_PASSWORD_REQUIRED) unsupported. Pool must use `UsernameAttributes:["email"]` (email-as-alias breaks `sign_up`). |
| **entra** (additive SSO) | Verifies Entra access tokens offline against tenant JWKS (RS256; issuer v1/v2; audience ∈ `ENTRA_ALLOWED_AUDIENCES` or `[client_id, api://client_id]`; `tid`); subject = `oid` or `sub`; `leeway=30`. `register`/`login` unsupported. |
| **CompositeAuthService** | Wraps primary + Entra when `ENTRA_SSO_ENABLED`. `verify_token`/`get_profile`/`logout` dispatch on the token's (unverified) `iss`; `register/login/confirm/refresh/forgot/reset` always go to the primary. `provider_for(token)` returns `entra`/`cognito`/`local`. |

`get_current_user`: verify token → look up `users.external_auth_id == sub` → else provision from token email (or `get_profile`) — **but** if the email already exists under a *different* `auth_provider` return **409** (account-takeover guard). The user id never comes from the client.

Login protections: per-IP `auth` rate bucket (20/min) **and** per-account `LoginThrottle` (default 8 failures → lock 900 s, 429 + `Retry-After`; reset on success/password reset). Password policy (server + mirrored client): ≥8 chars, letter+digit, ≥4 distinct chars, not in a common list, must not contain the email local-part (≥4 chars). `forgot-password` always returns 204 (no enumeration); registering an existing email still returns 409 (documented trade-off).

---

## 12. Storage, queues, voice, OCR, AI providers

**Storage** (`StorageService`: `put_object, get_object, download_url, delete_object, delete_prefix`)
- `s3`: SSE-S3 (AES256), reads only via presigned GET (`PRESIGNED_URL_TTL_SECONDS`, default 900), never public.
- `local`: files under `LOCAL_STORAGE_DIR`; HMAC-SHA256-signed URLs (key+expiry) served by `GET /storage/local/{key}`; strict key allow-list and path-escape checks; download always `application/octet-stream` with sanitised `Content-Disposition`.
- Keys are server-generated: `projects/{project_id}/floorplans/{uuid4hex}.{ext}`; the client filename is sanitised and kept only for display.

**Upload validation** (`upload_validation.py` + `images.probe_image`): extension (`png|jpg|jpeg|pdf`) ∧ declared MIME ∧ magic bytes must agree; non-empty; ≤ `MAX_UPLOAD_BYTES` (25 MB); then structural verify + full decode of the already size-checked image, pixel cap `MAX_IMAGE_PIXELS` (64 MP), PDF checks (encrypted, zero pages, absurd page size >14 400 pt, render DPI 200 capped to pixel budget). Multi-page PDF → only page 1 processed, with a warning in the upload response. Orphan blob deleted if the DB commit fails. Per-project (100) and per-user project (200) quotas → 409.

**Queue** (`QueueService.enqueue_processing(job_id)`): `inline` (runs synchronously; tests), `local` (daemon worker thread; dev default; loses an in-flight hand-off on restart), `sqs` (publish with `call_with_retry`; body `{"type":"process_floorplan","job_id":…}`).
- `python -m app.worker`: long-poll SQS (≤20 s), one message at a time, deletes on success; drops unparseable messages; leaves failed ones for redelivery/DLQ. Only valid with `QUEUE_PROVIDER=sqs`.
- `app.lambda_handler.handler`: per-record `run_pipeline`, returns `batchItemFailures` for failed records; drops poison messages (metric `queue.message.unparseable`).

**Speech** (`SpeechService.transcribe(audio, content_type, language)`): `stub` (canned/by-size transcript; default) or `google` (sync `recognize`, model `command_and_search`, wrapped in `call_with_retry`). Allowed audio types: `audio/webm`, `ogg`, `wav`/`x-wav`/`l16`, `flac` (Safari `audio/mp4` → 415). Voice routes are plain `def` (threadpool), read capped at `MAX_AUDIO_BYTES` (10 MB), transcript clipped to 500 chars, then call **the same `EditPipeline`**.

**OCR** (`OCR_PROVIDER`): `auto` (default) = Tesseract if the binary is on PATH (bundled in the API Docker image) else stub; `stub`; `tesseract`; `google_vision` (lazy SDK).

**AI providers** are lazy-imported; the factories catch `*Unavailable`/`KeyError` and fall back to the offline implementation with a warning.

---

## 13. Database schema & migrations

Alembic revisions: `0001_initial_schema`, `0002_phase2_pipeline`, `0003_phase4_editing`, `0004_fks` (adds the two FKs that existed on the ORM models but not in migrations; nulls orphans first; `alembic check` is now a test and a CI job). Tests do **not** use migrations (`Base.metadata.create_all` on SQLite). `0001` was fixed to use `postgresql.ENUM` because `sa.Enum(create_type=False)` is lost on dialect adaptation (it only ever worked on SQLite before).

All tables have `created_at`/`updated_at` (`UTCDateTime` — always timezone-aware UTC; API emits `…Z`).

| Table | Key columns / constraints |
|---|---|
| `users` | `id` UUID PK; `external_auth_id` (unique, indexed) = token `sub`; `email` (unique, lowercased); `auth_provider` |
| `local_credentials` | `subject` UUID PK; `email` unique; `password_hash` (Argon2id). **Dev/test only.** |
| `projects` | `owner_id` → users (CASCADE); `name` ≤200; `description` |
| `floorplans` | `project_id` → projects (CASCADE); `version` (`UNIQUE(project_id, version)`); `original_filename` (sanitised); `storage_key` unique; `content_type`; `size_bytes`; `checksum_sha256`; `status` (PG enum `processing_status`); `current_model_version` (HEAD) |
| `processing_jobs` | `floorplan_id` (CASCADE); `status`; `error_message`; `attempts`; `stages` JSON; `started_at`/`finished_at`; `building_model_id` → building_models (SET NULL, `use_alter`); `created_at` has Python-assigned microsecond precision for deterministic "latest job" ordering |
| `building_models` | `floorplan_id` (CASCADE); `job_id` (SET NULL); `version` (`UNIQUE(floorplan_id, version)`); `data` JSON (the `FloorPlanModel`); `origin`; `parent_version`; `discarded`; `edit_id` → building_model_edits (SET NULL) |
| `building_model_edits` | audit log (see §10); `user_id` SET NULL |
| `processing_artifacts` | `floorplan_id` (CASCADE); `job_id`; `kind`; `storage_key` unique; `content_type`; `size_bytes` |

Relationships: `User 1─< Project 1─< FloorPlan 1─< ProcessingJob`; `FloorPlan 1─< BuildingModel` (versioned; HEAD pointer); `FloorPlan 1─< BuildingModelEdit`; `FloorPlan 1─< ProcessingArtifact`.

D11: the model is stored as **one JSON document per version**, not table-per-entity (no cross-project SQL queries over walls/rooms yet — deliberate).

---

## 14. HTTP API reference

All endpoints except `/health` and the public `/auth/*` calls require `Authorization: Bearer <access token>`. Every project/floor-plan route is **owner-scoped**; another user's resource returns **404** (no existence leak — swept by `test_security.py`).

| Method & path | Purpose / notable behaviour |
|---|---|
| `GET /health` | Liveness (rate-limit exempt). |
| `POST /auth/register` | 201; `confirmation_required` true only for Cognito; 409 existing email; 400 provider rejection; 422 weak password. |
| `POST /auth/confirm` | 204; Cognito code confirm (400 for providers without confirmation). |
| `POST /auth/login` | Token bundle; 401 bad credentials; 403 + `X-Error-Code: user_not_confirmed`; 429 lockout. |
| `POST /auth/refresh` | Exchange refresh token (`email` needed for Cognito apps with a secret). |
| `POST /auth/resend-confirmation` · `forgot-password` · `reset-password` | 204s; forgot never reveals existence. |
| `POST /auth/logout` | 204 (local: revokes `jti`; Cognito: global sign-out; Entra: no-op). |
| `GET /auth/me` | Current user; provisions the local row on first sight. |
| `POST /projects` · `GET /projects?limit&offset` · `GET /projects/{id}` · `DELETE /projects/{id}` | CRUD; list is paginated (limit ≤200) with a grouped count query; delete commits the DB first, then removes blobs (failure only orphans blobs). |
| `POST /projects/{id}/floorplans` | Multipart `file`; validated, probed, stored, new immutable version + `PENDING` job; returns `warnings[]`. |
| `GET /projects/{id}/floorplans` · `GET …/{fpId}` | List / detail with short-lived download URL + latest job. |
| `POST /floorplans/{id}/process` | 202; see §7. 503 if enqueue fails. |
| `GET /floorplans/{id}/processing-status` | Latest job, per-stage outcomes, `has_model`. |
| `GET /floorplans/{id}/model` | HEAD model + `summary` + `insights`; 409 while processing; 404 if none. |
| `GET /floorplans/{id}/model/insights` | Analytics only. |
| `GET /floorplans/{id}/artifacts` | Artifact list with signed URLs. |
| `POST /floorplans/{id}/commands/interpret` | Dry run → `OK` / `CLARIFICATION` / `REJECTED`. |
| `POST /floorplans/{id}/commands` | Body `{instruction? \| command?, expected_version?}` → `APPLIED` (with new model) / `CLARIFICATION` / `REJECTED`; 409 `stale_model`. |
| `POST /floorplans/{id}/commands/voice` · `…/voice/interpret` | Multipart `audio` → transcript → same pipeline; 415/413/422/502 as described. |
| `POST /floorplans/{id}/model/undo` · `…/redo` | `?expected_version=`; 409 when nothing to undo/redo or stale. |
| `GET /floorplans/{id}/model/history` | Versions (`is_head`, `discarded`, `origin`), edit log, `can_undo`/`can_redo`. |
| `GET /storage/local/{key}?expires&sig&filename` | Local provider only; 403 on bad/expired signature. |

Error shape: `{"detail": "..."}` (+ `"code"` for `stale_model`). Unhandled errors → `{"detail":"An internal error occurred."}` 500, logged server-side only. Security headers on every API response: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cross-Origin-Resource-Policy: same-site`, `Cache-Control: no-store`. Request bodies capped at `max(MAX_UPLOAD_BYTES, MAX_AUDIO_BYTES)+1 MiB` (413).

Rate-limit buckets (60 s fixed window, per client IP): `auth` (non-GET `/auth/*`) 20/min, `write` (POST/PUT/PATCH/DELETE on `/projects*` and `/floorplans*` — **this includes edit commands, undo/redo and process**) 90/min, `read` (everything else) 300/min. `/health`, `/docs`, `/redoc`, `/openapi.json`, `OPTIONS` exempt. Client IP = socket peer unless `TRUSTED_PROXY_COUNT>0`, then the N-th entry from the **right** of `X-Forwarded-For`.

---

## 15. Configuration (every environment variable)

Pydantic-settings; `.env` in the working dir; blank strings for optional values are coerced to `None` (fixes `S3_ENDPOINT_URL=` crashing boto3). **Startup guards:** in `staging`/`production` it refuses the default `LOCAL_JWT_SECRET` (`dev-insecure-change-me`), secrets <32 chars, `*` in `CORS_ORIGINS`, and SQLite; in `production` it also refuses `AUTH_PROVIDER=local` and `STORAGE_PROVIDER=local`. It also requires: Cognito ids for `cognito`, bucket for `s3`, queue URL for `sqs`, tenant+client for Entra SSO.

| Group | Variables (default) |
|---|---|
| Core | `ENVIRONMENT` (development; also test/staging/production), `SERVICE_NAME` (aec-api), `DATABASE_URL` (postgresql+psycopg://aec:aec@localhost:5432/aec), `DATABASE_URL_SECRET` (Secrets Manager id; JSON `DATABASE_URL` key or raw URL), `CORS_ORIGINS` (["http://localhost:3000"]), `API_PUBLIC_BASE_URL` |
| Auth | `AUTH_PROVIDER` (local\|cognito), `LOCAL_JWT_SECRET`, `LOCAL_JWT_TTL_SECONDS`, `AWS_REGION` (us-east-1), `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`, `COGNITO_CLIENT_SECRET` |
| Entra SSO | `ENTRA_SSO_ENABLED` (false), `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_ALLOWED_AUDIENCES` |
| Storage | `STORAGE_PROVIDER` (local\|s3), `LOCAL_STORAGE_DIR`, `S3_BUCKET_NAME`, `S3_ENDPOINT_URL`, `PRESIGNED_URL_TTL_SECONDS` (900) |
| Uploads | `MAX_UPLOAD_BYTES` (25 MiB), `MAX_IMAGE_PIXELS` (64 000 000), `IMAGE_MAX_DIMENSION` (2400), `MAX_PROJECTS_PER_USER` (200), `MAX_FLOORPLANS_PER_PROJECT` (100) |
| Processing | `QUEUE_PROVIDER` (local; inline\|local\|sqs), `SQS_QUEUE_URL`, `PROCESSING_MAX_ATTEMPTS` (3), `PROCESSING_STALE_SECONDS` (600; keep < SQS visibility timeout), `PROCESSING_WORKER_POLL_SECONDS` (5) |
| CV | `OCR_PROVIDER` (auto), `TESSERACT_CMD`, `GOOGLE_APPLICATION_CREDENTIALS`, `OBJECT_DETECTOR` (heuristic), `YOLO_WEIGHTS_PATH` |
| AI | `SEMANTIC_AI_PROVIDER` (rules), `SEMANTIC_AI_MODEL`, `COMMAND_AI_PROVIDER` (rules), `COMMAND_AI_MODEL`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` |
| Voice | `SPEECH_PROVIDER` (stub\|google), `SPEECH_LANGUAGE` (en-US), `MAX_AUDIO_BYTES` (10 MiB), `GOOGLE_CLOUD_PROJECT` |
| Observability | `METRICS_PROVIDER` (logging\|none), `METRICS_NAMESPACE` (aec), `LOG_FORMAT` (json\|text) |
| Resilience | `EXTERNAL_CALL_MAX_ATTEMPTS` (3), `EXTERNAL_CALL_BACKOFF_SECONDS` (0.5) |
| Rate limits | `RATE_LIMIT_ENABLED` (true), `RATE_LIMIT_PER_MINUTE` (300), `RATE_LIMIT_AUTH_PER_MINUTE` (20), `RATE_LIMIT_WRITE_PER_MINUTE` (90), `TRUSTED_PROXY_COUNT` (0), `LOGIN_MAX_FAILURES` (8), `LOGIN_LOCKOUT_SECONDS` (900) |
| Web (build-time) | `NEXT_PUBLIC_API_URL` (http://localhost:8000), `NEXT_PUBLIC_ENTRA_CLIENT_ID`, `NEXT_PUBLIC_ENTRA_TENANT_ID`, optional `NEXT_PUBLIC_ENTRA_SCOPES`, `NEXT_PUBLIC_ENTRA_REDIRECT_URI` |
| Compose | `POSTGRES_USER/PASSWORD/DB`, `LOCAL_JWT_SECRET` (**required**; compose refuses to start without it) |

`NEXT_PUBLIC_*` are inlined at **build** time (Docker build args), not runtime.

---

## 16. Security, resilience, observability

**Security controls in code:** server-side identity only; owner-scoped repositories + IDOR sweep test; upload hardening (magic bytes, bombs, truncated/encrypted PDFs, body cap); safe object keys; signed/expiring URLs; Argon2id; account lockout; spoof-resistant client IP; default-secret/CORS/SQLite guards in deployed envs; CORS narrowed to `GET/POST/DELETE/OPTIONS` and `Authorization/Content-Type`; no stack traces to clients; `Content-Disposition` CRLF stripping; open-redirect guard (`safeNext`) on `?next=`; account-takeover guard (email under a different provider → 409); web CSP (`default-src 'self'`; `script-src 'self' 'unsafe-inline'` (+`unsafe-eval` in dev); `connect-src` = self + API origin + `login.microsoftonline.com`; `frame-ancestors 'none'`; `object-src 'none'`), X-Frame-Options, nosniff, Referrer-Policy, Permissions-Policy (`microphone=(self)`), COOP, HSTS in prod; `X-Powered-By` removed. CI runs `pip-audit` and `npm audit --omit=dev --audit-level=high`.

**Resilience:** `call_with_retry` (bounded exponential backoff; re-raises the last error) wraps SQS publish, Speech `recognize`, LLM `_complete`; `CircuitBreaker` (5 failures → open 30 s → half-open) exists. Degradation table:

| Failure | Result |
|---|---|
| SQS publish fails after retries | job `FAILED`, 503, re-runnable |
| Worker/Lambda crash | redelivery (visibility timeout) → DLQ after `maxReceiveCount`; stale-claim recovery; attempt cap |
| OCR / semantic AI down | stage `degraded`, job still `COMPLETED` |
| LLM parser down | edit `REJECTED` at `parse`, model unchanged, audited |
| Speech down | 502, model unchanged |
| S3 / RDS error | 502 / 500; every mutation is one transaction |
| Entra down | new SSO sign-ins fail; issued tokens still verify offline; local/Cognito unaffected |

**Observability:** JSON logs with a `RedactingFilter` (scrubs `*key*/token/password/secret/authorization=…`, `Bearer …`, `sk-…`, `ghp_…`, JWTs). Metrics are **CloudWatch Embedded Metric Format** lines written to the `app.metrics` logger via its **own handler with `propagate=False`** (an earlier bug nested `_aws` inside the JSON wrapper so CloudWatch never extracted metrics). Metric names: `pipeline.duration_ms`, `pipeline.run{status}`, `pipeline.failed`, `pipeline.stage.duration_ms{stage,status}`, `pipeline.stage.degraded`, `edit.duration_ms`, `edit.command{status,operation,entry}`, `geometry.command.failed`, `ai.latency_ms`, `ai.error`, `queue.enqueue.failed`, `queue.message.unparseable`, `external.error{service,error_type}`, `external.retry.recovered`, `external.circuit_open`. `timer()`/`timed()` helpers; `METRICS_PROVIDER=none` disables.

---

## 17. Frontend (Next.js)

`apps/web/src` (App Router, all data fetching client-side with a bearer token; no SSR data path).

### Routes

| Route | Purpose |
|---|---|
| `/login`, `/register` | Public. Login honours `?next=` (via `safeNext`), shows "Sign in with Microsoft" only if `NEXT_PUBLIC_ENTRA_*` set, surfaces unconfirmed-email flow. Register gives live password feedback (`lib/password.ts`). |
| `/confirm`, `/forgot-password`, `/reset-password` | Email-code confirmation, resend, reset flow. |
| `/auth/sso/callback` | Parses the Entra fragment (`state` checked), calls `loginWithToken`. |
| `/` | Dashboard: stats, empty/loading/error states, "New project". |
| `/projects` | List + create. |
| `/projects/[id]` | Upload (drag-drop, XHR progress, client pre-checks: type, empty, 25 MB), **auto-starts processing after upload**, floor-plan list, delete with `ConfirmDialog`, shows upload warnings (e.g. multi-page PDF). |
| `/projects/[id]/floorplans/[fpId]` | Processing control + stage timeline + (once a model exists) AI command panel, insights panel, interactive viewer, detected-element counts, coordinate-system note, rooms table, dimension list, artifact links. |
| `error.tsx`, `loading.tsx`, `not-found.tsx` | Global boundaries. |

### Key modules

- `lib/api.ts` — typed fetch client; `ApiError{status,message,code}`; `withAuth` retries once after a silent token refresh on 401, else `onUnauthorized` (clears session, navigates to `/login?next=…`); special handling for 429 `Retry-After`; `XMLHttpRequest` for upload progress; `postAudio` for voice.
- `lib/auth-context.tsx` — tokens in `localStorage` (`aec.access_token`, `aec.refresh_token`, `aec.email`); **a stored token is discarded only when the server positively rejects it** (a network blip / 5xx / 429 must not log the user out); one shared in-flight refresh.
- `lib/render/` — **deterministic renderer**: `buildScene(model) → Scene` (flat ordered primitives in model coordinates; draw order rooms → labels → walls → windows → doors → columns → stairs → furniture → dimensions; 2-dp rounding; invalid elements skipped, null model → empty scene), `sceneToSvgString` (byte-identical, escaped), `view-transform.ts` (`modelToScreen`/`screenToModel` exact inverses, `fitTransform`, `zoomAt` cursor-anchored with limits 0.02–40, `panBy`).
- `lib/model/` — `geometry.ts` (area/perimeter/centroid/point-in-polygon/bounds), `units.ts` (px vs mm/m formatting; never fakes a conversion), `derive.ts` (`describeElement` → sidebar facts).
- `components/viewer/` — `FloorPlanViewer` (state = transform/selection/hover only; model stays a prop), `FloorPlanCanvas` (single `<g transform>` updated **imperatively** during pan/wheel and committed to React state once per gesture; event-delegated hit testing via `data-element-id`), memoised `BaseLayer` + thin `HighlightLayer`, `PropertySidebar`, `ViewerToolbar`, optional "show original drawing" underlay (the preprocessed artifact at 55 % opacity model overlay), re-fit on resize unless user has panned.
- `components/editor/ai-command-panel.tsx` — text box with **Preview** (interpret) and **Apply**, Undo/Redo gated on history, **🎤 Speak** (MediaRecorder → voice endpoint, shows "Heard: …"), history list, clarification picker (re-sends the chosen id), stale-model handling (refreshes the view and explains). All writes pass `expected_version`.
- `components/editor/selection-actions.tsx` — point-and-click editing for the selected element; builds the **same structured commands** (MOVE_WALL perpendicular only, ADD_DOOR/WINDOW, DELETE_*, SET_SCALE, RENAME_ROOM, RESIZE_ROOM) and sends them through the server pipeline — the client never changes geometry.
- `components/insights/building-insights-panel.tsx`, `components/states.tsx` (`Spinner`, `SkeletonList`, `EmptyState`, `ErrorState` with retry, `ConfirmDialog` with `role="dialog"`/Escape/focus), `components/ui.tsx` (design-system primitives: Button/IconButton/TextField/Alert/StatusBadge/Card/PageHeader/Stat/Chip/…), `nav-bar.tsx`, `require-auth.tsx` (client guard; backend is the real authority).
- Polling: 2 s while `PENDING/PROCESSING`; after 60 s every 6 s; after 10 min shows a "taking longer than usual" warning. A job is "running" only if `PROCESSING` or (`PENDING` with `started_at`); a fresh `PENDING` job shows an enabled **Start processing** (fixes an earlier bug).
- Styling: Tailwind 4 with CSS variables (`globals.css`, 570 lines; aurora background, glass, gradient accents).

---

## 18. Testing & CI

**Backend** (`apps/api/tests`, 43 modules, **354 tests passed** in ~29 s offline): SQLite in-memory via `create_all`; `conftest.py` forces offline config (including blanking `DATABASE_URL_SECRET` so a developer's real `.env` can't trigger AWS calls); `moto` for S3; fake boto3 clients for Cognito/SQS; offline RS256/JWKS keys for Cognito/Entra; scripted `MockCommandParser`; synthetic plan fixtures (`synthetic_plan.py` two-room plan, `apartment_plan.py` 5-room apartment with doors/window/stair/text/hatching, `edit_model.py` hand-built model).

Highlights by area: auth (`test_auth`, `test_auth_hardening` — lockout, refresh, revocation, reset, spoofed XFF), `test_cognito_auth`, `test_entra_auth`; uploads (`test_upload_validation`, `test_upload_hardening`); storage (`test_storage_service`); CV (`test_preprocess`, `test_walls`, `test_rooms_and_calibrate`, `test_object_normalize`, `test_cv_apartment`, `test_ocr_parsing`, `test_pipeline`, `test_processing_api`, `test_processing_retry_cap`); domain (`test_coordinates_and_model`, `test_relationships`, `test_insights*`); editing (`test_command_models`, `test_command_parser_rules`, `test_entity_resolution`, `test_geometry_engine`, `test_geometry_integrity`, `test_editing_pipeline`, `test_editing_api`); voice (`test_speech_service`, `test_voice_api`); reliability (`test_reliability` — parallel starts/edits, reprocess+undo, `test_resilience`, `test_cloud_failure_handling`, `test_lambda_handler`, `test_observability`, `test_rate_limit`); `test_migrations` (alembic vs models); `test_config_and_projects`; `test_security` (IDOR sweep, CORS, safe-500); end-to-end `test_workflow` (register → project → upload → process → model → insights → NL edit → v2 → undo/redo → history, plus failure variant).

**Frontend** (`vitest`, 15 files, **88 tests passed**, jsdom): geometry, view-transform, scene, svg, derive, `api.ts`, password, safe-next, entra, states, insights panel, viewer interactions, AI command panel (text, voice, point-and-click edit).

**CI** (`.github/workflows/ci.yml`): `api` job (ruff, black --check, mypy app, pytest, pip-audit), `web` job (eslint, `tsc --noEmit`, vitest, `next build`, npm audit), `migrations-postgres` job on a real Postgres 16 service (`alembic upgrade head` → `alembic check` → `downgrade base` → `upgrade head`). **The CI file is untracked/uncommitted** — it has never run on GitHub from this repo state.

Caveats: all tests are offline/synthetic. Real floor plans, real Postgres in a human-run session, real GCP/Entra, real browsers' pan/zoom feel have not been verified. `tsc` fails on a cold clone (`LayoutProps` global generated by `next dev`/`next build`) until Next has run once.

---

## 19. Deployment, cloud state & cost

### What is actually live (per `SETUP_PROGRESS.md` / `context.md`, last verified Aug–Sep 2026)

Single-cloud **AWS**, region **`ap-south-1`**, account `615371646456` (free-tier-only mode), IAM user `aec-dev`. GCP and Azure were **skipped on purpose**.

| Service | Resource | Notes |
|---|---|---|
| Cognito | pool `ap-south-1_bfbnZaKBS` (`aec-platform-dev`), email-as-username, public app client with `ALLOW_USER_PASSWORD_AUTH` | verified end-to-end; no UI code-entry for confirmation originally (a `/confirm` page now exists) |
| S3 | `aec-floorplans-vajeeda-dev` | Block Public Access, SSE-S3, 30-day lifecycle; presigned URLs |
| SQS | `aec-processing` + DLQ (`maxReceiveCount=5`), visibility 720 s | |
| Lambda | `aec-processing` container image (`Dockerfile.lambda`), 2048 MB / 120 s, SQS event source (batch 5, `ReportBatchItemFailures`) | built on a throwaway t3.micro EC2 (CodeBuild unavailable); replaced the local worker; ~6.5 s cold / 4.5 s warm for the 8-stage pipeline |
| RDS | `aec-db` PostgreSQL 16.15, `db.t4g.micro`, 20 GB gp3, public, SG on 5432 | **the only standing cost** (~$13/mo after the free year) |
| Secrets Manager | `aec/database-url` (`DATABASE_URL_SECRET`) | DB password no longer in env/`.env` |
| CloudWatch | `/aws/lambda/aec-processing` (14 d), EMF → `aec` namespace, alarm `aec-pipeline-failed` → SNS `aec-alerts` (email subscription is a manual step), dashboard `aec-review` | |

Only the **API and web run locally**; worker/data/auth are on AWS. Topology: Browser → local Next.js → local FastAPI → Cognito/RDS/S3/SQS → Lambda → RDS+S3 → CloudWatch.

### Not built for production
API Gateway, API hosting (App Runner/ECS), IaC (Terraform/CDK — `infrastructure/*` are READMEs), CloudWatch dashboards beyond the manual one, MSAL PKCE for Entra, SES, GCP/Azure deployments, a shared (Redis/edge) rate limiter.

### Production checklist (from the docs)
`ENVIRONMENT=production` (forces cognito+s3), RDS + `alembic upgrade head`, `QUEUE_PROVIDER=sqs` + Lambda/Cloud Run + DLQ, HTTPS/LB, real `CORS_ORIGINS`, `TRUSTED_PROXY_COUNT`, edge rate limiting, secrets in a manager, IAM roles (not access keys), JSON logs + metrics.

### Cost principles
Scale-to-zero compute; offline defaults; 30-day S3 lifecycle; 14-day log retention; budget alarms; teardown commands in `SETUP_PROGRESS.md` (delete RDS first — it's the only always-on cost). `AWS_MIGRATION_PLAN.md` would swap Cloud Vision→Textract, Gemini→Bedrock, Speech→Transcribe, drop Entra→Cognito federation (**not executed**; requires amending `claude.md` §§5–6 because the charter mandates multi-cloud).

---

## 20. Phase history & feature status

| Phase | Delivered |
|---|---|
| **0 Foundation** | Monorepo, Next shell, FastAPI `/health`, SQLAlchemy/Alembic wiring (no tables on purpose), Docker Compose, lint/test tooling. |
| **1 Auth, projects, upload** | `AuthService` (local/Cognito), owner-scoped projects, validated versioned uploads, `StorageService` (local/S3), `ProcessingJob` on upload, migration 0001. |
| **2 Floor-plan intelligence** | `QueueService`, 8-stage async CV pipeline, graceful degradation, typed Building Model, pixel coords + optional scale, artifacts, migration 0002, SQS worker. |
| **3 Viewer** | Deterministic scene/SVG renderer, pan/zoom/fit/hover/select, property sidebar, wall↔room linking, Vitest. |
| **4 AI editing** | Command union, `CommandParser` (rules + LLMs), `EditPipeline`, entity resolution + clarification, Shapely engine, versioning/undo/redo, audit log, migration 0003. |
| **5 Multi-cloud/voice/resilience/observability** | Entra SSO (additive), voice commands through the same pipeline, retry + breaker, JSON logging + redaction, EMF metrics, Lambda handler / Cloud Run parity. |
| **6 Reliability/polish/insights/security** | Deterministic insights, enforced attempt cap, rate limiting, security review + fixes, shared state components, runbook & testing docs. |
| **Production-readiness pass** (uncommitted) | See below. |

### The production-readiness pass (`docs/PRODUCTION_READINESS.md`; reproduced → fixed → tested)
Reliability R1–R9 (atomic job claim/idempotent runs/stale recovery; re-process keeps edits reachable via Undo; optimistic concurrency + CAS HEAD + 409; tz-aware timestamps; migration `0004` FKs + `alembic check` test; delete commits DB before blobs; pagination + N+1 fix + quotas; 500s carry CORS headers; voice routes off the event loop). Security S1–S10 (trusted-proxy-aware IP + per-account lockout; deployed-env secret/CORS/SQLite guards; logout revocation + refresh tokens; password policy; account-takeover guard; timing-safe login; decompression-bomb/PDF hardening; dependency upgrades; security headers/CSP; `safeNext`). Core product P1–P7 (stroke-thickness wall model, openings as gaps on continuous walls, validated door swings, stairs, rooms to centre-lines; sideways-only wall moves with connected-wall re-projection and room-corner follow; delete-wall merges rooms and refuses exterior walls; `OCR_PROVIDER=auto`, `RENAME_ROOM`, `SET_SCALE`; clarification picker; point-and-click selection editing; exterior-wall insight fix). Frontend/ops items (token resilience, confirm/forgot/reset pages, boundaries, page titles, polling back-off, viewer re-fit/underlay, non-root images with healthchecks, Tesseract in the API image, migrate as a one-shot compose service, CI).

### Feature-status labels (policy)
Everything implemented is `TESTED` at best; **no feature is `VERIFIED`**. `docs/FEATURE_STATUS.md` tracks per-feature rows (its Phase tables are accurate for Phases 0–6; the production pass is a short table at the bottom).

Explicitly **NOT_STARTED**: quantity takeoff, cost estimation, building-code compliance, architectural-grade geometry validation, custom CV models, server-side rendering/export (SVG/PNG/PDF/thumbnails), DWG/DXF/IFC/Revit import, real-time collaboration, manual scale-calibration UI beyond the `SET_SCALE` command, MSAL PKCE, SES, API Gateway, IaC.

---

## 21. Known limitations, gaps, and doc drift

### Product / technical limitations
- **CV accuracy is only proven on synthetic plans** (`tests/fixtures`). No real-plan evaluation has been done. Hairline-double-line walls, curved walls, and noisy scans are unsupported.
- Default OCR is weak: without Tesseract (bundled in the Docker image; **not** present on a plain Windows dev box) rooms are unlabelled and the scale is unknown until the user names rooms and uses **Set scale** in the editor. Consequently "the kitchen wall" and `mm` commands only work after labelling/calibration; pixel distances and click-selection always work.
- Entity resolution still depends on wall↔room linking; rooms with empty `wall_ids` produce errors/clarifications for room-based wall references.
- Geometry validation is structural only (no code/structural reasoning). `RESIZE_ROOM` assumes a side formed by movable, roughly axis-aligned walls.
- Exterior-wall classification is "rooms on both sides = interior", approximate when linking is incomplete.
- Only PDF page 1 is processed.
- Local-auth logout revocation and the rate limiter are **per process**. Cognito logout can't revoke an already-issued access token (verified offline; keep lifetimes short). Entra frontend uses the **implicit flow** (move to MSAL + PKCE).
- Voice: Safari/`audio/mp4` rejected (415). Cognito MFA/NEW_PASSWORD challenges unsupported.
- The `local` queue provider loses an in-flight hand-off on restart (job stays `PENDING`; re-press Start).
- JSON-document model storage means no SQL-level queries over elements (D11).

### Verification gaps
Nothing is `VERIFIED`. Postgres was exercised manually (Aug 2026: migrations round-trip on live PG 16 and RDS) but the production-readiness pass was developed on SQLite; its row-lock/CAS paths are covered by the CI Postgres job **which has not run** (workflow uncommitted). Real GCP (Speech/Vision/Gemini), real Entra tenant, real LLM parsers, Docker compose end-to-end, and real-browser pan/zoom feel are unverified.

### Working-tree state (as of generation)
Branch `main`, last commit `b33df52 UI Polish of MVP`. **71 tracked files modified and ~27 untracked** (the whole production-readiness pass: `.github/`, `middleware.py`, `strokes.py`, migration `0004`, new tests, new frontend pages/components, `docs/PRODUCTION_READINESS.md`). Git warns that CRLF will become LF on next touch. Root `.env` and `apps/api/.env` exist locally (gitignored; contain real credentials/ids) — do not commit.

### Doc drift (the code is right; the doc is stale)
1. `README.md` — says Phase 3 / 68 tests / `next lint`; reality is Phases 0–6 + hardening, 354 + 88 tests.
2. `PROJECT_OVERVIEW.md`, `docs/FEATURE_STATUS.md` headline, `docs/TESTING.md` — quote 270 backend / 65 frontend tests; now 354 / 88. Rate-limit numbers in these (write 40/min, read 120/min) are old; current defaults are 90 and 300.
3. `docs/GEOMETRY_ENGINE.md` — describes free-direction translation, 1.5 px coincident-endpoint connectivity, and "8 operations"; the code now enforces sideways-only moves with re-projection, has 10 operations (adds `RENAME_ROOM`, `SET_SCALE`), merge-on-delete, and the richer constraint set in §9.
4. `docs/COMMAND_SYSTEM.md` — lists 8 operations; two more exist.
5. **LLM system prompt omits `RENAME_ROOM` and `SET_SCALE`** (`editing/ai_providers.py`): with an LLM parser those two operations can't be produced from free text (they still work from the UI and the rules parser for rename).
6. `docs/ARCHITECTURE.md` "Repository layout" still says "Next.js 16 … services placeholders — Phase 2+" and omits Phase-6+ items like `middleware.py`; `docs/HUMAN_TASKS.md` item 9 ("repo on master with no commits") is stale.
7. `domain/enums.py::ProcessingStatus` docstring still says "the pipeline … does not exist yet".
8. `semantic/rules.py` has a no-op ternary (both branches `INFERRED`).
9. `context.md` §5 lists "Entra `auth_provider` label wrong" — **fixed** in code (`_provider_for` uses `provider_for(token)`), though `POST /auth/register` still records `settings.auth_provider` (correct, since register is always the primary provider).
10. `AWS_MIGRATION_PLAN.md` describes a change that has **not** happened: GCP/Entra/Gemini code is still present.
11. Starlette now deprecates `HTTP_422_UNPROCESSABLE_ENTITY` / `HTTP_413_REQUEST_ENTITY_TOO_LARGE` (warnings in test output); `datetime.utcnow()` warnings come from botocore inside moto tests.

---

## 22. How to run everything

### Quick offline run (no cloud, no Docker)
```bash
# Backend (Windows: use `py -3.13`; python may be a Store stub)
cd apps/api
py -3.13 -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt     # large wheels; slow links need --retries 10 --timeout 120
cp .env.example .env                                                   # then edit as needed
# SQLite smoke setup (no Postgres): create schema, then serve
PYTHONPATH=. DATABASE_URL="sqlite+pysqlite:///./dev_smoke.db" ./.venv/Scripts/python.exe \
  -c "from app.db.base import Base; from app.db.session import engine; import app.db.models; Base.metadata.create_all(engine)"
PYTHONPATH=. DATABASE_URL="sqlite+pysqlite:///./dev_smoke.db" RATE_LIMIT_ENABLED=false \
  ./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000

# Frontend (separate shell)
cd apps/web && npm install && cp .env.example .env.local && npm run dev   # http://localhost:3000
```

### Docker Compose
```bash
cp .env.example .env     # set LOCAL_JWT_SECRET to a long random value (compose refuses without it)
docker compose up --build   # postgres → migrate (alembic upgrade head) → api :8000 → web :3000 (all bound to 127.0.0.1)
```

### Checks
```bash
cd apps/api && python -m pytest -q && ruff check . && black --check . && mypy app
cd apps/web && npm run lint && npx tsc --noEmit && npm test && npm run build
```
(Cold clone: run `next dev` or `next build` once before `tsc`, to generate `LayoutProps`. On Windows/OneDrive a locked `.next` can break `next build`; delete it and rebuild.)

### Synthetic test plan
`cd apps/api && PYTHONPATH=. python -c "from tests.fixtures.synthetic_plan import make_two_room_plan; open('plan.png','wb').write(make_two_room_plan().png_bytes)"`

### Typical user flow to demo
Register → create project → upload plan (auto-starts processing) → watch 8 stages → viewer + insights → type "delete the door" (→ clarification with picker) or click a wall and use the editor buttons → Apply → v2 → Undo/Redo → history. For metric commands: select a wall → **Set scale** with its real length, or name rooms first.

### Cloud operations
See `SETUP_PROGRESS.md` for live resource IDs and the full teardown script (delete RDS first), `DEMO_SCRIPT.md` for the live AWS demo, `docs/AWS_SETUP.md` / `GCP_SETUP.md` / `AZURE_SETUP.md` / `AI_SETUP.md` for provider steps.

---

## 23. Documentation map

| File | Contents | Trust level |
|---|---|---|
| `CLAUDE.md` / `claude.md` | Charter and rules for the AI engineer | Authoritative (intent) |
| `docs/DECISIONS.md` | D1–D30 with context/options/tradeoffs | Accurate for D1–D30 |
| `docs/PRODUCTION_READINESS.md` | R/S/P findings and limits of the hardening pass | Accurate (most current) |
| `docs/ARCHITECTURE.md` | Phase-by-phase architecture | Mostly accurate; pre-hardening in places |
| `docs/FEATURE_STATUS.md` | Per-feature status tables | Accurate statuses; test counts stale |
| `docs/COMMAND_SYSTEM.md`, `docs/GEOMETRY_ENGINE.md` | Editing & geometry | **Stale in details** (see §21) |
| `docs/MULTI_CLOUD_ARCHITECTURE.md`, `CLOUD_SERVICES.md`, `COST_OPTIMIZATION.md` | Provider ownership, per-service failure/cost/teardown | Design intent; GCP/Azure never live |
| `docs/AWS_SETUP.md`, `GCP_SETUP.md`, `AZURE_SETUP.md`, `AI_SETUP.md` | Manual setup steps | Reference |
| `docs/HUMAN_TASKS.md` | Manual tasks by phase (REQUIRED NOW / OPTIONAL / LATER) | Partly stale |
| `docs/TESTING.md`, `docs/DEMO_RUNBOOK.md` | How to test / demo | Counts stale |
| `PROJECT_OVERVIEW.md`, `context.md` | Overview and session handoff (Aug 2026) | Good narrative; numbers stale |
| `final.md`, `SETUP_GUIDE.md`, `SETUP_PROGRESS.md`, `DEMO_SCRIPT.md`, `VIDEO_SCRIPT.md`, `Review-1.md` | Setup, live AWS state, demo/video scripts, review module ranking | Reference / presentation |
| `AWS_MIGRATION_PLAN.md` | Unexecuted GCP/Azure→AWS consolidation plan | Plan only |
| `phase0.md`–`phase6.md` | Original prompts given per phase | Historical requirements |

---

## 24. Glossary & gotchas

- **Building Model / FloorPlanModel** — the canonical structured plan (JSON, versioned).
- **HEAD** — `floorplans.current_model_version`; the version the app treats as current.
- **Clarification** — the system's refusal to guess; returns candidate ids/labels.
- **Opening** — door/window; attached to a wall by `wall_id`, represented as a bbox.
- **`mm_per_pixel`** — optional scale; absence means world units are unavailable (never faked).
- **EMF** — CloudWatch Embedded Metric Format (metrics as structured log lines).
- **Gotchas:** (1) The class is named `HoughWallDetector` but is a thickness-aware morphology+Hough hybrid. (2) Uploading creates a `PENDING` job but only `POST /process` enqueues it (the web app now calls it automatically). (3) `get_latest_for_floorplan` ≠ current model — use `get_head`. (4) The `write` rate bucket includes edit/undo/redo calls. (5) The default `LOCAL_JWT_SECRET` also signs local storage URLs. (6) Local password-reset codes appear in the API log. (7) Windows `python` may be a Store stub → `py -3.13`. (8) Chrome-devtools hard navigations can wipe `localStorage` in automated runs. (9) Setting `ENVIRONMENT=production` with local providers will (intentionally) crash at startup.

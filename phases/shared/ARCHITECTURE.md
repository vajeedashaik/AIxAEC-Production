# AEC AI Platform: Architecture (confirmed)

> Status: **CONFIRMED**. Every phase builds against this document. Changing it requires the integration phase (P7) or an explicit decision by the project owner.

## 1. Product in one paragraph

A user signs in, creates a project and uploads a floor plan (PNG / JPG / PDF). A computer-vision service turns the drawing into a **structured, typed, versioned Building Model**: walls, rooms, doors, windows, columns, stairs, furniture and dimensions. The user explores the model in an interactive vector viewer and edits it with **typed or spoken natural-language commands** ("move the wall between the kitchen and the living room 300 mm left") or with point-and-click actions. Language models only *interpret* text into a structured command. A **deterministic geometry engine** performs, validates and explains every change. Every change becomes a new immutable version with undo/redo and an audit trail.

**Mantra:** *AI interprets → structured commands describe intent → validation checks intent → geometry computes change → the Building Model stores truth → the renderer displays truth.*

## 2. Non-negotiable rules (inherited from the original charter)

| Rule | Meaning |
|---|---|
| A floor plan is a structured model, not an image | `FloorPlanModel` JSON is canonical. The upload is never re-edited. |
| The LLM never edits geometry | LLM output is a *command dict* only, re-validated as untrusted input. Only the geometry service writes coordinates. |
| AI output is untrusted | `parse → schema → resolve → semantic → geometry → constraints → persist`. `extra="forbid"` everywhere. |
| Don't guess on ambiguity | Return `CLARIFICATION` with described candidates, never pick silently. |
| Pixels ≠ millimetres | Geometry is stored in image pixels. `mm_per_pixel` is optional. `mm` commands are **rejected** without a calibrated scale. |
| Geometry integrity | Validate → propose → validate → commit-or-rollback. A failed edit never corrupts the stored model. |
| Append-only versions | Model versions are never overwritten. Undo/redo move a HEAD pointer. |
| Explicit job states | `PENDING / PROCESSING / COMPLETED / FAILED`, and the jobs table is the source of truth. |
| Providers behind interfaces | OCR, STT, LLM, storage and object detection sit behind small interfaces with an offline default, so a missing key degrades and never crashes. |
| Honest status | `NOT_STARTED / IN_PROGRESS / IMPLEMENTED / TESTED / VERIFIED`. Only a human-run real check earns `VERIFIED`. |
| Zero cloud-vendor lock | **No AWS, GCP or Azure service of any kind.** Free tiers or self-hosted only. |

## 3. System diagram

```
                        ┌──────────────────────────── Clerk (hosted auth, free tier) ───────────────────────────┐
                        │  sign-in UI, sessions, JWT (RS256, JWKS)                                              │
                        ▼                                                                                        │
┌──────────────────────────────┐   Bearer <Clerk session JWT>   ┌───────────────────────────────────────────┐   │
│ apps/web  (Next.js 16, :3000)│ ─────────────────────────────► │ services/api  (FastAPI, :8000)            │ ◄─┘ verifies JWT via JWKS
│ landing · dashboard · upload │                                │ the ONLY public backend & ONLY DB client   │
│ viewer · AI command panel    │ ◄───────────── JSON ────────── │ projects · uploads · jobs · versions ·     │
└──────────────────────────────┘                                │ undo/redo · audit · edit orchestration    │
                                                                │ + worker process (python -m app.worker)    │
                                                                └──────┬───────────────┬──────────────┬──────┘
                                              X-Internal-Token (HTTP)  │               │              │
                          ┌────────────────────────────────────────────┘               │              │
                          ▼                                                            ▼              ▼
          ┌───────────────────────────────┐  ┌───────────────────────────────┐  ┌──────────────────────────────┐
          │ services/vision  (:8001)      │  │ services/geometry  (:8002)    │  │ services/language  (:8003)   │
          │ image/PDF → FloorPlanModel    │  │ resolve · validate · apply    │  │ NL → command (rules + LLM)   │
          │ OpenCV · Tesseract · PyMuPDF  │  │ Shapely · deterministic       │  │ room-label classify          │
          │ stateless                     │  │ insights · plan brief         │  │ speech-to-text (whisper)     │
          └───────────────────────────────┘  │ stateless                     │  │ stateless                    │
                                             └───────────────────────────────┘  └──────────────┬───────────────┘
                                                                                               │ OpenAI-compatible
          ┌───────────────────────── Supabase (free tier, or local `supabase start`) ─┐        ▼
          │ Postgres 15+: users, projects, floorplans, jobs, model versions, edits    │  ┌────────────────────┐
          │ Storage: private buckets `floorplans`, `artifacts` (signed URLs)          │  │ OmniRoute (:20128) │
          └───────────────────────────────────────────────────────────────────────────┘  │ free-tier LLM pool │
                         ▲ only services/api talks to Supabase                            └────────────────────┘
```

## 4. Components and their purpose

| Component | Tech | Purpose | Owner phase |
|---|---|---|---|
| `packages/contracts` | Python 3.12, Pydantic v2; JSON Schema → TypeScript | **Single source of truth** for every shape that crosses a boundary: Building Model, commands, inter-service DTOs, public API DTOs, the room-label lexicon and fixtures. | P0 (frozen after) |
| `services/vision` | FastAPI, OpenCV-headless, NumPy, PyMuPDF, Pillow, Tesseract (pytesseract), optional YOLO | Stateless 8-stage CV pipeline: image/PDF → `FloorPlanModel` + stage reports + artifacts. | P1 |
| `services/geometry` | FastAPI, Shapely 2, NumPy | Stateless, deterministic. Entity resolution, semantic validation, the 10 operations, constraint validation, change sets, insights and plan brief. | P2 |
| `services/api` | FastAPI, SQLAlchemy 2 + psycopg 3, supabase-py (Storage), PyJWT (Clerk JWKS), httpx | Public REST API, Clerk auth, owner scoping, uploads, job queue (Postgres `SKIP LOCKED`) and worker, versioning, undo/redo, audit, edit orchestration across services, rate limiting. | P3 |
| `services/language` | FastAPI, OpenAI SDK → OmniRoute, faster-whisper | Offline rule grammar plus an LLM parser (via OmniRoute) for commands. Room-label classification. Local speech-to-text. | P4 |
| `apps/web` shell | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, shadcn/ui, Clerk, TanStack Query, MSW | Landing page, auth screens, dashboard, projects, upload, processing timeline, settings and the design system. | P5 |
| `apps/web` workspace | same stack, plus a dependency-free SVG renderer | Floor-plan workspace: deterministic renderer, pan/zoom viewer, selection, inspector, AI command bar, voice, preview-diff ghost, history, insights. | P6 |
| Integration | Docker Compose, Playwright CLI | Merge, end-to-end flows, contract conformance, hardening and docs. | P7 |

## 5. What replaced each cloud service

| Original (cloud) | Replacement (free) | Notes |
|---|---|---|
| AWS Cognito, Azure Entra ID | **Clerk** | Hosted UI components, social and email sign-in, MFA. Free tier is far beyond our needs. The backend verifies the session JWT offline against Clerk's JWKS. |
| AWS RDS PostgreSQL | **Supabase Postgres** | Free project or local `supabase start`. Migrations live in `services/api/supabase/migrations`. |
| AWS S3 | **Supabase Storage** | Private buckets with short-lived signed URLs. Only `services/api` holds the service-role key. |
| AWS SQS + Lambda | **Postgres job table + worker process** | Atomic claim with `UPDATE … FOR UPDATE SKIP LOCKED`, attempt cap, stale-claim recovery. No broker to run. |
| AWS Secrets Manager | `.env` files (gitignored) per service | `.env.example` committed for every service. |
| CloudWatch EMF metrics | Structured JSON logs to stdout with request IDs and timing fields | Keep it greppable. No metrics backend. |
| Google Cloud Vision OCR | **Tesseract** (local) | Bundled in the vision Docker image. `auto` falls back to a stub if missing. |
| Google Speech-to-Text | **faster-whisper** (local, CPU, int8) | `base.en` default, configurable. Stub provider for tests. |
| Gemini / OpenAI / Claude APIs | **OmniRoute** self-hosted gateway → free-tier providers, plus the offline rules parser | OpenAI-compatible `http://localhost:20128/v1`. MIT, no paid tier, fallback "combos" across free providers. Chosen over FreeLLMAPI because it's fully free, Dockerised and has the larger free pool. |
| Lambda container / Cloud Run | Docker Compose services | Local-first. Deployment to free hosts is optional and out of scope. |

## 6. Key technical decisions

| ID | Decision | Why |
|---|---|---|
| A1 | **Contract-first microservices**: four Python services and one web app, all speaking the shapes in `packages/contracts`. | Enables six independent Claude sessions to build in parallel without touching each other's files. |
| A2 | **Only `services/api` touches Supabase.** Other services are stateless and receive and return data over HTTP. | One security boundary, one place for credentials, trivially testable services. |
| A3 | Inter-service auth uses a shared secret header `X-Internal-Token`. Internal services are not published outside the Docker network. | Free, simple and enough for a local-first deployment. |
| A4 | Room-label rules (lexicon) live in `aec_contracts.lexicon`. | Vision (labelling), geometry (entity resolution) and language (classification) all need the same synonyms. |
| A5 | Geometry `execute` supports `dry_run` and returns a `ChangeSet`. | Powers the **preview ghost** in the UI before Apply. |
| A6 | Edit orchestration lives in `services/api`: parse (language) → schema (contracts) → execute (geometry) → persist (api). | The API is the only component that has both the HEAD version and the DB transaction. |
| A7 | Default command parsing is `hybrid`: rules first, then the LLM if rules return `UNKNOWN`, then `UNKNOWN`. | Works fully offline. The LLM improves coverage but is never required. |
| A8 | Models are stored as **one JSON document per version** (`jsonb`). | Same as the original D11. Simple, append-only, fast to load. |
| A9 | The renderer is a **dependency-free deterministic TS module** (`buildScene(model) → Scene → SVG`). | Byte-identical output is testable, and the viewer has no canvas library lock-in. |
| A10 | The web app talks only to `services/api` (never to Supabase directly). Status updates use polling with back-off. | No RLS policy surface to get wrong, and fewer moving parts. |
| A11 | Python per-service environments via **uv**. Node via **npm** (no workspaces; one lockfile, owned by `apps/web`). | No shared lockfile means no cross-session lockfile collisions. |

## 7. Ports

| Service | Port |
|---|---|
| web (P5 / prod dev server) | 3000 |
| web (P6 dev server, to avoid clashing) | 3001 |
| api | 8000 |
| vision | 8001 |
| geometry | 8002 |
| language | 8003 |
| OmniRoute | 20128 |
| Supabase local (API / DB / Studio) | 54321 / 54322 / 54323 |

## 8. Free-tier notes and limits

- **Clerk** free tier is ample for development. Keyless mode works in local development without keys.
- **Supabase** free tier gives 500 MB DB and 1 GB storage, and **pauses after 7 days of inactivity**. For development, prefer `supabase start` (Docker, unlimited, offline).
- **OmniRoute** costs nothing itself. Free capacity comes from provider free tiers (Groq, Google AI Studio, OpenRouter free models, Cerebras, Mistral…) added in its dashboard. Rate limits apply, which is why the rules parser is always the fallback.
- Everything else (Tesseract, faster-whisper, OpenCV, Shapely) is local and free.

# AEC AI Platform: Tech Stack Analysis

Versions below come from the manifests (`package.json`, `pyproject.toml`, `ci.yml`, `Dockerfile`s, `supabase/config.toml`) as of 2026-11-09. Ranges like `>=0.115` are minimums; the exact resolved versions are in `uv.lock` and `package-lock.json`. For the design rationale see `phases/shared/ARCHITECTURE.md`.

## 1. At a glance

| Layer | Choice |
|---|---|
| Product | Floor plan → typed, versioned Building Model → edit by text/voice/click → deterministic geometry → immutable versions with undo/redo |
| Architecture | Contract-first microservices, local-first, Docker Compose |
| Web | Next.js 16.4 (App Router), React 19.3, TypeScript 5, Tailwind CSS 4, shadcn/ui |
| Services | 4 × FastAPI on Python 3.12 (`api`, `vision`, `geometry`, `language`) |
| Data | Supabase (Postgres 17 in local config, Storage) |
| Auth | Clerk (`@clerk/nextjs` 7.x on the web, RS256 JWT verified via JWKS in the API) |
| AI | OmniRoute (OpenAI-compatible free-LLM gateway), faster-whisper, Tesseract |
| Tooling | uv, npm, ruff, mypy (strict), pytest, Vitest, Playwright, GitHub Actions |
| Cloud lock-in | None. AWS, GCP and Azure are explicitly excluded |

## 2. Architecture

```
Browser ── Next.js (web :3000) ── Bearer Clerk JWT ──► FastAPI api (:8000) ──► Supabase (Postgres + Storage)
                                                          │  X-Internal-Token
                                      ┌───────────────────┼───────────────────┐
                                      ▼                   ▼                   ▼
                               vision (:8001)      geometry (:8002)     language (:8003) ──► OmniRoute (:20128)
```

Key decisions (from `ARCHITECTURE.md`):

- **A1 Contract-first.** Every shape that crosses a boundary lives in `packages/contracts`.
- **A2 Single data boundary.** Only `services/api` touches Supabase. The other three services are stateless.
- **A3 Internal auth.** Services trust each other through a shared `X-Internal-Token` header, and they are not published outside the Docker network. Only `api` (8000) and `web` (3000) publish ports, on 127.0.0.1.
- **A6 Edit orchestration in the API.** The flow is parse (language) → schema (contracts) → execute (geometry) → persist (api).
- **A8 One JSON document per version** (`jsonb`), append-only. Undo/redo move a HEAD pointer.
- **A10 The web app talks only to the API.** It never talks to Supabase directly. Status updates use polling with back-off.
- **A11 No shared lockfile.** Each Python service has its own uv environment, and Node has a single npm lockfile owned by `apps/web`.

## 3. Frontend: `apps/web`

| Area | Technology | Version |
|---|---|---|
| Framework | Next.js (App Router, Turbopack, `cacheComponents`) | 16.4.3 |
| UI runtime | React / React DOM | 19.3.0 |
| Language | TypeScript | ^5 |
| Styling | Tailwind CSS (+ `@tailwindcss/turbopack`), `tw-animate-css` | ^4 |
| Components | shadcn/ui (`shadcn` CLI ^4.23) on `radix-ui` ^1.8, `cmdk`, `sonner`, `react-resizable-panels` | |
| Class utilities | `class-variance-authority`, `clsx`, `tailwind-merge` | |
| Icons / fonts / motion | `lucide-react`, `geist`, `motion` | |
| Theming | `next-themes` (light/dark, plus a density preference) | ^0.4.6 |
| Server state | TanStack Query | ^5.105 |
| Validation | Zod | ^4.6 |
| Auth | Clerk (`@clerk/nextjs`) | ^7.9 |
| API mocking | MSW | ^3.0 |

Notes:

- **Viewer.** The floor-plan renderer is a dependency-free deterministic TS module (`buildScene(model) → Scene → SVG`). Output is byte-identical, so it is testable, and there is no canvas library lock-in.
- **API client.** A hand-rolled client in `src/lib/api` with `ApiError` and query-key helpers, wrapped by a `QueryProvider`.
- **Feature folders.** `src/features/projects`, `src/features/viewer`, shared `components/ui` and `components/shell` (app shell, command palette, breadcrumbs, theme toggle).
- **Contract types.** TypeScript types are generated from the contracts' JSON Schema with `json-schema-to-typescript` (`npm run gen:contracts`). CI fails if the generated output is stale (`gen:contracts:check`).
- **Known traps.** Next 16 `cacheComponents` needs runtime hooks under `<Suspense>`. Clerk Core 3 replaced `<SignedIn>` with `<Show>`. MSW v3 renamed `onUnhandledRequest` to `onUnhandledFrame`.

## 4. Backend services

All four services share the same shape: FastAPI + Uvicorn + pydantic-settings + httpx, Python `>=3.12,<3.13`, built from `python:3.12-slim` with uv, running as a non-root user (uid 10001) with an HTTP healthcheck.

### 4.1 `services/api`: public REST API (the only DB client)

| Concern | Technology |
|---|---|
| HTTP | FastAPI, Uvicorn, `python-multipart` (uploads) |
| ORM / DB driver | SQLAlchemy ≥2.0.36, psycopg 3 (binary) |
| Storage | `supabase` (supabase-py) ≥2.10 for Storage |
| Auth | `pyjwt[crypto]` verifying Clerk RS256 session JWTs against JWKS (`clerk.py`, `auth.py`) |
| Upload handling | Pillow, PyMuPDF (PDF/image intake) |
| Downstream calls | httpx via `clients/` (`VisionClient`, `GeometryClient`, `LanguageClient`) with `call_with_retry` and a `CircuitBreaker` |
| Job queue | A Postgres table claimed with `UPDATE … FOR UPDATE SKIP LOCKED`, attempt cap and stale-claim recovery. The worker runs as a separate process (`python -m app.worker`). No broker. |
| Cross-cutting | Rate limiting (`ratelimit.py`), structured JSON logs with request IDs (`observability.py`), typed errors (`errors.py`) |
| Domain | `versions.py` (append-only versions, undo/redo), `editing.py` (edit orchestration), `uploads.py`, `jobs.py` |

### 4.2 `services/vision`: stateless CV pipeline

- **Stack.** OpenCV (headless) ≥4.10, NumPy ≥2, PyMuPDF, Pillow, pytesseract (Tesseract OCR). Optional YOLO is mentioned in the architecture doc but is not in the dependencies.
- **Pipeline.** `pipeline/runner.py` and `stages.py` implement an 8-stage pipeline (image/PDF → `FloorPlanModel` + stage reports + artifacts). Stage names seen in the code map include preprocess, wall detection and OCR.
- **Recent work.** Closing door gaps, keeping jogged walls and reading scale from dimension lines (per recent commits).

### 4.3 `services/geometry`: deterministic geometry engine

- **Stack.** Shapely ≥2, with Hypothesis (property-based tests) in dev.
- **Responsibilities.** Entity resolution, semantic and constraint validation, the 10 operations, change sets, `dry_run` (powers the UI's preview ghost), insights and plan brief. Modules: `engine/`, `analysis/`, `insights.py`, `brief.py`.
- **Rule.** The LLM never edits geometry. Only this service writes coordinates.

### 4.4 `services/language`: NL → command

- **Parsing.** An offline rule grammar (`rules.py`, `parsers.py`) plus an LLM parser (`llm.py`) through the `openai` SDK (`>=2,<3`) pointed at OmniRoute. Default mode is `hybrid`: rules first, then the LLM if rules return `UNKNOWN`.
- **Classification.** Room-label classification (`classify.py`) using the shared lexicon.
- **Speech.** faster-whisper (`base.en`, CPU, int8) with PyAV (`av`) and NumPy. A stub provider is used in tests.
- **Test markers.** `slow` (real Whisper model) and `live` (needs a running OmniRoute) are excluded by default.

### 4.5 `packages/contracts`: shared source of truth

- Python 3.12, Pydantic v2 (`>=2.11,<3`), built with Hatchling and installed editable into each service.
- Contains the Building Model, commands, inter-service DTOs, public API DTOs, the room-label lexicon, and test fixtures including a synthetic plan generator (NumPy + OpenCV).
- Exports JSON Schema, which the web app turns into TypeScript.
- `extra="forbid"` is applied everywhere, so unknown fields are rejected.
- Frozen for phases P1–P6.

## 5. Data layer: Supabase

- **Postgres.** Local config targets major version 17 (the architecture doc says 15+). CI validates migrations on Postgres 16. Both are fine as long as no 17-only features are used; worth keeping in sync.
- **Migrations.** `services/api/supabase/migrations/20261101000000_initial_schema.sql` (currently one migration). CI applies every migration in order to a fresh Postgres 16.
- **Storage.** Private buckets `floorplans` and `artifacts` with short-lived signed URLs. Only `services/api` holds the service-role key.
- **Models.** Stored as `jsonb`, one document per immutable version.
- **Local development.** `supabase start` / `supabase db reset` (ports 54321 API, 54322 DB, 54323 Studio).
- **Access pattern.** No RLS policy surface for the web app, because the browser never talks to Supabase directly.

## 6. AI and ML components

| Capability | Provider | Where it runs | Fallback |
|---|---|---|---|
| Command understanding | OmniRoute (OpenAI-compatible gateway over free-tier providers such as Groq, Google AI Studio, OpenRouter, Cerebras, Mistral) | Self-hosted, :20128 | Offline rules parser |
| OCR | Tesseract via pytesseract | Inside the vision image | A stub if Tesseract is missing |
| Speech-to-text | faster-whisper `base.en` | Local CPU, int8 | Stub provider |
| Room-label classification | Shared lexicon + classifier in `language` | Local | n/a |

Safety model: LLM output is untrusted. It passes `parse → schema → resolve → semantic → geometry → constraints → persist`. Ambiguity returns a `CLARIFICATION` with candidates. Pixel coordinates are never treated as mm, and `mm` commands are rejected without a calibrated scale.

## 7. Authentication and security

- **Clerk.** Hosted sign-in UI on the web. The API verifies the session JWT offline against Clerk's JWKS (RS256). Owner scoping is enforced in the API.
- **Inter-service.** The `X-Internal-Token` shared secret, with internal services not exposed outside the Docker network.
- **Secrets.** Per-service `.env` files (gitignored) with committed `.env.example`.
- **Containers.** Non-root user, healthchecks, ports bound to 127.0.0.1.
- **Supply chain.** CI runs `pip-audit` on the exported Python lockfile and `npm audit --omit=dev --audit-level=high` for the web.
- **Docs.** `docs/SECURITY.md`.

## 8. Testing and quality

| Scope | Tools |
|---|---|
| Python | pytest, respx (httpx mocking), Hypothesis (geometry), ruff (`E,F,I,UP,B,W`, line length 120), mypy `strict` with the pydantic plugin |
| Web unit/component | Vitest 5, Testing Library (react, dom, user-event, jest-dom), jsdom 29, MSW |
| Web static | ESLint 9 (`eslint-config-next`), `tsc --noEmit` |
| End to end | Playwright ^1.64 with `@clerk/testing` and `@clerk/backend` (`e2e/`, TypeScript 7 in that package) |
| Contract conformance | Generated TS contracts verified in CI |

## 9. Build, run and CI

- **Orchestration.** The root `compose.yaml` uses Compose `include` of per-service fragments (`services/*/compose.yaml`, `apps/web/compose.yaml`). Services: `vision`, `geometry`, `language`, `api`, `worker`, `web`.
- **Python.** uv (Docker images use `ghcr.io/astral-sh/uv:0.11`, `uv sync --frozen --no-dev`, bytecode compiled).
- **Node.** npm, Node 24 in CI.
- **GitHub Actions** (`ci.yml`):
  - `python`: a matrix over contracts, vision, geometry, language and api, with Postgres 16, Tesseract for vision, then ruff, mypy, pytest and pip-audit.
  - `web`: contract check, lint, `next typegen`, tsc, Vitest, build, npm audit.
  - `migrations`: applies SQL to a fresh Postgres 16.
  - `e2e`: manual (`workflow_dispatch`). It starts local Supabase, builds the Compose stack, then runs Playwright with Clerk dev keys from repo secrets.
- **Ports.** web 3000 (3001 for P6 dev), api 8000, vision 8001, geometry 8002, language 8003, OmniRoute 20128.

## 10. Observability

Structured JSON logs to stdout with request IDs and timing fields. There is no metrics backend by design (replaces CloudWatch EMF).

## 11. Cloud services replaced

| Original | Replacement |
|---|---|
| AWS Cognito / Azure Entra ID | Clerk |
| AWS RDS | Supabase Postgres |
| AWS S3 | Supabase Storage |
| AWS SQS + Lambda | Postgres job table + worker |
| AWS Secrets Manager | `.env` files |
| CloudWatch | JSON logs |
| Google Cloud Vision | Tesseract |
| Google Speech-to-Text | faster-whisper |
| Gemini / OpenAI / Claude APIs | OmniRoute + offline rules |
| Lambda container / Cloud Run | Docker Compose |

## 12. Assessment

**Strengths**

- **Clear trust boundaries.** One data-owning service, stateless compute services, and a frozen contract package keep the surface small.
- **Determinism where it matters.** The LLM only produces a command, and Shapely-based geometry validates and applies it. The deterministic SVG renderer makes output byte-testable.
- **Graceful degradation.** Every external capability (LLM, OCR, STT) has an offline default, so a missing key degrades and never crashes.
- **Low operational weight.** There is no broker, no cache layer and no metrics stack. A Postgres `SKIP LOCKED` queue is enough at this scale.
- **Strict typing and supply-chain checks.** mypy strict, Zod, Pydantic with `extra="forbid"`, generated TS types, and audits in CI.

**Risks and things to watch**

- **Bleeding-edge web versions.** Next 16, React 19.3, Tailwind 4, Clerk Core 3, MSW 3, Vitest 5 and Zod 4 all changed recently. The team has already documented several traps, so look up docs with context7 before upgrading or adding features.
- **Python version pinned to 3.12 only** (`<3.13`) in the services. Contracts allow `>=3.12`.
- **Postgres version drift.** Local Supabase is on 17, CI on 16, and the doc says 15+. Align them to avoid surprises.
- **Single migration so far.** Fine now, but the CI loop applies files in lexical order, so keep the timestamp naming.
- **`openai>=2,<3` as the LLM client.** It works with OmniRoute because the API is OpenAI-compatible, but free-tier providers have rate limits, which is why the rules parser must stay the fallback.
- **Free-tier ceilings.** The hosted Supabase free tier pauses after 7 days of inactivity and has 500 MB DB and 1 GB storage limits.
- **Whisper and OpenCV are CPU-bound.** There is no GPU path and no horizontal scaling story beyond running more worker processes. That is acceptable for local-first use.
- **e2e not in default CI.** It needs Clerk secrets and runs only on manual dispatch, so regressions in the integrated stack are caught late.
- **`e2e` uses TypeScript 7 and `@types/node` 26, while `apps/web` uses TypeScript 5 and `@types/node` 22.** This is harmless but inconsistent.

## 13. Not verified

- Exact resolved versions (lockfiles weren't read).
- The contents of the per-service `compose.yaml` fragments and the `.env.example` files.
- The vision pipeline's eight stage names beyond what the code map shows.
- The Supabase schema's tables and indexes (only the migration filename was listed).

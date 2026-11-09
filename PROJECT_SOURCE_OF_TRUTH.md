# AEC AI Platform: Project Source of Truth

> **Single reference for the whole project:** what it is, why it exists, how it is built, what has been proven, what has not, and the full plan.
> **Last verified:** 2026-11-10, against the working tree on branch `main` (base commit `bd0fcec`, plus uncommitted AWS work: Rekognition OCR, SSM secrets, script fixes, two new docs), live AWS read-only queries and offline test runs. Section 17 holds the AWS detail.
> **Use it for:** presentations, reports, reviews and onboarding. Section 28 maps each section to typical slides and report chapters, and section 29 is a numbers cheat sheet.
>
> **How conflicts are settled:** running code and measured results win over documents. Where an older document disagrees, the disagreement is listed in section 27.
>
> **Status labels used everywhere:** `NOT_STARTED` → `IN_PROGRESS` → `IMPLEMENTED` → `TESTED` → `VERIFIED`. `VERIFIED` means a human checked it on the real stack. **Nothing in this project is `VERIFIED` yet.** Say "tested", not "verified", in any report.

## Contents

1. [One-page snapshot](#1-one-page-snapshot)
2. [The product](#2-the-product)
3. [Project history and timeline](#3-project-history-and-timeline)
4. [Non-negotiable engineering rules](#4-non-negotiable-engineering-rules)
5. [System architecture](#5-system-architecture)
6. [Repository map](#6-repository-map)
7. [Technology stack](#7-technology-stack)
8. [Contracts and the Building Model](#8-contracts-and-the-building-model)
9. [Vision service: drawing to model](#9-vision-service-drawing-to-model)
10. [Geometry service: the deterministic engine](#10-geometry-service-the-deterministic-engine)
11. [Building intelligence](#11-building-intelligence)
12. [Language service: text, voice, questions](#12-language-service-text-voice-questions)
13. [Core API and worker](#13-core-api-and-worker)
14. [API reference](#14-api-reference)
15. [Web application](#15-web-application)
16. [Configuration reference](#16-configuration-reference)
17. [AWS profile](#17-aws-profile)
18. [Security](#18-security)
19. [Testing and quality evidence](#19-testing-and-quality-evidence)
20. [Feature status](#20-feature-status)
21. [The build plan](#21-the-build-plan)
22. [Decision log](#22-decision-log)
23. [Limitations and risks](#23-limitations-and-risks)
24. [Roadmap and next steps](#24-roadmap-and-next-steps)
25. [Running the project](#25-running-the-project)
26. [Demo scripts](#26-demo-scripts)
27. [Document drift register](#27-document-drift-register)
28. [Using this file for slides and reports](#28-using-this-file-for-slides-and-reports)
29. [Numbers cheat sheet](#29-numbers-cheat-sheet)
30. [Glossary](#30-glossary)
31. [Where every other document fits](#31-where-every-other-document-fits)

---

## 1. One-page snapshot

| Item | Fact |
|---|---|
| Project name | **AEC AI Platform**. The product's UI brand is **AEC Studio**. The Clerk application is named "AI x AEC". The repository folder is `AIxAEC`. |
| AEC means | Architecture, Engineering and Construction |
| What it does | Reads a floor-plan image or PDF into a structured, versioned Building Model, then lets a user edit that model by typing, speaking or clicking. A deterministic geometry engine applies every change, and each change is a new immutable version with undo and redo. It also produces quantities, cost estimates, indicative code compliance, interior proposals, layout options and structural advice. |
| Core idea | **The AI never moves a wall.** A language model only turns words into a structured command. Deterministic code checks and performs the change. |
| Status | Working end-to-end product on the local and hosted-Supabase stack (P0–P7 plus Building Intelligence complete and tested). AWS profile (P8) is coded, tested offline and was deployed to real AWS twice (see section 17); the full upload flow on AWS has not been run. |
| Default stack (free) | Next.js web app, 4 FastAPI services, Clerk auth, Supabase Postgres and Storage, OmniRoute free LLM gateway, Tesseract OCR, faster-whisper speech, Docker Compose |
| Optional AWS profile | Env-switched. 9 services used: S3, SQS, Lambda, ECR, ECS Fargate, SNS, CloudWatch, Rekognition and SSM Parameter Store (8 seen working on AWS, SQS partly). Textract, Transcribe and Bedrock are blocked by the Free Plan and replaced by Tesseract/Rekognition, Whisper and the rules parser. Deployed and destroyed twice; nothing is running. |
| Size | About 8,300 lines of backend Python, 7,200 lines of product TypeScript and TSX, about 4,900 lines of Python tests and 2,300 lines of web and e2e tests |
| Automated tests (run 2026-11-09) | **1,234 passing**: contracts 154, vision 129, geometry 237, language 299, API 193, web 222. Plus 13 Playwright e2e tests defined. |
| CI | GitHub Actions. Latest 3 runs on `main` passed (contracts, 4 services, web, migrations). The e2e job is manual and has been skipped. |
| Real-world proof | Three AI-generated clean plans plus synthetic fixtures. **Not yet tested on real scanned drawings.** |
| Owner | A student developer (GitHub `vajeedashaik`), building for a faculty review. Compliance basis: NBC India 2016. Currency default: INR. |

**Elevator pitch:** Upload a floor plan. Computer vision turns it into a typed building model. Say "move the wall between the kitchen and the living room 300 mm left", see a preview, and apply it. Language models only interpret the words, a deterministic geometry engine does the work, and every edit can be undone.

**Mantra:** AI interprets → structured commands describe intent → validation checks intent → geometry computes change → the Building Model stores truth → the renderer displays truth.

---

## 2. The product

### 2.1 Problem

> This framing is written for presentations. The repository contains no user research or market data, so do not present market sizes or user statistics as findings of this project.

Floor plans usually exist as images or PDFs. An image cannot be queried or safely edited: nothing in it knows what a wall is. Generic AI image tools can change pixels, but they cannot guarantee that geometry stays correct, that a change can be undone, or that a measurement is real. Anyone who needs quantities, costs or a code check has to re-measure by hand or redraw in CAD.

### 2.2 Solution

Convert the drawing into a **structured model** and make it the only source of truth. Then allow natural-language editing **without ever letting a language model touch geometry**.

### 2.3 Intended users

A precision tool for people who work from floor plans: architects, engineers and similar professionals. `apps/web/DESIGN.md` describes a tool "kept open for hours: dense plans, exact numbers, small decisions repeated many times".

### 2.4 End-to-end user journey

1. Sign up through Clerk and land on a first-run dashboard.
2. Create a project and upload a PNG, JPG or PDF (up to 25 MiB).
3. Watch an 8-stage processing timeline (about 2.5 s on the sample plan).
4. Open the workspace: interactive vector plan with outline, inspector and insights.
5. If the drawing had a readable dimension, areas already show in m². If not, select a wall and use Set scale.
6. Edit by typing, voice (hold `V`) or point-and-click. See a **preview ghost**, then Apply. The version number increases.
7. If the request is ambiguous, the system asks which element, with candidates highlighted on the plan.
8. Undo, redo, browse history, view any old version read-only.
9. Open Analyze for quantities, costs, compliance, interior, layouts and structure. Export CSV.
10. Ask questions in plain language ("how many bedrooms?") and see the elements highlighted.

### 2.5 Capability list

| Capability | Description |
|---|---|
| Plan reading | PNG, JPG, PDF page 1. Detects walls, rooms, doors, windows, columns, stairs, text and dimensions. |
| Typed model | Every element has an id, source (`DETECTED`, `INFERRED`, `USER_CONFIRMED`) and confidence. |
| Scale calibration | Read from drawn dimensions, or set manually. Never assumed. |
| Text editing | 10 operations in natural language, plus a hybrid rules-then-LLM parser. |
| Voice editing | Local Whisper transcription into the same pipeline. |
| Point-and-click editing | Selection actions build the same structured commands. |
| Preview before apply | Ghost overlay on the canvas of added, changed and removed elements. |
| Clarification | Never guesses; lists candidates and highlights them on hover. |
| Versioning | Append-only versions, undo, redo, discarded branches, read-only history, audit log. |
| Insights | Counts, areas, wall lengths, rooms by type. |
| Quantity takeoff | 21-line Bill of Quantities with CSV export. |
| Cost estimate | Editable rates, default INR, CSV export. |
| Compliance | Indicative checks based on published summaries of NBC India 2016, CSV export. |
| Interior | Furniture proposal drawn on the plan, lighting plan, 5 themes. |
| Layout suggestions | Goals such as another bedroom, more parking or a larger kitchen, each option engine-validated and previewable. |
| Structural suggestions | Advisory, with some one-click previewable fixes. |
| Blueprint chatbot | Rules answer from the model; an LLM only sees a facts sheet with no ids or coordinates. |

### 2.6 What makes it different

1. **Deterministic core.** Same input gives byte-identical output, which is asserted in tests.
2. **AI output is treated as untrusted input** and re-validated by non-AI code.
3. **Refusal is a feature.** It asks rather than guesses, and refuses millimetres without a known scale.
4. **Full version history** for a drawing, with a real audit trail.
5. **Offline-capable.** With no LLM configured, the rules parser still handles every fixture command (51 of 51).
6. **Contract-first engineering.** One Pydantic definition generates JSON Schema and TypeScript for every boundary.

---

## 3. Project history and timeline

### 3.1 Two codebases

This repository (`AIxAEC`) is a **from-scratch rebuild** of an earlier project in a folder called `CSPM`. `FULL_PROJECT_CONTEXT.md` documents that predecessor and remains the algorithmic spec the rebuild followed. It is kept because phase prompts and a code comment cite its section numbers.

| Aspect | Predecessor (`CSPM`) | This rebuild (`AIxAEC`) |
|---|---|---|
| Architecture | Modular monolith, one FastAPI app | Contract-first: 4 services and one web app |
| Auth | Cognito, Entra (additive), local | Clerk |
| Database | RDS PostgreSQL | Supabase Postgres |
| Storage | S3 | Supabase Storage (S3 for artifacts in the AWS profile) |
| Queue | SQS and Lambda | Postgres `SKIP LOCKED` job table (SQS wake-up in the AWS profile) |
| OCR | Google Vision or Tesseract | Tesseract (Rekognition coded for the AWS profile; Textract blocked) |
| Speech | Google Speech or stub | faster-whisper (Transcribe in the AWS profile) |
| LLM | Claude, OpenAI, Gemini | OmniRoute free-tier gateway (Bedrock coded for the AWS profile) |
| Viewer styling | Aurora, glass, gradients | "Precision instrument" design system |
| Tests | 354 backend + 88 frontend | 1,234 automated + 13 e2e |
| Takeoff, cost, compliance | Not built | Built |

**Why rebuild:** zero-cost operation, and the ability to run six independent Claude Code sessions in parallel without file collisions.

### 3.2 Timeline

| Date | Event | Evidence |
|---|---|---|
| Aug–Sep 2026 | Predecessor deployed on AWS `ap-south-1` | `FULL_PROJECT_CONTEXT.md` §19 |
| 2026-11-01 | Rebuild decided. P0 foundation and contracts. P1–P6 built in parallel worktrees. P7 merge, e2e, hardening, docs | Commits `57618f8` to `38b6b61` |
| 2026-11-07 | Testing progress recorded | `docs/FEATURE_STATUS.md` |
| 2026-11-08 | **Building Intelligence** added: 75 files, +13,148 lines (`aa85389` "Complete MVP"). Owner decisions: NBC India, INR. Hosted Supabase project activated. Pushed to GitHub; CI repaired | Git log, GitHub Actions |
| 2026-11-09 (early) | Vision accuracy pass on 3 AI-generated plans (`eee4aea`). About 150 real-browser edge cases, 12 fixes (`a1de848`) | Git log, `docs/FEATURE_STATUS.md` |
| 2026-11-09 | "No AWS" rule replaced by an env-switched AWS profile (P8) for the faculty review. Code and Terraform written. ECR repositories created on real AWS | `docs/AWS_MIGRATION_PLAN.md`, live AWS query |
| 2026-11-09 | Two deploy/destroy runs on real AWS. Free Plan blocks Textract, Transcribe, Bedrock, Comprehend and Translate; Tesseract, Whisper and the rules parser stand in | Section 17 |
| 2026-11-09 | Rekognition added as an OCR provider (replaces blocked Textract); SSM Parameter Store added for the 5 secrets; Polly checked and **not used** (no feature needs speech output); ALB with HTTPS **dropped** | Section 17.3 |
| 2026-11-10 | Third deploy: `build-push` login fixed (PowerShell 5.1 pipe broke `docker login`), `smoke.ps1` now accepts `rekognition`. Rekognition OCR (2 words) and SSM secrets seen working on AWS | Section 17.7, `docs/AWS_DEMO_RUNBOOK.md` |

**Git state today:** `main` has 30 commits, level with `origin/main` (`vajeedashaik/AIxAEC-Production`). Branch `aws-profile` holds **uncommitted** work: 31 modified tracked files and 52 untracked files. Seven worktrees are registered (`C:\dev\aec\p*` plus the main folder). The owner stages, commits and pushes personally.

---

## 4. Non-negotiable engineering rules

| Rule | Meaning in practice |
|---|---|
| A floor plan is a structured model, not an image | `FloorPlanModel` JSON is canonical. The upload is never re-edited. |
| The LLM never edits geometry | LLM output is only a command dict, re-validated as untrusted input. Only the geometry service writes coordinates. |
| AI output is untrusted | `parse → schema → resolve → semantic → geometry → constraints → persist`. `extra="forbid"` everywhere. |
| Don't guess on ambiguity | Return `CLARIFICATION` with described candidates. |
| Pixels are not millimetres | Geometry is stored in image pixels. `mm_per_pixel` is optional. `mm` commands are refused without a calibrated scale. |
| Geometry integrity | Validate, propose, validate, commit or roll back. A failed edit never corrupts the stored model. |
| Append-only versions | Versions are never overwritten. Undo and redo only move a HEAD pointer. |
| Explicit job states | `PENDING / PROCESSING / COMPLETED / FAILED`. The jobs table is the source of truth. |
| Providers behind interfaces | OCR, speech, LLM, storage, queue and object detection have an offline default, so a missing key degrades rather than crashes. |
| Honest status | Only a human check on the real stack earns `VERIFIED`. |
| Free by default | The default profile uses free tiers or self-hosted services. AWS exists only behind env switches. No GCP or Azure. |

Working rules for contributors (`CLAUDE.md`): write only inside paths your phase owns; contracts are frozen for P1–P6; never `git add -A` or `git commit -a`; never run repo-wide formatters; don't push unless asked; look up every library API with context7.

---

## 5. System architecture

### 5.1 Default stack

```
                      Clerk (hosted auth: sign-in UI, sessions, RS256 JWT, JWKS)
                         │ session                                  │ JWKS
                         ▼                                          ▼
   ┌───────────────────────────────┐  Bearer JWT   ┌───────────────────────────────────┐
   │ apps/web  Next.js 16   :3000  │ ────────────► │ services/api  FastAPI      :8000  │
   │ landing, dashboard, upload,   │ ◄──── JSON ── │ only public backend, only DB      │
   │ workspace, analyze, ask       │               │ client. + worker process          │
   └───────────────────────────────┘               └──┬───────────┬───────────┬────────┘
                              X-Internal-Token (HTTP) │           │           │
                ┌─────────────────────────────────────┘           │           │
                ▼                               ▼                 ▼           │
   ┌────────────────────────┐  ┌───────────────────────────┐ ┌──────────────┐ │
   │ services/vision  :8001 │  │ services/geometry  :8002  │ │ language     │ │
   │ OpenCV, Tesseract,     │  │ Shapely, deterministic    │ │ :8003 rules, │ │
   │ PyMuPDF. Stateless     │  │ engine + analysis.        │ │ LLM, Whisper │ │
   └────────────────────────┘  │ Stateless                 │ └──────┬───────┘ │
                               └───────────────────────────┘        │         │
                                                OmniRoute :20128 ◄──┘         │
   Supabase: Postgres (7 tables) + private Storage (floorplans, artifacts) ◄──┘
```

### 5.2 Components

| Component | Tech | Responsibility | State |
|---|---|---|---|
| `packages/contracts` | Pydantic v2, JSON Schema, generated TS | Every shape crossing a boundary; room lexicon; fixtures | Library |
| `services/vision` | FastAPI, OpenCV, PyMuPDF, Pillow, Tesseract | 8-stage pipeline, image or PDF to `FloorPlanModel` | Stateless |
| `services/geometry` | FastAPI, Shapely 2, NumPy | Entity resolution, validation, 11 operations, constraints, insights, all analysis | Stateless |
| `services/language` | FastAPI, OpenAI SDK, faster-whisper, PyAV | Parsing, room classification, speech, LLM answers | Stateless |
| `services/api` | FastAPI, SQLAlchemy 2, psycopg 3, supabase-py, PyJWT, httpx | Public REST API, auth, uploads, jobs, versions, audit, orchestration | Owns all data |
| Worker | `python -m app.worker` | Claims jobs and runs the processing flow | Uses Postgres |
| `apps/web` | Next.js 16, React 19, Tailwind 4, shadcn/ui, Clerk, TanStack Query, MSW | All screens and the dependency-free renderer | Browser |
| OmniRoute | Docker image `diegosouzapw/omniroute:3.8.52` | Routes LLM calls to free providers with fallback | Volume |

### 5.3 Ports

| Service | Port | Exposure |
|---|---|---|
| web | 3000 (3001 was the P6 dev port) | `127.0.0.1` |
| api | 8000 | `127.0.0.1` |
| vision / geometry / language | 8001 / 8002 / 8003 | Docker network only |
| OmniRoute | 20128 | Docker network only (dashboard needs a temporary override) |
| Local Supabase API / DB / Studio | 54321 / 54322 / 54323 | Host |

### 5.4 Flow: upload to model

1. Browser posts multipart to `POST /v1/projects/{id}/floorplans`.
2. API checks ownership and quota, validates the file, stores it, inserts the row and a `PENDING` job, then commits. If the commit fails, the blob is deleted.
3. Worker claims the job atomically (`FOR UPDATE SKIP LOCKED`), starts a 15 s heartbeat.
4. Worker fetches the source, calls vision `POST /v1/analyze` (180 s timeout, retries on 5xx or connection errors only).
5. Worker optionally classifies unknown room labels through language (best effort).
6. Worker stores artifacts, then in one transaction appends a model version, inserts artifact rows and marks the job `COMPLETED`.
7. Browser polls `GET /v1/floorplans/{id}/job` every 2 s, then 6 s after a minute.

### 5.5 Flow: edit

```
instruction → API loads HEAD (checks expected_version)
            → geometry /models/brief  (no ids, no coordinates)
            → language /commands/parse (rules, then LLM on UNKNOWN)
            → geometry /commands/execute:
                 schema → mm-without-scale check → entity resolution
                 → semantic validation → operation on a copy
                 → model re-validation → constraints → change set + summary
            → APPLIED / CLARIFICATION / REJECTED
Preview (/interpret): returns a PREVIEW, never saved, never audited
Apply (/commands): one transaction, row lock, HEAD re-check, compare-and-swap, audit row
```

No database transaction ever spans an HTTP call. What the user previewed is exactly what gets applied, because Apply re-sends the **resolved** command.

### 5.6 Why these boundaries

- Only `services/api` touches the database, giving one security boundary and one place for credentials.
- The web app never talks to Supabase, so there is no client-side RLS policy surface.
- Compute services are stateless, so they are simple to test and to move (vision moves to Lambda in the AWS profile with no contract change).

---

## 6. Repository map

```
AIxAEC/
├─ PROJECT_SOURCE_OF_TRUTH.md   this file
├─ FULL_PROJECT_CONTEXT.md      spec of the predecessor (archive; cited by phase prompts)
├─ CLAUDE.md, README.md         working rules; product summary and quick start
├─ compose.yaml                 includes one compose fragment per service
├─ .github/workflows/ci.yml     python matrix, web, migrations, manual e2e
├─ apps/web/                    Next.js app
│  ├─ DESIGN.md                 design system ("law for every UI change")
│  ├─ qa/p5, qa/p7              committed QA screenshots (68 PNGs)
│  └─ src/
│     ├─ app/                   routes: (marketing) (auth) (app) (dev)
│     ├─ components/            ui/ (30 primitives), shell/, composites
│     ├─ contracts/             generated.ts + friendly names (generated, frozen)
│     ├─ features/              marketing, dashboard, projects, upload, settings, viewer, workspace
│     ├─ lib/                   api client, errors, format, preferences
│     └─ mocks/                 MSW handlers and in-memory backend
├─ packages/contracts/          aec_contracts: src/, schema/ (51 JSON files), fixtures/, scripts/
├─ services/
│  ├─ vision/app/               pipeline/, vision/, ocr/, lambda_handler.py
│  ├─ geometry/app/             engine/, engine/operations/, analysis/, insights.py, brief.py
│  ├─ language/app/             rules.py, llm.py, llm_bedrock.py, parsers.py, classify.py, answer.py, speech.py, speech_transcribe.py
│  └─ api/app/                  v1.py, editing.py, versions.py, jobs.py, worker.py, uploads.py, auth.py, clerk.py,
│                               storage.py, ratelimit.py, ports.py, container.py, repo.py, orm.py, clients/, aws/
│  └─ api/supabase/migrations/  one initial schema
├─ e2e/                         Playwright suite (7 spec files, 13 tests) and fixtures
├─ infra/                       Terraform (12 files), PowerShell scripts, deployer IAM policy
├─ phases/                      the build plan: P0–P7, aws/A1–A10, shared/, STATUS.md
├─ docs/                        ARCHITECTURE, FEATURE_STATUS, RUNBOOK, SECURITY, DEMO_SCRIPT, TECH_STACK, AWS_MIGRATION_PLAN, AWS_DEMO_RUNBOOK, AWS_FACULTY_SUMMARY
└─ tasks/plan.md                Building Intelligence plan
```

### Module reference

**Vision (`services/vision/app`)**

| Path | Role |
|---|---|
| `main.py`, `v1.py`, `config.py`, `errors.py` | Service shell, route, settings, error envelope |
| `lambda_handler.py` | AWS Lambda entry point with files passed through S3 |
| `pipeline/runner.py`, `pipeline/stages.py` | `run_stage`, `run_pipeline`, the 8 stages |
| `vision/decode.py` | PNG, JPG and PDF decode with limits |
| `vision/preprocess.py` | Downscale, invert dark drawings, denoise, CLAHE, binarise, deskew |
| `vision/strokes.py` | Wall thickness, structural mask, compact blobs, text layer |
| `vision/walls.py` | Wall detector |
| `vision/rooms.py` | Room polygons and labels |
| `vision/objects.py` | Door swings, columns, stairs, optional YOLO |
| `vision/calibrate.py` | Scale from dimensions |
| `vision/assemble.py` | Builds the validated model, links walls to rooms |
| `vision/overlay.py` | Debug overlay image |
| `ocr/base.py`, `ocr/factory.py`, `ocr/stub.py`, `ocr/tesseract.py`, `ocr/textract.py`, `ocr/parsing.py` | OCR providers and dimension parser |

**Geometry (`services/geometry/app`)**

| Path | Role |
|---|---|
| `main.py`, `v1.py`, `config.py`, `errors.py` | Service shell and 8 routes |
| `engine/execute.py` | The execute pipeline |
| `engine/resolve.py` | Entity resolution |
| `engine/semantic.py` | Semantic validation |
| `engine/operations/walls.py` | MOVE_WALL, RESIZE_ROOM, ADD_WALL, DELETE_WALL |
| `engine/operations/openings.py` | ADD and DELETE of doors and windows |
| `engine/operations/split.py` | SPLIT_ROOM |
| `engine/operations/metadata.py` | RENAME_ROOM, SET_SCALE |
| `engine/operations/ids.py` | Deterministic ids for new elements |
| `engine/constraints.py` | Constraint validator |
| `engine/changes.py`, `engine/summary.py` | Change set and human summary |
| `engine/geom.py`, `engine/errors.py` | Geometry helpers, typed errors |
| `insights.py`, `brief.py` | Insights, LLM-safe brief |
| `analysis/measure.py` | Plan measured in real units, travel distances |
| `analysis/takeoff.py`, `analysis/cost.py`, `analysis/compliance.py`, `analysis/interior.py`, `analysis/structural.py`, `analysis/layouts.py`, `analysis/qa.py` | Each analysis |

**Language (`services/language/app`)**

| Path | Role |
|---|---|
| `main.py`, `v1.py`, `config.py`, `errors.py` | Service shell and 4 routes |
| `rules.py` | Offline grammar |
| `llm.py`, `llm_bedrock.py` | OpenAI-compatible client and parser; Bedrock client |
| `parsers.py` | rules, llm, hybrid selection |
| `classify.py` | Room label classification |
| `answer.py` | LLM answers from a facts sheet |
| `speech.py`, `speech_transcribe.py` | Whisper and stub; Amazon Transcribe |

**API (`services/api/app`)**

| Path | Role |
|---|---|
| `main.py` | App factory, body cap, request context, CORS, error handlers, health |
| `v1.py` | The 23 public routes |
| `auth.py`, `clerk.py` | Current user, provisioning, JWT verification |
| `editing.py`, `versions.py` | Edit orchestration; versions, undo, redo, history |
| `jobs.py`, `worker.py` | Postgres queue, processing, worker loop |
| `uploads.py`, `storage.py` | Upload validation; `BlobStore` and Supabase implementation |
| `repo.py`, `orm.py`, `db.py` | Owner-scoped queries, ORM, sessions |
| `ratelimit.py`, `observability.py`, `errors.py` | Rate limit, JSON logs, error types |
| `container.py`, `ports.py`, `config.py` | Dependency wiring and AWS seams |
| `clients/base.py`, `clients/vision.py`, `clients/geometry.py`, `clients/language.py` | Internal HTTP clients with retry and circuit breaker |
| `aws/s3.py`, `aws/sqs.py`, `aws/sns.py`, `aws/lambda_vision.py` | AWS profile adapters |

---

## 7. Technology stack

Versions come from `package.json`, `pyproject.toml` and `uv.lock` on 2026-11-09.

| Layer | Technology | Version |
|---|---|---|
| Language | Python | 3.12 |
| Language | TypeScript | ^5 |
| Web framework | Next.js (App Router, Turbopack, `cacheComponents`) | 16.4.3 |
| UI runtime | React | 19.3.0 |
| Styling | Tailwind CSS | ^4 |
| Components | shadcn/ui on Radix | shadcn ^4.23, radix-ui ^1.8 |
| Data fetching | TanStack Query | ^5.105 |
| Validation (web) | Zod | ^4.6 |
| Auth | Clerk (`@clerk/nextjs`) | ^7.9 |
| API mocks | MSW | ^3.0 |
| API framework | FastAPI | 0.162.0 |
| Validation (Python) | Pydantic | 2.14.2 |
| ORM | SQLAlchemy | 2.1.6 |
| JWT | PyJWT | 2.15.1 |
| Storage SDK | supabase-py | 2.33.0 |
| Vision | OpenCV headless | 5.0.0.93 |
| PDF | PyMuPDF | 2.0 |
| OCR | Tesseract via pytesseract | 0.3.13 |
| Geometry | Shapely | 2.2.0 |
| Speech | faster-whisper (`base.en`, CPU, int8) | 1.2.1 |
| LLM client | OpenAI SDK, kept below 3 | 2.54.0 |
| AWS SDK | boto3 | 1.43.126 |
| Database | Postgres (17 in local Supabase config, 16 in CI) | |
| IaC | Terraform, AWS provider | 1.17.0, 6.72.0 |
| Python tooling | uv, ruff, mypy strict, pytest, respx, Hypothesis, moto | |
| Web tests | Vitest 5, Testing Library, jsdom | |
| E2E | Playwright with `@clerk/testing` | ^1.64 |
| Containers | `python:3.12-slim`, `node:22-alpine`, `public.ecr.aws/lambda/python:3.12` | |

Image sizes measured locally: geometry 499 MB, api and worker 1.33 GB, language 1.54 GB, vision 1.74 GB, OmniRoute 1.93 GB, vision-lambda 2.27 GB.

Known traps: Next 16 `cacheComponents` needs runtime hooks under `<Suspense>`; Clerk Core 3 replaced `<SignedIn>` with `<Show>` and no longer auto-creates keyless keys; MSW 3 renamed `onUnhandledRequest` to `onUnhandledFrame`; Next 16 renamed middleware to `proxy.ts`.

---

## 8. Contracts and the Building Model

`packages/contracts` (`aec_contracts`) defines every cross-boundary shape in Pydantic. `scripts/export_schema.py` writes JSON Schema and `scripts/gen_ts.mjs` generates `apps/web/src/contracts/generated.ts`. CI fails if generated TS is stale. Modules: `model.py`, `commands.py`, `results.py`, `vision.py`, `geometry.py`, `language.py`, `public.py`, `analysis.py`, `errors.py`, `lexicon.py`.

### 8.1 Conventions

- Coordinates are image pixels of the **preprocessed** image, origin top-left, +x right, +y down, rounded to 2 decimals.
- `mm_per_pixel` is optional. Metric fields are `null` without it.
- UUID v4-shaped ids; element ids stay stable across versions unless deleted.
- ISO-8601 UTC timestamps. `snake_case` everywhere, including TypeScript.
- Every model is `extra="forbid"`.
- Every non-2xx response uses `{"error": {"code", "message", "details"}}`.

### 8.2 Building Model

| Type | Key fields |
|---|---|
| `Element` (base) | `id`, `confidence` 0–1, `source` |
| `Point` | `x ≥ 0`, `y ≥ 0` |
| `BBox` | `x`, `y`, `width > 0`, `height > 0` |
| `Wall` | `start`, `end` (must differ), `thickness_px` |
| `Door` | `bbox`, `wall_id`, `width_px`, `swing` (`LEFT`, `RIGHT`, `DOUBLE`, `SLIDING`) |
| `Window` | `bbox`, `wall_id`, `width_px` |
| `Column` | `bbox` |
| `Stair` | `bbox`, `polygon` |
| `Furniture` | `bbox`, `category` |
| `Dimension` | `text`, `value_mm`, `span_px`, `position` |
| `Room` | `polygon` (3+ points), `wall_ids`, `label_text`, `room_type`, `room_type_source`, `room_type_confidence`, `area_px` |
| `CoordinateSystem` | `image_width`, `image_height`, `mm_per_pixel`, `calibration_source`, `calibration_confidence` |
| `FloorPlanModel` | `schema_version` = 1, `id`, `floorplan_id`, `coordinate_system`, lists of all elements. Validates reference integrity and unique ids. |

Enums. `RoomType` (17): UNKNOWN, BEDROOM, MASTER_BEDROOM, BATHROOM, KITCHEN, LIVING_ROOM, DINING_ROOM, HALLWAY, CLOSET, GARAGE, OFFICE, LAUNDRY, BALCONY, STORAGE, STAIRWELL, UTILITY, OTHER. `Source`: DETECTED, INFERRED, USER_CONFIRMED. `CalibrationSource`: UNKNOWN, ASSUMED_DEFAULT, DIMENSION_OCR, MANUAL.

### 8.3 Commands

Targeted commands need exactly one of `target_id` (UUID) or `target_query` (1–200 characters).

| Operation | Target | Fields |
|---|---|---|
| `MOVE_WALL` | wall | `direction`, `distance {value, unit mm or px}` |
| `ADD_WALL` | none | `start`, `end`, `thickness_px?` |
| `DELETE_WALL` | wall | |
| `RESIZE_ROOM` | room | `direction`, `distance`, `mode` EXPAND or CONTRACT |
| `ADD_DOOR` | wall | `position` 0–1 (default 0.5), `width?` |
| `ADD_WINDOW` | wall | `position`, `width?` |
| `DELETE_DOOR` | door | |
| `DELETE_WINDOW` | window | |
| `RENAME_ROOM` | room | `name` 1–80, `room_type?` |
| `SET_SCALE` | wall | `length_mm` up to 1,000,000 |
| `SPLIT_ROOM` *(engine only)* | room | `axis`, `position` 0.2–0.8, `new_room_name`, `new_room_type` |

`Command` is the union of the first 10. `EngineCommand` adds `SPLIT_ROOM`. **Parsers and LLMs can only produce `Command`**, so `SPLIT_ROOM` can only come from layout suggestions.

### 8.4 Result shapes

- `ExecuteResult`: `ExecuteApplied` (`command`, `model`, `changes`, `summary`), `ExecuteClarification` (`question`, 2+ `candidates`), `ExecuteRejected` (`stage`, `detail`).
- `RejectStage`: `parse`, `schema`, `entity_resolution`, `semantic_validation`, `geometry`, `constraints`.
- `CommandResponse.status`: `APPLIED`, `PREVIEW`, `CLARIFICATION`, `REJECTED`.
- `ChangeSet`: `added`, `modified`, `removed`.
- `Candidate`: `id`, `kind`, human `label`, anchor `x`, `y`.
- `AnalyzeResult`: `status`, `model`, 8 `stages`, `artifacts`, `warnings`, `error`.
- `Insights`, `PlanBrief` (no coordinates, no ids), `Analysis`, `Answer`, `LayoutSuggestions`.

### 8.5 Error codes

| Code | HTTP | Meaning |
|---|---|---|
| `unauthorized` | 401 | Missing or invalid token |
| `forbidden` | 403 | Authenticated but not allowed |
| `not_found` | 404 | Does not exist **or is not yours** |
| `validation_error` | 422 | Bad request |
| `conflict` | 409 | Nothing to undo, for example |
| `stale_model` | 409 | `expected_version` differs from HEAD |
| `model_not_ready` | 409 | No model yet, or processing |
| `already_processing` | 409 | A live job exists |
| `quota_exceeded` | 409 | Project or plan quota hit |
| `payload_too_large` | 413 | Upload or audio too big |
| `unsupported_media_type` | 415 | Bad file type |
| `rate_limited` | 429 | With `Retry-After` |
| `upstream_unavailable` | 502 / 503 | Internal service or provider failed |
| `internal_error` | 500 | Unexpected, never with a stack trace |

### 8.6 Room lexicon

`lexicon.py` maps text to `RoomType` through an ordered regex list (specific before generic, so "master bed" wins over "bed") and `ROOM_SYNONYMS`. It is shared by vision, geometry and language. An exact synonym scores 0.95, a regex match 0.8.

### 8.7 Fixtures

| Fixture | Content |
|---|---|
| `apartment.model.json` | 5 rooms, 17 walls, 4 doors, 3 windows, 1 column, 1 stair, 3 dimensions, 10 mm/px |
| `apartment.unscaled.model.json` | Same, no scale |
| `two_room.model.json` | Two rooms sharing a wall |
| `synthetic_plan.py` | Deterministic PNG generator for both plans |
| `commands.examples.json` | 51 instruction cases across all 10 operations plus UNKNOWN |
| `api/*.json` | Example response per public endpoint, used by MSW and tests |

---

## 9. Vision service: drawing to model

`POST /v1/analyze` (multipart `file`, `floorplan_id`, optional `options`). A failed analysis still returns HTTP 200 with `status="FAILED"`.

### 9.1 The 8 stages

| # | Stage | UI label | Critical | What happens |
|---|---|---|---|---|
| 1 | `preprocess` | Clean up image | Yes | Decode, downscale to longest edge 2400, invert light-on-dark blueprints, denoise, CLAHE, adaptive threshold, deskew if at least 0.3° |
| 2 | `wall_detection` | Find walls | Yes | Thickness-aware morphology plus Hough |
| 3 | `ocr` | Read text | No | Tesseract, stub or Textract on a text-only layer |
| 4 | `object_detection` | Find openings | No | Door swings, columns, stairs |
| 5 | `room_detection` | Find rooms | No | Enclosed free space between walls, labelled by OCR |
| 6 | `calibration` | Calibrate scale | No | Scale from dimensions, or none |
| 7 | `semantic_assembly` | Assemble model | Yes | Validated `FloorPlanModel` |
| 8 | `artifacts` | Save artifacts | No | `preprocessed`, `walls_overlay`, `detected_elements`, `semantic_model` |

A non-critical failure marks the stage `degraded` and continues. A critical failure marks it `failed`, later stages `skipped`, and the job fails with a user-safe message.

### 9.2 Wall detection

1. Estimate wall thickness from a distance-transform ridge. No thick strokes means no walls, and a degraded stage with a warning.
2. Build a structural mask that removes text, hatching, dimension lines, furniture and swings.
3. Extract axis-aligned walls as least-squares centre-lines per connected body. A wall that jogs sideways is treated as two lines, and a step in stroke width splits a wall.
4. Find diagonals on the residual with probabilistic Hough (confidence 0.45, versus 0.9 for axis walls).
5. Straighten anything within 3° of an axis, merge collinear overlaps.
6. **Bridge gaps** up to 14 % of the image's longest side into one wall plus an opening. Glazed gaps can reach twice that limit. At least 2 thin parallel lines in the gap means window, otherwise door.
7. Close doors hung against a side wall, snap junctions onto centre-lines, drop short segments.

### 9.3 Rooms

Rasterise walls and openings, close, find 4-connected free-space components that do not reach the image border and cover 0.3 %–90 % of the image. Grow half a stroke so edges land on centre-lines, simplify, snap vertices to wall joints, drop collinear vertices. Labels are OCR words inside the polygon with confidence at least 0.6, at least 3 letters (or a known short label: WC, BR, DR, LR, MB) and no digits, joined in reading order.

### 9.4 Objects

Door swings are found with Hough circles on thin ink, accepted only if ink fills one quadrant (fill ≥ 0.8, other quadrants ≤ 0.35) and the hinge is on a wall. Columns are compact solid blobs. Stairs are at least 4 evenly spaced parallel lines. `reconcile_openings` drops swings not on a wall and uses swings over gaps to set handedness. A YOLO path exists but is untested and `ultralytics` is not a dependency.

### 9.5 Calibration

`parse_dimension` understands `3600` (100–100,000 treated as mm), `3.6 m`, `360 cm`, `3600 mm`, `12'-6"`, `12ft 6in`. For each reading it prefers the **drawn dimension line** next to the number, otherwise the nearest wall's bay within 120 px. The ratio must be 0.05–500 mm/px. The result is the median of ratios, confidence `min(0.8, 0.3 + 0.15n)`. No match means no scale. A default is never assumed.

### 9.6 Assembly and determinism

Elements are sorted spatially and given `uuid5(floorplan_id, "<kind>:<index>")`, so re-analysis gives the same ids and byte-identical output. A wall links to a room when at least max(20 px, 10 % of its length) lies within 12 px of the room boundary. Openings bind to the nearest wall within 40 px.

---

## 10. Geometry service: the deterministic engine

Stateless with no database, network or randomness. New element ids are deterministic hashes of (model, command). Scope statement kept in the code: *geometric consistency, not building-code or structural compliance.* (Compliance is a separate analysis, section 11.)

### 10.1 Pipeline

`schema → mm-needs-a-scale check → entity_resolution → semantic_validation → geometry → model re-validation → constraints → change set + summary`.

Always HTTP 200 for a well-formed request. `dry_run` does not change the computation.

### 10.2 Entity resolution

| Query shape | 0 matches | 1 | More than 1 |
|---|---|---|---|
| Room (label substring or synonym) | Reject | Resolved | "Which room do you mean?" |
| `wall between X and Y` | "Those rooms don't share a wall." | Resolved | Prefer walls with a room on each side, else clarify |
| `<room> wall` | "No walls are linked to …" | Resolved | Clarify |
| `north wall of <room>` (also south, east, west, top, bottom, left, right) | "… has no north wall." | Resolved | Clarify on ties within 2 px |
| `shared wall` | Reject | Resolved | Clarify |
| `<room> door or window` | Reject | Resolved | Clarify |
| `door` with no room | "This plan has no doors." | Resolved | Clarify across all |
| Explicit `target_id` | Kind-checked only | | |

### 10.3 Semantic validation

Moves and resizes up to 3× the image's larger side. Opening width no wider than the wall. `ADD_WALL` inside the image (+6 px), at least 1 px long, thickness finite and sane. `SET_SCALE` result between 0.05 and 500 mm/px.

### 10.4 Operations

| Operation | Behaviour |
|---|---|
| MOVE_WALL | Perpendicular only. More than 35 % along the wall is refused with a hint. Collinear continuations move too. End and T-junction neighbours are re-projected. Room corners and attached openings follow. |
| RESIZE_ROOM | Finds walls forming the chosen side (near the room's extreme edge, overlapping more than 25 %) and shifts them. Shares code with MOVE_WALL. |
| ADD_WALL | Endpoints snap to centre-lines, median thickness, `USER_CONFIRMED`. |
| DELETE_WALL | Rooms on both sides merge (Shapely union; larger room's label and type survive). Exterior walls are refused. Openings on it are removed. |
| ADD_DOOR / ADD_WINDOW | Default 900 / 1200 mm scaled, 40 / 48 px unscaled, minimum 4 px, at most 90 % of the wall, overlap refused. |
| DELETE_DOOR / DELETE_WINDOW | Removal. |
| RENAME_ROOM | Label and type (given, or inferred, else UNKNOWN), `USER_CONFIRMED`, confidence 1.0. |
| SET_SCALE | `mm_per_pixel = length_mm / wall length`, source `MANUAL`, confidence 1.0. |
| SPLIT_ROOM | One atomic edit: new wall, two rooms and a door between them. Refused if it crosses an opening. Larger piece keeps the original id. |

### 10.5 Constraint validator

Judged against the previous model, so existing imperfections never block unrelated edits.

| Code | Meaning |
|---|---|
| `duplicate_id` | Two elements share an id |
| `out_of_bounds` | Wall or room corner outside the image (6 px margin) |
| `wall_not_axis_aligned` | An axis-aligned wall would tilt |
| `wall_collision` | Moved onto or through a parallel wall |
| `wall_flipped` | A connected wall would reverse direction |
| `room_invalid` | Outline crosses itself |
| `room_too_small` | Under 1 px² |
| `room_inverted` | Signed area flips |
| `room_crushed` | Under 20 % of its former area |
| `opening_orphan` | References a missing wall |
| `opening_detached` | More than 30 px from its wall |

### 10.6 Insights and brief

Insights computes areas with the shoelace formula on polygons (never the stored `area_px`). A wall is interior only when rooms lie on both sides, probed geometrically. Metric values appear only when a scale exists. The brief holds room labels, types, wall counts, element counts, `has_scale` and image size, and is the **only plan context the command-parsing LLM ever sees**.

---

## 11. Building intelligence

All numeric output is deterministic and lives in `services/geometry/app/analysis/`. **Everything needs a scale.** Without `mm_per_pixel` the response is `needs_scale: true`. No new tables or caching: analysis runs on demand.

### 11.1 Quantity takeoff (Bill of Quantities)

21 lines: WL-01..03 (wall lengths), FA-01 (floor), OP-01..02 (doors, windows), MA-01..02 (brickwork, bricks), CO-01..04 (slab, columns, lintels, total concrete), ST-01 (steel), PA-01..03 (paint), TI-01..04 (tiles), FL-01 (other flooring).

| Stated assumption | Value |
|---|---|
| Wall / door / window height | 3.0 / 2.1 / 1.2 m |
| Slab, lintel depth, lintel bearing | 150 mm each |
| Wall thickness if undetected | 230 mm exterior, 115 mm interior |
| Bricks | 500 per m³ with mortar, plus 5 % waste |
| Paint | 2 coats at 10 m² per litre |
| Tiles | 600×600 floor, 300×300 wall, plus 10 % waste; bathroom wall tile to 2.1 m |
| Steel | 80 kg/m³ slab, 160 columns, 100 lintels |
| Excluded | Foundations, roof finishes, external works |

### 11.2 Cost estimate

Default rates are rough India averages in INR and are editable per user (stored in the browser).

| Rate | Default | Rate | Default |
|---|---|---|---|
| Concrete per m³ | 7,000 | Painting labour per m² | 120 |
| Steel per kg | 70 | Floor tile per m² | 1,000 |
| Brick each | 9 | Wall tile per m² | 1,000 |
| Door each | 12,000 | Other flooring per m² | 1,300 |
| Window each | 15,000 | Electrical point each | 1,500 |
| Paint per litre | 320 | Plumbing fixture each | 9,000 |
| Labour | 35 % of structure, openings, flooring | Contingency | 10 % |

Electrical points: one light per 9 m² plus sockets by room type. Plumbing: bathroom 3, kitchen 2, laundry 2. Output includes `construction_cost` and `cost_per_m2`. Rates are capped at 1,000,000,000.

### 11.3 Compliance

Profile: *NBC India 2016, residential (indicative)*. The report always carries a disclaimer: **not a certified code review.** Room minimums follow NBC 2016 Part 3 as summarised; corridor, door, glazing and accessibility values are common Indian practice and not confirmed clause by clause.

| Check | Threshold |
|---|---|
| Bedroom, master bedroom, living | ≥ 9.5 m², width ≥ 2400 mm |
| Dining, office | ≥ 7.5 m², width ≥ 2100 mm |
| Kitchen | ≥ 5.0 m², width ≥ 1800 mm |
| Bathroom, laundry | ≥ 1.8 m², width ≥ 1200 mm |
| Corridor | ≥ 1000 mm (warn below 1200 mm for wheelchair) |
| Doors | Internal ≥ 800, bathroom ≥ 700, exit ≥ 1000 mm; wheelchair warn below 900 mm |
| Bathroom turning space | Warn below 1500 mm |
| Habitable room window | Fail without an exterior window; warn if glazing under 10 % of floor |
| Exits | At least 1; warn if under 2 above 150 m² |
| Sleeping room escape | Exterior door or window ≥ 600 mm |
| Travel distance | ≤ 22.5 m along a door graph (Dijkstra) |
| Stair width | ≥ 1000 mm |

Categories: Corridor width, Room size, Accessibility, Emergency exits, Door width, Window placement, Fire safety.

### 11.4 Interior

Furniture catalogue for 10 room types, placed by search along walls with clearances: 50 mm from walls, 300 mm walkways, door swings kept clear, tall items not in front of windows. Items that do not fit are reported in notes. Furniture is drawn over the plan and **not saved to the model**. Lighting targets lux by room type and computes lumens and fixtures. Themes: Modern, Minimalist, Industrial, Luxury, Scandinavian, each with palette, materials, lighting and room finishes.

### 11.5 Layout suggestions

Goals are matched by rules (other phrasing gets a help message):

| Goal | Strategy |
|---|---|
| "Another bedroom" | Convert a donor room meeting bedroom minimums, or split a room big enough for two |
| "More parking" | Enlarge a garage, or convert a room of at least 13 m² and 2.7 m width with an outside door |
| "Make the kitchen larger" | Try 300, 600 and 900 mm in four directions |

Each candidate runs through the real engine. Options are scored by area gained, minus half the area lost from neighbours, minus 5 per new compliance failure. At most 3 distinct options are returned. Apply uses the normal command flow, so preview, undo and history all work.

### 11.6 Structural suggestions

Advisory only ("Loads and soil are unknown"). Categories: Column placement (clear span over 5 m, wall run over 6 m, off-grid columns), Wall alignment (near-misses of 50–300 mm), Space optimization (hallways over 15 %, rooms over 2.5× as long as wide), Natural ventilation, Lighting improvement. A fix is only offered if the engine would apply it today.

### 11.7 Blueprint chatbot

`POST /v1/floorplans/{id}/ask`. Rules answer counts, largest and smallest room, room lists, areas, wall lengths, material quantities, cost, compliance and exits, with element ids highlighted on the plan. Rule misses go to the LLM with a **facts sheet with no ids or coordinates**, and the LLM must reply `UNKNOWN` if the facts don't hold the answer. LLM answers are labelled "(AI wording)". Costs use Indian digit grouping.

---

## 12. Language service: text, voice, questions

Routes: `POST /v1/commands/parse`, `/v1/rooms/classify`, `/v1/speech/transcribe`, `/v1/questions/answer`.

### 12.1 Parsing modes

`COMMAND_PARSER`: `hybrid` (default; rules, then LLM on UNKNOWN), `rules` (fully offline), `llm`. An LLM failure in hybrid mode returns the rules' UNKNOWN, never a 5xx.

### 12.2 Rules grammar

Deterministic regex over: units (mm, cm, m, px with conversion to mm), number words up to twenty, direction synonyms (left, right, up, down, top, bottom, north, south, east, west), "between X and Y", "at 30 %", "900 wide", rename and set-scale phrasing. Anything uncertain becomes UNKNOWN: compound number words, "towards the kitchen", several edits in one sentence, quantifiers ("all doors"), pronouns.

**Coverage on the fixture set: 51 of 51 exact** (MOVE_WALL 8, ADD_WALL 3, DELETE_WALL 4, RESIZE_ROOM 5, ADD_DOOR 5, ADD_WINDOW 4, DELETE_DOOR 3, DELETE_WINDOW 2, RENAME_ROOM 4, SET_SCALE 3, UNKNOWN 10).

### 12.3 LLM parser guardrails

- System prompt generated from the contract's JSON Schema, so it cannot drift, plus 15 few-shot examples kept in sync with fixtures by a test.
- JSON mode with fallback to tolerant extraction of the first balanced object.
- `target_id` refused. `ADD_WALL` coordinates must be numbers the user actually stated.
- One corrective retry, then `ERROR`.
- Room labels are user-authored, so the brief and instruction are sent as a JSON object with a system prompt stating they are data. This is the prompt-injection boundary.
- Timeout covers a whole parse. Circuit breaker opens after 3 consecutive failures for 30 s.
- Logs never contain the API key or command text.

### 12.4 OmniRoute

Self-hosted OpenAI-compatible gateway routing to free tiers. The live combo is `aec-parser` (Groq Qwen first, Gemini fallback). `LLM_TIMEOUT_SECONDS` is 10 in the local `.env` (default 20), and OmniRoute fails over after 3 s. Free tiers may rate-limit under bursts.

### 12.5 Speech

faster-whisper `base.en`, int8, CPU, VAD on, loaded once, biased with a domain vocabulary prompt. Audio limits: 10 MiB and 60 s, enforced **while decoding**, because browser recordings often lack a duration header. Accepted: `audio/webm`, `ogg`, `wav`, `x-wav`, `mp4`, `mpeg`, `flac`. Transcript clipped to 500 characters. First call takes about 15 s to load the model.

### 12.6 Room classification

Lexicon first, then one batched LLM call for unknown labels (up to 200), output restricted to the `RoomType` enum.

---

## 13. Core API and worker

### 13.1 Database (7 tables, 3 enums)

| Table | Key columns |
|---|---|
| `users` | `clerk_user_id` unique, `email` unique, `display_name` |
| `projects` | `owner_id`, `name` ≤ 200, `description` ≤ 2000 |
| `floorplans` | `project_id`, `version`, `original_filename`, `storage_key`, `content_type`, `size_bytes`, `checksum_sha256`, `status`, `current_model_version` (**HEAD**), `warnings` |
| `processing_jobs` | `floorplan_id`, `status`, `attempts`, `stages`, `error_message`, `started_at`, `finished_at`, `heartbeat_at` |
| `building_models` | `floorplan_id`, `version`, `origin`, `parent_version`, `discarded`, `data` jsonb, `job_id`, `edit_id` |
| `model_edits` | Audit: `instruction`, `command`, `operation`, `status`, `stage`, `error`, `clarification`, `parent_version`, `result_version`, `user_id` |
| `processing_artifacts` | `job_id`, `kind`, `storage_key`, `content_type`, `size_bytes` |

Enums: `job_status`, `model_origin`, `edit_status`. RLS is **on with no policies**, so anon and authenticated roles read nothing; the API connects as `postgres`. Every foreign key is indexed. `set_updated_at` pins `search_path`. Migration: `20261101000000_initial_schema.sql`. Each version stores one JSON document, so the model cannot be queried element by element in SQL.

**Storage:** private buckets `floorplans` (26,214,400 bytes; PNG, JPEG, PDF) and `artifacts` (52,428,800 bytes; PNG, JSON). Keys: `{project_id}/{floorplan_id}/source.{ext}` and `{project_id}/{floorplan_id}/{job_id}/{kind}.{png|json}`. Signed URLs last 15 minutes.

### 13.2 Authentication

Clerk session JWT verified offline: RS256 only, JWKS cached with refresh on unknown `kid`, `iss` must equal `CLERK_ISSUER`, `exp` required, 30 s leeway, `azp` must be in `CLERK_AUTHORIZED_PARTIES`. The user id never comes from the client. Users are provisioned on first request from token claims, else best-effort from the Clerk Backend API. If an email already belongs to another Clerk identity, the new user is stored without the email; accounts are never merged on email.

### 13.3 Job queue

- `enqueue` fails stale live jobs, refuses if one is alive (409), then inserts `PENDING`.
- Atomic claim with `FOR UPDATE SKIP LOCKED` picks `PENDING` jobs or `PROCESSING` jobs whose heartbeat is older than `PROCESSING_STALE_SECONDS` (600).
- Heartbeat every 15 s.
- **Fencing:** `attempts` is the token. A slow worker that lost its job cannot commit over the new owner.
- Attempts above 3 fail with "giving up".
- Any exception ends in `FAILED` with a user-safe message. A job is never left stuck.
- Re-processing appends a version branching from HEAD, so **Undo returns to the user's edits**.
- Run as many workers as you like (`WORKER_REPLICAS`).

### 13.4 Versioning

HEAD is `floorplans.current_model_version`, never max(version). Undo moves HEAD to `parent_version`. Redo moves it to the non-discarded child. A new edit while behind marks later versions `discarded`, which stay readable. Edits are refused while re-processing is live.

**Concurrency:** floorplan row lock, HEAD re-check, compare-and-swap update, unique-violation mapped to `stale_model`. Tested: 6 parallel edits give 1 applied and 5 × 409.

**Audit:** rejected edits, clarifications, applied edits, undo and redo are all logged in `model_edits`. Previews are not. History returns the newest 200 edits.

### 13.5 Upload validation

Extension, declared MIME and magic bytes must agree. Empty rejected. Size cap streamed. Pixel cap (64,000,000) reads the header only, so decompression bombs are refused. Corrupt images and PDFs, encrypted PDFs, zero pages and pages over 14,400 points are rejected. Filenames are sanitised for display only. Storage keys are server-generated. SHA-256 recorded. Multi-page PDFs get a page-1-only warning. Quotas: 200 projects per user, 100 plans per project.

### 13.6 Cross-cutting

| Concern | Implementation |
|---|---|
| Body cap | ASGI cap at max(upload, audio) + 1 MiB, including chunked bodies |
| CORS | Listed origins only; GET, POST, PATCH, DELETE, OPTIONS |
| Security headers | `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` |
| Rate limit | Per user (per IP for bad tokens), fixed window. 300 reads and 90 writes per minute. In memory, per process |
| Resilience | 3 attempts with exponential backoff on 5xx or connection errors only. Circuit breaker opens after 5 failures for 30 s, then half-open |
| Timeouts | Vision 180 s, geometry 30 s, language 30 s (90 s for transcribe) |
| Logging | JSON with request id, user id and duration; authorization redacted |
| Insights cache | Per process, keyed by (floorplan, version), cleared at 1024 entries |
| Production guards | Refuses the default internal token, tokens under 32 characters, `*` in CORS, or a missing Clerk issuer |

---

## 14. API reference

### 14.1 Public API (`services/api`, 23 `/v1` routes)

All require `Authorization: Bearer <Clerk token>` and are owner-scoped. Another user's resource returns 404.

| Method and path | Body or params | Result |
|---|---|---|
| `GET /healthz`, `GET /readyz` | | Health (no auth) |
| `GET /v1/me` | | `Me`, provisions on first call |
| `GET /v1/projects` | `limit` ≤ 100, `offset` | `Page[Project]` |
| `POST /v1/projects` | `ProjectCreate` | 201 `Project` |
| `GET /v1/projects/{project_id}` | | `Project` |
| `PATCH /v1/projects/{project_id}` | `ProjectUpdate` | `Project` |
| `DELETE /v1/projects/{project_id}` | | 204 |
| `GET /v1/projects/{project_id}/floorplans` | | `list[FloorPlan]` |
| `POST /v1/projects/{project_id}/floorplans` | multipart `file`, `?process=` | 201 `FloorPlan` |
| `GET /v1/floorplans/{floorplan_id}` | | `FloorPlan` |
| `DELETE /v1/floorplans/{floorplan_id}` | | 204 |
| `POST /v1/floorplans/{floorplan_id}/process` | | 202 `Job`, or 409 |
| `GET /v1/floorplans/{floorplan_id}/job` | | Latest `Job` |
| `GET /v1/floorplans/{floorplan_id}/model` | `?version=` | `ModelEnvelope` |
| `GET /v1/floorplans/{floorplan_id}/artifacts` | | `list[Artifact]` |
| `POST /v1/floorplans/{floorplan_id}/analysis` | `AnalysisQuery` | `Analysis` |
| `POST /v1/floorplans/{floorplan_id}/ask` | `AskRequest` | `Answer` |
| `POST /v1/floorplans/{floorplan_id}/layouts` | `LayoutGoal` | `LayoutSuggestions` |
| `POST /v1/floorplans/{floorplan_id}/commands/interpret` | `CommandRequest` | PREVIEW, CLARIFICATION or REJECTED |
| `POST /v1/floorplans/{floorplan_id}/commands` | `CommandRequest` | APPLIED, CLARIFICATION or REJECTED |
| `POST /v1/floorplans/{floorplan_id}/commands/voice` | multipart `audio`, `expected_version?`, `dry_run?` | `CommandResponse` with `transcript` |
| `POST /v1/floorplans/{floorplan_id}/model/undo` | `?expected_version=` | `CommandResponse` |
| `POST /v1/floorplans/{floorplan_id}/model/redo` | `?expected_version=` | `CommandResponse` |
| `GET /v1/floorplans/{floorplan_id}/history` | | `History` |

### 14.2 Internal routes (`X-Internal-Token`, 13 routes)

| Service | Route |
|---|---|
| Vision | `POST /v1/analyze` |
| Geometry | `POST /v1/commands/execute`, `/v1/models/insights`, `/v1/models/brief`, `/v1/models/validate`, `/v1/models/analysis`, `/v1/models/answer`, `/v1/models/facts`, `/v1/models/layouts` |
| Language | `POST /v1/commands/parse`, `/v1/rooms/classify`, `/v1/speech/transcribe`, `/v1/questions/answer` |

---

## 15. Web application

### 15.1 Routes

| Route | Purpose |
|---|---|
| `/` | Landing page with a live hero demo |
| `/sign-in`, `/sign-up` | Clerk, themed, split layout |
| `/dashboard` | Greeting, totals, recent plans, first-run panel |
| `/projects` | Grid or list, search and sort in the URL, pagination, create, rename, delete |
| `/projects/[projectId]` | Inline edit, upload queue, plan list, live timeline, retry |
| `/projects/[projectId]/floorplans/[floorplanId]` | The workspace |
| `/settings` | Theme, density, units, Clerk profile |
| `/playground` | Dev-only fixtures and a 500+ element test plan (404 in production) |

`src/proxy.ts` guards `/dashboard`, `/projects` and `/settings`. The API remains the real security boundary.

### 15.2 Landing page message

Headline: "Floor plans you edit by saying what changes." Trust section: "The AI never moves a wall. The geometry engine does." The hero is a working fragment with a preview, a clarification, a rejection and undo, using real areas. Sections: Hero, How it works (3 steps), Capabilities (filterable like a command menu), the 6-step pipeline, call to action, footer.

### 15.3 Workspace

Resizable panels at 1024 px and up; below that, panels move to a Details sheet.

| Area | Content |
|---|---|
| Top bar | Plan name, version chip, undo, redo, status, artifact downloads |
| Left | Outline of rooms, walls and openings, with search |
| Centre | Canvas: grid, scale bar, zoom %, minimap, layer toggles, original-drawing underlay, cursor coordinates |
| Right tabs | Inspect, Insights, Analyze, Ask, History |
| Floating | AI command bar with voice |

**Analyze views:** Quantities and BOQ, Cost estimate, Code compliance, Interior design, Layout suggestions, Structural suggestions.

**Selection actions** build the same structured commands as text. Wall: Move (perpendicular directions only), Delete, Add door, Add window, Set scale. Room: Rename, Resize. Door or window: Delete.

**Command flow states:** idle, busy, preview, clarification, rejected, stale, error. Only the latest request may update the flow.

**Keyboard map**

| Key | Action |
|---|---|
| `/` | Focus command bar |
| `Enter` | Preview |
| `Ctrl/⌘ + Enter` | Apply |
| `↑` / `↓` | Previous instructions |
| Hold `V` | Push to talk |
| `Esc` | Discard preview, then clear selection |
| `Ctrl/⌘ + Z`, `Ctrl/⌘ + Shift + Z` | Undo, redo |
| `F`, `0`, `+`, `-` | Fit, 100 %, zoom in, zoom out |
| Arrow keys | Nudge the view |
| `Space` + drag, middle-drag | Pan |
| Wheel or pinch | Zoom at cursor (0.02–40) |
| Double-click | Zoom to element |
| `Tab` | Cycle elements of the same kind |
| `Shift` + click | Multi-select |
| `Ctrl/⌘ + K` | Command palette (app shell) |

### 15.4 Renderer

`features/viewer/render/` is pure TypeScript with no dependencies. `buildScene(model)` returns flat ordered primitives (rooms, labels, walls, windows, doors, columns, stairs, furniture, dimensions), each with an element id and a style **token name**. `sceneToSvgString` is byte-identical and snapshot-tested. Pan and zoom update one `<g transform>` imperatively and commit to React once per gesture. `units.ts` never fakes a conversion. `diff.ts` draws the preview ghost.

### 15.5 Polling

Every 2 s, 6 s after a minute, a "taking longer than usual" notice after 10 minutes. A fresh `PENDING` job with no `started_at` offers Start processing.

### 15.6 Design system ("precision instrument")

| Aspect | Decision |
|---|---|
| Personality | Calm, exact, confident. The canvas is the protagonist. |
| Banned | Aurora or mesh gradients, glassmorphism, gradient text, purple-blue AI palettes, glows, emoji icons, centred-everything heroes, more than one accent, decorative motion |
| Tokens | Primitive → semantic → component layers, plus frozen `--canvas-*` names |
| Colour | Neutral graphite chrome, **one accent (cobalt)**. Status colours always pair with an icon or word |
| Type | Geist Sans for UI (13 px default), Geist Mono for measurements |
| Grid | 4 px base; 44 px top bar, 240 px sidebar, 300 px inspector, 48 px command bar |
| Motion | 80, 120, 180, 280 ms; explains change, never decorates; off under reduced motion |
| Icons | lucide, 1.5 stroke |
| Accessibility | WCAG AA contrast checked by script in both themes, visible focus, keyboard reachable, loading, empty, error and success states on every view |
| Preview colours | `--canvas-preview-add`, `--canvas-preview-modify`, `--canvas-preview-remove` |

### 15.7 Other web facts

Security headers and CSP live in `next.config.ts`. CSV exports add a UTF-8 BOM so Excel renders `m²`. Costs use Indian digit grouping in INR. Dates are absolute. With `NEXT_PUBLIC_API_MOCKING=on`, the whole UI runs on MSW fixtures with no backend.

---

## 16. Configuration reference

**All Python services:** `ENVIRONMENT`, `LOG_LEVEL`, `LOG_FORMAT`, `INTERNAL_SERVICE_TOKEN`.

| Service | Variable | Default |
|---|---|---|
| api | `DATABASE_URL` | Local Supabase on 54322 |
| api | `WORKER_DATABASE_URL` | Falls back to `DATABASE_URL`; use session or direct mode |
| api | `SUPABASE_URL`, `SUPABASE_PUBLIC_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Local; `SUPABASE_PUBLIC_URL` is what the browser reaches |
| api | `CLERK_ISSUER`, `CLERK_JWKS_URL`, `CLERK_AUTHORIZED_PARTIES`, `CLERK_SECRET_KEY` | |
| api | `VISION_URL`, `GEOMETRY_URL`, `LANGUAGE_URL` | `127.0.0.1:8001`, `:8002`, `:8003` |
| api | `CORS_ORIGINS` | localhost 3000 and 3001 |
| api | `MAX_UPLOAD_BYTES`, `MAX_AUDIO_BYTES`, `MAX_IMAGE_PIXELS` | 26,214,400; 10,485,760; 64,000,000 |
| api | `MAX_PROJECTS_PER_USER`, `MAX_FLOORPLANS_PER_PROJECT` | 200; 100 |
| api | `PROCESSING_MAX_ATTEMPTS`, `PROCESSING_STALE_SECONDS`, `WORKER_POLL_SECONDS` | 3; 600; 2 |
| api | `RATE_LIMIT_READ_PER_MINUTE`, `RATE_LIMIT_WRITE_PER_MINUTE` | 300; 90 |
| api (AWS) | `BLOB_BACKEND` | `supabase` (`hybrid`) |
| api (AWS) | `QUEUE_BACKEND` | `postgres` (`sqs`) |
| api (AWS) | `VISION_MODE` | `http` (`lambda`) |
| api (AWS) | `NOTIFIER` | `none` (`sns`) |
| api (AWS) | `AWS_REGION`, `S3_BUCKET`, `SQS_QUEUE_URL`, `SNS_TOPIC_ARN`, `VISION_LAMBDA_NAME` | Required only with the matching switch |
| vision | `OCR_PROVIDER` | `auto` (`stub`, `tesseract`, `textract`) |
| vision | `TESSERACT_CMD`, `OBJECT_DETECTOR`, `YOLO_WEIGHTS_PATH` | unset; `heuristic`; unset |
| vision | `IMAGE_MAX_DIMENSION`, `MAX_IMAGE_PIXELS`, `MAX_UPLOAD_BYTES` | 2400; 64,000,000; 26,214,400 |
| language | `COMMAND_PARSER` | `hybrid` (`rules`, `llm`) |
| language | `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS` | `127.0.0.1:20128/v1`; unset; unset; 20 |
| language | `STT_PROVIDER` | `whisper` (`stub`, `transcribe`) |
| language | `WHISPER_MODEL`, `WHISPER_COMPUTE_TYPE` | `base.en`; `int8` |
| language (AWS) | `LLM_PROVIDER` | `openai` (`bedrock`) |
| language (AWS) | `AWS_REGION`, `S3_BUCKET` | |
| web | `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_API_MOCKING` | `http://localhost:8000`; `off` |
| web | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` | |
| web | `NEXT_PUBLIC_SITE_URL`, `NEXT_PUBLIC_ARTIFACT_ORIGIN` | Optional |
| compose | `SUPABASE_URL_DOCKER`, `WORKER_REPLICAS` | `host.docker.internal:54321`; 1 |
| e2e | `E2E_BASE_URL`, `E2E_API_URL`, `E2E_COMPOSE` | Outage tests need `E2E_COMPOSE=1` |
| api tests | `TEST_DATABASE_URL` | Each run creates and drops its own database |

**Current local configuration:** hosted Supabase ("AI x AEC", Ireland), `COMMAND_PARSER=hybrid`, `LLM_MODEL=aec-parser`, `STT_PROVIDER=whisper`, Clerk in dev mode. Secrets live in gitignored `.env` files.

---

## 17. AWS profile

### 17.1 Why it exists

The faculty review needs a real multi-service AWS project. The owner has a student budget, so the stack is built to be **deployed briefly and destroyed**. The free stack stays the default and rolling back means unsetting env vars. The rule was changed on 2026-11-09.

### 17.2 Principles

Additive, not a rewrite. Use existing seams (`BlobStore`, `OCRService`, `SpeechService`, `LlmClient`, `Container`). Contracts stay frozen except adding `"transcribe"` to `TranscribeResult.provider`. Postgres stays the source of truth for jobs, with SQS only a wake-up signal. No credentials in code; IAM roles only. Offline tests first. Everything in `infra/`. Honest labels.

### 17.3 Services

| # | Service | Job | Status |
|---|---|---|---|
Labels: **SEEN** = observed running on real AWS (2026-11-09, two deploy/destroy runs). **TESTED** = offline stubs only. **BLOCKED** = refused by the Free Plan (`SubscriptionRequiredException`). Nothing is VERIFIED, because no human has checked the full upload flow on AWS.

| # | Service | Job | Status |
|---|---|---|---|
| 1 | S3 | Vision artifacts; temporary hand-off files | **SEEN** (smoke test) |
| 2 | SQS + DLQ | Wakes workers; visibility 360 s, DLQ after 3 receives | **PARTLY SEEN**: message accepted and queue drained; the worker's receipt is not proven in logs |
| 3 | Lambda | Vision pipeline from a container (Debian image, Tesseract); 3008 MB, 300 s | **SEEN**: 8/8 stages |
| 4 | ECR | Stores images | **SEEN** |
| 5 | ECS Fargate | One task, 4 containers, 1 vCPU, 3 GB | **SEEN**: API `readyz` ok, worker started |
| 6 | Rekognition | OCR via `DetectText` (`OCR_PROVIDER=rekognition`, Terraform `ocr_provider`), replaces blocked Textract | **SEEN** in the deployed Lambda on 2026-11-10 (smoke test: provider `rekognition`, 2 words). Provider code **TESTED** (Stubber). Test plan was tiny: accuracy vs Tesseract and the 100-words-per-image limit are untested on a real plan |
| 7 | SNS | "Job finished or failed" email and alarms | **SEEN**: manual test mail arrived. The app's own notification not yet triggered |
| 8 | CloudWatch | Log groups (7 days), dashboard, 3 alarms, saved query | **SEEN**: dashboard and 3 alarms exist |
| 9 | SSM Parameter Store | Holds 5 secrets as SecureString under `/aec-demo/`, injected through ECS `secrets` | **SEEN** on 2026-11-10: 5 parameters exist, task definition lists them as `secrets` with none in plain env, service ran 1/1 healthy. Values are still in the local Terraform state |
| - | Textract | OCR via `DetectDocumentText` | **BLOCKED** (Free Plan). Code TESTED (Stubber). Tesseract is used instead |
| - | Transcribe | Batch speech-to-text through S3 `tmp/` | **BLOCKED**. Code TESTED (Stubber). Whisper is the default (`stt_provider`); Whisper on Fargate is untested |
| - | Bedrock | Converse API for parsing | **BLOCKED**. Code TESTED (Stubber), off. The rules parser answers |

Also refused on this account: Comprehend and Translate. Polly works (direct call returned audio) but is **not used**: no feature needs speech output.

**Say "9 AWS services used: 8 seen working on AWS and SQS partly proven; 3 more are blocked by the Free Plan and replaced by free substitutes".** The 8 seen: S3, Lambda, ECR, Fargate, SNS (manual mail only), CloudWatch, Rekognition, SSM. Clerk and Supabase remain in use, so describe the system as: *AWS for compute, queueing, OCR, notification and monitoring, with Clerk for auth and Supabase for data.* The ALB with HTTPS was considered and dropped.

### 17.4 AWS architecture

```
Browser (local web on :3000, Clerk)
   │  http://<task-public-ip>:8000  (ingress restricted to one IP)
   ▼
ECS Fargate: one task, four containers sharing localhost
   api :8000 ── worker ── geometry :8002 ── language :8003
   │            │ long-poll              │ Transcribe via S3 tmp/
   │ publish    ▼
   │         SQS ──(3 failures)──► DLQ ──► alarm
   │            │ worker claims the job in Postgres, copies source to S3 tmp/
   │            ▼
   │         Lambda (vision image from ECR) ──► Tesseract (or Rekognition)
   │            │ result JSON and artifacts in S3; returns only the key
   ▼            ▼
   SNS (email)  S3 (artifacts; tmp/ expires after 1 day)
   Supabase (Postgres + source files) via pooler    Clerk JWT    CloudWatch
```

### 17.5 Design decisions

| ID | Decision | Why |
|---|---|---|
| D1 | Lambda receives S3 keys, not files | Sync payloads cap near 6 MB; uploads reach 25 MB |
| D2 | No load balancer; public task IP | An ALB adds a service, a domain and a certificate |
| D3 | One Fargate task, 4 containers | No service discovery; `*_URL` point at localhost |
| D4 | Terraform-managed VPC, public subnets, no NAT | NAT is the biggest avoidable cost; account has no default VPC |
| D5 | Supabase via pooler; worker uses session mode | IPv4 from Fargate; worker needs `SKIP LOCKED` |
| D6 | Hybrid storage | Keeps the upload path; artifacts move to S3 |
| D7 | Transcribe is asynchronous | Simplest SDK path; slower than Whisper |
| D8 | Bedrock via `converse`, optional | No `response_format`, so JSON is prompt-only |
| D9 | Terraform, local state | Clear plan and destroy for a live demo |
| D10 | Secrets in SSM Parameter Store (SecureString) | Free, keeps them out of the task definition. Values are still in the local Terraform state |
| D11 | Region `eu-west-1` | Same region as hosted Supabase |

Lambda is called with automatic retries **off** and a read timeout of 330 s, longer than the function's 300 s, or a slow job would run twice.

### 17.6 Infrastructure

Terraform in `infra/terraform/`: `s3`, `sqs`, `sns`, `lambda`, `ecr`, `ecs`, `iam`, `network`, `cloudwatch`, `variables`, `outputs`, `versions`. `terraform validate` and a read-only `plan` pass with **41 resources**. Scripts in `infra/scripts/`: `init-tfvars`, `budget`, `build-push`, `deploy`, `smoke`, `destroy`, `common`.

Least-privilege IAM: execution role, task role (scoped to the bucket, queue, topic and function) and Lambda role (only `tmp/` hand-off files and Textract). CloudWatch alarms: DLQ has messages, Lambda errors, no running task.

### 17.7 Current real AWS state (2026-11-10)

| Item | State |
|---|---|
| Account, user | Owner's account, IAM user `aec-dev`, AWS Free Plan |
| Deploys | Three `build-push` / `deploy` / `smoke` runs in `eu-west-1`. The first two were destroyed |
| Running now | The last read-only check (2026-11-10) found the ECS service **DRAINING with 0 tasks** and the CloudWatch alarms and SNS subscription already gone, so a destroy was in progress. SQS queues and the SNS topic still existed at that moment. **Confirm with `aws ecs list-clusters --region eu-west-1` and `destroy.ps1`'s leftover list** |
| IAM policy `aec-demo-deploy` | Applied by the owner, including `ssm:*` (SSM parameters were created) |
| Budget `aec-demo-monthly` | Exists, $10 (alerts only, it does not stop spending) |
| Seen on the third deploy | Smoke test: Lambda ran with Rekognition OCR (2 words); 5 SSM parameters; ECS service ACTIVE 1/1; no API errors in logs; owner received multiple SNS mails, but their type (alarm, confirmation or job finished) was not confirmed |
| Not exercised | Full web upload through SQS, worker, Lambda and the app's own "job finished" SNS email (the worker log showed only "worker started", so no job had reached it); Whisper first-use model download on Fargate |
| Not re-queried | Leftovers from the predecessor in `ap-south-1` (Lambda and SQS `aec-processing`, S3 `aec-floorplans-vajeeda-dev`, dashboard `aec-review`) |

**Never claim a service works on AWS unless it ran there.** Offline tests (2026-11-09, working tree): api 193 passed / 1 skipped, vision 130 / 1, language 299 / 1 (1 deselected). They use moto and Stubber and prove the code, not the services.

**Progress (owner's scale):** about 8 of 10. The remaining points are the manual end-to-end upload (SQS receipt, app SNS mail), Whisper on Fargate, and the three Free-Plan-blocked services. Nothing is VERIFIED.

**Cost:** Fargate (1 vCPU, 3 GB) is the main cost, billed per hour while up (roughly $0.06/hour from memory, unchecked), plus a small hourly public-IP charge; the other services are negligible at demo volume. Deploy, test, destroy: staying deployed only adds idle hours. Procedure: `docs/AWS_DEMO_RUNBOOK.md`.

**Known script fixes:** `build-push.ps1` pipes the ECR token through `cmd /c` because PowerShell 5.1 made ECR answer 400. `smoke.ps1` accepts `textract`, `tesseract` and `rekognition`.

### 17.8 Definition of done (AWS)

With defaults, all existing tests pass. With the profile on, one uploaded plan goes through SQS, Lambda and Textract, ends `COMPLETED` in the UI, stores artifacts in S3, sends an SNS email and shows on the CloudWatch dashboard. Voice and text work or fall back cleanly. `terraform destroy` leaves nothing billable.

---

## 18. Security

### 18.1 Trust boundaries

| Boundary | Control |
|---|---|
| Browser → API | Clerk JWT, owner scoping, 404 for other users' data |
| API → internal services | `X-Internal-Token` (constant-time compare); no published ports |
| API → Supabase | API is the only client; RLS on with no policies; private buckets; 15-minute signed URLs |
| User text and audio → LLM | LLM only proposes; output schema-validated, then re-resolved and re-validated. Labels sent as data |
| Uploads | See section 13.5 |
| Web | CSP, `X-Frame-Options: DENY`, `frame-ancestors 'none'`, `nosniff`, `Referrer-Policy`, `Permissions-Policy` (microphone self only), HSTS in production. User text renders as text, never HTML |

### 18.2 Evidence

17-route IDOR sweep as a second user. Second-user e2e. Hypothesis fuzzing of geometry. `pip-audit` clean for all five Python packages and `npm audit` with 6 low or moderate transitive issues and none high (2026-11-01). Log scan after e2e found no tokens or secrets. Prompt-injection attempts during edge-case testing leaked no prompt or key. XSS-style names rendered as text.

### 18.3 Accepted risks

- CSP allows `'unsafe-inline'` scripts (nonces would force dynamic rendering).
- Rate limiter is in memory and per process; behind a proxy, anonymous traffic shares one bucket.
- A chunked language upload is capped only after spooling (internal service).
- No render timeout for hostile vector-heavy PDFs.
- AWS demo: plain HTTP, secrets in SSM but also in the local Terraform state, local state.
- Supabase advisors have not been run. Expected finding: only `rls_enabled_no_policy`, by design.
- No external penetration test. The `/security-review` was a manual review.

---

## 19. Testing and quality evidence

### 19.1 Automated suites (run 2026-11-09)

| Suite | Result | Time | Test modules |
|---|---|---|---|
| `packages/contracts` | **154 passed** | 2 s | 4 |
| `services/vision` | **129 passed**, 1 skipped | 25 s | 8 |
| `services/geometry` | **237 passed** | 6 s | 9 |
| `services/language` | **299 passed**, 1 skipped, 1 deselected | 26 s | 9 |
| `services/api` | **193 passed**, 1 skipped | 49 s | 9 |
| `apps/web` | **222 passed** | 33 s | 11 |
| **Total** | **1,234 passed**, 3 skipped, 1 deselected | | 50 |

Skipped: real Tesseract or Whisper when absent locally and the opt-in Supabase Storage test. Deselected: live OmniRoute. Static checks were also run on 2026-11-09 on the working tree, including the uncommitted AWS code: **ruff, mypy (strict), `tsc` and eslint are all clean**. `next build` and the e2e suite were not re-run that day. `next build` passed in CI on `a1de848`, which does not include the AWS work.

API tests run against real Postgres. Clerk uses a fake JWKS server, downstream services are mocked with respx, AWS with moto and botocore Stubber. No test touches real AWS.

### 19.2 End-to-end (Playwright, real stack)

| # | Test | Spec |
|---|---|---|
| 1–2 | Sign up, first-run dashboard, create project, upload, 8-stage timeline, workspace | `01-onboarding` |
| 3 + 6b | mm needs a scale, then Set scale switches insights to m² | `02-editing` |
| 4–6 | Preview ghost and apply, clarification and pick, nonsense gives friendly UNKNOWN | `02-editing` |
| 7 | Spoken WAV transcribed and applied | `03-versions` |
| 8–9 | Undo ×2, redo, fresh edit discards; re-process then undo returns to edits | `03-versions` |
| 10 | Second user gets 404 | `04-isolation` |
| 11 | Two tabs, second apply gets stale-model message | `04-isolation` |
| 12a | Language down: refused at parse, app healthy | `05-outages` |
| 12b | Vision down: job fails cleanly, retry works | `05-outages` |
| 7b | Browser voice: hold V, fake microphone | `06-voice-ui` |
| 13 | Analyze: BOQ, cost, compliance, interior, suggestions | `07-analysis` |
| 14 | Ask: chatbot answers from the model | `07-analysis` |
| 15 | Layout suggestion: preview, apply, undo | `07-analysis` |

Last full run (2026-11-09, on hosted Supabase): 11 passed, 2 skipped (outage tests need `E2E_COMPOSE=1`). Every test also fails on any CSP violation. The P7 run passed 10 of 10 with zero CSP violations.

### 19.3 Continuous integration

`.github/workflows/ci.yml` on push to `main` and pull requests. Jobs: `python` matrix (uv sync, ruff, mypy, pytest, pip-audit, with Postgres 16 and Tesseract), `web` (contract check, lint, typegen, tsc, Vitest, build, npm audit), `migrations` (apply SQL to fresh Postgres 16), `e2e` (manual dispatch only).

**History:** 5 runs. The first 2 failed (`d5dc662`, `1c0be6a`). The last 3 passed (`d97dea5`, `eee4aea`, `a1de848`), with all jobs green and e2e skipped.

### 19.4 Measured performance

| Check | Result | Target |
|---|---|---|
| Vision, apartment plan, end to end | 2.4–2.6 s (12 jobs) | Under 6 s |
| Geometry execute including HTTP | p50 10–13 ms, p95 ≤ 23 ms | Under 50 ms |
| Workspace pan and zoom | 16.7 ms average frame on 1,020 primitives (in-page measurement) | 60 fps |
| Landing page | LCP 213 ms, CLS 0 (unthrottled), Accessibility 100, SEO 100, Best Practices 77 | Lighthouse ≥ 95 |
| Worker killed mid-job | Recovered on attempt 2 (manual run, stale timeout lowered) | |
| Dense plan: 19×19 rooms, 684 doors | Under 5 s | |
| Geometry on a 312-wall, 144-room grid | About 200 ms per execute | |

Best Practices 77 is due to third-party cookies from Clerk's development instance. The Lighthouse performance category was not obtained.

### 19.5 Plan reader accuracy (2026-11-09)

Three AI-generated plans of rising difficulty, compared with hand counts. These are clean images, so they say nothing about scans.

| Measure | Before fixes | After fixes |
|---|---|---|
| Rooms found (31 actual) | 17 | **27** |
| Bedrooms typed correctly (7 actual) | 4 | **7** |
| Plans with a working scale (3) | 2 | **3** |
| Doors, simple and medium plans (16 actual) | 12 | **16** |

On the synthetic apartment: 4 doors with correct swing handedness, 3 windows, 1 stair, 5 rooms all labelled and typed, "3600" read, 10.0 mm/px. Known misses: on the 16-room villa, 24 doors are detected against 18 actual, and a corridor merges with two rooms.

### 19.6 Edge-case testing (2026-11-09)

About 150 checks in a real browser on hosted Supabase, real OmniRoute and real Tesseract.

**Held up:** form validation, XSS-style input, double-click sending one request, keyboard undo and redo, stale-tab refresh, read-only history, all six Analyze views, CSV exports, layout preview and apply, prompt injection, corrupt, fake, empty, oversized and pixel-bomb uploads, and skewed, noisy and JPEG plans reading the same as clean ones.

**Found and fixed (12):** long-name overflow; Rename dialog overflow; `1e308` cost rate causing a 502; wrong message for oversized images; duplicate PDF warnings; OCR junk in room labels; light-on-dark drawings finding no rooms; Western digit grouping in chat costs; CSV mojibake in Excel; banner text spacing; phone tab row hidden; 22 s AI stall from rate limits (now 3 s failover and 10 s cap).

### 19.7 Not tested

Real scanned or photographed plans. Voice with a real microphone. Firefox, Safari, screen readers. Supabase advisors. Lighthouse performance score. Real AWS. The worker-crash test is not in the committed suite. OmniRoute-down and Whisper-missing only at unit level. Formal impeccable and hallmark audits.

---

## 20. Feature status

Nothing is `VERIFIED`. "e2e" means exercised by Playwright against the real stack.

| Area | Feature | Status |
|---|---|---|
| Accounts | Sign up, sign in, sessions | TESTED (e2e); form password path not exercised |
| Projects | CRUD, quotas, pagination | TESTED |
| Upload | Validation, progress, warnings | TESTED |
| Vision | 8-stage pipeline with heuristics | TESTED (e2e, synthetic + AI-generated plans) |
| Vision | YOLO path | IMPLEMENTED, untested |
| Editing | Text commands with preview | TESTED (e2e) |
| Editing | Clarification | TESTED (e2e) |
| Editing | Point-and-click actions | TESTED (unit, exact payloads) |
| Editing | Voice via API and in browser | TESTED (e2e, fake microphone) |
| Editing | LLM parsing via OmniRoute | TESTED (real gateway) |
| Versions | Undo, redo, discard, history, re-process | TESTED (e2e) |
| Concurrency | Parallel edits, stale tabs | TESTED |
| Reliability | Language and vision outages | TESTED (e2e with `E2E_COMPOSE=1`) |
| Reliability | Worker crash recovery | TESTED (manual on compose) |
| Isolation | Other users get 404 | TESTED (e2e + 17-route sweep) |
| Intelligence | Takeoff, cost, compliance, interior, layouts, structural | TESTED (e2e) |
| Intelligence | Chatbot rules | TESTED (e2e) |
| Intelligence | Chatbot LLM fallback | TESTED (real gateway) |
| Web | Landing, projects, settings, palette | TESTED (unit, seen in e2e) |
| Security | Headers and CSP | TESTED (e2e) |
| CI | GitHub Actions | TESTED (3 latest runs green) |
| AWS | A1 S3, A2 SQS, A3 Textract, A4 Lambda, A5 Transcribe, A7 SNS | TESTED offline only |
| AWS | A6 Bedrock | TESTED offline, off on AWS |
| AWS | A8 Fargate and Terraform, A9 CloudWatch | IMPLEMENTED |
| AWS | A10 Deploy and demo | **IN_PROGRESS**: deployed and destroyed twice; end-to-end upload not yet run |

---

## 21. The build plan

### 21.1 Approach

Eight prompts for independent Claude Code sessions that never edit the same file, followed by an AWS phase.

```
P0  Foundation & Contracts ─── alone, first
     ├── P1 Vision     ┐
     ├── P2 Geometry   │
     ├── P3 Core API   │  six in parallel,
     ├── P4 Language   │  one session + worktree each
     ├── P5 Web shell  │
     └── P6 Workspace  ┘
P7  Integration, E2E, hardening ─── alone, last
P8  AWS profile (A1–A10) ─── after P7, alone
```

**Why it doesn't collide:** contract-first, disjoint ownership, separate worktrees outside OneDrive, no shared lockfiles, and gaps are logged rather than patched (`CONTRACT-GAP`).

### 21.2 Phases

| Phase | Deliverables | Status |
|---|---|---|
| P0 Foundation | Monorepo, contracts, JSON Schema, TS generation, fixtures, runnable stubs, typed API client, MSW mocks, seed design system, worktrees | TESTED |
| P1 Vision | 8-stage pipeline, Docker image with Tesseract | TESTED, merged |
| P2 Geometry | Resolution, 10 operations, constraints, insights, Hypothesis tests | TESTED, merged |
| P3 Core API | Clerk, Supabase, queue, worker, versions, orchestration | TESTED, merged |
| P4 Language | Rules, LLM, classification, Whisper, OmniRoute | TESTED, merged |
| P5 Web shell | Landing, auth, shell, dashboard, projects, upload, settings, design system | TESTED, merged |
| P6 Workspace | Renderer, viewer, command bar, voice, history, insights, playground | TESTED, merged |
| P7 Integration | Merge, real-stack e2e, security, CI, docs | TESTED, hardening partial |
| Post-P7 | Building Intelligence (12 tasks in `tasks/plan.md`), all done | TESTED |
| Post-P7 | Hosted Supabase, GitHub push, CI repair, vision accuracy, edge-case pass | Done |
| P8 AWS | A1–A9 built, A10 started | See section 17 |

### 21.3 Original acceptance targets

| Target | Result |
|---|---|
| Vision under 6 s | Met (2.4–2.6 s) |
| Geometry under 50 ms | Met (p95 ≤ 23 ms) |
| 60 fps pan and zoom | Met by in-page measure; no trace |
| Landing Lighthouse ≥ 95 | Partial (A11y and SEO 100, Performance not measured, Best Practices 77) |
| Rules parser ≥ 95 % on fixtures | Met (100 %, 51 of 51) |
| At least 40 P5 tests, 60 P6 tests | Met (web suite now 222) |
| Parallel edits: exactly one wins | Met (6 → 1 + 5 × 409) |
| Zero cloud dependencies in default stack | Met |
| Supabase advisors clean | **Not done** |
| Impeccable and hallmark audits with no high findings | **Not done formally** |

### 21.4 Ownership

Each path has exactly one writer. P0, then P7: root files, `.claude/**`, `e2e/**`, `phases/**`, `packages/contracts/**`, `apps/web/src/contracts/**`, `apps/web/src/lib/api/**`, `apps/web/src/mocks/**`. P1 `services/vision/**`. P2 `services/geometry/**`. P3 `services/api/**`. P4 `services/language/**`. P5 everything else under `apps/web/**`. P6 `features/viewer/**`, `features/workspace/**`, the workspace route, `(dev)/**`. P7 `docs/**`. P8 `infra/**`, `phases/aws/**`, the `aws*` files and listed wiring. Full map: `phases/shared/OWNERSHIP.md`.

### 21.5 AI-assisted development method

The project was built with Claude Code as the implementer under strict rules, which is itself a notable part of the method. Tools used: agent-skills (spec, TDD, security, review), ponytail (minimal code), context7 (library docs), Supabase plugin, impeccable, hallmark, taste-skill and ui-ux-pro-max for UI, playwright-cli for browser QA, token-optimizer. Session protocol: plan, look up library APIs, TDD with incremental commits, then review before handoff. Each phase left a `HANDOFF.md` with honest status.

### 21.6 AWS prompts

| Prompt | Service |
|---|---|
| A1 | S3 |
| A2 | SQS + DLQ |
| A3 | Textract |
| A4 | Lambda + ECR |
| A5 | Transcribe |
| A6 | Bedrock |
| A7 | SNS |
| A8 | ECS Fargate + Terraform |
| A9 | CloudWatch |
| A10 | Deploy, test, destroy, demo (spends money) |

Milestones M0–M9 in `docs/AWS_MIGRATION_PLAN.md`.

---

## 22. Decision log

### Architecture

| ID | Decision | Why |
|---|---|---|
| A1 | Contract-first services | Six sessions in parallel without collisions |
| A2 | Only `services/api` touches Supabase | One security boundary |
| A3 | Shared `X-Internal-Token`; internal services unpublished | Free and sufficient locally |
| A4 | Lexicon in contracts | Three services need the same synonyms |
| A5 | Geometry supports `dry_run` and returns a `ChangeSet` | Powers the preview ghost |
| A6 | Orchestration in `services/api` | It holds HEAD and the transaction |
| A7 | Default parsing is `hybrid` | Offline first; LLM only widens coverage |
| A8 | One JSON document per version | Simple, append-only, fast to load |
| A9 | Dependency-free renderer | Byte-identical and testable |
| A10 | Web talks only to the API; polling with back-off | No RLS surface |
| A11 | uv per service; npm with one lockfile | No shared lockfile collisions |

### Build decisions

| ID | Phase | Decision | Why | Rejected |
|---|---|---|---|---|
| D1 | P0 | Pydantic is the single source of truth | One definition per shape | Hand-written TS |
| D2 | P0 | Plain HTTP with internal token | Free and simple | mTLS, message bus |
| D3 | P3 | Postgres job queue | No extra infrastructure | Redis, Celery |
| D4 | P3 | Compare-and-swap on HEAD | Exactly one of N edits wins | Row locks across HTTP |
| D5 | P4 | Rules first, LLM for UNKNOWN | Offline; keeps LLM away from geometry | LLM-only |
| D6 | P1 | Coordinates are pixels of the preprocessed image | Avoids overlay drift | Mapping to original |
| D7 | P7 | Clarification returns the parsed command | No schema change | New field |
| D8 | P7 | No `Dimension.orientation` | Nearest wall gives it | New field |
| D9 | P7 | "Wall between X and Y" prefers walls with a room each side | Found in e2e | Splitting walls in vision |
| D10 | P7 | mm on unscaled plan refused before resolution | Found in e2e | |
| D11 | P7 | Cross-project list and edit counts deferred | Features, not gaps | |
| D12 | P7 | CSP with `'unsafe-inline'` scripts | Nonces conflict with PPR | Nonce CSP |
| D13 | P7 | e2e as its own package using `@clerk/testing` | Supported bypass of bot protection | Driving the form each test |

### Building Intelligence

Numbers are deterministic and live in geometry. One analysis call with no new tables. All of it needs a scale. Options and fixes are ordinary engine commands. `SPLIT_ROOM` is engine-only. Chatbot: rules first, then an LLM with a facts sheet. Thresholds and rates are indicative defaults in one place.

### Owner decisions

| Date | Decision |
|---|---|
| 2026-11-01 | Rebuild from scratch with a free stack and parallel phases |
| 2026-11-08 | Compliance follows NBC India 2016 |
| 2026-11-08 | Costs default to INR |
| 2026-11-08 | Clerk stays in dev mode; hosting decided later |
| 2026-11-08 | Hosted Supabase "AI x AEC" is the active backend |
| 2026-11-08 | Owner runs git add, commit and push personally |
| 2026-11-09 | "No AWS" replaced by the AWS profile for the review |
| 2026-11-09 | No load balancer; Terraform; S3, SQS, Textract first |
| 2026-11-09 | Region `eu-west-1`; Bedrock skipped on the Free Plan |

AWS design decisions are in section 17.5.

---

## 23. Limitations and risks

### Product

| Limitation | Detail |
|---|---|
| Walls | Solid thick-stroke walls of at least 3 px only. Hairline double-line, curved walls and noisy scans are unsupported and produce no walls, with a warning. |
| Real drawings | **Accuracy has only been measured on synthetic and AI-generated plans.** |
| PDF | Page 1 only |
| Doors | Quarter-circle swings only. Double and sliding doors come out as plain doors. Garage and sliding doors with parallel lines count as windows. Bathroom fixtures can look like swings on dense plans. |
| Columns | Columns fused into wall junctions are not detected |
| Small rooms | Below 0.3 % of the image are dropped |
| Wide gaps | Above 14 % of the longest side are not bridged, unless glazed |
| Geometry | Scales with plan size; very large models are slower. `RESIZE_ROOM` needs roughly axis-aligned sides. Merges that would leave a hole are refused. |
| Room-based wall references | Depend on vision's wall linking |
| Compliance | Indicative only, based on published summaries; not certified |
| Quantities and cost | Assumed heights and ratios; default rates are rough; excludes foundations, roof finishes, external works |
| Structural | Advisory, no load or soil data |
| Furniture | Drawn over the plan, not saved |
| Layouts | Goals matched by rules; site outside the building is not modelled |
| Model storage | One JSON per version, no SQL query over elements |

### Operational

| Risk | Detail |
|---|---|
| Latency | Hosted Supabase is in Ireland; from India each database call costs 0.5–1.5 s, so actions take 2–4 s |
| Free tiers | Supabase pauses after 7 days idle. 500 MB DB and 1 GB storage. LLM free tiers rate-limit under bursts |
| Scale | Rate limiter and insights cache are per process. Whisper and OpenCV are CPU-bound |
| Versions | Next 16, React 19.3, Tailwind 4, Clerk Core 3, MSW 3, Vitest 5, Zod 4 are recent. Local Postgres 17 versus CI 16 |
| E2E | Manual in CI. Running against hosted Supabase leaves test data |
| Web UX | App header and workspace bar stack to 88 px on the workspace route. Search covers only the loaded page of projects |

### AWS demo

| Risk | Mitigation |
|---|---|
| Stack left running | `destroy.ps1`, budget alert, tag `project=aec-demo` |
| Free Plan blocks more services | Keep Tesseract and Whisper selectable |
| Supabase pooler from Fargate | Test early; session URL setting exists |
| Supabase project paused | Unpause before the review |
| Clerk dev keys with a public IP | Keep web on localhost; explicit CORS and authorized parties |
| Secrets in the task definition | Single-owner account, short-lived |
| Tokens over plain HTTP | Ingress limited to one IP |

---

## 24. Roadmap and next steps

### Immediate (faculty review)

1. Finish `infra\scripts\build-push.ps1` (the owner types `yes`). It created ECR repositories but did not push images.
2. Run `deploy.ps1`, confirm the SNS email, point the web app at the printed URL.
3. Run `smoke.ps1`, then one full upload in the browser.
4. Capture evidence: S3 artifacts, SNS email, CloudWatch dashboard, empty DLQ, billing.
5. Run `destroy.ps1` and confirm no billable resources remain.
6. Update `phases/STATUS.md`. Mark `VERIFIED` only what the owner has seen work.
7. Commit the `aws-profile` work (owner).
8. Unpause Supabase the day before the review.

### Quality gaps to close

- A human walkthrough on the real stack, so features can become `VERIFIED`.
- Run Supabase advisors.
- Test real scanned drawings and publish accuracy.
- Commit the worker-crash test.
- Test Firefox, Safari, screen readers and a real microphone.
- Run formal design and security audits.
- Obtain a Lighthouse performance score.

### Product roadmap

Items marked *(doc)* are named in project documents as not built. Items marked *(suggested)* are reasonable extensions and are not commitments in any document.

| Item | Source |
|---|---|
| Learned wall detector for hairline, curved and noisy drawings | doc |
| Custom computer-vision models, real YOLO weights | doc |
| Multi-page PDF | doc (limit) |
| Server-side export: SVG, PNG, PDF, thumbnails | doc |
| DWG, DXF, IFC, Revit import | doc |
| Real-time collaboration | doc |
| Architectural-grade geometry validation | doc |
| Cross-project plan list, edit counts on `/v1/me`, server-side project search | doc (P5 requests) |
| Clerk production instance and web hosting | doc (deferred) |
| Production Supabase in `ap-south-1` (Mumbai) | doc |
| ALB with HTTPS, Secrets Manager, shared rate limiter | doc |
| Nonce-based CSP | doc |
| Pin bye-laws per state, confirm thresholds clause by clause | suggested |
| Multi-floor buildings (`FloorPlanModel` covers one plan) | suggested |
| Save furniture to the model | suggested |

---

## 25. Running the project

Prerequisites: Docker Desktop, Node 22 or newer, Python 3.12 (`py -m uv`), Supabase CLI, a free Clerk application. Windows PowerShell 5.1 has no `&&`.

```powershell
# 1. Copy every .env.example to .env (apps/web/.env.example to .env.local) and add Clerk keys
# 2. Database and storage
cd services/api; supabase start; supabase db reset; cd ../..
# Put SERVICE_ROLE_KEY from `supabase status -o env` into .env
# 3. Backend
docker compose up -d --build --wait vision geometry language api worker
# 4. Web
cd apps/web; npm ci; npm run build; npx next start -p 3000
# 5. E2E (optional)
cd ../../e2e; npm ci; npx playwright install chromium; npx playwright test
```

UI without any backend: `cd apps/web; $env:NEXT_PUBLIC_API_MOCKING="on"; npm run dev`

| Task | Command |
|---|---|
| Service with reload | `cd services/<name>; py -m uv run uvicorn app.main:app --reload --port 800N` |
| Worker | `cd services/api; py -m uv run python -m app.worker` |
| Service gates | `py -m uv run pytest; py -m uv run ruff check .; py -m uv run mypy app` |
| Web gates | `npm test; npx tsc --noEmit; npm run lint; npm run build` |
| Contract change | edit `packages/contracts/src`, run `fixtures/build_api_examples.py` and `scripts/export_schema.py`, then `npm run gen:contracts` |
| New migration | `supabase migration new <name>; supabase db reset` |
| AWS | `build-push.ps1` → `deploy.ps1` → `smoke.ps1` → `destroy.ps1` in `infra/scripts` |

| Symptom | Fix |
|---|---|
| Every API call is 401 | `CLERK_ISSUER` mismatch, or web origin missing from `CLERK_AUTHORIZED_PARTIES` |
| CORS errors | Add the exact origin to `CORS_ORIGINS` |
| Uploads stay queued | Worker not running or cannot reach Postgres |
| Rooms unknown, no scale | Tesseract missing; use the Docker image |
| "Assistant is unavailable" | Language service down |
| First voice command takes 15 s | Whisper loading once |
| Signed images don't load | `SUPABASE_PUBLIC_URL` must be browser-reachable; check CSP `img-src` |

---

## 26. Demo scripts

### Product demo (about 6 minutes)

Fixture: `e2e/fixtures/apartment.png`. Start signed out with the stack running.

| # | Step | Say or show |
|---|---|---|
| 1 | Landing | "The AI reads the instruction; the geometry engine moves the wall; every edit is a version." |
| 2 | Sign up | First-run panel, create "Riverside flat" |
| 3 | Upload | 8-stage timeline in about 3 s |
| 4 | Read the model | LIVING, KITCHEN, BEDROOM, HALL, BATH; "3600" was read, so areas are in m² |
| 5 | Edit by text | Press `/`, type *move the wall between the kitchen and the living room 300 mm left*, Enter, Apply → v2 |
| 6 | Clarification | *delete the door* → "Which door do you mean?" |
| 7 | Guardrails | *make it look like a banana* → friendly refusal |
| 8 | Voice | Hold `V`, *rename the bathroom to wet room* |
| 9 | History | Undo twice, redo, new edit; discarded branch visible |
| 10 | Re-process | Undo returns to the edited model |

Add for the review: Analyze tab (BOQ, cost, compliance), Ask ("How many bedrooms?"), a layout preview.

**Fallback lines:** without OmniRoute everything above still works, because rules cover these phrases. Voice is slow only on first use.

### AWS demo (after deployment)

Follow one upload: browser → API on Fargate → SQS message → worker claims in Postgres → Lambda with Textract → artifacts in S3 → SNS email → CloudWatch dashboard and the saved "follow one job" query. Then `terraform destroy`.

### Likely review questions

| Question | Honest answer |
|---|---|
| Is the AI editing the drawing? | No. It only produces a structured command, which non-AI code validates and applies. |
| What if the LLM is down? | Rules still handle known phrasing. Nothing breaks. |
| What if it's ambiguous? | It asks, showing candidates. |
| How accurate is it? | Clean plans: 27 of 31 rooms and 7 of 7 bedrooms typed correctly. Real scans have not been tested. |
| Is compliance legally valid? | No. It is indicative and says so on every report. |
| Is it really on AWS? | Say only what has actually been deployed at that moment. Check section 17.7. |
| Why Clerk and Supabase on AWS? | Scope: AWS for compute, queueing, AI and monitoring. Auth and data stayed to limit cost and risk. |
| How do you prevent two people overwriting each other? | Compare-and-swap on the version pointer; the loser gets a stale-model message. |
| How is it tested? | 1,234 automated tests, 13 browser end-to-end tests, CI on every push. |

---

## 27. Document drift register

Where older documents are out of date. This file reflects the corrected position.

| Document | Says | Actual |
|---|---|---|
| `docs/AWS_MIGRATION_PLAN.md`, `phases/STATUS.md` | Nothing applied on AWS; A10 NOT_STARTED (status block and "9 services" text are stale) | Deployed three times, A10 IN_PROGRESS, 8 services in design |
| `docs/AWS_MIGRATION_PLAN.md` §10 | Region still open | Decided (`eu-west-1`) |
| `README.md`, AWS plan | "10" AWS services | 9 will run; Bedrock off |
| `docs/ARCHITECTURE.md` §2, `docs/SECURITY.md`, `docs/TECH_STACK.md` | No AWS; zero cloud lock | AWS profile exists; only `phases/shared/ARCHITECTURE.md` was updated |
| `docs/ARCHITECTURE.md` §8, CONTRACTS §10 | Clerk keyless mode works | Clerk Core 3 no longer auto-creates keyless keys |
| `phases/STATUS.md`, `docs/FEATURE_STATUS.md` (2026-11-07) | CI never ran; nothing pushed | Pushed; 5 runs, last 3 green |
| `phases/STATUS.md`, `docs/FEATURE_STATUS.md` (2026-11-07) | OmniRoute LLM path not run | Run through the real gateway |
| `phases/STATUS.md`, `docs/FEATURE_STATUS.md` | Test counts 151 to 276 per suite; web 209 | 193 API, 129 vision, 237 geometry, 299 language, 222 web |
| `docs/FEATURE_STATUS.md` | e2e 10 tests | 13 defined |
| `phases/shared/CONTRACTS.md` §7, §10 | `provider` lacks `transcribe`; no AWS env vars | Code has both |
| `services/api/.env.example` | Comment `AWS_REGION=ap-south-1` | `eu-west-1` |
| Handoffs | Various older test counts; P3 says `supabase db reset` not run | P7 later ran the real stack |
| `docs/TECH_STACK.md` §1, §6 | No AWS; missing analysis features | Pre-dates P8 changes and omits Building Intelligence |
| `docs/Testing.md` | Empty file | Use section 19 here |
| Root `package-lock.json` | 85-byte untracked file | Stray |

---

## 28. Using this file for slides and reports

### Suggested presentation (15 minutes, about 15 slides)

| # | Slide | Source |
|---|---|---|
| 1 | Title and one-sentence pitch | 1 |
| 2 | Problem | 2.1 |
| 3 | Solution and the core principle | 2.2, 2.6, mantra |
| 4 | User journey | 2.4 |
| 5 | Architecture | 5.1, 5.2 |
| 6 | Reading a plan: 8 stages | 9.1 |
| 7 | Editing: the safety pipeline | 5.5, 10.1 |
| 8 | Deterministic engine and refusal behaviour | 10.4, 10.5 |
| 9 | Building intelligence | 11 |
| 10 | Live demo | 26 |
| 11 | AWS architecture and real status | 17.3, 17.4, 17.7 |
| 12 | Engineering method | 21.1, 21.5 |
| 13 | Results | 19.1, 19.4, 19.5 |
| 14 | Limitations | 23 |
| 15 | Future work | 24 |

Screenshots: `apps/web/qa/p7/` (preview ghost, clarification, history, compliance, cost, interior, takeoff, ask, layouts, outages) and `apps/web/qa/p5/` (every screen in light and dark at 3 sizes).

### Suggested report chapters

| Chapter | Source |
|---|---|
| Abstract | 1 |
| Introduction, problem, objectives | 2 |
| Existing system and motivation | 3.1 |
| Requirements (functional, non-functional) | 2.5, 21.3 |
| System design | 4, 5, 8, 13.1 |
| Implementation | 9–15 |
| Cloud deployment | 17 |
| Security | 18 |
| Testing and results | 19, 20 |
| Limitations | 23 |
| Conclusion and future scope | 24 |
| Appendices | 14, 16, 22 |

### Writing rules for reports

- Say "tested", never "verified" or "production-ready".
- Say "9 AWS services, 8 seen working and SQS partly" (section 17.3); never say "running on AWS" unless it is deployed right now.
- Say "indicative, based on published summaries of NBC India 2016".
- Say accuracy figures are from clean, AI-generated plans.
- Do not invent market data, user studies or literature citations. None exist in this repository, so a literature review must be researched separately.
- Costs are estimates from default rates, not quotations.

---

## 29. Numbers cheat sheet

| Metric | Value |
|---|---|
| Automated tests passing | 1,234 |
| Test modules | 50 (Python 39, web 11) |
| E2E tests defined | 13 in 7 specs |
| Latest e2e run | 11 passed, 2 skipped |
| Backend Python (app code) | About 8,300 lines: vision 1,895, geometry 2,745, language 1,022, API 1,849, contracts 787 |
| Python tests | About 4,900 lines |
| Product TS and TSX (excluding tests, UI kit, mocks, generated) | About 7,190 lines in 85 files |
| Web tests | About 1,880 lines |
| UI primitives | 30 |
| Terraform | 12 files, 575 lines, 41 planned resources |
| Tracked files | 639 |
| Commits on `main` | 30 |
| Services | 4 backend + 1 web + worker |
| Public `/v1` routes | 23 |
| Internal routes | 13 |
| Database tables | 7 |
| JSON Schema files | 51 |
| Edit operations | 10 public + `SPLIT_ROOM` |
| Pipeline stages | 8 (3 critical) |
| Reject stages | 6 |
| Room types | 17 |
| Error codes | 14 |
| Constraint codes | 11 |
| BOQ lines | 21 |
| Compliance categories | 7 |
| Cost line items | 12 |
| Interior themes | 5 |
| Structural categories | 5 |
| Rules parser coverage | 51 of 51 fixtures |
| Vision time on apartment | 2.4–2.6 s |
| Geometry execute p95 | ≤ 23 ms |
| Landing LCP / CLS | 213 ms / 0 |
| Upload limit / audio limit | 25 MiB / 10 MiB, 60 s |
| Pixel cap | 64 MP |
| Signed URL life | 15 minutes |
| Rate limits | 300 reads, 90 writes per minute |
| Quotas | 200 projects, 100 plans per project |
| Accuracy (clean plans) | Rooms 27 of 31; bedrooms 7 of 7; scale 3 of 3; doors 16 of 16 on simple and medium plans |
| Edge-case checks | About 150; 12 fixes |
| AWS services planned to run | 9 |
| Real AWS resources from the demo | 4 empty ECR repositories, $10 budget |

---

## 30. Glossary

| Term | Meaning |
|---|---|
| AEC | Architecture, Engineering and Construction |
| Building Model / `FloorPlanModel` | Canonical structured plan, one JSON per version |
| HEAD | `floorplans.current_model_version`, the current version |
| Preview ghost | Overlay of what an edit would change, before saving |
| Clarification | The system asking which element, instead of guessing |
| Brief | LLM-safe plan summary with no ids or coordinates |
| Facts sheet | Same idea for chatbot answers, with measurements |
| Discarded version | A redo branch abandoned by a new edit, kept for audit |
| Fencing | `attempts` token stopping a slow worker from committing |
| BOQ | Bill of Quantities |
| NBC | National Building Code of India |
| mm/px | Millimetres per image pixel, the scale |
| OmniRoute | Self-hosted free-LLM gateway; "combo" is its fallback chain |
| RLS | Row Level Security in Postgres |
| IDOR | Accessing another user's object by changing an id |
| CAS | Compare-and-swap |
| DLQ | Dead-letter queue |
| MSW | Mock Service Worker |
| PPR | Partial Prerendering in Next.js |

---

## 31. Where every other document fits

| File | Purpose | Trust |
|---|---|---|
| `PROJECT_SOURCE_OF_TRUTH.md` | This file | Current |
| `CLAUDE.md` | Rules for every AI session | Current |
| `README.md` | Summary and quick start | Mostly current |
| `FULL_PROJECT_CONTEXT.md` | Predecessor spec, cited by section number | Historical |
| `phases/README.md`, `P0`–`P7` | Original build prompts and acceptance criteria | Historical plan |
| `phases/aws/*` | AWS prompts | Current plan |
| `phases/STATUS.md` | Phase status log | Partly stale |
| `phases/shared/ARCHITECTURE.md` | Confirmed design | Current |
| `phases/shared/CONTRACTS.md` | Normative contract spec | Current apart from section 27 notes |
| `phases/shared/OWNERSHIP.md`, `TOOLING.md` | Ownership and tools | Current |
| `docs/ARCHITECTURE.md` | Final P7 architecture and decisions | Partly stale on AWS |
| `docs/FEATURE_STATUS.md` | Dated test and status notes | Accurate per date; early entries stale |
| `docs/AWS_MIGRATION_PLAN.md` | AWS design and milestones | Current apart from section 27 notes |
| `docs/TECH_STACK.md` | Stack analysis | Pre-dates AWS |
| `docs/RUNBOOK.md`, `DEMO_SCRIPT.md`, `SECURITY.md` | Operations, demo, threat model | Mostly current |
| `tasks/plan.md` | Building Intelligence plan | Complete |
| `infra/README.md` | AWS deployment steps | Current |
| `apps/web/DESIGN.md` | Design system | Current |
| `services/*/HANDOFF.md`, `apps/web/HANDOFF.shell.md`, `apps/web/src/features/workspace/HANDOFF.md` | Phase handoffs | Point-in-time |
| `services/language/docs/OMNIROUTE.md` | OmniRoute setup | Current |

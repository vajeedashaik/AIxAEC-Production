# AEC AI Platform

Upload a floor plan (PNG / JPG / PDF). Computer vision turns it into a **typed, versioned Building Model**: walls, rooms, doors, windows, columns, stairs and dimensions. Edit it by typing, speaking or clicking ("move the wall between the kitchen and the living room 300 mm left"). Language models only *interpret* text into a structured command; a **deterministic geometry engine** validates and applies every change, and each change becomes a new immutable version with undo/redo.

Free stack only: Clerk (auth), Supabase (Postgres + Storage), OmniRoute (free LLMs), Tesseract, faster-whisper, local Docker. No AWS, GCP or Azure.

## Architecture

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

| Path | What |
|---|---|
| `packages/contracts` | `aec_contracts`: every cross-boundary shape (Pydantic → JSON Schema → TypeScript), the room lexicon, fixtures |
| `services/{vision,geometry,language,api}` | FastAPI services, one uv project each |
| `apps/web` | Next.js 16 app (Tailwind 4, shadcn/ui, Clerk, TanStack Query, MSW) |
| `phases/` | The build plan: one prompt per Claude session, shared architecture, contracts, ownership, tooling |

## Quick start (Windows PowerShell)

Prerequisites: Python launcher `py` (uv via `py -m uv`), Node 22+, Docker Desktop (for Supabase / compose), Supabase CLI.

```powershell
# contracts
cd packages/contracts; py -m uv sync; py -m uv run pytest; cd ../..

# any service (vision 8001, geometry 8002, language 8003, api 8000)
cd services/geometry; py -m uv sync; py -m uv run uvicorn app.main:app --port 8002

# web against mocks (no backend needed)
cd apps/web; npm install; copy .env.example .env.local   # set NEXT_PUBLIC_API_MOCKING=on
npm run dev

# everything in Docker (after copying .env.example to .env)
docker compose up --build
```

Regenerate contracts after a change (P7 only): `cd packages/contracts; py -m uv run python scripts/export_schema.py`, then `cd apps/web; npm run gen:contracts`.

## Build plan

Start with [phases/README.md](phases/README.md). Status: [phases/STATUS.md](phases/STATUS.md). Shared docs: [ARCHITECTURE](phases/shared/ARCHITECTURE.md) · [CONTRACTS](phases/shared/CONTRACTS.md) · [OWNERSHIP](phases/shared/OWNERSHIP.md) · [TOOLING](phases/shared/TOOLING.md).

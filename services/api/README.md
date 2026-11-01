# services/api (Core API, :8000)

Public REST API: Clerk auth, Supabase DB + Storage, job queue + worker, versions, undo/redo, edit orchestration.

Owned by **P3** (see `phases/shared/OWNERSHIP.md`). Contracts: `phases/shared/CONTRACTS.md`.
Status: **P0 stub**. `/healthz` and `/readyz` work; every `/v1` route returns `501` with the request/response models wired, so `/docs` already shows the contract.

## Run
```powershell
cd services/api
py -m uv sync
copy .env.example .env
py -m uv run uvicorn app.main:app --reload --port 8000
```

Every `/v1` route needs `Authorization: Bearer <Clerk session token>`. The P0 stub only checks the header is present; P3 verifies it against Clerk's JWKS.

## Test
```powershell
py -m uv run pytest
py -m uv run ruff check .
py -m uv run mypy app
```

## Docker
Build context is the repo root (the image copies `packages/contracts`):
`docker build -f services/api/Dockerfile .` or `docker compose up api` from the root.

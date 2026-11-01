# services/geometry (Geometry, :8002)

Stateless, deterministic: entity resolution, validation, the 10 operations, insights, plan brief.

Owned by **P2** (see `phases/shared/OWNERSHIP.md`). Contracts: `phases/shared/CONTRACTS.md`.
Status: **P0 stub**. `/healthz` and `/readyz` work; every `/v1` route returns `501` with the request/response models wired, so `/docs` already shows the contract.

## Run
```powershell
cd services/geometry
py -m uv sync
copy .env.example .env
py -m uv run uvicorn app.main:app --reload --port 8002
```

Every `/v1` route needs `X-Internal-Token: <INTERNAL_SERVICE_TOKEN>` (401 otherwise).

## Test
```powershell
py -m uv run pytest
py -m uv run ruff check .
py -m uv run mypy app
```

## Docker
Build context is the repo root (the image copies `packages/contracts`):
`docker build -f services/geometry/Dockerfile .` or `docker compose up geometry` from the root.

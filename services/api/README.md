# services/api (Core API, :8000)

The only public backend and the only database and storage client: Clerk auth, owner scoping, Supabase Postgres + Storage,
the processing queue and worker, append-only model versions with undo/redo and an audit log, and edit orchestration
across the vision, geometry and language services. Owned by **P3** (`phases/shared/OWNERSHIP.md`).

## Layout
| Module | What |
|---|---|
| `app/main.py` | app factory, error envelope, request IDs, security headers, CORS, body cap, safe 500s |
| `app/v1.py` | every route in CONTRACTS.md §8 |
| `app/auth.py`, `app/clerk.py` | Clerk JWT verification (PyJWT + JWKS), user provisioning, rate-limit hook |
| `app/repo.py` | owner-scoped lookups, ORM → DTO mapping |
| `app/versions.py` | HEAD pointer, append version, undo/redo, history |
| `app/editing.py` | parse → execute → persist pipeline |
| `app/jobs.py`, `app/worker.py` | Postgres queue (`FOR UPDATE SKIP LOCKED`), heartbeat, fencing, `python -m app.worker` |
| `app/uploads.py` | type/MIME/magic checks, Pillow/PyMuPDF probes |
| `app/storage.py` | `BlobStore` interface + Supabase Storage implementation |
| `app/clients/*` | httpx clients with retry and circuit breaker |
| `supabase/migrations/` | the schema (CONTRACTS.md §9), RLS on, buckets |

## Run
```powershell
cd services/api
py -m uv sync
copy .env.example .env          # fill CLERK_ISSUER and SUPABASE_SERVICE_ROLE_KEY (from `supabase status`)
supabase start                  # Docker; first run downloads the images
supabase db reset               # applies supabase/migrations
py -m uv run uvicorn app.main:app --reload --port 8000
py -m uv run python -m app.worker   # second terminal; start as many as you like
```

## Test
Tests need a real Postgres. Each run creates and drops its own `aec_test_*` database on that server, schema from the
migrations. Default is local Supabase (`127.0.0.1:54322`); any Postgres 15+ works:
```powershell
docker run -d --name aec-p3-test -e POSTGRES_PASSWORD=postgres -p 127.0.0.1:54399:5432 postgres:16
$env:TEST_DATABASE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:54399/postgres"
py -m uv run pytest
py -m uv run ruff check .
py -m uv run mypy app tests
```
The Supabase Storage round trip is opt-in: `$env:SUPABASE_TEST = "1"` with `SUPABASE_URL` and
`SUPABASE_SERVICE_ROLE_KEY` set.

## Docker
Build context is the repo root (the image copies `packages/contracts`); `Dockerfile.dockerignore` trims it.
`docker compose up api worker` from the root, or `docker compose -f services/api/compose.yaml up` here.
Scale workers with `WORKER_REPLICAS=3`.

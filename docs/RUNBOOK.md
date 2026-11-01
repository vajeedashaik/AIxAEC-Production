# Runbook

Windows PowerShell 5.1 is assumed (no `&&`; the Python launcher is `py`, uv runs as `py -m uv`). Bash works the same with `/` paths.

## 1. Setup from zero

Prerequisites: Docker Desktop (running), Node 22+ (CI uses 24), Python 3.12 via `py`, `uv` (`py -m pip install uv`), Supabase CLI.

1. **Clerk** (dashboard.clerk.com, free): create an application. Copy the publishable key, the secret key and the Frontend API URL (the issuer).
2. **Env files**: copy each `.env.example` to `.env` (`apps/web/.env.example` → `apps/web/.env.local`).
   - `apps/web/.env.local`: `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`, `NEXT_PUBLIC_API_URL=http://localhost:8000`, `NEXT_PUBLIC_API_MOCKING=off`.
   - `services/api/.env`: `CLERK_ISSUER`, `CLERK_AUTHORIZED_PARTIES=["http://localhost:3000"]`, `CORS_ORIGINS=["http://localhost:3000"]`, `SUPABASE_SERVICE_ROLE_KEY` (step 3).
   - Root `.env` (read by compose): the same Clerk values plus `SUPABASE_SERVICE_ROLE_KEY`.
   - `INTERNAL_SERVICE_TOKEN` must match across services. Any value works in development; production refuses the default.
3. **Supabase (local)**:
   ```powershell
   cd services/api; supabase start; supabase db reset    # applies supabase/migrations, creates private buckets
   supabase status -o env                                # SERVICE_ROLE_KEY → SUPABASE_SERVICE_ROLE_KEY
   ```
   Hosted Supabase instead: `DATABASE_URL` = transaction pooler (6543), `WORKER_DATABASE_URL` = session pooler (5432), `SUPABASE_URL` = project URL. Apply migrations with `supabase db push`.
4. **OmniRoute** (optional; without it the language service uses rules only, which cover every fixture command): follow `services/language/docs/OMNIROUTE.md`, then set `LLM_API_KEY` and `LLM_MODEL` in `services/language/.env`.
5. **Start everything**:
   ```powershell
   docker compose up -d --build --wait vision geometry language api worker   # backend (+ omniroute if configured)
   cd apps/web; npm ci; npm run build; npx next start -p 3000                 # or: docker compose up -d web
   ```
   Open http://localhost:3000. API health: http://localhost:8000/readyz.

## 2. Daily development

| Task | Command |
|---|---|
| One service with reload | `cd services/<name>; py -m uv run uvicorn app.main:app --reload --port 800N` (vision 1, geometry 2, language 3, api 0) |
| Worker | `cd services/api; py -m uv run python -m app.worker` |
| Web against mocks (no backend) | `cd apps/web; $env:NEXT_PUBLIC_API_MOCKING="on"; npm run dev` |
| Service gates | `py -m uv run pytest; py -m uv run ruff check .; py -m uv run mypy app` |
| API tests | need Postgres: `docker run -d --name aec-testpg -e POSTGRES_PASSWORD=postgres -p 127.0.0.1:54399:5432 postgres:16`, then `$env:TEST_DATABASE_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:54399/postgres"` |
| Web gates | `cd apps/web; npm test; npx tsc --noEmit; npm run lint; npm run build` |
| Contract change | edit `packages/contracts/src`, then `py -m uv run python fixtures/build_api_examples.py; py -m uv run python scripts/export_schema.py`, then `cd apps/web; npm run gen:contracts` |
| New migration | `cd services/api; supabase migration new <name>; supabase db reset` |
| e2e | stack running, then `cd e2e; npm ci; npx playwright install chromium; npx playwright test`. `$env:E2E_COMPOSE="1"` also runs the outage tests (they stop and start compose services). Clerk keys come from `apps/web/.env.local`. Screenshots land in `apps/web/qa/p7/`. |

## 3. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Every API call is 401 | `CLERK_ISSUER` doesn't match the Frontend API URL, or the web origin is missing from `CLERK_AUTHORIZED_PARTIES` (`azp` is required). |
| Browser shows CORS errors | Add the exact web origin (scheme + host + port) to `CORS_ORIGINS`. |
| Uploads stay QUEUED | The worker isn't running (`docker compose ps worker`) or can't reach Postgres. Stale jobs are recovered after `PROCESSING_STALE_SECONDS`. |
| Job FAILED "vision unavailable" | `docker compose up -d --wait vision`, then "Retry" in the project page (or `POST /v1/floorplans/{id}/process`). |
| Room labels UNKNOWN and no scale | Vision without Tesseract (`OCR_PROVIDER=auto` falls back to stub). Use the Docker image, or install Tesseract and put it on PATH. |
| Edits say "The command assistant is unavailable" | The language service is down: `docker compose up -d language`. |
| `/readyz` of language shows `llm: unreachable` | OmniRoute isn't running or the key is wrong. Rules still work. |
| First voice command takes ~15 s | Whisper downloads and loads `base.en` once into the `whisper-models` volume. |
| Signed images don't load in the browser | `SUPABASE_PUBLIC_URL` must be what the *browser* can reach (`http://127.0.0.1:54321` locally). Also check the CSP `img-src` in `apps/web/next.config.ts`. |
| `supabase db reset` ends with a 502 | Containers were still restarting. `supabase status` should show them healthy a few seconds later; the migration was applied. |
| Clerk "Verifying your request" blocks automation | Expected: bot protection. e2e uses `@clerk/testing` testing tokens. |
| `docker compose` builds slowly or pulls fail | Large images (language ≈2 GB). Retry on a stable network; images are cached afterwards. |

# P3: Core API & Worker (the system of record)

> Parallel phase. Worktree `phase/p3-api`. **Write only inside `services/api/**`** (including `services/api/supabase/**`).

## Read first
`CLAUDE.md` · `phases/shared/{ARCHITECTURE,CONTRACTS,OWNERSHIP,TOOLING}.md` (CONTRACTS §8–§10 are your spec) · `FULL_PROJECT_CONTEXT.md` §7 (job lifecycle), §8 (outcomes), §10 (versioning), §12–§16 (uploads, security, resilience).

## Mission
Build the **only public backend** and the **only database and storage client**. It verifies Clerk users, owner-scopes every resource, stores uploads in Supabase Storage, runs the processing queue on Postgres, persists append-only model versions with undo/redo and an audit log, and **orchestrates edits** across the language and geometry services. You never import vision, geometry or language code. You talk to them over HTTP using `aec_contracts` types only.

## 1. Database (Supabase)
- Migrations in `services/api/supabase/migrations/` (Supabase CLI): implement CONTRACTS.md §9 exactly. Add `updated_at` triggers, and enable **RLS on every table with no policies**.
- Create the buckets `floorplans` and `artifacts` (private) in a migration or seed (`storage.buckets`).
- Run locally with `supabase start` (Docker), then `supabase db reset`. Use the **Supabase plugin's skills** (`supabase`, `supabase-postgres-best-practices`) and, once authenticated, the **Supabase MCP** to run advisors (security and performance) against your schema. Fix every warning or justify it in the HANDOFF.
- SQLAlchemy 2 (typed ORM mapping onto these tables, **no** `create_all` in production paths) + psycopg 3. With a Supabase pooler in transaction mode, set `prepare_threshold=None`. The worker uses a session-mode or direct connection.

## 2. Auth (Clerk)
- Verify `Authorization: Bearer <token>` offline with **PyJWT + JWKS** from `CLERK_JWKS_URL` (cache the keys, refresh on an unknown `kid`). Check RS256, `exp`/`nbf` (leeway 30 s), `iss == CLERK_ISSUER`, and `azp ∈ CLERK_AUTHORIZED_PARTIES`. Confirm the current Clerk guidance with context7.
- `get_current_user`: look up `users.clerk_user_id = sub`, else provision. Email and name come from token claims if present, else from the Clerk Backend API (`CLERK_SECRET_KEY`) best-effort. **The user id never comes from the client.**
- Every repository method takes `owner_id`. Another user's resource → `404 not_found`. Add an **IDOR sweep test** that walks every route with a second user.

## 3. Projects and uploads
- CRUD and pagination per CONTRACTS §8, with quotas (`MAX_PROJECTS_PER_USER`, `MAX_FLOORPLANS_PER_PROJECT` → 409 `quota_exceeded`). `thumbnail_url` = signed URL of the latest `preprocessed` artifact.
- Upload validation: extension ∈ {png, jpg, jpeg, pdf}, the declared MIME **and magic bytes** must agree, non-empty, ≤ `MAX_UPLOAD_BYTES` (stream with a running counter; reject early with 413). Cheap probe with Pillow/PyMuPDF (pixel cap, encrypted or zero-page PDF). Sanitise the filename for display only. The server generates storage keys (CONTRACTS §9). Compute the SHA-256.
- Order: store blob → insert rows (floorplan with the next `version` per project, plus a `PENDING` job) → commit. If the commit fails, delete the orphan blob. Auto-enqueue unless `?process=false`.
- Delete project or floorplan: commit the DB delete first, then delete blobs by prefix (a failure only orphans blobs, so log it).
- Downloads only via short-lived **signed URLs** (15 min).

## 4. Processing queue and worker (replaces SQS/Lambda)
- `POST /process`: lock the floorplan row; if a live job exists → 409 `already_processing`; fail *stale* jobs (no heartbeat for `PROCESSING_STALE_SECONDS`); insert a `PENDING` job. Return 202.
- Worker (`python -m app.worker`, separate process and compose service):
  - **Atomic claim**: `UPDATE processing_jobs SET status='PROCESSING', attempts=attempts+1, started_at=now(), heartbeat_at=now() WHERE id = (SELECT id FROM processing_jobs WHERE status='PENDING' OR (status='PROCESSING' AND heartbeat_at < now() - stale) ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *`.
  - Poison guard: `attempts > PROCESSING_MAX_ATTEMPTS` → `FAILED` "giving up".
  - Heartbeat every 15 s while working. Mirror the status onto `floorplans.status`.
  - Download the source → `POST vision /v1/analyze` (timeout 180 s, retry with bounded backoff on 5xx or connection errors only) → store artifacts → **optionally** call language `/v1/rooms/classify` for rooms still `UNKNOWN` that have label text (best-effort, so a failure leaves them `UNKNOWN`) → append a `building_models` row (`origin=PROCESSING`, `parent_version = current HEAD`, version = max+1) → set `current_model_version`. Re-processing therefore **branches from HEAD**, so Undo returns to the user's edits.
  - Any exception → rollback → job `FAILED` with a user-safe message. Never leave a job stuck in `PROCESSING`.
  - Graceful shutdown on SIGINT/SIGTERM. Run N workers safely.

## 5. Versioning, edits, undo/redo
- `get_head(floorplan)` uses `current_model_version`, never "max version".
- **Edit orchestration** (`POST /commands` and `/commands/interpret`):
  1. Load HEAD. If `expected_version` is given and ≠ HEAD → 409 `stale_model`.
  2. If `instruction`: `POST geometry /v1/models/brief` → `POST language /v1/commands/parse`. `UNKNOWN` → `REJECTED(stage="parse", detail=…)`. `ERROR` or language down → `REJECTED(stage="parse")` with a friendly message (the model is unchanged).
  3. `POST geometry /v1/commands/execute {model, command, dry_run}`.
  4. interpret: return `PREVIEW` (candidate model + changes, base version). **Don't persist and don't audit.**
  5. execute + `APPLIED`: in **one transaction**: `SELECT … FOR UPDATE` the floorplan, re-check HEAD (CAS), mark later non-discarded versions `discarded` if HEAD was behind, insert the audit row, insert the new version (`origin=EDIT`, parent=HEAD), then do a compare-and-swap `UPDATE floorplans SET current_model_version=new WHERE id=… AND current_model_version=old`. Zero rows or a unique violation → 409 `stale_model`.
  6. CLARIFICATION / REJECTED: roll back any partial work, then commit an audit row (`status`, `stage`, `error`, `clarification`).
- **Undo** → HEAD := `head.parent_version`. **Redo** → HEAD := the non-discarded child of HEAD. Both are audited (`UNDO`/`REDO`), copy no data, take `expected_version` and return 409 `conflict` when there is nothing to undo or redo.
- **Voice**: read the multipart `audio` capped at `MAX_AUDIO_BYTES`, check the content type, call language `/v1/speech/transcribe`, then the same pipeline. Return `transcript`. Use `def` routes (threadpool).
- `GET /model` returns HEAD (or `?version=`) + summary + insights (from geometry). Cache insights per (floorplan, version) in-process.
- `GET /history`: versions + edit log + `can_undo` / `can_redo`.

## 6. Cross-cutting
- **Service clients** (`app/clients/{vision,geometry,language}.py`): httpx with timeouts, `X-Internal-Token`, `X-Request-ID` propagation, `call_with_retry` (bounded exponential backoff) for idempotent calls, and a small circuit breaker. Map upstream failures to 502/503 `upstream_unavailable`.
- **Middleware**: CORS (only `CORS_ORIGINS`; methods GET/POST/PATCH/DELETE/OPTIONS), security headers (`nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`), a max body size, a request ID, and safe 500s (the envelope carries CORS headers).
- **Rate limiting**: in-process fixed window per user (else IP) with `read` / `write` buckets. 429 + `Retry-After`. Document that it's per-process.
- **Startup guards** in production: refuse the default `INTERNAL_SERVICE_TOKEN`, `*` in CORS or a missing Clerk issuer.
- **Logging**: JSON with request ID, user ID (never the token) and a redaction filter for secrets.

## Tests
- Run against **real Postgres** (`supabase start`, or a disposable Postgres via `TEST_DATABASE_URL`), schema from the migrations, transactional per-test isolation. Storage is a `BlobStore` interface with an in-memory fake for tests and a Supabase implementation (one opt-in integration test).
- Clerk: generate an RSA key pair in tests and serve a fake JWKS. Cover valid, expired, wrong `iss`, wrong `azp`, unknown `kid` and malformed tokens.
- Downstream services: mock with **respx** using the contract fixtures (`packages/contracts/fixtures/api/*.json` and fixture models).
- Must cover: the IDOR sweep, upload hardening (magic mismatch, empty, oversize, bomb, encrypted PDF), quotas, the job lifecycle (claim exclusivity with 2 concurrent workers, stale recovery, attempts cap, vision FAILED → job FAILED with stages persisted), reprocess-then-undo returns to edits, **6 parallel edits → exactly 1 APPLIED and 5 × 409**, undo/redo/discard semantics, interpret doesn't persist, rejected edits audited with the model untouched, voice happy path plus 415/413, rate-limit 429, safe 500 with CORS, and the end-to-end workflow test (create → upload → process → model → NL edit → v2 → undo → redo → history).

## Done when
- [ ] Every endpoint in CONTRACTS §8 is implemented and matches the DTOs (assert with `aec_contracts.public` in tests).
- [ ] Migrations apply cleanly on `supabase db reset`, and the Supabase advisors are clean or justified.
- [ ] Worker and API both run in compose (`services/api/compose.yaml`: `api` + `worker`).
- [ ] Tests, ruff and mypy are green. `HANDOFF.md` is complete (env setup, Supabase steps, limitations).
- [ ] `/ponytail-review`, `security-and-hardening` and `code-review-and-quality` done.

## Tooling
**supabase plugin** (skills + MCP), **context7** (FastAPI, SQLAlchemy 2, psycopg 3, supabase-py, PyJWT, Clerk backend docs, respx), `api-and-interface-design`, `security-and-hardening`, `test-driven-development`, `observability-and-instrumentation`.

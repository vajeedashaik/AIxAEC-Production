# HANDOFF: services/api (P3)

## Status
| Feature | Status |
|---|---|
| Schema migration (CONTRACTS §9, `updated_at` triggers, RLS on with no policies, private buckets) | TESTED on plain Postgres 16; `supabase db reset` **not yet run** (see limitations) |
| Clerk auth: RS256 via JWKS (cached, refresh on unknown `kid` with cooldown), `exp`/`nbf` leeway 30 s, `iss`, `azp`; provisioning from claims, else Clerk Backend API best effort | TESTED with a fake JWKS server |
| Owner scoping on every route, IDOR sweep (17 owner-scoped routes → 404 as a second user, no upstream calls) | TESTED |
| Projects CRUD, pagination, quotas (409 `quota_exceeded`), `floorplan_count`, `thumbnail_url` | TESTED |
| Uploads: extension + MIME + magic, empty, size cap, pixel cap/bomb, corrupt image/PDF, encrypted/absurd PDF, filename sanitising, server keys, SHA-256, orphan-blob cleanup | TESTED |
| Deletes: DB first, then blobs by prefix (failure only logs orphans) | TESTED |
| Signed URLs (15 min) via `BlobStore` | TESTED with the in-memory fake; Supabase implementation IMPLEMENTED (opt-in test not run) |
| Queue: `/process` (lock, 409 `already_processing`, stale-fail, 202), atomic claim, poison cap, heartbeat, status mirror, stale recovery, fencing by `attempts` | TESTED (incl. 2 concurrent workers) |
| Worker: vision with bounded retry on 5xx/connection only, artifacts, best-effort room classification, PROCESSING version branching from HEAD, graceful SIGINT/SIGTERM | TESTED (signal handling itself not unit-tested) |
| Edit orchestration: brief → parse → execute → CAS persist; interpret never persists/audits; rejects/clarifications audited | TESTED (6 parallel edits → 1 APPLIED, 5 × 409 `stale_model`) |
| Undo/redo/discard, history, reprocess-then-undo returns to edits | TESTED |
| Voice: content type 415, size 413, empty 422, transcribe → same pipeline, `dry_run` | TESTED |
| `GET /model` with in-process insights cache | TESTED |
| Middleware: CORS, security headers, body cap (incl. chunked), request IDs, safe 500 with CORS, rate limit 429 + `Retry-After`, redacting JSON logs, production startup guards | TESTED |
| Compose `api` + `worker` | TESTED as containers: image builds, API `/healthz` + `/readyz` against a migrated Postgres, worker polls and exits 0 on SIGTERM. Full compose stack not run (needs P1/P2/P4) |
| End-to-end against real vision/geometry/language | NOT_STARTED (needs P1/P2/P4, P7) |

151 tests pass, 1 skipped (opt-in Supabase Storage). `ruff check .` and `mypy app tests` (strict) are clean.

## How to run
See `README.md`. Short version:
1. `py -m uv sync`, `copy .env.example .env`.
2. `supabase start`, then `supabase db reset` (applies `supabase/migrations`, creates the buckets). Copy the service-role
   key from `supabase status` into `SUPABASE_SERVICE_ROLE_KEY`.
3. Set `CLERK_ISSUER` (Clerk dashboard → API keys → Frontend API URL) and `CLERK_AUTHORIZED_PARTIES` to the web origins.
   `CLERK_SECRET_KEY` is optional: it only fills email/name when the session token has no `email`/`name` claims. To
   avoid that call, add `{"email": "{{user.primary_email_address}}", "name": "{{user.full_name}}"}` to the Clerk
   session token template.
4. `uvicorn app.main:app --port 8000` and `python -m app.worker` (or `docker compose up api worker`).
5. Hosted Supabase: `DATABASE_URL` = transaction pooler (6543), `WORKER_DATABASE_URL` = session pooler (5432) or direct.
   `prepare_threshold=None` is always set, so the transaction pooler works.
6. Tests: any Postgres via `TEST_DATABASE_URL`; each run creates and drops its own database.

## Contract change requests
None. Two notes for P7:
- `error.stale_model.json` has `details.head_version`; the API sends it whenever HEAD is known (expected-version
  mismatch, lost race at lock time). A lost compare-and-swap or unique-violation race returns `stale_model` with empty
  `details`, because HEAD is not re-read there. Clients should refetch on any `stale_model`.
- History `edits` is newest first and capped at the 200 most recent (`HISTORY_EDIT_LIMIT`).

## Requests to other phases
- **P0/P7:** add a root `.dockerignore` (at least `**/.venv`, `**/node_modules`, `apps/web/.next`). Until then
  `services/api/Dockerfile.dockerignore` covers this image under BuildKit.
- **P7:** run the Supabase advisors (security + performance) via the Supabase MCP once it is authenticated; it was not
  authenticated in this session. Expected result is in "Known limitations".
- **P1 (vision):** the worker sends `file` with the stored content type and `floorplan_id`; it rejects a model whose
  `floorplan_id` differs. Artifacts are stored with extension `.png`/`.json` by content type.
- **P2 (geometry):** `brief`, `insights` and `execute` share one circuit breaker in the API; a run of 5 failures on any
  of them opens it for 30 s.
- **P4 (language):** `parse` and `classify` are not retried by the API (you already fail over between providers);
  `transcribe` is retried on 5xx/connection errors only, with a 90 s timeout.

## Known limitations
- **`supabase start` did not complete in this session.** Docker's CDN kept resetting the `supabase/postgres` image pull,
  so `supabase db reset` and the advisors were not run. The migration was applied and tested on plain Postgres 16 (the
  bucket insert is skipped there because `storage.buckets` does not exist). Expected advisor findings and why:
  - `rls_enabled_no_policy` (INFO) on all 7 tables: intended, CONTRACTS §9 (anon/authenticated get nothing; the API
    connects as `postgres`).
  - `unindexed_foreign_keys`: fixed, every FK has an index (a test asserts this).
  - `function_search_path_mutable`: fixed, `set_updated_at` pins `search_path = ''`.
  - `unused_index` may show on a fresh database; ignore until there is traffic.
- Rate limiting is **per process** (fixed window, in memory): N API processes allow N × the limit. Clients are keyed
  by user id, or by socket IP for bad tokens (no `X-Forwarded-For` trust, so behind a proxy all anonymous traffic shares
  one bucket).
- Starlette parses multipart bodies before the route runs, so the early cut-off is the ASGI body cap
  (`max(MAX_UPLOAD_BYTES, MAX_AUDIO_BYTES) + 1 MiB`, including chunked bodies). The exact per-file limit is then
  enforced while reading. The same cap bounds JSON bodies such as a structured `command`.
- The insights cache is per process and is cleared wholesale at 1024 entries.
- A worker that loses its job to stale recovery is fenced by `attempts` and drops its result, but artifacts it already
  uploaded under the same key may be overwritten by the winner (same key, upsert), which is harmless.
- `GET /projects/{id}` and list endpoints return `thumbnail_url`/`download_url` = `null` if Storage is down, rather than
  failing. `GET /artifacts` returns 502 in that case.
- Clerk `azp` is required; tokens without it (e.g. some machine tokens) are rejected.

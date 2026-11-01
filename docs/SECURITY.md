# Security: threat model summary

Scope: the local/free stack (Clerk, Supabase, OmniRoute, Docker). No AWS, GCP or Azure.

## Assets
Users' floor-plan files and derived models, the edit history, Clerk sessions, the Supabase service-role key, the OmniRoute key, and the internal service token.

## Trust boundaries

| Boundary | Control | Evidence |
|---|---|---|
| Browser → API | Clerk session JWT (RS256 via JWKS, `iss`, `azp` against `CLERK_AUTHORIZED_PARTIES`, `exp`/`nbf` with 30 s leeway). Every route is owner-scoped; another user's ids return **404**, never 403. | P3 tests: 17-route IDOR sweep. e2e `04-isolation`: a second user gets 404 on project, plan, model, history and edit, and sees no projects. |
| API → vision / geometry / language | `X-Internal-Token` (constant-time compare). These services publish **no host ports**; only `api` (8000) and `web` (3000) bind, on 127.0.0.1. | `docker compose config`; service stub tests (401 without the token). |
| API → Supabase | The API is the only DB client (service role, `postgres`). RLS is **on with no policies**, so the anon/authenticated keys read nothing. Buckets are private; browsers get 15-minute signed URLs. | Migration; P3 tests. |
| User text / audio → LLM | The LLM only proposes a command. Its output is schema-validated in language (`target_id` refused, ADD_WALL coordinates must appear in the text), then re-resolved and re-validated by geometry. Room labels (user-authored) go to the LLM as JSON data, under a system prompt stating they are data. | P4 tests; geometry Hypothesis fuzzing (random/garbage commands always return a valid union member). |
| Uploads | Extension + MIME + magic bytes, empty-file and size caps, pixel cap (decompression bombs), corrupt image/PDF, encrypted/absurd PDF, sanitised filenames, server-generated storage keys, SHA-256. Vision re-checks size, magic and pixels. ASGI body cap including chunked bodies. | P3 + P1 tests. |
| Web | CSP, `X-Frame-Options: DENY` + `frame-ancestors 'none'`, `nosniff`, `Referrer-Policy`, `Permissions-Policy` (microphone self only), HSTS in production. Candidate labels and room names render as text, never HTML. | `apps/web/next.config.ts`; `curl -I` check. |

## Other controls
- **Rate limits**: per user (or per IP for bad tokens), fixed window, `429` + `Retry-After`. Per process: N API replicas allow N × the limit.
- **Concurrency**: compare-and-swap versions; parallel edits → exactly one wins, the rest get `409 stale_model` (tested with 6). Two browser tabs: e2e `04-isolation` #11.
- **Secrets in logs**: JSON logs redact authorization headers; language never logs the API key or command text. A scan of all compose logs after the e2e run found no bearer tokens, JWTs, Clerk or Supabase secrets, or the internal token.
- **Production guards**: services refuse to start with the default internal token, `*` CORS, or missing Clerk config in production.
- **Dependencies** (2026-11-01): `pip-audit` clean for contracts, vision, geometry, language and api. `npm audit --omit=dev` in `apps/web`: 6 low/moderate, all transitive (`minimatch`, `deepmerge`), none high. CI fails on high.

## Known gaps and accepted risks
- CSP allows `'unsafe-inline'` scripts (nonces would force dynamic rendering; see the `shortcut:` in `next.config.ts`).
- The rate limiter is in memory and per process; behind a proxy, all anonymous traffic shares one bucket (no `X-Forwarded-For` trust).
- Language caps a chunked upload with no `Content-Length` only after spooling (internal-only service).
- Vision: no render timeout for hostile vector-heavy PDFs (page 1 only, pixel-capped).
- Supabase MCP advisors were **not run**: the Supabase MCP wasn't authenticated in the P7 session. Expected findings are listed in `services/api/HANDOFF.md` (only `rls_enabled_no_policy` INFO, by design).
- `/security-review` and the security skills were run as a manual review in P7 (findings above); no external penetration test.

# Feature status (2026-11-01, end of P7)

Labels: `NOT_STARTED / IN_PROGRESS / IMPLEMENTED / TESTED / VERIFIED`.
**VERIFIED means a human checked it on the real stack (CLAUDE.md).** Nothing here is VERIFIED yet: P7's checks were automated. "TESTED (e2e)" means the committed Playwright suite (`e2e/`) exercised it in Chromium against the real stack: compose services, local Supabase, Clerk dev instance, real Tesseract and Whisper, no mocks. The run was 10/10 green with zero CSP violations.

## Product flows

| Feature | Status | Evidence |
|---|---|---|
| Sign up (Clerk) → first-run dashboard → create project | TESTED (e2e) | `01-onboarding`; `qa/p7/01-*` |
| Upload PNG → 8-stage processing timeline → workspace | TESTED (e2e) | `01-onboarding`; `qa/p7/02-*` |
| Vision on the synthetic apartment (5 rooms typed, "3600" read, 10 mm/px) | TESTED (e2e) | Workspace shows the rooms and m² areas |
| Set scale from a wall → insights in m² | TESTED (e2e) | `02-editing` #3; `qa/p7/03-*` |
| mm command on an unscaled plan → "Set a scale first" path | TESTED (e2e) | `02-editing` #3; `qa/p7/06-needs-scale` |
| Typed edit → preview ghost → Apply → v+1 | TESTED (e2e) | `02-editing` #4; `qa/p7/04-*` |
| Ambiguous edit → clarification → pick → applied | TESTED (e2e) | `02-editing` #5; `qa/p7/05-*` |
| Nonsense → friendly UNKNOWN, nothing changes | TESTED (e2e) | `02-editing` #6 |
| Voice via API (spoken WAV → Whisper → same pipeline) | TESTED (e2e) | `03-versions` #7 |
| Voice in the browser (hold V, fake microphone) | TESTED (e2e) | `06-voice-ui`; `qa/p7/07-*` |
| Undo ×2 → Redo → new edit discards the branch (History) | TESTED (e2e) | `03-versions` #8; `qa/p7/08-*` |
| Re-process → undo returns to the edited model | TESTED (e2e) | `03-versions` #9 |
| Second user gets 404 (API and UI) | TESTED (e2e) | `04-isolation` #10; P3's 17-route IDOR sweep |
| Two tabs → the second apply gets the stale-model message | TESTED (e2e) | `04-isolation` #11 |
| Language down → refused at parse ("assistant is offline"), app healthy | TESTED (e2e) | `05-outages` 12a |
| Vision down → job FAILED cleanly → retry succeeds | TESTED (e2e) | `05-outages` 12b |
| Worker killed mid-job → stale recovery completes it (attempt 2) | TESTED (manual run on compose) | Stale timeout lowered to 20 s for the run; not in the committed suite |
| Parallel edits → exactly one wins | TESTED | P3 integration test (6 parallel → 1 APPLIED, 5 × 409) |
| LLM parsing through OmniRoute | TESTED (real gateway) | Combo `aec-parser` (Groq Qwen first, Gemini fallback). Live smoke test and a free-phrased command parsed through the compose network |
| Whisper model missing / OmniRoute unreachable paths | TESTED (unit, P4) | Not exercised on the real stack |
| Landing, projects list, project detail, settings, command palette | TESTED (unit, P5) + seen in e2e | |
| Sign-in with Clerk (ticket sign-in in e2e) | TESTED (e2e) | Password sign-in through the form not exercised |

## Non-functional

| Item | Status | Measured |
|---|---|---|
| Vision < 6 s on the apartment | TESTED | 2.4–2.6 s per job end to end (12 jobs, worker included); object detection is the slowest stage (1.4 s) |
| Geometry execute < 50 ms | TESTED | p50 10–13 ms, p95 ≤ 23 ms including the HTTP hop (30 calls each, RENAME_ROOM and MOVE_WALL) |
| Workspace 60 fps pan/zoom | TESTED (P6, in-page rAF) | 16.7 ms average frame on a 1,020-primitive plan; no DevTools trace |
| Landing Lighthouse ≥ 95 | PARTIAL | Accessibility 100, SEO 100, Best practices 77 (third-party cookies from Clerk's *development* instance). The Lighthouse performance category wasn't available; a DevTools trace gives LCP 213 ms, CLS 0.00 (unthrottled) |
| Security headers + CSP on web | TESTED (e2e) | Every e2e test fails on a CSP violation |
| Internal services unreachable from the host | TESTED | Only 127.0.0.1:8000 and :3000 published |
| Dependency audit | TESTED | pip-audit clean ×5; npm audit: 6 low/moderate transitive, none high |
| Supabase advisors | NOT_STARTED | Supabase MCP not authenticated in the P7 session |
| Zero AWS/GCP/Azure | TESTED | Stack ran on Docker + local Supabase + Clerk only |
| CI workflow | IMPLEMENTED | `.github/workflows/ci.yml` has not run on GitHub yet (nothing pushed) |

## Known limitations
See the "Known limitations" sections in each `HANDOFF.md`, and `docs/SECURITY.md` for accepted risks. Biggest product limits: vision supports solid/thick walls only (no hairline double-line walls, curves or noisy scans), PDF page 1 only, columns fused into wall junctions aren't detected, and the app header plus workspace top bar stack to 88 px on the workspace route.

## Testing progress (2026-11-07)

After P7 (commit `38b6b61`). Nothing is `VERIFIED` yet, because that label means a human checked it on the real stack.

### Unit and integration suites (all green on `main`)

| Suite | Result | Gates |
|---|---|---|
| `packages/contracts` | 154 passed | ruff, mypy, generated TS up to date |
| `services/vision` | 113 passed, 1 skipped | ruff, mypy |
| `services/geometry` | 200 passed | ruff, mypy |
| `services/language` | 276 passed, 1 skipped, 1 deselected (live OmniRoute) | ruff, mypy |
| `services/api` | 151 passed, 1 skipped (Supabase Storage, opt-in) | ruff, mypy; needs Postgres via `TEST_DATABASE_URL` |
| `apps/web` | 209 passed | tsc, eslint, `next build` |

### End to end (`e2e/`, Playwright, real stack)

10/10 passed in the final run (3.3 min), with zero Content-Security-Policy violations. No mocks: compose backend, local Supabase, Clerk dev instance, real Tesseract and Whisper.

| Flow | Spec |
|---|---|
| 1–2. Sign up, first-run dashboard, create project, upload, 8-stage timeline, open workspace | `01-onboarding` |
| 3, 6. Set scale then m²; mm on an unscaled plan; preview, apply, clarification, UNKNOWN | `02-editing` |
| 7. Voice through the API (spoken WAV, Whisper) | `03-versions` |
| 8–9. Undo ×2, redo, discarded branch; re-process then undo | `03-versions` |
| 10–11. Second user gets 404; two tabs give the stale-model message | `04-isolation` |
| 12. Language down (refused at parse) and vision down (job FAILED, retry works) | `05-outages` (needs `E2E_COMPOSE=1`) |
| 7b. Voice in the browser, fake microphone | `06-voice-ui` |

Run: `cd e2e; npm ci; npx playwright install chromium; npx playwright test`. Screenshots land in `apps/web/qa/p7/`.

### Measured performance

| Check | Result | Target |
|---|---|---|
| Vision, apartment plan | 2.4–2.6 s | under 6 s |
| Geometry execute | p95 23 ms or less | under 50 ms |
| Landing page | LCP 213 ms, CLS 0; accessibility 100, SEO 100, best practices 77 | Lighthouse 95 or more |
| Worker killed mid-job | recovered on attempt 2 (manual run) | |

### Not tested yet

- Supabase advisors (the Supabase MCP isn't authenticated).
- The LLM path through OmniRoute on the real stack (no key; rules cover 51/51 fixture commands).
- OmniRoute-down and whisper-model-missing paths on the real stack (unit-tested only).
- The Lighthouse performance score (LCP and CLS were measured instead).
- The worker-crash test is not in the committed suite.
- CI (`.github/workflows/ci.yml`) has never run on GitHub.
- Impeccable and hallmark design audits, the formal `/security-review`, and the `/token-optimizer` audit.

### Flaky or timing-sensitive

- `apps/web` workspace tests sit near vitest's 5 s default under load (OneDrive sync plus the running stack); that file now sets a 15 s timeout.
- `services/vision` tests take 50–80 s when the machine is busy.

## Building intelligence (2026-11-08)

Everything numeric is deterministic. Nothing here is `VERIFIED`. "TESTED (e2e)" means `e2e/tests/07-analysis.spec.ts` in Chromium on compose services with local Supabase.

| Feature | Status | Notes |
|---|---|---|
| Quantity takeoff and Bill of Quantities (walls, floor, doors, windows, paint, concrete, bricks, tiles, steel), CSV | TESTED (e2e) | Build-ups (wall height, slab, ratios) are stated assumptions |
| Compliance report (corridors, room sizes, accessibility, exits, doors, windows, fire), CSV | TESTED (e2e) | Based on published summaries of NBC India 2016; indicative, not certified |
| Cost estimate (construction, material, painting, flooring, tile count, electrical, plumbing), editable rates, CSV | TESTED (e2e) | Default rates are rough India averages in INR |
| Blueprint chatbot (rules on the model) | TESTED (e2e) | |
| Chatbot LLM fallback | TESTED (real gateway) | Answered from a facts sheet and returned UNKNOWN for a fact it wasn't given |
| Interior: furniture proposal, lighting, 5 themes | TESTED (e2e) | Furniture is drawn over the plan, not saved to the model |
| Layout suggestions (more space, another bedroom, parking), preview and apply | TESTED (e2e) | Goals are matched by rules; other phrasing gets a help message |
| Structural suggestions with previewable fixes | TESTED (e2e) | Advisory; no load or soil data |

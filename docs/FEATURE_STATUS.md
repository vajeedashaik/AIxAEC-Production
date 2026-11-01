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
| LLM parsing through OmniRoute | NOT_STARTED on the real stack | No OmniRoute key on this machine. Rules handle 51/51 fixture commands; the LLM path is tested against a fake gateway (P4) |
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

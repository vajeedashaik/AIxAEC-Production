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

## Plan reader accuracy (2026-11-09)

Three AI-generated plans of rising difficulty, compared with hand counts of what each image actually shows. These are clean test images, so they say nothing yet about scans or real drawings.

| Measure | Before fixes | After fixes |
|---|---|---|
| Rooms found (31 actual) | 17 | 27 |
| Bedrooms typed correctly (7 actual) | 4 | 7 |
| Plans with a working scale (3) | 2 | 3 |
| Doors, simple and medium plans (16 actual) | 12 | 16 |

Known limits: on the 16-room villa, doors are over-counted (24 detected, 18 actual), because bathroom fixtures can look like door swings, and the corridor still merges with two neighbouring rooms. Garage and sliding doors drawn with parallel lines count as windows.

## Edge-case testing in a real browser (2026-11-09)

About 150 checks driven through Playwright on the real stack (hosted Supabase, real OmniRoute, real Tesseract), plus the full e2e suite (11 passed, 2 skipped: the outage tests need `E2E_COMPOSE=1`). Nothing is `VERIFIED`: a person has not yet walked through it.

**Held up:** form validation, XSS-style names and questions (rendered as text, never run), a double-click on Create or Apply sending one request, undo and redo by button and keyboard (and Ctrl+Z inside a text box leaving the model alone), a stale tab refreshing itself, read-only history, all six Analyze views, CSV exports, preview, apply and discard for layout suggestions, prompt-injection attempts (no prompt or key leaked), corrupt, fake, empty, oversized and pixel-bomb uploads, and skewed, noisy and JPEG versions of a plan reading the same as the clean one.

**Found and fixed:**

| Problem | Fix |
|---|---|
| A 200-character name with no spaces overflowed the project page | The title now wraps |
| A long description pushed the Rename dialog's Save button off-screen, sideways and (at 2,000 characters) downwards | The form can't grow past the dialog, the textarea is height-capped, and the dialog scrolls |
| A rate of `1e308` returned a 502 after 14 s and was saved to local storage | Rates are capped (API 422 at once, and the form refuses them) |
| A 20,000×20,000-pixel image said "Upload a file of 25 MB or less" | The message now says the image has too many pixels |
| A 3-page PDF showed two near-identical warnings | One note |
| Room labels picked up OCR junk (`KITCHEN fl`, `OFFICE Sg`, `LAUNDRY OO`) | Short fragments are dropped |
| Light-on-dark (blueprint-style) drawings found no rooms | They are inverted first |
| The chat cost answer used Western digit grouping | Indian grouping, as in the Cost view |
| CSV files showed `mÂ²` and `â‰¥` in Excel | A UTF-8 byte-order mark is added |
| The read-only banner read "Viewing v1 , read-only" | Text no longer split by the flex gap |
| On a phone, the Ask and History tabs sat off-screen under the close button | The tab row reserves room and hides its scrollbar |
| An AI question could stall for 22 s when the free Groq tier rate-limited | OmniRoute now fails over after 3 s and the language service caps the AI at 10 s |

**Known limits, not fixed:**
- The hosted Supabase project is in Ireland (`eu-west-1`). From India every API call that touches the database costs 0.5 to 1.5 s, so actions take 2 to 4 s and the 11-test e2e run took 8 minutes. The code isn't slow. Use local Supabase while developing, and create the production project in `ap-south-1` (Mumbai).
- The free AI tiers still rate-limit under bursts: several simultaneous AI questions can take about 10 s and then answer "can't answer". Single questions take about 2 s.
- On the 16-room villa the reader still merges the corridor with two rooms and over-counts doors (24 found, 18 real).
- Not tested: voice recording (needs a real microphone), Firefox and Safari, a screen reader, and real scanned or photographed plans.
- Running the e2e suite against a hosted project leaves test data behind (the suite recreates its users each run). Run it against local Supabase instead.

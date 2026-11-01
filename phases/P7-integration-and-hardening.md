# P7: Integration, End-to-End & Hardening

> **Run alone, after P1–P6 have finished and committed.** You own the whole repo again. Work on `main` in the original folder, or in a fresh `phase/p7-integration` worktree.

## Read first
`CLAUDE.md` · `phases/shared/*` · `phases/STATUS.md` · **every** `HANDOFF*.md` (`services/*/HANDOFF.md`, `apps/web/HANDOFF.shell.md`, `apps/web/src/features/workspace/HANDOFF.md`).

## Mission
Turn six independently built parts into one working product. Merge, resolve contract gaps, run the real stack end to end, close security and UX gaps, and document honestly.

## 1. Merge
- `git merge --no-ff` each `phase/*` branch into `main` one at a time, running that part's tests after each merge. A conflict means an ownership violation: resolve it by the owner's version and note it.
- `grep -R "CONTRACT-GAP"` across the repo. Triage every contract change request from the HANDOFFs, decide (accept / reject / alternative), apply accepted ones in `packages/contracts`, regenerate the JSON Schema and TS types, remove the workarounds, and re-run every suite.
- Apply "requests to other phases" (e.g. P6 dependency or component requests to P5's area).

## 2. Run the real stack
- `supabase start` → `supabase db reset` (migrations) → start OmniRoute → `docker compose up --build` (or run each service with uv and `npm run dev`).
- Fill every `.env` from the `.env.example` files. Clerk dev keys, Supabase local keys and the OmniRoute key come from the human setup in TOOLING.md §4.
- Fix startup, CORS, auth (`azp` / authorized parties), timeouts between services, and Docker build contexts.

## 3. End-to-end verification with **playwright-cli** (real browser, real services)
Script and run these flows, saving screenshots to `apps/web/qa/p7/`:
1. Sign up → dashboard first-run → create project.
2. Upload `apartment.png` (generated from the fixtures) → watch the 8-stage timeline → open the workspace.
3. Select a wall → **Set scale** 3600 mm → insights switch to m².
4. Type "move the wall between the kitchen and the living room 300 mm left" → preview ghost → Apply → v+1.
5. Type "delete the door" → clarification → pick a candidate → applied.
6. Type nonsense → friendly UNKNOWN. Type a mm command on an unscaled plan → the "Set a scale first" path.
7. Voice: use a WAV fixture through the API (and the UI if the browser allows a fake mic: `--use-fake-device-for-media-stream`).
8. Undo ×2 → Redo → History shows discarded versions after a fresh edit.
9. Re-process the plan → undo returns to the edited model.
10. A second user cannot see the first user's project (404).
11. Two tabs editing → one gets the stale-model message.
12. Kill the language service → the edit is rejected at `parse` with a friendly message, and the app is otherwise healthy. Kill vision → the job FAILS cleanly and can be retried.

Turn these into a committed Playwright test suite (`e2e/` at the root, owned by you) that can run against the compose stack.

## 4. Hardening
- Security: run the `security-and-hardening` skill and `/security-review`. Check the IDOR sweep, upload fuzzing (bad magic, bombs, huge PDFs), JWT edge cases, internal token enforcement (internal ports not published), secrets never logged, CSP and security headers on web, `npm audit` / `pip-audit` per service.
- Supabase: run the MCP advisors (security and performance) on the final schema.
- Reliability: worker crash mid-job → stale recovery. Parallel edits → exactly one wins. Run the OmniRoute-down and whisper-model-missing paths.
- Performance: vision < 6 s on the apartment, geometry execute < 50 ms, workspace 60 fps pan/zoom, landing Lighthouse ≥ 95.
- UX: a final **impeccable audit + polish** pass and a **hallmark audit** across all screens for consistency between P5 and P6 (spacing, type, states, motion). Fix the seams.
- `/token-optimizer` audit of the Claude setup. Trim `CLAUDE.md` if it grew.

## 5. CI and docs
- `.github/workflows/ci.yml`: per-service jobs (uv sync, ruff, mypy, pytest), a contracts job (tests + "generated TS is up to date" check), a web job (lint, tsc, vitest, build, npm audit), a migrations job (Postgres service, apply the Supabase migrations), and optionally e2e on compose.
- `docs/`: `ARCHITECTURE.md` (final, including the decisions log), `RUNBOOK.md` (setup from zero, daily dev, troubleshooting), `FEATURE_STATUS.md` (honest labels; only items you verified in step 3 are `VERIFIED`), `DEMO_SCRIPT.md`, and `SECURITY.md` (threat model summary).
- Update `README.md` with the quick start, screenshots and the tech table.

## Done when
- [ ] All branches are merged, contract gaps resolved, and every suite green on `main`.
- [ ] The full stack runs locally with **zero AWS/GCP/Azure** dependencies, and the e2e suite passes.
- [ ] Docs and CI are complete. `phases/STATUS.md` has the final state.
- [ ] A commit on `main`. Push only if the user asks.

## Tooling
**playwright-cli**, **supabase plugin + MCP**, **impeccable**, **hallmark**, **context7**, agent-skills `ci-cd-and-automation`, `shipping-and-launch`, `security-and-hardening`, `documentation-and-adrs`, `code-review-and-quality`, **token-optimizer**, `/ponytail-audit` and `/ponytail-debt` for a final lean-code sweep.

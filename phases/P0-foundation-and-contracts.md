# P0: Foundation & Contracts

> **Run alone, first.** Every parallel phase (P1–P6) starts from what you commit. Your job is to make six independent sessions productive on day one without ever needing to touch each other's files.

## Read first
1. `CLAUDE.md`
2. `phases/shared/ARCHITECTURE.md`: the confirmed architecture
3. `phases/shared/CONTRACTS.md`: **you implement this verbatim**
4. `phases/shared/OWNERSHIP.md`: the map you are creating
5. `phases/shared/TOOLING.md`
6. `FULL_PROJECT_CONTEXT.md`: the product being rebuilt. Its cloud parts are intentionally dropped.

## Mission
Create the monorepo skeleton, the **contracts package** (Python + JSON Schema + TypeScript), shared **fixtures**, **runnable stubs** for every service and the web app, the **seed design system**, the **typed API client and mocks**, then commit and create the per-phase worktrees.

When you finish, any phase can run `pytest` / `npm test` in its folder and get green, and can boot its stub on its port.

## You own (for this phase)
The whole repo. After you merge, ownership passes to the phases per `OWNERSHIP.md`.

## Deliverables

### 1. Root
- `README.md`: product summary, architecture diagram (copy from ARCHITECTURE.md), quick start, links to `phases/`.
- Update `CLAUDE.md` only if something here changes a rule (keep it short).
- `.gitignore`: Python (`.venv`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`), Node (`node_modules`, `.next`, `out`), env files (`.env`, `.env.*` except `.env.example`), `supabase/.temp`, `apps/web/qa/**/*.png` (keep folder), OS files.
- `.gitattributes`: `* text=auto eol=lf` and binary for png/jpg/pdf. `.editorconfig`.
- `.env.example`: root values consumed by `compose.yaml`.
- `compose.yaml` using **`include:`** of `services/vision/compose.yaml`, `services/geometry/compose.yaml`, `services/language/compose.yaml`, `services/api/compose.yaml` and `apps/web/compose.yaml`, so each phase owns its own fragment. Use one shared network named `aec`. Only `api` (8000) and `web` (3000) publish ports to `127.0.0.1`.

### 2. `packages/contracts` (Python package `aec_contracts`, Python 3.12, managed by uv)
- Modules: `model.py`, `commands.py`, `results.py`, `vision.py`, `geometry.py` (Insights, PlanBrief, validate DTOs, ExecuteRequest/Result), `language.py`, `public.py`, `errors.py` (code enum + `ErrorEnvelope`), `lexicon.py`, `__init__.py` re-exports.
- Implement **exactly** the shapes in CONTRACTS.md §2–§8, including every validator: wall `start != end`, Targeted exactly-one, `CommandRequest` exactly-one, `FloorPlanModel` reference integrity and unique ids.
- `lexicon.py`: an ordered regex lexicon from text to `RoomType` (master bed before bed; bath/wc/toilet/ensuite; kitchen/kitchenette; living/lounge/family; dining; hall/corridor/passage/foyer/entry; closet/wardrobe/wic; garage; office/study/den; laundry/utility; balcony/terrace/deck; storage/store/pantry; stair; …). Expose `room_type_for_text(text) -> tuple[RoomType, float]` and `ROOM_SYNONYMS` (phrase → RoomType) for entity resolution.
- `scripts/export_schema.py` writes JSON Schema for every public and inter-service model into `packages/contracts/schema/`.
- `scripts/gen_ts.mjs` (or an npm script inside `apps/web`) converts the schemas with `json-schema-to-typescript` into **`apps/web/src/contracts/generated.ts`**, plus a hand-written `apps/web/src/contracts/index.ts` re-exporting friendly names.
- Tests (`packages/contracts/tests`): round-trip every fixture, every validator's positive and negative case, discriminated-union parsing of all 10 operations, `extra="forbid"` rejection, lexicon cases.

### 3. Fixtures (`packages/contracts/fixtures`), see CONTRACTS.md §11
- Hand-author `apartment.model.json` carefully. Rooms must be closed polygons whose edges lie on wall centre-lines, `wall_ids` must be correct, and openings must sit on their walls. It's the backbone of P2's and P6's tests, so make it geometrically honest.
- `synthetic_plan.py` must be deterministic (fixed seeds). P1 uses it heavily. Include solid walls of consistent thickness, gaps for doors with quarter-circle swings, double thin lines for windows, ≥4 parallel stair treads, room-label text, one dimension string (`"3600"` along a wall), and hatching.
- `commands.examples.json`: ≥40 cases (all 10 operations; mm/cm/m/px; left/right/up/down plus north/south/east/west; "between X and Y"; "at 30 %"; "900 wide"; ambiguous and nonsense inputs marked `expected: "UNKNOWN"`).
- `api/*.json`: one realistic example per public endpoint (CONTRACTS.md §8), validated against `aec_contracts.public` in tests.

### 4. Service stubs (one per service: `vision`, `geometry`, `language`, `api`)
For each `services/<name>/`:
- `pyproject.toml` (uv, Python 3.12) depending on `aec-contracts` via `[tool.uv.sources] aec-contracts = { path = "../../packages/contracts", editable = true }`, plus fastapi, uvicorn, pydantic-settings, httpx and the dev deps (pytest, ruff, mypy). Each service gets its own `uv.lock`.
- `app/main.py`: app factory, `/healthz`, `/readyz`, error envelope handlers, request-ID middleware, JSON logging. For vision/geometry/language, add an `X-Internal-Token` dependency on a `/v1` router. Every `/v1` route returns `501 {"error":{"code":"internal_error","message":"not implemented"}}` for now, **with the exact request/response models wired** so OpenAPI already shows the contract.
- `app/config.py` (pydantic-settings, env vars from CONTRACTS.md §10).
- `tests/test_health.py` and `tests/test_contract_wiring.py` (routes exist, auth enforced).
- `Dockerfile`: python:3.12-slim, non-root, healthcheck, build context = repo root so it can `COPY packages/contracts`. Vision installs `tesseract-ocr`. Language leaves a note for ffmpeg if faster-whisper needs it.
- `compose.yaml` fragment (service, env_file, network `aec`, healthcheck).
- `.env.example`, `README.md` (how to run and test) and an empty `HANDOFF.md` with the standard sections.
- **api only:** run `supabase init` inside `services/api` so `services/api/supabase/` exists (P3 writes the migrations).

### 5. Web app (`apps/web`)
- `npx create-next-app@latest` → Next.js 16, App Router, TypeScript, Tailwind CSS 4, ESLint, `src/` dir, import alias `@/*`. **Verify current flags with context7.**
- Install **now** (so P6 never needs to add deps): `@clerk/nextjs`, `@tanstack/react-query`, `msw`, `zod`, `clsx`, `tailwind-merge`, `class-variance-authority`, `lucide-react`, `motion`, `sonner`, `cmdk`, `next-themes`, `@fontsource-variable/*` or `geist` as chosen in DESIGN.md. Dev: `vitest`, `@vitejs/plugin-react`, `jsdom`, `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom`, `json-schema-to-typescript`.
- `npx shadcn@latest init`, then add a generous base set: button, input, textarea, label, card, dialog, alert-dialog, dropdown-menu, popover, tooltip, tabs, badge, separator, skeleton, scroll-area, sheet, command, toggle, toggle-group, slider, switch, select, progress, table, avatar, sonner, breadcrumb, resizable, kbd (if available).
- Clerk: `ClerkProvider` in the root layout and **`src/proxy.ts`** (Next 16 renamed middleware → proxy; confirm with context7) protecting `/(app)` routes. Keyless mode must work in dev.
- `src/lib/api/`: a typed fetch client covering **every** endpoint in CONTRACTS.md §8. It takes a `getToken` function, parses the error envelope into `ApiError {status, code, message, details}`, retries once on 401 after a token refresh, honours `Retry-After` on 429, uses an XHR upload with progress, and has a `postAudio`. Add TanStack Query `queryKeys` and a `QueryProvider`.
- `src/mocks/`: MSW handlers for every endpoint, serving the fixtures, enabled when `NEXT_PUBLIC_API_MOCKING=on`. Mutations must behave plausibly: commands return `PREVIEW`/`APPLIED` with the next version, undo and redo work in memory, and processing advances through stages over ~6 s.
- Route skeleton with placeholder pages (P5 replaces them, P6 replaces the workspace):
  - `src/app/(marketing)/page.tsx` (landing), `src/app/(auth)/sign-in/[[...sign-in]]/page.tsx`, `sign-up/[[...sign-up]]/page.tsx`
  - `src/app/(app)/layout.tsx` (app shell), `dashboard/page.tsx`, `projects/page.tsx`, `projects/[projectId]/page.tsx`, `settings/page.tsx`
  - `src/app/(app)/projects/[projectId]/floorplans/[floorplanId]/page.tsx` (**P6's** route, render a placeholder)
  - `src/app/(dev)/playground/page.tsx` (P6, dev-only and unauthenticated: `notFound()` in production)
- Empty owned folders with `.gitkeep`: `src/features/{viewer,workspace,projects,dashboard,upload,marketing,settings}`, `qa/p5`, `qa/p6`.
- `vitest.config.ts`, `src/test/setup.ts`, one smoke test for the API client against MSW.
- `apps/web/compose.yaml` (Node 22 multi-stage, non-root) and `apps/web/.env.example`.
- Create `apps/web/HANDOFF.shell.md` and `apps/web/src/features/workspace/HANDOFF.md` with the standard sections.

### 6. Seed design system: `apps/web/DESIGN.md` + tokens
Use the UI tooling (TOOLING.md §3):
1. Run **`/impeccable init`** (and `/impeccable document` if useful) to capture product context: a precision tool for architects and engineers, used for long sessions, dense information, and a canvas-centric workspace.
2. Study `docs/design/references/{linear,figma,miro,vercel,raycast}.DESIGN.md`. Optionally run `skillui --url https://linear.app --out docs/design/extracted/linear` for token ideas (principles only, never brand copying).
3. Use **ui-ux-pro-max `design-system`** to define a three-layer token architecture (primitive → semantic → component).
4. Write `apps/web/DESIGN.md` covering: product personality ("precision instrument": calm, exact, confident), type scale (sans for UI plus **mono for dimensions, coordinates and versions**), colour (neutral chrome, **one** accent, semantic success/warning/danger/info, plus a dedicated **canvas palette**: paper, grid, wall, room fills by type, door, window, selection, hover, preview-add / preview-modify / preview-remove), spacing, radius, elevation, motion (durations and easing, reduced-motion), density, iconography (lucide, 1.5 stroke), light and dark themes.
5. Implement the tokens as CSS variables in `src/app/globals.css` (Tailwind 4 `@theme`). **Freeze the token names**: P5 may tune values, P6 consumes names. The canvas tokens must be named `--canvas-*` (e.g. `--canvas-paper`, `--canvas-grid`, `--canvas-wall`, `--canvas-room-kitchen`, `--canvas-selection`, `--canvas-preview-add`).
6. Explicitly ban the old look (aurora backgrounds, glass, gradient accents).

### 7. Verify, commit, fan out
- `cd packages/contracts && uv run pytest`. Then for each service: `uv sync && uv run pytest && uv run ruff check . && uv run mypy app`.
- `cd apps/web && npm run lint && npx tsc --noEmit && npm test && npm run build`.
- Boot every stub (`uv run uvicorn app.main:app --port <port>`, `npm run dev`) and hit `/healthz`.
- If Docker Desktop is running: `docker compose config` must be valid.
- Commit on `main` (conventional message; stage explicit paths, not `-A`, but this phase owns everything, so staging the whole tree is OK after reviewing `git status`).
- Create the six worktrees and branches exactly as in OWNERSHIP.md §4. Each worktree contains `.claude/` (plugins and skills), so sessions there have the full toolset.
- Write `phases/STATUS.md`: what you built, the honest status of each deliverable, and the exact command to start each phase session.

## Acceptance criteria
- [ ] Contracts match CONTRACTS.md field by field, with all tests green.
- [ ] TS types are generated and the web compiles against them.
- [ ] Every service stub boots, `/healthz` is 200, `/v1/*` without the token is 401 and with it is 501.
- [ ] Web boots in mock mode, all routes render placeholders, the Clerk sign-in renders (keyless) and the API client test passes.
- [ ] `DESIGN.md` exists, the tokens are in `globals.css` and the canvas tokens are named.
- [ ] Fixtures are valid, and the synthetic PNG generator is deterministic (identical hash on two runs).
- [ ] `main` is committed, six worktrees exist, and `phases/STATUS.md` is written.

## Tooling for this phase
`planning-and-task-breakdown` → `spec-driven-development` → **context7** (Next 16, Clerk, Tailwind 4, shadcn, Pydantic v2, uv) → **impeccable init**, **ui-ux-pro-max design-system**, **skillui** → `/ponytail-review` → `/token-optimizer` (audit the repo's Claude setup once, and keep `CLAUDE.md` lean).

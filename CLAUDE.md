# AEC AI Platform: rules for every Claude session

Upload a floor plan → computer vision builds a typed, versioned Building Model → edit it by text, voice or click → a deterministic geometry engine applies every change → new immutable version with undo/redo.

## Read before working
1. `phases/README.md`, then your phase prompt `phases/P<n>-*.md`
2. `phases/shared/ARCHITECTURE.md` · `CONTRACTS.md` · `OWNERSHIP.md` · `TOOLING.md`
3. `FULL_PROJECT_CONTEXT.md` is the reference spec of the original product. Its AWS/GCP/Azure parts are **dropped**.

## Hard rules
- **Write only inside the paths your phase owns** (OWNERSHIP.md). Anything else goes into your HANDOFF file as a request.
- **Contracts (`packages/contracts`, `apps/web/src/contracts`) are frozen** for P1–P6. Log gaps per CONTRACTS.md §12.
- **No AWS, GCP or Azure.** Stack: Clerk (auth), Supabase (Postgres + Storage), OmniRoute (free LLMs), Tesseract, faster-whisper, local Docker.
- The LLM never edits geometry. Its output is untrusted. Don't guess on ambiguity, return a clarification. Never treat px as mm.
- Never `git add -A` / `git commit -a`. Stage your own paths. Never run repo-wide formatters. Don't push unless asked.
- Don't install project-level skills or plugins (`.claude/**` is P0/P7-owned). Use `-g` for anything extra.
- Honest status labels: `NOT_STARTED / IN_PROGRESS / IMPLEMENTED / TESTED / VERIFIED` (VERIFIED = human-checked on the real stack).

## Tools (details in TOOLING.md)
- Start with `/ponytail lite`, the `planning-and-task-breakdown` skill and `spec-driven-development`.
- Look up **every** library API with **context7**. Don't rely on memory (Next.js 16, Clerk and Tailwind 4 changed recently). Installed docs also live in `apps/web/node_modules/next/dist/docs`. Known traps: Next 16 `cacheComponents` needs runtime hooks under `<Suspense>`; Clerk Core 3 replaced `<SignedIn>` with `<Show>` and no longer auto-creates keyless keys; msw v3 renamed `onUnhandledRequest` → `onUnhandledFrame`.
- Before handoff: `/ponytail-review`, plus the `code-review-and-quality` and `security-and-hardening` skills.
- UI work: `DESIGN.md` is law → impeccable (shape → critique → audit → polish) → hallmark for new pages → design-taste-frontend look-and-fix → ui-ux-pro-max design-system / shadcn MCP → playwright-cli screenshots.
- Database work: the supabase plugin skills + Supabase MCP (advisors).

## Commands
- Python service: `cd services/<name>; uv sync; uv run pytest; uv run ruff check .; uv run mypy app` (use `py -m uv` if `uv` isn't on PATH)
- Web: `cd apps/web; npm run dev; npm test; npx tsc --noEmit; npm run lint; npm run build`
- Local Supabase: `cd services/api; supabase start; supabase db reset`
- Windows shell: PowerShell 5.1 (no `&&`). Python launcher is `py`.
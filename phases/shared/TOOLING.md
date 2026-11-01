# Tooling: what is installed and when each session uses it

Everything below is installed **at project scope**: plugins are enabled in `.claude/settings.json`, skills live in `.claude/skills/`, and both are committed. Every Claude session opened in this repo or any of its worktrees gets them automatically. On first launch in a new worktree, accept the prompt to trust or install the project's plugins.

## 1. Inventory

| Tool | Kind | Provides | Primary users |
|---|---|---|---|
| **agent-skills** (addyosmani) | plugin | engineering-discipline skills: `spec-driven-development`, `test-driven-development`, `incremental-implementation`, `api-and-interface-design`, `security-and-hardening`, `code-review-and-quality`, `debugging-and-error-recovery`, `performance-optimization`, `frontend-ui-engineering`, `browser-testing-with-devtools`, `documentation-and-adrs`, `git-workflow-and-versioning`, `observability-and-instrumentation`, `context-engineering`, `planning-and-task-breakdown` | all |
| **ponytail** | plugin | "write less code" ruleset. Skills `ponytail` (`lite\|full\|ultra\|off`), `ponytail-review`, `ponytail-audit`, `ponytail-debt` | all |
| **token-optimizer** (alexgreensh) | plugin | `token-optimizer`, `token-coach`, `token-dashboard`, `resume-checkpoint`, `fleet-auditor` | all (long sessions), P0/P7 audit |
| **find-skills** (vercel-labs) | project skill | discover skills via `npx skills find <query>` | all (install results **user-level only**) |
| **supabase** (official) | plugin | skills `supabase`, `supabase-postgres-best-practices` + **Supabase MCP** (`https://mcp.supabase.com/mcp`) | P3, P7 |
| **context7** (official) | plugin | **Context7 MCP**: up-to-date library docs (`resolve-library-id`, `query-docs`) | all |
| **impeccable** (pbakaus) | plugin | design workflow: `/impeccable init\|document\|extract\|shape\|critique\|audit\|layout\|typeset\|colorize\|animate\|delight\|quieter\|bolder\|clarify\|distill\|adapt\|harden\|onboard\|optimize\|polish\|live` | P0, P5, P6 |
| **hallmark** (nutlope) | plugin | anti-slop builder for **new** pages: `/hallmark <prompt>`, `/hallmark audit <path>`, `/hallmark redesign <path>` | P5 (landing, auth, empty states), P6 |
| **ui-ux-pro-max** | plugin | skills `ui-ux-pro-max`, `design-system`, `ui-styling`, `design`, `brand` + MCPs **shadcn**, **playwright**, **chrome-devtools** | P0, P5, P6 |
| **taste-skill** (`design-taste-frontend`) | project skill | art direction and a no-slop house style, with a screenshot look-and-fix loop for landing pages *and* app screens | P5, P6 |
| **playwright-cli** | global CLI + project skill | token-efficient browser automation: screenshots, flows, visual QA | P5, P6, P7 |
| **skillui** | global CLI | extract a site's design system into `DESIGN.md` and tokens (`skillui --url <site>`) | P0 (once), P5 |
| **awesome-design-md** | reference files | curated DESIGN.md references in `docs/design/references/` (linear, figma, miro, vercel, raycast, notion, stripe, supabase) | P0, P5, P6 |
| **OmniRoute** | global CLI / Docker service | free-tier LLM gateway, OpenAI-compatible on `:20128` | P4 (runtime), P7 |
| **uv** | Python tool | per-service venvs and locks (`py -m uv …` if `uv` isn't on PATH) | P0–P4, P7 |
| **Supabase CLI** | CLI | `supabase start` (local stack), `supabase migration new`, `supabase db reset` | P3, P7 |

## 2. Working protocol (all phases)

1. **Start of session:** read `CLAUDE.md`, then `phases/shared/*`, then your phase prompt. Run `/ponytail lite` (production code, so *lite*: lean but not reckless).
2. **Plan:** use the agent-skills `planning-and-task-breakdown` and `spec-driven-development` skills to turn the prompt into a task list before writing code.
3. **Library facts:** **never trust memory for library APIs.** Query **context7** for FastAPI, Pydantic v2, SQLAlchemy 2, OpenCV, Shapely 2, PyMuPDF, faster-whisper, the OpenAI SDK, Next.js 16, React 19, Tailwind 4, shadcn/ui, Clerk and TanStack Query. Next.js 16 and Clerk in particular changed recently (e.g. `proxy.ts`).
4. **Build:** `test-driven-development` + `incremental-implementation`. Commit at every green step.
5. **Before handoff:** run `/ponytail-review` on your diff, then the `code-review-and-quality` and `security-and-hardening` skills, and fix what they find.
6. **Long sessions:** run `/token-optimizer` if context feels heavy. Use `resume-checkpoint` before a deliberate `/compact`.

## 3. UI protocol (P5, P6, and P7 for polish)

The design tools overlap, so they have a fixed order of authority:

1. **`apps/web/DESIGN.md` is law.** P0 seeds it and P5 refines it. Token *names* are frozen after P0, values can be tuned by P5.
2. **impeccable** is the primary workflow for app screens: `shape` before building a screen, `critique` / `audit` after, `polish` last. Use `typeset`, `colorize`, `layout` and `animate` for targeted passes.
3. **hallmark** is for **new** page-level compositions: the landing page, auth pages, empty and first-run states. Run `/hallmark audit <path>` on every finished page.
4. **taste-skill (`design-taste-frontend`)** gives art direction for the landing page and runs the screenshot look-and-fix loop on app screens.
5. **ui-ux-pro-max** handles token architecture (`design-system`), component specs (`ui-styling`) and the **shadcn MCP** for finding and adding components (P5 only adds).
6. **References:** `docs/design/references/*.DESIGN.md`. Linear for app chrome and density, Figma/Miro for the canvas, Vercel/Raycast for type and contrast. Borrow principles, never copy brand identity.
7. **Visual QA:** `playwright-cli` screenshots at **1440×900, 1024×768, 390×844** in **light and dark**, saved under your owned folder (`apps/web/qa/<phase>/`). Review them like a design lead and iterate.

**Quality bar:** no generic "AI look" (no purple-blue gradients, no glassmorphism, no emoji icons, no centred-everything hero). Every data view has loading (skeleton), empty, error and success states. Keyboard reachable, visible focus, WCAG AA contrast, `prefers-reduced-motion` respected, and no layout shift.

## 4. Human setup (one time, done by the project owner)

| Task | Where |
|---|---|
| Create a **Clerk** application (free) and copy the publishable and secret keys | dashboard.clerk.com |
| Create a **Supabase** project (free) *or* use `supabase start` locally (requires Docker Desktop running) | supabase.com |
| Authenticate the Supabase MCP and Context7 once: in Claude Code run `/mcp` and complete the OAuth | Claude Code |
| Start OmniRoute (`omniroute`), open its dashboard, add free provider keys (e.g. Groq, Google AI Studio, OpenRouter, Cerebras), create an API key and a fallback **combo** | `http://localhost:20128` |
| Start **Docker Desktop** before P0 and P7 | Windows |
| Configure ponytail's 4 options if prompted: `/plugin configure ponytail@ponytail` | Claude Code |

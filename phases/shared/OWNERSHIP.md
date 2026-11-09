# Ownership, isolation and git workflow

The goal: **six Claude sessions build at the same time and never write the same file.** Every path in the repo has exactly one owner per stage.

## 1. Execution order

```
P0 Foundation & Contracts   (alone, first, about 1 session)
        │  merged to main, worktrees created
        ▼
┌──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
│ P1       │ P2       │ P3       │ P4       │ P5       │ P6       │   ← all in parallel,
│ vision   │ geometry │ core api │ language │ web shell│ workspace│     one session each,
└──────────┴──────────┴──────────┴──────────┴──────────┴──────────┘     one worktree each
        │  each merges its branch to main (conflict-free by construction)
        ▼
P7 Integration, E2E & Hardening   (alone, last)
```

## 2. Ownership map

| Path | Owner | Others |
|---|---|---|
| `CLAUDE.md`, `README.md`, `.gitignore`, `.gitattributes`, `.editorconfig`, `compose.yaml`, `.env.example` (root), `.claude/**`, `skills-lock.json`, `e2e/**`, `phases/**`, `docs/design/references/**` | **P0**, then **P7** | read-only |
| `packages/contracts/**` (Python, schema, fixtures) | **P0**, then **P7** | read-only |
| `apps/web/src/contracts/**` (generated TS) | **P0**, then **P7** | read-only |
| `apps/web/src/lib/api/**` (typed client, query keys) | **P0**, then **P7** | read-only |
| `apps/web/src/mocks/**` (MSW handlers on fixtures) | **P0**, then **P7** | read-only |
| `services/vision/**` | **P1** | read-only |
| `services/geometry/**` | **P2** | read-only |
| `services/api/**` (including `services/api/supabase/**`) | **P3** | read-only |
| `services/language/**` | **P4** | read-only |
| `apps/web/src/features/viewer/**` | **P6** | read-only |
| `apps/web/src/features/workspace/**` | **P6** | read-only |
| `apps/web/src/app/(app)/projects/[projectId]/floorplans/[floorplanId]/**` | **P6** | read-only |
| `apps/web/src/app/(dev)/**` (component playgrounds) | **P6** | read-only |
| **everything else under `apps/web/**`**: `package.json`, `package-lock.json`, `next.config.ts`, `src/app/**` (other routes and layouts), `src/components/**` (including `components/ui`), `src/features/{projects,dashboard,upload,marketing,settings}/**`, `src/styles/**`, `src/app/globals.css`, `DESIGN.md` | **P5** | read-only |
| `docs/**` (except `docs/design/references`) | **P7** | phases write only their own `HANDOFF.md` |
| `infra/**`, `phases/aws/**`, `services/api/app/aws/**`, `services/api/app/ports.py`, `services/vision/app/lambda_handler.py`, `services/vision/app/ocr/textract.py`, `services/vision/Dockerfile.lambda`, `services/language/app/speech_transcribe.py`, `services/language/app/llm_bedrock.py`, the `NEXT_PUBLIC_ARTIFACT_ORIGIN` line in `apps/web/next.config.ts`, and the small wiring edits listed in `docs/AWS_MIGRATION_PLAN.md` | **P8** (AWS profile, runs after P7, alone) | read-only |

### Each phase's handoff file (the only "shared-style" file each phase writes)

| Phase | Handoff file |
|---|---|
| P1 | `services/vision/HANDOFF.md` |
| P2 | `services/geometry/HANDOFF.md` |
| P3 | `services/api/HANDOFF.md` |
| P4 | `services/language/HANDOFF.md` |
| P5 | `apps/web/HANDOFF.shell.md` |
| P6 | `apps/web/src/features/workspace/HANDOFF.md` |

Sections in every handoff: `## Status` (per feature, honest labels), `## How to run`, `## Contract change requests`, `## Requests to other phases`, `## Known limitations`.

## 3. Rules every parallel session obeys

1. **Write only inside your owned paths.** Reading anything is fine. If a change is needed elsewhere, put it in your HANDOFF under "Requests to other phases".
2. **Dependencies:**
   - Python services: each has its own `pyproject.toml` + `uv.lock` + `.venv`. Add deps freely **inside your service**.
   - Web: **only P5** may change `apps/web/package.json` / `package-lock.json`. P0 pre-installs everything P6 should need. If P6 truly needs a package, it writes a request in its HANDOFF and implements without it.
3. **Skills and plugins:** do **not** install project-level skills or plugins (`.claude/**` is P0/P7-owned). If `find-skills` finds something useful, install it **user-level** (`npx skills add <pkg> -g --agent claude-code`) and note it in your HANDOFF.
4. **shadcn components:** only P5 runs `npx shadcn add` (it writes `src/components/ui`). P6 composes existing primitives, and any extra primitive it needs lives in `src/features/workspace/ui/`.
5. **Ports:** use only your assigned dev ports (ARCHITECTURE.md §7).
6. **Contracts are frozen.** See CONTRACTS.md §12.
7. **Never run repo-wide formatters or codemods** (`prettier --write .`, `ruff format .` at the root, `git add -A`, `git commit -a`). Scope every tool to your paths.

## 4. Git workflow (worktrees)

P0 finishes by committing to `main` and creating one worktree and branch per parallel phase, **outside OneDrive** to avoid sync locks on `node_modules` and `.venv`:

```powershell
$root = "C:\dev\aec"                                   # change if you like
git worktree add "$root\p1-vision"    -b phase/p1-vision
git worktree add "$root\p2-geometry"  -b phase/p2-geometry
git worktree add "$root\p3-api"       -b phase/p3-api
git worktree add "$root\p4-language"  -b phase/p4-language
git worktree add "$root\p5-web-shell" -b phase/p5-web-shell
git worktree add "$root\p6-workspace" -b phase/p6-workspace
```

Each session:
- starts Claude **inside its worktree** (`cd C:\dev\aec\p1-vision; claude`)
- commits early and often, staging **only owned paths** (`git add services/vision`)
- never rebases or merges other phase branches. P7 does all merging.
- finishes with all tests green, the HANDOFF updated and a final commit. It does **not** push or merge unless the user says so.

Because ownership is disjoint, `git merge phase/p1-vision phase/p2-geometry …` into `main` is conflict-free. If P7 ever sees a conflict, a phase broke rule 1.

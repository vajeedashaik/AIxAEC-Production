# Build plan: AEC AI Platform (parallel phases)

Eight prompts, designed for **independent Claude Code sessions** that never edit the same file.

```
P0  Foundation & Contracts ─────────────── alone, first
        │
        ├── P1  Vision service         ┐
        ├── P2  Geometry service       │
        ├── P3  Core API & worker      │  all six in parallel,
        ├── P4  Language & voice       │  one session + one worktree each
        ├── P5  Web shell & design     │
        └── P6  Floor-plan workspace   ┘
        │
P7  Integration, E2E & hardening ───────── alone, last
```

| Prompt | Builds | Writes only in |
|---|---|---|
| [P0](P0-foundation-and-contracts.md) | monorepo, contracts (Py + JSON Schema + TS), fixtures, runnable stubs, typed API client + MSW mocks, seed DESIGN.md, worktrees | everything (first) |
| [P1](P1-vision-service.md) | image/PDF → Building Model (OpenCV, Tesseract, PyMuPDF) | `services/vision` |
| [P2](P2-geometry-service.md) | entity resolution, 10 operations, constraints, insights (Shapely) | `services/geometry` |
| [P3](P3-core-api.md) | Clerk auth, Supabase DB + Storage, Postgres job queue, versions, undo/redo, edit orchestration | `services/api` |
| [P4](P4-language-service.md) | rules + OmniRoute LLM command parser, room classification, faster-whisper STT | `services/language` |
| [P5](P5-web-app-shell.md) | landing, auth, app shell, dashboard, projects, upload, settings, design system | `apps/web` (minus P6 / frozen paths) |
| [P6](P6-floorplan-workspace.md) | renderer, canvas viewer, AI command bar with preview ghost, voice, history, insights | `apps/web/src/features/{viewer,workspace}` + workspace route |
| [P7](P7-integration-and-hardening.md) | merge, real-stack E2E, security, CI, docs | everything (last) |

**Shared, read by every session:** [ARCHITECTURE](shared/ARCHITECTURE.md) · [CONTRACTS](shared/CONTRACTS.md) · [OWNERSHIP](shared/OWNERSHIP.md) · [TOOLING](shared/TOOLING.md)

**After P7:** the optional AWS profile (P8) has its own prompts in [aws/](aws/README.md).

## How to run the sessions

1. Do the **human setup** in [TOOLING.md §4](shared/TOOLING.md) (Clerk app, Supabase or Docker, OmniRoute keys, `/mcp` auth).
2. **P0**, from this folder:
   ```powershell
   claude "Read phases/P0-foundation-and-contracts.md and execute it completely."
   ```
3. After P0 commits and creates the worktrees, open **six terminals**, one per phase:
   ```powershell
   cd C:\dev\aec\p1-vision;    claude "Read phases/P1-vision-service.md and execute it completely."
   cd C:\dev\aec\p2-geometry;  claude "Read phases/P2-geometry-service.md and execute it completely."
   cd C:\dev\aec\p3-api;       claude "Read phases/P3-core-api.md and execute it completely."
   cd C:\dev\aec\p4-language;  claude "Read phases/P4-language-service.md and execute it completely."
   cd C:\dev\aec\p5-web-shell; claude "Read phases/P5-web-app-shell.md and execute it completely."
   cd C:\dev\aec\p6-workspace; claude "Read phases/P6-floorplan-workspace.md and execute it completely."
   ```
   On first launch in each worktree, accept the prompt to trust the project's plugins.
4. When all six report done (their HANDOFF files are complete), run **P7** from the main folder:
   ```powershell
   claude "Read phases/P7-integration-and-hardening.md and execute it completely."
   ```

## Why it doesn't collide
- **Contract-first**: every cross-boundary shape is frozen in `packages/contracts` before the parallel phases start.
- **Disjoint ownership**: each path has exactly one writer ([OWNERSHIP.md](shared/OWNERSHIP.md)).
- **Separate worktrees and branches**: separate `node_modules`, `.venv` and dev ports, so merges are conflict-free by construction.
- **No shared lockfiles**: each Python service has its own `uv.lock`, and only P5 edits the web `package.json`.
- **Gaps are logged, not patched**: each phase records contract change requests in its own HANDOFF, and P7 applies them.

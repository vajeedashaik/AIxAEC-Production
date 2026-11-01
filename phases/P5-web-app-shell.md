# P5: Web App Shell, Design System & Product Screens

> Parallel phase. Worktree `phase/p5-web-shell`. **Write only inside `apps/web/**` *excluding* P6's paths and the P0-frozen paths** (see OWNERSHIP.md: `src/features/{viewer,workspace}`, the floorplan workspace route, `src/app/(dev)`, `src/contracts`, `src/lib/api`, `src/mocks`). Dev server on **:3000**.

## Read first
`CLAUDE.md` · `phases/shared/*` (especially TOOLING.md §3, the UI protocol) · `apps/web/DESIGN.md` (P0 seed) · `docs/design/references/*.DESIGN.md` · `FULL_PROJECT_CONTEXT.md` §17 (the old frontend: keep the behaviours, **replace the look**).

## Mission
Own the product's **look, feel and every screen except the floor-plan workspace**. You make it feel like a premium, precise, trustworthy professional tool, not a template. You also own the design system that P6 consumes.

Develop against **MSW mocks** (`NEXT_PUBLIC_API_MOCKING=on`) so you never wait for the backend. Everything must also work against the real API (same client).

## Design process (follow TOOLING.md §3 in order)
1. **Direction**: run `design-taste-frontend` (taste-skill) for art direction and `/impeccable shape` for each screen *before* coding it. Write the decisions into `DESIGN.md` (append a "Decisions log").
2. **System**: refine token **values** in `globals.css` (names are frozen) with ui-ux-pro-max `design-system`. Build typography, colour (light and dark), elevation, focus rings and motion primitives. Use the **shadcn MCP** to find and add components (you are the only phase that adds to `src/components/ui`). Theme every primitive to the tokens, so nothing looks like stock shadcn.
3. **Build** screens (below). For brand-new page compositions (landing, auth, first-run, empty states) use **`/hallmark`**.
4. **Review loop** for every screen: `playwright-cli` screenshots at 1440×900, 1024×768 and 390×844 in light and dark → `qa/p5/<screen>-<viewport>-<theme>.png` → `/impeccable critique` → fix → `/impeccable audit` → `/hallmark audit <path>` → `/impeccable polish`. Iterate until a design lead would ship it.

## Screens and features
1. **Landing** `(marketing)/page.tsx`: hero with a real product moment (an animated SVG floor plan being "understood": walls draw in, rooms tint by type, and a command like "move the kitchen wall 300 mm left" applies with a preview ghost. Build it as a lightweight self-contained SVG/motion component in `src/features/marketing/`, not a video), a 3-step "upload → understand → edit by voice/text" story, a feature grid (detection, natural-language and voice editing, undo history, insights), a trust/precision section ("the AI never moves a wall; the geometry engine does"), a CTA and a footer. Lighthouse ≥ 95 performance and accessibility. Use `design-taste-frontend` for the art direction.
2. **Auth** `(auth)/sign-in`, `sign-up`: Clerk `<SignIn/>` / `<SignUp/>` themed via Clerk `appearance` to match the tokens (fonts, colours, radius, dark mode) in a split layout with brand panel. Post-auth redirect to `/dashboard`.
3. **App shell** `(app)/layout.tsx`: a collapsible left sidebar (Dashboard, Projects, Settings; recent projects), a top bar with breadcrumbs, a **⌘K command palette** (cmdk: jump to a project or floor plan, create a project, toggle the theme), Clerk `<UserButton/>`, a theme toggle (next-themes) and a toast host (sonner). It must look excellent at 1024 px. On mobile the sidebar becomes a sheet.
4. **Dashboard** `/dashboard`: greeting, stat tiles (projects, floor plans, edits this week; derive from the existing endpoints, and if a number isn't available, skip it rather than fake it), recent floor plans with thumbnails and status badges, a "new project" CTA, and a first-run onboarding empty state.
5. **Projects** `/projects`: grid and list toggle, search and sort (client-side), create dialog (validated with zod), rename, delete with a confirm dialog, pagination via the API, skeletons, and empty and error states with retry.
6. **Project detail** `/projects/[projectId]`: header with inline-editable name and description, and an **upload dropzone** (`src/features/upload/`): drag and drop plus file picker, client pre-checks (type, empty, 25 MB), real progress (XHR), multi-file queue, warnings surfaced (e.g. "Only page 1 of 3 processed"). Below it, a floor-plan list with thumbnail, version, status and a **live processing timeline** (8 stages from `Job.stages`; polling 2 s → 6 s after 60 s → "taking longer than usual" after 10 min; a fresh `PENDING` job shows **Start processing**), plus retry for FAILED. Clicking a completed plan navigates to P6's workspace route.
7. **Settings** `/settings`: Clerk `<UserProfile/>` themed to match, appearance (theme, density compact or comfortable stored in localStorage and exposed as a CSS class P6 can honour), and units display preference (px or metric when scaled).
8. **Global**: `not-found.tsx`, `error.tsx`, `loading.tsx`, page titles and metadata, favicon and OG image, and a 401 → sign-in redirect that preserves `?redirect_url`.

## Shared UI you provide for P6 (document each in `HANDOFF.shell.md`)
- Every themed shadcn primitive in `src/components/ui/`.
- `src/components/` composites: `PageHeader`, `EmptyState`, `ErrorState` (with retry), `SkeletonList`, `StatusBadge` (job statuses), `ConfirmDialog`, `Kbd`, `CopyButton`, `StatTile`, `Spinner`.
- A density class (`.density-compact`) and `prefers-reduced-motion` handling in `globals.css`.

## Engineering
- TanStack Query using the P0 client and `queryKeys`. Optimistic updates only where safe (rename). Invalidate on mutations.
- Server Components for static marketing. Client components for data (the token comes from Clerk `useAuth().getToken()`).
- No new state library. URL state for filters (`useSearchParams`).
- Accessibility: landmarks, labelled controls, focus management in dialogs, visible focus, AA contrast in both themes, everything keyboard reachable. Test with Testing Library queries by role.
- Tests (Vitest + MSW): API error mapping in the UI, the upload flow (progress, rejection messages), polling back-off logic (fake timers), project CRUD, command palette navigation, theme toggle persistence. Target ≥ 40 meaningful tests.

## Done when
- [ ] All screens are built, look premium in light and dark at 3 viewports, with QA screenshots committed under `qa/p5/`.
- [ ] `/impeccable audit` and `/hallmark audit` have no high-severity findings. Lighthouse on the landing page is ≥ 95 for perf and a11y.
- [ ] `npm run lint`, `npx tsc --noEmit`, `npm test` and `npm run build` are green.
- [ ] `DESIGN.md` is updated (decisions log), and `HANDOFF.shell.md` documents the shared components and any requests.
- [ ] `/ponytail-review` + `code-review-and-quality` done.

## Tooling
**design-taste-frontend**, **impeccable**, **hallmark**, **ui-ux-pro-max** (+ shadcn MCP), **playwright-cli**, **context7** (Next.js 16, React 19, Clerk `appearance` and components, Tailwind 4, shadcn, TanStack Query, cmdk, motion), agent-skills `frontend-ui-engineering`, `browser-testing-with-devtools`, `performance-optimization`.

# HANDOFF: P5 (web shell)

## Status

| Feature | Status |
|---|---|
| Design tokens (AA-tuned values, `--link`, `--row-gap`, `.density-compact`, browser surfaces) | TESTED (contrast script and screenshots) |
| Themed primitives in `src/components/ui` | IMPLEMENTED |
| Shared composites (below) | TESTED |
| Landing `/` (live hero demo, story, capabilities, trust, CTA, footer) | TESTED |
| Auth `/sign-in`, `/sign-up` (Clerk themed, split layout, redirect to `/dashboard`) | IMPLEMENTED (renders with dev keys; sign-in not exercised) |
| App shell (sidebar, rail, mobile sheet, breadcrumbs, Ctrl/⌘K palette, theme toggle, UserButton, toasts) | TESTED |
| Dashboard (greeting, real totals, recent plans, first run) | TESTED |
| Projects (grid/list, search and sort in the URL, API pagination, create/rename/delete, skeleton/empty/error) | TESTED |
| Project detail (inline edit, upload queue with XHR progress and pre-checks, floor-plan list, live 8-stage timeline, start/retry) | TESTED |
| Settings (theme, density, units, Clerk `<UserProfile/>` when signed in) | TESTED |
| Global: not-found, error, loading, metadata, icon, OG image, robots, 401 → `/sign-in?redirect_url=` | TESTED |

Checks: `npm run lint`, `npx tsc --noEmit`, `npm test` (**92 tests**) and `npm run build` are all green.

Landing page (production build, Chrome DevTools): **LCP 143 ms, CLS 0**. Lighthouse scores: accessibility **100**, SEO 100, best practices 77. Both best-practices failures are third-party cookies from Clerk's **development instance**; re-check with production Clerk keys.

QA screenshots: `qa/p5/<screen>-<1440|1024|390>-<light|dark>.png`, 8 screens × 3 viewports × 2 themes, against MSW mocks.

Nothing is VERIFIED: no human has checked it against the real API.

## How to run
```powershell
cd apps/web; npm ci
$env:NEXT_PUBLIC_API_MOCKING="on"; npm run dev    # :3000, MSW mocks, auth bypassed in dev
npm test; npx tsc --noEmit; npm run lint; npm run build
```
Against the real API: `NEXT_PUBLIC_API_MOCKING=off`, `NEXT_PUBLIC_API_URL=http://localhost:8000`, Clerk keys in `.env.local`. Optional `NEXT_PUBLIC_SITE_URL` sets `metadataBase` for the OG image (default `http://localhost:3000`).

## Shared UI for P6
All are exported from `@/components/composites` unless noted. Icons are lucide with `strokeWidth={ICON_STROKE}` (1.5).

| Component | Use |
|---|---|
| `PageHeader({ title, description?, actions? })` | One h1 per screen. |
| `EmptyState({ icon?, title, description?, action? })` | One sentence and one action. |
| `ErrorState({ error, onRetry?, title? })` | Pass the thrown error; copy comes from `describeError` (`@/lib/errors`). Retry appears only for retryable codes. `role="alert"`. |
| `SkeletonList({ rows?, rowClassName?, label? })` | `role="status"` with an accessible label. |
| `StatusBadge({ status: JobStatus })` | Icon and word. |
| `ConfirmDialog({ open, onOpenChange, title, description, confirmLabel, onConfirm, destructive? })` | `onConfirm` may be async. The dialog stays open until it settles, so the caller can toast an error. |
| `Kbd`, `KbdGroup` | Re-exported from `ui/kbd`. |
| `CopyButton({ value, label? })` | Icon button; announces "Copied". |
| `StatTile({ label, value, detail? })` | Use inside a `<dl>`. A `null` value means loading. |
| `Spinner({ label? })` | Stops spinning under reduced motion. |
| `PlanThumb` (`@/components/plan-thumb`) | Plan image on drawing paper. Falls back to blank paper when a signed URL expires. |
| `Logo`, `LogoMark` (`@/components/logo`) | |
| `useShellActions()` (`@/components/shell/shell-actions`) | `{ createProject, openPalette }` from anywhere under `(app)`. |
| `usePreference("density" \| "units" \| "sidebar")` (`@/lib/preferences`) | `units` is `"metric" \| "px"`. **Metric applies only when the model has `mm_per_pixel`**; never convert without it. |
| `describeError(err)` (`@/lib/errors`); `formatBytes`, `formatDate`, `formatDateTime`, `formatDuration` (`@/lib/format`) | |
| `STAGE_LABELS`, `stageRows`, `pollInterval`, `isRunning` (`@/features/projects/job-poll`); `ProcessingTimeline` | Reuse for the workspace's processing state. |

Density: `.density-compact` on `<html>` retunes the component tokens and `--row-gap`. `prefers-reduced-motion` zeroes `--duration-*` and every animation (`globals.css`).

The shell around the workspace:
- The sidebar is forced to its 48 px rail on `/projects/*/floorplans/*`.
- The top bar stays, with breadcrumbs Projects › project › plan filename.
- The page renders inside `<main id="main">`, a flex column with `min-h-0 flex-1 overflow-y-auto`, so `flex-1` or `h-full` fills the rest of the screen.

## Contract change requests
- **A way to list floor plans across projects** (or `recent_floorplans` on `/v1/me`). The dashboard and palette send one request per project, capped at the 6 and 8 most recently updated projects respectively.
- **Edit counts** (e.g. `edits_this_week` on `/v1/me`). The dashboard skips that tile until it exists.
- **Server-side search and sort on `GET /v1/projects`.** Search and sort run client-side over the loaded page, as the phase asked; the empty state says so when there is more than one page.

## Requests to other phases
- **P7**: `apps/web/.gitignore` now tracks `qa/p5/*.png`, because the phase requires committed QA screenshots. `qa/p6` stays ignored.
- **P7**: `src/test/render.tsx` duplicates `FetchXhr` from `src/lib/api/client.test.ts`. The copy adds a `sent` log because MSW in Node can't parse jsdom's `FormData`. Fold the two into one helper once `src/lib/api` unfreezes.
- **P3**: Plan rows use `download_url` and the `preprocessed` artifact (as a thumbnail). Both must be signed URLs the browser can load directly in `<img>` and `<a>`.
- **P6**: The workspace route still renders the P0 placeholder. P5 relies on it only as a link target.

## Known limitations
- Skills not run this session: `/hallmark audit`, the impeccable `critique`, `audit` and `polish` commands, `/ponytail-review`, `code-review-and-quality` and `security-and-hardening`. A manual screenshot critique-and-fix loop was done instead (commit `05afe9e`). context7 was not authenticated, so library APIs were checked against installed sources and `node_modules/next/dist/docs`.
- No Lighthouse **performance** score: downloading the Lighthouse CLI was blocked. The LCP and CLS above come from an unthrottled DevTools trace.
- Clerk sign-in, sign-up, `<UserButton/>` and `<UserProfile/>` render with the dev keys but were not exercised signed in. The Clerk card's title ("AI x AEC") is the application name set in the Clerk dashboard.
- Search covers only the loaded page of projects (up to 20).
- The dashboard's "Floor plans" total appears only when every project fits in one 100-item page.
- Tests get upload progress from a stub XHR. Real byte-level progress was not measured.

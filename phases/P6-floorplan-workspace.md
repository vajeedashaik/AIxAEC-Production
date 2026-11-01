# P6: Floor-Plan Workspace (viewer, AI command bar, voice, history)

> Parallel phase. Worktree `phase/p6-workspace`. **Write only inside:** `apps/web/src/features/viewer/**`, `apps/web/src/features/workspace/**`, `apps/web/src/app/(app)/projects/[projectId]/floorplans/[floorplanId]/**`, `apps/web/src/app/(dev)/**`, `apps/web/qa/p6/**`. **No new npm dependencies** and no `npx shadcn add` (OWNERSHIP.md §3). Dev server on **:3001** (`npm run dev -- -p 3001`).

## Read first
`CLAUDE.md` · `phases/shared/*` (CONTRACTS §2–§4 and §8 are your data) · `apps/web/DESIGN.md` (canvas tokens `--canvas-*`) · `docs/design/references/{figma,miro,linear}.DESIGN.md` · `FULL_PROJECT_CONTEXT.md` §17 (old viewer and editor behaviours to keep) · fixtures `packages/contracts/fixtures/apartment*.json`.

## Mission
Build the heart of the product: a **fast, precise, beautiful canvas workspace** where the user sees the understood plan, selects elements and changes the model by **typing, speaking or clicking**, with a **preview of every change before it's applied**, plus full undo/redo history. It should feel like Figma's precision with Linear's calm.

Develop against MSW mocks (the P0 handlers implement PREVIEW/APPLIED/undo/redo in memory) and the `(dev)/playground` route.

## 1. Deterministic renderer: `src/features/viewer/render/` (pure TS, zero deps)
- `buildScene(model, options) → Scene`: flat ordered primitives in model coordinates. Draw order: room fills → room labels and areas → walls (polygons from centre-line + thickness) → windows → doors (leaf + swing arc) → columns → stairs (treads) → furniture → dimensions. 2-dp rounding. Invalid elements are skipped (and counted). A null model gives an empty scene. Each primitive carries `elementId`, `kind` and a style **token name** (never a raw colour).
- `sceneToSvgString(scene)`: byte-identical, escaped (used for tests and export).
- `view-transform.ts`: `modelToScreen` / `screenToModel` exact inverses, `fitTransform(bounds, viewport, padding)`, `zoomAt(point, factor)` cursor-anchored with limits 0.02–40, `panBy`.
- `geometry.ts` (area, perimeter, centroid, point-in-polygon, bounds) and `units.ts` (px vs mm/m formatting that **never fakes a conversion** without `mm_per_pixel`).
- `diff.ts`: given `ChangeSet` + before/after models, produce overlay primitives for the **preview ghost** (added = `--canvas-preview-add`, modified = before as dashed and after as solid in `--canvas-preview-modify`, removed = `--canvas-preview-remove` struck).

## 2. Interactive viewer: `src/features/viewer/components/`
- `FloorPlanViewer` (state: transform, selection, hover, layer visibility; the model stays a prop). `FloorPlanCanvas` renders one SVG with a single `<g transform>` updated **imperatively** during pan/zoom gestures and committed to React state once per gesture (keeps 60 fps on large plans). A memoised base layer and thin highlight/preview layers. Event-delegated hit testing via `data-element-id`.
- Interactions: wheel zoom (cursor-anchored), trackpad pinch, space-drag or middle-drag pan, double-click to zoom to element, `F` fit, `0` reset, `+`/`-`, arrow keys nudge the view, `Esc` clears selection, `Tab` cycles elements of the selected kind. Hover highlight, click select, shift-click multi-select (read-only for now).
- Canvas chrome: a subtle **blueprint grid** that scales with zoom, a scale bar (metric when calibrated, otherwise px with a "not calibrated" chip), a zoom % indicator, a **minimap**, layer toggles (rooms, walls, openings, objects, dimensions, labels), a "show original drawing" underlay (the `preprocessed` artifact at adjustable opacity), and a coordinate readout under the cursor (mono font).
- Re-fit on resize unless the user has panned. Honour `prefers-reduced-motion` and the `.density-compact` class.

## 3. Workspace page: `.../floorplans/[floorplanId]/page.tsx` + `src/features/workspace/`
Layout (resizable panels via the existing `resizable` primitive): **left** = element outline (rooms → walls/openings tree, search, click to select and zoom), **centre** = canvas, **right** = inspector + insights, **bottom-centre floating** = the AI command bar. Top bar: plan name, version chip (`v7 · HEAD`), Undo/Redo, history toggle, processing status, and download links for artifacts.

- **Inspector** (`describeElement`): kind, id (copyable), dimensions (length/area in px plus metric when scaled, mono font), room type with confidence and source badges (DETECTED / INFERRED / USER_CONFIRMED), linked walls and rooms (clickable).
- **Selection actions** (point-and-click editing): context buttons for the selected element that build **the same structured commands** and send them through the server. Wall → Move (direction + distance popover; only perpendicular directions offered), Delete, Add door, Add window (position slider 0–1, width), **Set scale** (enter real length). Room → Rename (with type select), Resize side (direction, distance, expand/contract). Door/window → Delete. **The client never changes geometry.**
- **AI command bar** (the hero interaction):
  - A single input with placeholder examples that rotate, `/` to focus, ⌘↵ to apply, ↵ to preview. History of past instructions with ↑/↓.
  - **Preview first**: ↵ calls `/commands/interpret` and renders the **ghost diff** on the canvas plus a summary card ("Move wall 300 mm left · 2 rooms resized") with **Apply** / **Discard**. Apply calls `/commands` with `expected_version`.
  - **Clarification**: show the question and candidate chips. Hovering a chip highlights that element on the canvas and pans to it. Picking one re-sends the structured command with `target_id`.
  - **Rejected**: an inline, friendly explanation keyed by `stage` (e.g. "Set a scale first", with a button that starts the Set-scale flow on a selected wall).
  - **Stale model (409)**: refetch, show "The plan changed; here's the latest" and keep the user's text.
  - **Voice**: a 🎤 button (lucide `Mic`, no emoji) with push-to-talk (hold `V`) or click-to-toggle via `MediaRecorder` (prefer `audio/webm;codecs=opus`, fallback `audio/mp4` for Safari), a live level meter, a 60 s cap, then "Heard: …" with the transcript editable before preview. Handle mic permission denial gracefully.
- **History panel**: the version timeline (origin icons PROCESSING/EDIT, discarded versions greyed), edit log entries with status and stage, Undo/Redo (⌘Z / ⇧⌘Z) gated on `can_undo`/`can_redo`, and click a version to view it read-only (`?version=`) with a "Back to HEAD" bar.
- **Insights panel**: counts, total and average area, largest and smallest room, wall lengths (exterior/interior), rooms by type (a small bar list using canvas room colours), and metric values only when scaled, otherwise a "Calibrate to see m²" CTA.
- **Changes animate**: after APPLIED, the changed elements pulse briefly (`--canvas-selection`) and the version chip ticks up.
- Loading (canvas skeleton), processing (link back to the timeline), failed and empty states.

## 4. Dev playground `(dev)/playground`
Loads the fixture models directly (no auth, `notFound()` in production) with knobs: fixture choice, layer toggles, theme, force-preview a sample ChangeSet. Use it for fast iteration and screenshots.

## Design and QA loop (TOOLING.md §3)
`/impeccable shape` the workspace before building. Take `playwright-cli` screenshots (1440×900 and 1024×768, light and dark) of: the idle plan, a selected wall with the inspector, a preview ghost, a clarification, a rejection, the history open, voice recording, and the playground. Save them to `qa/p6/`. Then `/impeccable critique` → fix → `/impeccable audit` → `design-taste-frontend` look-and-fix loop on app screens → `/impeccable polish`. Performance: pan/zoom at 60 fps on a 500-element synthetic model (generate it in the playground). Use `browser-testing-with-devtools` / chrome-devtools MCP for a performance trace.

## Tests (Vitest, jsdom, MSW)
Renderer: scene ordering, rounding, invalid-element skipping, SVG byte-identity snapshot, view-transform inverse property tests, zoom limits, units never faking mm, diff overlay classification. Viewer: hover, select, keyboard shortcuts, fit. Workspace: preview → apply flow, clarification pick re-sends `target_id`, rejection rendering per stage, a stale 409 path, undo/redo gating, voice recording with mocked `MediaRecorder` and the transcript shown, the selection-actions command payloads (assert the exact JSON per operation). Target ≥ 60 meaningful tests.

## Done when
- [ ] Every interaction above works in mock mode and against the real API.
- [ ] The QA screenshots are committed, impeccable audit has no high-severity issues, and 60 fps pan/zoom is verified with a trace.
- [ ] lint, tsc, tests and build are green (scoped checks are fine, but the whole web build must pass).
- [ ] `src/features/workspace/HANDOFF.md`: feature status, keyboard map, requests (e.g. deps or shared components wanted from P5).
- [ ] `/ponytail-review` + `code-review-and-quality` done.

## Tooling
**impeccable**, **design-taste-frontend**, **hallmark** (empty and first-run states only), **ui-ux-pro-max** (`ui-styling`; **don't** add shadcn components), **playwright-cli**, chrome-devtools MCP, **context7** (React 19, Next.js 16, MediaRecorder, Pointer Events, TanStack Query), agent-skills `frontend-ui-engineering`, `performance-optimization`, `test-driven-development`.

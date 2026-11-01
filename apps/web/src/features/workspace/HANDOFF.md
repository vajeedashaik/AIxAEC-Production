# HANDOFF: P6 (workspace)

## Status
| Feature | Status | Notes |
|---|---|---|
| Renderer `features/viewer/render/` (`buildScene`, `sceneToSvgString`, view transform, geometry, units, diff, `describeElement`) | TESTED | Pure TS, no deps. Snapshot plus inverse/limit/unit tests. |
| Canvas viewer (`FloorPlanViewer`, `FloorPlanCanvas`) | TESTED | Pan/zoom are imperative on one `<g transform>`, committed once per gesture. Includes the grid, scale bar, zoom %, minimap, layers, original-drawing underlay and cursor coordinates. |
| Workspace page (outline, canvas, inspector/insights/history tabs, top bar, downloads) | TESTED in mock mode | Resizable at ≥1024 px; below that, the side panels move into a "Details" sheet. |
| AI command bar (preview first, apply, clarification chips with hover-to-locate, rejection per stage, stale 409) | TESTED in mock mode | |
| Selection actions (wall, room, door, window) | TESTED | Exact JSON payload asserted for each operation. |
| Voice (click to toggle, hold V, level meter, 60 s cap, editable "Heard" transcript, mic denial) | TESTED with a mocked `MediaRecorder`; verified in Chromium with a synthetic stream | Uploads with `dry_run=true` and only uses the transcript. |
| History (versions, edit log, undo/redo gating, `?version=` read-only view with "Back to HEAD") | TESTED in mock mode | |
| Insights | TESTED in mock mode | Metric values appear only when `metric` is present; otherwise a "Set scale" call to action. |
| Post-apply pulse plus version chip update | IMPLEMENTED | Disabled under `prefers-reduced-motion`. |
| Dev playground `/playground` | IMPLEMENTED | Fixture picker, preview-ghost toggle, theme toggle, 500+ element synthetic plan. Returns `notFound()` in production. |
| Against the real API | NOT_STARTED | P3/P2/P4 weren't running. Uses only the typed P0 client, so it should work as is. |
| VERIFIED (human check on the real stack) | NOT_STARTED | |

Checks: 125 web tests pass; `tsc`, eslint (P6 paths) and `next build` are green.
Performance: wheel zoom on the synthetic plan (1,020 SVG primitives) ran 239 frames in Chromium at an average of 16.67 ms, p95 16.8 ms and worst 17.1 ms (an in-page rAF measurement, not a DevTools trace).
Screenshots: `apps/web/qa/p6/` (idle, selected wall, preview, clarification, rejection, history, voice, voice heard, playground; 1440 and 1024; light and dark).

## How to run
```powershell
cd apps/web
# .env.local: NEXT_PUBLIC_API_MOCKING=on to use MSW fixtures
npm run dev -- -p 3001
# http://localhost:3001/projects/a3e1b2c4-d5f6-4a7b-8c9d-e0f1a2b3c4d5/floorplans/c0d50567-abaa-43fd-ba84-0b9e05790fa7
# http://localhost:3001/playground
npx vitest run src/features
```

## Keyboard map
| Key | Action |
|---|---|
| `/` | Focus the command bar |
| `Enter` (in the bar) | Preview (`/commands/interpret`) |
| `Ctrl/⌘ + Enter` | Apply the preview, or apply the typed text directly |
| `↑` / `↓` (in the bar) | Previous instructions |
| Hold `V` | Push to talk |
| `Esc` | Discard the preview or question, then clear the selection |
| `Ctrl/⌘ + Z`, `Ctrl/⌘ + Shift + Z` | Undo, redo (gated on `can_undo`/`can_redo`) |
| `F` / `0` / `+` / `-` | Fit / 100 % / zoom in / zoom out |
| Arrow keys | Nudge the view |
| `Space` + drag, middle-drag | Pan |
| Wheel, trackpad pinch | Zoom at the cursor (0.02–40) |
| Double-click | Zoom to the element |
| `Tab` / `Shift+Tab` (canvas focused, something selected) | Cycle elements of the same kind |
| Shift + click | Add to or remove from the selection |

## Contract change requests
1. **`CommandResponse.command` on CLARIFICATION for typed instructions.** The parsed command (with `target_query`) should come back so the UI can re-send it with the picked `target_id`. Today it is `null` (mock and contract example), so `commandFromInstruction` in `commands.ts` rebuilds only commands whose words are explicit (delete door/window/wall, or move wall with a direction and an mm/px distance), and otherwise asks the user to rephrase. Blast radius: API (P3) passes the parser result through; the TS type is already nullable. Marked `// CONTRACT-GAP:`.
2. **`Dimension` orientation.** There is no axis field, so the renderer guesses vertical when the label sits outside the wall extent. Suggest `orientation: "HORIZONTAL" | "VERTICAL" | null`. Marked `// CONTRACT-GAP:` in `scene.ts`.

## Requests to other phases
- **P5:** `react-resizable-panels` v4 hit-tests pointers globally. In jsdom (no layout) every click lands on a separator, so workspace tests mock `@/components/ui/resizable`. No change needed unless P5 wants a test helper.
- **P5:** the app shell header and the workspace top bar stack (88 px total). Consider a full-bleed variant of `(app)/layout.tsx` for this route, or let P6 own the top bar there.
- **P0/P7 (mocks):** the MSW voice handler can't parse jsdom `FormData` in Node tests, so the workspace voice test overrides it. Also, the mock backend never returns `command` on CLARIFICATION (see contract request 1).
- **P3:** the voice route is called with `dry_run=true` purely to transcribe. If a lighter transcribe-only endpoint gets added, the workspace can switch to it.

## Known limitations
- No 60 fps DevTools trace was recorded; the frame-time figure above comes from an in-page measurement (chrome-devtools MCP wasn't used in this session).
- `/impeccable critique`/`audit`/`polish` and the design-taste look-and-fix loop were done as one screenshot review pass (fixes: outline-only room ghosts, coordinates moved above the scale bar, explicit recording state). A formal audit report wasn't produced.
- The 390 px phone layout works (Details sheet) but wasn't screenshotted.
- Selecting a version flashes the skeleton while that version loads.
- Room labels sit at the polygon centroid and can overlap stairs or furniture.
- Exterior vs interior walls are inferred from how many rooms reference a wall.

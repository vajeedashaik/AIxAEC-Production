# DESIGN.md: AEC Studio design system

> **Law for every UI change.** P0 seeded it, P5 refines it. **Token names are frozen** (P5 may tune values; P6 consumes names). Tokens live in `src/app/globals.css`.

## 1. Product personality: a precision instrument

AEC Studio is a tool architects and engineers keep open for hours: dense plans, exact numbers, small decisions repeated many times. It should feel **calm, exact and confident**, like a good drafting instrument.

- **Calm:** neutral graphite chrome, one accent, no decoration competing with the drawing.
- **Exact:** numbers in tabular mono, aligned edges, hairline borders, a strict 4 px grid. Never round a measurement silently. Show units every time (`3600 mm`, `360 px`).
- **Confident:** clear states (preview, applied, rejected), direct copy, no hedging.
- **The canvas is the protagonist.** Chrome recedes; the plan and its changes carry the colour.

### Banned (the old look and generic "AI" styling)
Aurora / mesh / gradient backgrounds · glassmorphism, backdrop blur as decoration · gradient text or gradient accents · purple-blue "AI" palettes · glowing shadows · emoji as icons · centred-everything heroes · more than one accent hue · decorative motion.

## 2. Token architecture (three layers)

| Layer | Prefix | Who uses it |
|---|---|---|
| Primitive | `--p-gray-0…13`, `--p-cobalt-*`, `--p-green-*`, `--p-amber-*`, `--p-red-*`, `--p-sky-*` | Only the semantic layer. Never referenced by components. |
| Semantic | shadcn names (`--background`, `--foreground`, `--card`, `--popover`, `--primary`, `--secondary`, `--muted`, `--accent`, `--destructive`, `--border`, `--input`, `--ring`, `--sidebar-*`, `--chart-1…5`) plus `--border-strong`, `--surface-sunken`, `--surface-raised`, `--success`, `--warning`, `--danger`, `--info` (+ `-foreground`) | All components, via Tailwind (`bg-card`, `text-muted-foreground`, `border-border-strong`, `bg-success`…). |
| Component | `--control-h-sm/md/lg`, `--topbar-h`, `--sidebar-w`, `--inspector-w`, `--command-bar-h`, `--focus-ring-width`, `--icon-stroke` | Layout and controls. |
| Canvas | `--canvas-*` (§5) | The floor-plan renderer only (P6). |

Light values live in `:root`, dark values in `.dark` (next-themes, `attribute="class"`, default `system`).

## 3. Typography

- **Sans:** Geist Sans (variable, self-hosted via the `geist` package) for all UI.
- **Mono:** Geist Mono for **dimensions, coordinates, areas, ids, version numbers and keyboard shortcuts**. Use the `.numeric` class (mono + `tabular-nums slashed-zero`).
- Default UI size is **13 px** (`text-ui`, line-height 20 px). Dense metadata uses `text-micro` (11 px).

| Role | Class | Size / weight | Use |
|---|---|---|---|
| Display | `text-4xl font-semibold tracking-tight` | 36 / 600 | Marketing only |
| Page title | `text-2xl font-semibold tracking-tight` | 24 / 600 | One per screen |
| Section | `text-base font-medium` | 16 / 500 | Panel and card titles |
| Body | `text-sm` | 14 / 400 | Paragraphs, forms |
| UI (default) | `text-ui` | 13 / 400 | Lists, inspector, menus |
| Meta | `text-micro text-muted-foreground` | 11 / 400 | Timestamps, labels, eyebrows (`uppercase tracking-wider`) |
| Numeric | `numeric` | inherits size | Measurements, coordinates, versions |

Negative tracking only at 24 px and up. Sentence case everywhere except eyebrows.

## 4. Colour

- **Chrome is neutral graphite** (cool hue 255, very low chroma). Hierarchy comes from the surface ladder `--surface-sunken` → `--background` → `--card`/`--surface-raised` → `--popover`, plus hairline borders.
- **One accent: cobalt** (`--primary`). Use it for the primary action on a screen, focus rings, selection and links. Never as a large fill or background wash.
- **Semantic colours** are for state only: `--success` (applied, completed), `--warning` (degraded stage, needs scale), `--danger` (rejected, failed, destructive), `--info` (neutral notices, processing). Pair colour with an icon or text; never colour alone.
- Contrast: body text ≥ 4.5:1, large text and UI glyphs ≥ 3:1 in both themes.

## 5. Canvas palette (frozen names)

Paper-and-ink in light mode, "blueprint at night" in dark mode. Room fills are deliberately low-chroma so walls, selection and previews dominate.

| Token | Meaning |
|---|---|
| `--canvas-paper` | Drawing background |
| `--canvas-grid`, `--canvas-grid-major` | Minor / major grid lines |
| `--canvas-wall`, `--canvas-wall-exterior` | Wall fill (interior / exterior) |
| `--canvas-door`, `--canvas-door-swing` | Door leaf, swing arc |
| `--canvas-window` | Window glazing |
| `--canvas-column`, `--canvas-stair`, `--canvas-furniture` | Other elements |
| `--canvas-dimension` | Dimension lines and text |
| `--canvas-room-label`, `--canvas-room-area`, `--canvas-room-stroke` | Room name, area text, room outline |
| `--canvas-room-<type>` | Fill per `RoomType`, kebab-case: `unknown`, `bedroom`, `master-bedroom`, `bathroom`, `kitchen`, `living-room`, `dining-room`, `hallway`, `closet`, `garage`, `office`, `laundry`, `balcony`, `storage`, `stairwell`, `utility`, `other`. Helper: `roomFillVar(type)` in `@/contracts`. |
| `--canvas-hover` | Hover outline |
| `--canvas-selection`, `--canvas-selection-fill`, `--canvas-handle` | Selected element stroke / fill, drag handles |
| `--canvas-preview-add` | Preview ghost: added elements (solid) |
| `--canvas-preview-modify` | Preview ghost: modified (before dashed, after solid) |
| `--canvas-preview-remove` | Preview ghost: removed (dashed, struck) |

Canvas strokes scale with zoom so walls keep their true pixel thickness; overlays (selection, hover, handles) use constant screen-space widths (1.5 px stroke, 8 px handles).

## 6. Spacing, layout and density

- 4 px base. Use Tailwind steps 1, 2, 3, 4, 6, 8, 12 (4–48 px). Panel padding 12–16 px; card padding 16–24 px.
- Default control height 32 px (`--control-h-md`); 28 px in toolbars and the inspector; 40 px on marketing and touch.
- App shell: top bar 44 px, sidebar 240 px, inspector 300 px, command bar 48 px. The workspace canvas takes every remaining pixel.
- Dense lists: 32 px rows, no zebra striping; hairline separators.

## 7. Shape and elevation

- Radius base 6 px (`--radius`): inputs and buttons `rounded-md`, cards and popovers `rounded-lg` (8 px), dialogs `rounded-xl` (12 px). No pills except status badges.
- Elevation is mostly surface + hairline. Shadows only for floating layers: `shadow-sm` (cards on hover), `shadow-md` (popovers, menus), `shadow-lg` (dialogs, command palette).

## 8. Motion

| Token | Value | Use |
|---|---|---|
| `--duration-instant` | 80 ms | Hover, press |
| `--duration-fast` | 120 ms | Toggles, tooltips |
| `--duration-base` | 180 ms | Panels, popovers, preview ghost fade |
| `--duration-slow` | 280 ms | Dialogs, the post-apply change pulse |
| `--ease-standard` / `--ease-enter` / `--ease-exit` | `cubic-bezier(.2,0,0,1)` / `(0,0,.2,1)` / `(.4,0,1,1)` | Move / appear / leave |

Motion explains change (what moved, what was added), never decorates. `prefers-reduced-motion` sets every duration to 0; state changes still read through colour and text.

## 9. Iconography

lucide-react only, **1.5 px stroke** (`strokeWidth={1.5}` / `--icon-stroke`), 16 px in UI, 14 px in dense toolbars, 20 px in empty states. Icons accompany labels; icon-only buttons need a tooltip and `aria-label`.

## 10. States and accessibility

Every data view ships loading (skeleton matching the final layout), empty (one sentence + one action), error (what happened + retry) and success states. Everything is keyboard-reachable with a visible focus ring (`--ring`, 2 px, 2 px offset). No layout shift on load. Toasts (sonner) for confirmations; inline messages for validation.

## 11. References

`docs/design/references/`: Linear for chrome and density, Figma and Miro for canvas interaction, Vercel and Raycast for type and contrast. Borrow principles, never brand identity.

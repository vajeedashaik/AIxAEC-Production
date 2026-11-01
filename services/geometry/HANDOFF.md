# HANDOFF: services/geometry (P2)

Stateless, deterministic. No database, no network, no randomness: new element ids are UUID v4-shaped hashes of
(model, command), so the same request always returns byte-identical JSON.
Scope: *geometric consistency, not building-code or structural compliance.*

## Status

| Feature | Status | Notes |
|---|---|---|
| `POST /v1/commands/execute` | TESTED | Always 200 with `APPLIED` / `CLARIFICATION` / `REJECTED` for a valid envelope; 422 only for a bad envelope. `dry_run` doesn't change the computation |
| `POST /v1/models/insights` | TESTED | Shoelace areas (stored `area_px` ignored); interior = rooms on both sides (probed geometrically, not via `wall_ids`) |
| `POST /v1/models/brief` | TESTED | No coordinates, no ids |
| `POST /v1/models/validate` | TESTED | Full-model check (no `before`), returns every issue |
| Stage: schema | TESTED | Pydantic errors → one plain sentence |
| Stage: entity_resolution | TESTED | See the catalogue below |
| Stage: semantic_validation | TESTED | mm needs a scale, 3× image limit, opening ≤ wall span, ADD_WALL bounds/length/thickness, SET_SCALE 0.05–500 mm/px |
| MOVE_WALL | TESTED | Perpendicular only (>35 % along → refused with a hint), collinear continuations translate, end and T-junction neighbours re-project, corners/openings follow, `area_px` recomputed |
| RESIZE_ROOM | TESTED | Side walls = within tolerance of the room's extreme edge, overlapping >25 %. Shares `_shift_walls` with MOVE_WALL |
| ADD_WALL | TESTED | Endpoints snap to centre-lines, median thickness, `USER_CONFIRMED` |
| DELETE_WALL | TESTED | Merge (Shapely union, simplify, winding kept, larger room's label and type survive), exterior → `constraints` refusal, openings removed, `wall_ids` cleaned |
| ADD_DOOR / ADD_WINDOW | TESTED | 900/1200 mm scaled, 40/48 px unscaled, min 4 px, ≤90 % of wall, centre clamped, overlap refused |
| DELETE_DOOR / DELETE_WINDOW | TESTED | |
| RENAME_ROOM | TESTED | Type = given, else `room_type_for_text`, else UNKNOWN; `USER_CONFIRMED`, 1.0 |
| SET_SCALE | TESTED | `MANUAL`, 1.0 |
| Constraint validator | TESTED | Unique ids, bounds ±6 px, ring valid/≥1 px²/not inverted/not crushed <20 %, axis-aligned stays aligned, no landing on/crossing a parallel wall, no reversed connected wall, openings attached ≤30 px. Judged against `before` |
| Property tests (Hypothesis) | TESTED | Random 1–8 step move/resize sequences on the apartment never produce an invalid model; random/garbage commands always return a union member |
| Budget | TESTED | Apartment execute ≈ 5 ms (budget 50 ms) |
| Real-stack check | NOT_STARTED | Needs P3 calling it (P7) |

Every `expected_command` in `commands.examples.json` resolves, and each one either applies or gets a geometry
refusal with a hint. The only refusal is "wall between office and bedroom … north", because that wall is vertical.

## How to run
```powershell
cd services/geometry
py -m uv sync
py -m uv run pytest          # 199 tests incl. Hypothesis
py -m uv run ruff check .
py -m uv run mypy app
py -m uv run uvicorn app.main:app --reload --port 8002
```

## Clarification catalogue (entity resolution)

| Query shape | 0 matches | 1 | >1 |
|---|---|---|---|
| room (`kitchen`, `lounge`, `toilet`, `corridor`…): label substring either way, or `ROOM_SYNONYMS` type | reject "I can't find a room called '…'." | resolved | "Which room do you mean?" |
| `wall between X and Y` | reject "Those rooms don't share a wall." | resolved | "Which wall do you mean?" |
| `<room> wall` | reject "No walls are linked to <room>." | resolved | "Which <room> wall do you mean?" |
| `north/south/east/west` (or top/bottom/left/right) `wall of <room>` | reject "The <room> has no north wall." | resolved | clarify (ties within 2 px) |
| `shared wall` | reject "No wall is shared by two rooms." | resolved | clarify |
| any wall query on a single-wall model | | resolved trivially | |
| `<room> door/window`, `door between X and Y` | reject "I can't find a door in <room>." | resolved | "Which door do you mean?" |
| `door` / `front door` (no room phrase) | reject "This plan has no doors." | resolved | clarify over all |
| explicit `target_id` | "No wall with that id…" / "That target is a door, not a wall." | kind-checked | |

Candidate labels: `"vertical wall, 450 px long (living ↔ kitchen)"`, `"door at (1130, 700) in hall / bath"`,
`"kitchen at (780, 325)"`. `x,y` is the midpoint or centroid. Order follows the model's list order (deterministic).
Orientation words are only stripped when they aren't part of a room label ("East Wing" still matches).

## Contract change requests
None.

## Requests to other phases
- **P3:** forward the geometry result unchanged. `REJECTED.detail` and `CLARIFICATION.question` are user-safe text.
  Candidate labels can include the user's room names, so render them as text, never HTML.
- **P3:** cap the request body. The engine is O(walls²) in places, so very large models are slow (see below).
- **P4:** emit `target_query` in the shapes listed above ("wall between X and Y", "north wall of X", "X door").

## Known limitations
- Performance scales with plan size: a synthetic 312-wall / 144-room grid takes ≈ 200 ms per execute
  (the apartment ≈ 5 ms). Fine for real floor plans, but not tuned for large ones.
- An unexpected internal exception becomes a 500 envelope rather than `REJECTED`. The Hypothesis fuzz test found none.
- RESIZE_ROOM assumes the side is formed by roughly axis-aligned walls. Diagonal walls can move (perpendicular)
  but can't be chosen as a room's side.
- Room-based wall references depend on `Room.wall_ids` (vision's linking). Insights and DELETE_WALL's side test
  use geometry instead, probing up to `thickness + 4` px from the centre-line.
- DELETE_WALL refuses merges that would leave a hole. Rooms nested inside each other merge into the outer outline.
- Ids of added elements are deterministic per (model, command): redoing the same add after an undo gives the same id.

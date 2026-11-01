# P2: Geometry Service (the only writer of coordinates)

> Parallel phase. Worktree `phase/p2-geometry`. **Write only inside `services/geometry/**`.**

## Read first
`CLAUDE.md` · `phases/shared/{ARCHITECTURE,CONTRACTS,OWNERSHIP,TOOLING}.md` · `FULL_PROJECT_CONTEXT.md` §6, §8 (entity resolution, semantic validation), §9 (your algorithmic spec) · fixtures in `packages/contracts/fixtures/`.

## Mission
Build a **stateless, deterministic FastAPI service** that takes `(model, raw command)` and returns `APPLIED` (new validated model + `ChangeSet` + human summary), `CLARIFICATION` (question + ≥2 described candidates) or `REJECTED` (stage + actionable detail). It also computes insights, the LLM-safe plan brief and model validation. No database, no network calls, no randomness.

## Endpoints (CONTRACTS.md §6), all behind `X-Internal-Token`
`POST /v1/commands/execute` · `POST /v1/models/insights` · `POST /v1/models/brief` · `POST /v1/models/validate`

## Execute pipeline
`execute(model, raw_command, dry_run) -> ExecuteResult`. Each step's failure maps to `REJECTED` with that stage:

1. **schema**: `COMMAND_ADAPTER.validate_python(raw)`. Convert Pydantic errors into one plain-English sentence.
2. **entity_resolution**: resolve `target_query` into `target_id` (`TARGET_KIND` tells you the kind). An explicit `target_id` is only kind-checked.
   - *Rooms*: match by label substring (either direction, case-insensitive) or by synonym → `RoomType` using `aec_contracts.lexicon.ROOM_SYNONYMS` ("master bedroom", "lounge", "toilet", "corridor", …). Several matches → clarification.
   - *Walls*: "between X and Y" → the intersection of both rooms' `wall_ids` (0 → reject "Those rooms don't share a wall", 1 → resolved, >1 → clarification). A single-room reference → that room's walls (0 → "No walls are linked to <room>", 1 → resolved, >1 → clarification). Orientation words narrow candidates ("the north wall of the kitchen" → the topmost horizontal wall of that room). A single-wall model resolves trivially.
   - *Doors/windows*: via the referenced room's walls. With no room phrase and exactly one of that kind → it. Otherwise clarification.
   - Candidate labels are human: `"horizontal wall, 240 px long (kitchen ↔ living room)"`, `"door at (410, 88) in bedroom"`. Include an anchor `x,y` (the midpoint).
3. **semantic_validation**: `mm` with no `mm_per_pixel` → "Set a scale first to use millimetres (select a wall and use Set scale)". Moves or resizes > 3× the image's larger dimension are rejected. Opening width must be in (0, wall span]. `ADD_WALL` endpoints must be inside the image (+6 px) with length ≥ 1. `SET_SCALE` ratio must be 0.05–500 mm/px.
4. **geometry**: dispatch to the operation on a **deep copy**.
5. **constraints**: re-validate the whole candidate with Pydantic, then `validate_model(candidate, before=model)`.
6. Build the `ChangeSet` (added / modified / removed by id-diff plus value-diff) and the summary string.

`dry_run` changes nothing in the computation. It exists for API semantics and logging only.

## Operations (current behaviour, FULL_PROJECT_CONTEXT §9; supersedes older docs)
- **MOVE_WALL**: **perpendicular moves only**. If >35 % of the requested displacement lies along the wall, refuse with a hint ("This wall is horizontal; move it up or down"). Walls meeting the moved wall at an end **or a T-junction** (within `max(6, 1.5×thickness)` px) get that endpoint re-projected onto the new line, while collinear continuations translate. Room corners on the wall follow, attached doors and windows move, and every affected room's `area_px` is recomputed.
- **RESIZE_ROOM**: find the walls forming the chosen side (within tolerance of the room's extreme edge, overlapping >25 % of their length), then shift them with the same `_shift_walls`. EXPAND moves outward and CONTRACT inward. Refuse if that side isn't formed by movable walls.
- **ADD_WALL**: endpoints snap onto existing centre-lines within tolerance. Thickness defaults to the median existing thickness. `source = USER_CONFIRMED`.
- **DELETE_WALL**: find the rooms on each side. Rooms on **both** sides → **merge** (Shapely union, simplify, keep the winding; the larger room's label and type survive; `wall_ids` merged). A room on only one side (exterior) → refuse (`constraints`, "Exterior walls can't be deleted"). Openings on the wall are deleted, and `wall_ids` cleaned.
- **ADD_DOOR / ADD_WINDOW**: width from the command or the default (900 / 1200 mm when scaled, else 40 / 48 px), min 4 px, rejected if > 90 % of the wall. Centre clamped so the opening stays on the wall. Overlap with an existing opening → reject. Bbox axis-aligned with wall thickness, `wall_id` set.
- **DELETE_DOOR / DELETE_WINDOW**: remove.
- **RENAME_ROOM**: set the label. The type is the given one, else `room_type_for_text(name)`, else `UNKNOWN`. Mark `USER_CONFIRMED`, confidence 1.0.
- **SET_SCALE**: `mm_per_pixel = length_mm / wall.length_px`, source `MANUAL`, confidence 1.0.

## Constraint validator (compare against `before`, so pre-existing imperfections never block unrelated edits)
1. Unique ids. 2. Wall endpoints and room vertices inside the image (±6 px). 3. Rooms: ≥3 vertices, simple and valid ring, area ≥ 1 px², **not inverted** (no signed-area flip), **not crushed** below 20 % of the former area. 4. An axis-aligned wall (≤0.5°) stays axis-aligned. 5. A moved wall must not land on or cross a **parallel** wall (unless they already touched). 6. Openings still reference an existing wall and lie within 30 px of it. Only judged if the opening or its wall changed.

Scope statement (keep it in code and docs): *geometric consistency, not building-code or structural compliance.*

## Insights and brief
- **Insights**: counts; total and average area (shoelace on polygons, **not** the stored `area_px`); largest and smallest room; total, exterior and interior wall length (interior only when rooms lie on **both** sides); rooms by type; `metric` only when `mm_per_pixel` is set.
- **Brief**: rooms (label, type, wall_count), counts, `has_scale`, image size. **No coordinates and no ids.**

## Engineering
- Layout: `app/engine/{execute.py,resolve.py,semantic.py,operations/*.py,constraints.py,changes.py,summary.py}`, `app/insights.py`, `app/brief.py`.
- All operations are **pure functions** `(model, command) -> model`. Same input gives **byte-identical** JSON (assert it).
- Errors are typed (`ResolutionError`, `ClarificationNeeded`, `SemanticError`, `GeometryError`, `ConstraintViolation`), each carrying its stage.
- Shapely 2 vectorised where it helps. Budget: execute on the apartment fixture in < 50 ms.

## Tests (offline)
- Every operation: happy path, every refusal path, determinism (2 runs → identical bytes).
- MOVE_WALL: T-junction re-projection, room corners follow, door moves with the wall, along-wall refusal, collision with a parallel wall refused, crushed-room refusal.
- DELETE_WALL: merge (two_room fixture → 1 room, merged wall_ids, surviving label), exterior refusal.
- Entity resolution: every branch above, using the apartment fixture (unique, ambiguous, none, "between X and Y", orientation words).
- Semantic: mm without scale is rejected (unscaled fixture), with a clear message.
- **Property-based tests (Hypothesis)**: random valid move or resize sequences on the apartment never produce an invalid model, and either apply or are rejected cleanly.
- Insights: hand-computed numbers on the two-room fixture. Metric is null without a scale.
- API: 401, a well-formed request always returns 200 with a valid `ExecuteResult` union member.

## Done when
- [ ] All 10 operations, resolution, semantic and constraints are implemented. All four endpoints match CONTRACTS.md §6.
- [ ] Tests (including Hypothesis) are green, plus ruff and mypy.
- [ ] `services/geometry/HANDOFF.md` with a status table per operation, the clarification catalogue and known limitations.
- [ ] `/ponytail-review` + `code-review-and-quality` done.

## Tooling
`test-driven-development` (write the refusal cases first), **context7** (Shapely 2, Pydantic v2, Hypothesis), `doubt-driven-development` for edge cases, `performance-optimization`.

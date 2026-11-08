# Plan: Building intelligence features (post-P7)

## Audit (2026-11-08)

| Feature | Before this work |
|---|---|
| Wall lengths, floor area, door/window counts | Partial: `Insights` only |
| Paint, concrete, bricks, tiles, steel, Bill of Quantities | Not built |
| Code compliance and report | Not built (`constraints.py` is geometric consistency only) |
| Cost estimation | Not built |
| Blueprint chatbot | Not built (the command bar only edits) |
| Interior designer | Not built (`Furniture` exists only when detected) |
| Layout suggestions | Not built |
| Structural suggestions | Not built |

## Architecture decisions

- **Everything numeric is deterministic and lives in the geometry service** (`services/geometry/app/analysis/`). The LLM never produces a quantity, a verdict or geometry.
- **One analysis call** (`POST /v1/floorplans/{id}/analysis`) returns takeoff, compliance, cost, interior and structural together. It is pure and takes milliseconds, so no new tables and no caching.
- **All of it needs a scale.** Without `mm_per_pixel` the response is `needs_scale: true`: never treat px as mm.
- **Layout options and fix-its are ordinary engine commands.** Preview, apply, undo and redo come from the existing flow; no new persistence path.
- **`SPLIT_ROOM` is engine-only.** It joins a new `EngineCommand` union, not `Command`, so the language parser and LLM can't emit it.
- **Chatbot:** rules answer from the model; only questions the rules miss go to the LLM, with a facts sheet that has no ids or coordinates. No LLM configured means an honest "can't answer".
- **Thresholds and rates are indicative defaults in one place.** Rates are editable per request. The compliance report states it is not a certified code check.

## Tasks

### Phase 1: backend
- [x] 1. Contracts: `analysis.py`, `SplitRoom`/`EngineCommand`, schema + TS regeneration
- [x] 2. `SPLIT_ROOM` operation in the engine, with tests
- [x] 3. Shared measurement, takeoff/BOQ, cost, with tests
- [x] 4. Compliance report, with tests
- [x] 5. Interior designer, structural suggestions, with tests
- [x] 6. Chatbot rules, layout generator, with tests
- [x] 7. Geometry routes; language `/v1/questions/answer`; API routes and clients

Checkpoint: all Python suites, ruff and mypy green.

### Phase 2: web
- [x] 8. API client, mocks, fixtures
- [x] 9. Analyze tab (takeoff, cost, compliance, interior, layouts, structure) with CSV export
- [x] 10. Ask tab (chat, highlights elements on the plan)

Checkpoint: vitest, tsc, eslint, build green; browser check.

### Phase 3: close-out
- [x] 11. Docs: `CONTRACTS.md`, `FEATURE_STATUS.md`
- [x] 12. Review pass (ponytail-review, security)

## Risks

| Risk | Mitigation |
|---|---|
| Thresholds differ by jurisdiction | One table in `compliance.py`, and the report says "indicative" |
| Rates are placeholders | Editable in the UI, currency included |
| Vision misses openings or rooms | Results follow the model; the report shows element links so a user can verify |

## Decisions

- Compliance follows NBC India 2016 (indicative).
- Costs default to INR at rough India averages, editable per user.

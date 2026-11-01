# packages/contracts (`aec_contracts`)

The frozen interface between every service and the web app. Normative spec: `phases/shared/CONTRACTS.md`.
**Owned by P0, then P7. Parallel phases never edit this folder** (log gaps per CONTRACTS.md §12).

| Module | Contents |
|---|---|
| `model.py` | Building Model (`FloorPlanModel`, walls, rooms…), `polygon_area`, `CoordinateTransform` |
| `commands.py` | The 10 commands, `Command` union, `COMMAND_ADAPTER`, `OPERATIONS`, `TARGET_KIND` |
| `results.py` | `Candidate`, `ChangeSet`, `RejectStage` |
| `vision.py` / `geometry.py` / `language.py` | Inter-service DTOs |
| `public.py` | Public API DTOs used by `apps/web` |
| `errors.py` | `ErrorCode`, `HTTP_STATUS`, `ErrorEnvelope` |
| `lexicon.py` | `room_type_for_text()`, `ROOM_SYNONYMS` |

## Fixtures (`fixtures/`)
- `apartment.model.json`, `apartment.unscaled.model.json`, `two_room.model.json`: built by `build_models.py` (layout drawn in its docstring). Room edges are exactly their walls; openings sit on their walls (tested).
- `synthetic_plan.py`: `make_apartment_plan()` / `make_two_room_plan()` draw those models as deterministic PNGs. CLI: `py -m uv run python fixtures/synthetic_plan.py <out_dir>`.
- `commands.examples.json`: 50 instruction → expected command cases.
- `api/*.json`: one example per public endpoint, built by `build_api_examples.py`.

Usage from a service test: `sys.path.insert(0, "<repo>/packages/contracts/fixtures"); import synthetic_plan`.

## Commands
```powershell
py -m uv sync; py -m uv run pytest; py -m uv run ruff check .; py -m uv run mypy src
py -m uv run python fixtures/build_models.py; py -m uv run python fixtures/build_api_examples.py   # regenerate fixtures
py -m uv run python scripts/export_schema.py      # JSON Schema → schema/
cd ../../apps/web; npm run gen:contracts          # TS types + mock fixtures
```

# HANDOFF: services/vision (P1)

## Status
| Stage | Status | Notes |
|---|---|---|
| 1 `preprocess` (decode PNG/JPG/PDF p1, limits, denoise, CLAHE, adaptive threshold, deskew) | TESTED | Bad input → 415/422 envelope before the pipeline starts |
| 2 `wall_detection` (thickness, structural mask, axis + Hough diagonals, straighten, merge, bridge, snap) | TESTED | |
| 3 `ocr` (`auto` / `stub` / `tesseract`) | TESTED | Real Tesseract 5.5 checked in the Docker image (skipped locally without the binary) |
| 4 `object_detection` (`heuristic` / `none` / `yolo`) | TESTED (heuristic, none) · IMPLEMENTED (yolo, untested, `# pragma: no cover`) | |
| 5 `room_detection` | TESTED | |
| 6 `calibration` | TESTED | Never assumes a default scale |
| 7 `semantic_assembly` (+ wall↔room linking) | TESTED | Validated by `FloorPlanModel` |
| 8 `artifacts` | TESTED | Overlay is best-effort |
| `POST /v1/analyze`, `/readyz` (503 if `OCR_PROVIDER=tesseract` and the binary is missing) | TESTED | |
| Docker image (with `tesseract-ocr-eng`) + compose fragment healthy | TESTED | Built and run locally on 2026-11-01; HTTP round trip with real OCR passed |

Nothing is VERIFIED: no human has run it on real-world plans yet.

## How to run
See `README.md`. Gates: `py -m uv run pytest; py -m uv run ruff check .; py -m uv run ruff format --check .; py -m uv run mypy app`.
`run_pipeline(bytes, content_type, floorplan_id, options, settings)` in `app/pipeline/runner.py` works without HTTP.

## Accuracy on the synthetic fixtures
- **Two-room** (1000×600): 5 walls (T-junction pieces merge into one wall per line), all axis-exact, thickness 21 px (±1 of the drawn 20), partition 11 px. Rooms: 2, corners within 3 px of the centre-line corners. Doors and windows added to the plan are bridged into one wall each, plus one opening, and the window is classified as a window.
- **Apartment** (1600×1200): 10 walls (the fixture's 17 are collinear pieces split at junctions; ours merge them, except where thickness changes: 20 px vs 10 px at y=700). 4 doors with correct swing handedness, 3 windows, 1 stair (±3 px), 0 columns, 5 rooms. With real Tesseract: all 5 labels read and typed (LIVING_ROOM, KITCHEN, BEDROOM, HALLWAY, BATHROOM), "3600" read, `mm_per_pixel = 10.0` (fixture: 10.0), confidence 0.45 (one dimension).
- **The fixture's column** (588,538 24×24) is drawn as part of the wall junction, so it's indistinguishable from the wall and isn't detected. Free-standing columns are detected (tested).
- **Timing** (laptop CPU): apartment ≈2.3 s end to end with Tesseract, budget 6 s. Dense 19×19-room plan with 684 doors: <5 s.
- **Determinism:** two runs give byte-identical model JSON, artifacts and stage details. Ids are `uuid5(floorplan_id, "<kind>:<index>")` after a (y, x) sort. The model id itself is `uuid5(floorplan_id, "model:0")`.

## Contract change requests
None. The contract covered everything.

## Requests to other phases
- **P3 / P6: coordinate space.** Model coordinates are pixels of the *preprocessed* image (downscaled so the longest edge ≤ `min(IMAGE_MAX_DIMENSION, options.max_dimension)`, and rotated onto a larger canvas when deskewed ≥0.3°, see the `preprocess` stage's `deskew_deg` detail). `coordinate_system.image_width/height` describe that image. Use the **`preprocessed` artifact** as the viewer backdrop, not the original upload, or the overlay drifts on large or skewed scans.
- **P3: model id.** `FloorPlanModel.id` is deterministic per floorplan, so re-analysis returns the same id. Rely on `building_models.id` / `version` for uniqueness, not on `data.id`.
- **P3: upload limits.** Vision re-checks size (`MAX_UPLOAD_BYTES`, 413), magic bytes (415) and pixel count (`MAX_IMAGE_PIXELS`, 422). A `FAILED` analysis returns 200 with `status="FAILED"`, per CONTRACTS §5.
- **P3: room labels.** Labels the lexicon can't type stay `UNKNOWN` (`room_type_source=null`). Classifying them with the language service is up to the API.

## Known limitations
- Only solid / thick-stroke walls (≥3 px). Hairline double-line walls, curved walls and noisy scans are unsupported. They produce no walls and the stage reports `degraded` with a warning, not a failure.
- Diagonal walls are found (confidence 0.45) but only as straight segments.
- Rooms below 0.3 % of the image area are dropped (spec), so very small closets on large sheets vanish.
- Gaps wider than 14 % of the longest side aren't bridged (spec), so very wide openings split the wall instead.
- Columns fused into wall junctions are not detected.
- Door swings: quarter-circle arcs only. Double and sliding doors come out as plain doors.
- PDF: page 1 only (warning names the page count). No render timeout on hostile vector-heavy PDFs.
- YOLO path maps COCO classes to furniture only (`shortcut:` comment in `objects.py`). `ultralytics` is not a dependency.

## Review
`/ponytail-review` run. Findings fixed: gap bridging was O(n³) (125 s → <5 s on a 684-door plan, regression test added), detector cached (YOLO weights no longer reload per request), coordinate-space note above.

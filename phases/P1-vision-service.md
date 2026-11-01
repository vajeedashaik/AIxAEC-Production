# P1: Vision Service (floor plan → Building Model)

> Parallel phase. Worktree `phase/p1-vision`. **Write only inside `services/vision/**`.**

## Read first
`CLAUDE.md` · `phases/shared/{ARCHITECTURE,CONTRACTS,OWNERSHIP,TOOLING}.md` · `FULL_PROJECT_CONTEXT.md` §6–§7 (your algorithmic spec) · `services/vision/README.md` (P0 stub).

## Mission
Build a **stateless FastAPI service** that turns a floor-plan image or PDF into a valid `FloorPlanModel` through an **8-stage, gracefully degrading pipeline**. It returns stage reports and debug artifacts exactly as described in CONTRACTS.md §5. You never touch a database or storage. The API sends bytes, and you return JSON.

## Endpoint
`POST /v1/analyze` (multipart `file`, `floorplan_id`, optional `options`) → `AnalyzeResult`. Protected by `X-Internal-Token`. CPU-bound work runs in a threadpool (`def` route or `run_in_threadpool`). Never block the event loop.

## Pipeline (each stage wrapped by `run_stage`)
`run_stage(name, fn, critical)` records `{name, status ok|degraded|failed|skipped, duration_ms, error, detail}`.
- Non-critical failure → `degraded`, and the pipeline continues with a safe default.
- Critical failure (`preprocess`, `wall_detection`, `semantic_assembly`) → remaining stages `skipped`, `status=FAILED`, `error="Processing failed at stage '<name>'."`
- Never leak exception text that contains paths or internals. Log the full error with the request ID instead.

| # | Stage | Spec |
|---|---|---|
| 1 | `preprocess` | Decode: PNG/JPG via OpenCV, **PDF page 1** via PyMuPDF, rasterised directly at working resolution (DPI capped by the pixel budget). Add a warning `"Only page 1 of N was processed."` when N > 1. Reject encrypted, zero-page or absurd page size (>14 400 pt) input. Pixel cap `MAX_IMAGE_PIXELS`. Then downscale so the longest edge ≤ `IMAGE_MAX_DIMENSION`, grayscale, `fastNlMeansDenoising`, CLAHE, Gaussian adaptive threshold (inverted, ink = 255), median blur, and **deskew** (median Hough-line angle, applied if \|angle\| ≥ 0.3°). |
| 2 | `wall_detection` | Thickness-aware morphology + Hough hybrid (FULL_PROJECT_CONTEXT §7 "Wall detector"). Steps: estimate the wall thickness via a distance-transform ridge histogram, take a structural mask (open ≈0.45×thickness, then close) that removes text, hatching, dimension lines, furniture, stair treads and swings, extract axis walls as least-squares centre-lines per connected body, run probabilistic Hough on the residual for diagonals (confidence 0.45), then straighten (≤3° → exact axis), merge collinear overlaps, **bridge gaps** (≤14 % of the longest side → one continuous wall plus an emitted opening), **snap junctions** (endpoints onto the centre-line they meet) and drop short segments. Classify each gap: ≥2 thin parallel lines in the band → `window`, else `door`. |
| 3 | `ocr` | `OCRService` interface: `auto` (Tesseract if on PATH, else stub), `stub`, `tesseract`. Returns word boxes with confidence. |
| 4 | `object_detection` | `ObjectDetector` interface: `heuristic` (default), `none`, `yolo` (optional, lazy import of `ultralytics`, `# pragma: no cover`). Heuristic: **door swings** (Hough circles on thin ink, validated so ink fills exactly one quadrant, hinge on a wall), **columns** (compact solid squares from wall width up to 4×), **stairs** (≥4 evenly spaced parallel thin lines). `reconcile_openings` drops swings with no hinge on a wall and duplicates of gap openings. |
| 5 | `room_detection` | Rasterise walls (stroke = median thickness), close, invert, flood the exterior from border seeds, take 4-connected enclosed components between 0.3 % and 90 % of the image, dilate by half a stroke so edges land on **centre-lines**, `approxPolyDP`, **snap vertices to wall joints** (endpoints + pairwise centre-line intersections), drop collinear vertices. Label = OCR words without digits whose centres fall inside, joined in reading order. |
| 6 | `calibration` | For each OCR word parsed as a dimension (`parse_dimension`: `"3600"` (100–100 000 → mm), `"3.6 m"`, `"360 cm"`, `"3600 mm"`, `12'-6"`, `12ft 6in`), find the nearest wall within 120 px and take ratio = value_mm / wall_px, accepted if 0.05–500 mm/px. Use the **median** across matches, confidence `min(0.8, 0.3 + 0.15·n)`, source `DIMENSION_OCR`. No match → `mm_per_pixel = None`, `UNKNOWN`. **Never assume a default scale.** |
| 7 | `semantic_assembly` | Build the model: clamp walls to the image, normalise objects into Door/Window/Column/Stair/Furniture (bind each opening to the nearest wall within 40 px, axis-aligned bbox with wall thickness), type rooms with `aec_contracts.lexicon.room_type_for_text` (unknown labels stay `UNKNOWN`; P3 may ask the language service later), turn OCR dimensions into `Dimension`, build the `CoordinateSystem`, then **link walls to rooms**: a wall joins a room when ≥ max(20 px, 10 % of the wall's length) lies within 12 px of the room boundary (sampled), keeping ids deduped. Compute `area_px` (shoelace). Validate with `FloorPlanModel`. |
| 8 | `artifacts` | `preprocessed` (PNG), `walls_overlay` (PNG: original plus coloured walls, openings and room outlines; best-effort), `detected_elements` (JSON: raw detections), `semantic_model` (JSON), all base64 in the response. Keep the PNGs small (optimised, ≤ ~2 MB). |

## Quality and engineering
- Module layout: `app/pipeline/{runner.py,stages.py}`, `app/vision/{decode.py,preprocess.py,strokes.py,walls.py,rooms.py,objects.py,calibrate.py,assemble.py,overlay.py}`, `app/ocr/{base.py,stub.py,tesseract.py,parsing.py,factory.py}`.
- Pure functions wherever possible (array in, dataclasses out). `run_pipeline(bytes, content_type, floorplan_id, options) -> AnalyzeResult` must be callable without HTTP.
- **Determinism:** the same input gives the same output. Sort elements spatially (y, then x) before assigning UUIDs, and derive UUIDs with `uuid5(floorplan_id, f"{kind}:{index}")` so re-analysis is stable.
- Performance budget: the synthetic apartment (≈1600×1200) runs in < 6 s on a laptop CPU. Log per-stage `duration_ms`.
- Limits to document honestly: hairline double-line walls, curved walls and noisy scans are unsupported.

## Tests (pytest, offline, using `packages/contracts/fixtures/synthetic_plan.py`)
- Decode: PNG, JPG, single- and multi-page PDF (warning), encrypted PDF, decompression bomb, corrupt bytes → 415/422 with the error envelope.
- Preprocess: a deskewed rotated plan gets an angle within ±0.3°.
- Walls: two-room plan → correct count, axis alignment, thickness estimate within ±1 px, door gap bridged into one wall plus one opening, window classified as window.
- Rooms: two-room → 2 polygons whose vertices are within 3 px of the expected centre-line corners. Apartment → 5 rooms with correct labels.
- Calibration: the `"3600"` dimension gives the expected mm/px within 5 %. No dimensions → `None`.
- Objects: the swing is detected and reconciled, stairs are detected, hatching yields no walls.
- Pipeline: a non-critical failure (monkeypatched OCR raising) → `degraded` + `COMPLETED`. A critical failure → `FAILED`, later stages `skipped`, safe message.
- Contract: the response validates as `AnalyzeResult`, the model passes `FloorPlanModel` validation, and two runs give identical JSON (determinism).
- API: 401 without the token, multipart validation, size limit.
- Tesseract-dependent tests are skipped with a clear reason when the binary is absent. CI image has it.

## Done when
- [ ] All 8 stages are implemented with graceful degradation, and `POST /v1/analyze` matches CONTRACTS.md §5.
- [ ] `uv run pytest`, `ruff check`, `ruff format --check` and `mypy app` are green (scoped to `services/vision`).
- [ ] The Docker image builds with Tesseract and the compose fragment is healthy.
- [ ] `services/vision/HANDOFF.md`: status per stage, accuracy notes with the synthetic results, limitations, contract requests.
- [ ] `/ponytail-review` and the `code-review-and-quality` skill have been run, with findings addressed.

## Tooling
`spec-driven-development`, `test-driven-development`, **context7** (OpenCV 4.10+, PyMuPDF, Pillow, pytesseract, FastAPI), `performance-optimization` for the budget, `debugging-and-error-recovery`. Use `find-skills` for computer-vision helper skills if useful (install **user-level only**).

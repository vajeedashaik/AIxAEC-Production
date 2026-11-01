# services/vision (Vision, :8001)

Stateless 8-stage CV pipeline: image/PDF → FloorPlanModel + stage reports + artifacts.

Owned by **P1** (see `phases/shared/OWNERSHIP.md`). Contracts: `phases/shared/CONTRACTS.md` §5. Status and accuracy: `HANDOFF.md`.

## Pipeline
`app/pipeline/runner.py::run_pipeline` runs each stage through `run_stage`. A non-critical failure → `degraded` and the pipeline continues. A failure in `preprocess`, `wall_detection` or `semantic_assembly` → `FAILED`, later stages `skipped`. Exception text only goes to the log.

| Stage | Code |
|---|---|
| preprocess | `app/vision/decode.py`, `preprocess.py` |
| wall_detection | `app/vision/strokes.py`, `walls.py` |
| ocr | `app/ocr/` (`OCR_PROVIDER=auto` uses Tesseract if installed, else a stub) |
| object_detection | `app/vision/objects.py` (`OBJECT_DETECTOR=heuristic|none|yolo`) |
| room_detection | `app/vision/rooms.py` |
| calibration | `app/vision/calibrate.py`, `app/ocr/parsing.py` |
| semantic_assembly | `app/vision/assemble.py` |
| artifacts | `app/vision/overlay.py` |

Model coordinates are pixels of the **preprocessed** image (the `preprocessed` artifact), not the original upload.

## Run
```powershell
cd services/vision
py -m uv sync
copy .env.example .env
py -m uv run uvicorn app.main:app --reload --port 8001
```

Every `/v1` route needs `X-Internal-Token: <INTERNAL_SERVICE_TOKEN>` (401 otherwise).
Without Tesseract on PATH, OCR degrades to the stub: no room labels, no scale, plus a warning.

## Test
```powershell
py -m uv run pytest
py -m uv run ruff check .
py -m uv run ruff format --check .
py -m uv run mypy app
```
The real-Tesseract test is skipped when the binary is missing. It runs in the Docker image.

## Docker
Build context is the repo root (the image copies `packages/contracts`):
`docker build -f services/vision/Dockerfile .` or `docker compose up vision` from the root. The image includes Tesseract.

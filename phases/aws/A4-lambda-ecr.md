# A4: Vision on Lambda (image in ECR)

**Switch:** `VISION_MODE=lambda` (default `http`). Needs `AWS_REGION`, `S3_BUCKET`, `VISION_LAMBDA_NAME`.

**Goal:** the worker runs the vision pipeline on Lambda, passing S3 keys because synchronous Lambda payloads are capped at about 6 MB and uploads can reach 25 MB.

**Files**
- New `services/vision/app/lambda_handler.py`: read the source from S3, call `run_pipeline` directly, write the `AnalyzeResult` JSON to S3, return `{"result_key": ...}`.
- New `services/vision/Dockerfile.lambda`: built from the repo root on the AWS Lambda Python 3.12 base image.
- New `services/api/app/aws/lambda_vision.py`: `LambdaVisionClient.analyze(floorplan_id, data, filename, content_type)`, same signature as `VisionClient`.
- Edit `app/ports.py` (`VisionAnalyzer` protocol) and `app/container.py`.

**Requirements**
- Handoff keys go under `tmp/<floorplan_id>/<random>/`. The client deletes them in a `finally`. The bucket's 1-day lifecycle rule is the backstop.
- The Lambda client must have **automatic retries off** and a read timeout longer than the function timeout, or a slow job would be run twice.
- Undecodable input (`ServiceError` in the handler) returns `{"error": message}`. The client raises a 502 `ServiceError`, matching how `VisionClient` treats a 4xx from the HTTP service, so the job ends `FAILED`.
- `FunctionError`, botocore errors and an invalid result JSON all become that same 502. Never log file contents.
- No changes to `aec_contracts`, or to `jobs.py`.

**Tests:** handler with moto S3 (happy path, undecodable file returns `error`). Client against moto S3 and a fake Lambda (result parsed, temp keys removed on success and failure, `FunctionError` → `ServiceError`, handler `error` → `ServiceError`).

**Check when Docker is available:** build the image and run it with the Lambda Runtime Interface Emulator. On AWS, confirm the memory limit and cold-start time.

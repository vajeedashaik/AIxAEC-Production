# A3: Textract OCR

**Switch:** `OCR_PROVIDER=textract` (existing setting, new value).

**Goal:** the vision pipeline reads labels through Textract behind `OCRService`.

**Files**
- New `services/vision/app/ocr/textract.py`: `TextractOCR` with `name = "textract"`.
- Edit `app/ocr/factory.py` and the `ocr_provider` literal in `app/config.py`.

**Requirements**
- Encode the grayscale image as PNG and call `DetectDocumentText` with bytes. If the PNG exceeds the API's byte limit (check the botocore model), re-encode as JPEG.
- Use only `WORD` blocks. Convert relative boxes to pixels with the image's width and height, and confidence from 0–100 to 0–1. Coordinates stay in image pixels and are never treated as mm.
- Don't catch errors: `run_stage` already turns an exception into a degraded OCR stage with a generic message.
- `/readyz` calls `get_ocr(...).name`, so constructing the provider must be cheap and need no network.

**Tests (Stubber):** words and pixel boxes are correct, `LINE` blocks are ignored, an empty result gives `[]`, oversized PNG falls back to JPEG, the factory returns the provider.

**Check on real AWS (A10):** compare label quality against Tesseract on the fixture plans.

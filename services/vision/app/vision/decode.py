"""Bytes → grayscale array. Bad input raises ServiceError (415/422), never a pipeline failure."""

import io
import math
from dataclasses import dataclass

import cv2
import numpy as np
import pymupdf
from aec_contracts import ErrorCode
from numpy.typing import NDArray
from PIL import Image

from app.errors import ServiceError

Gray = NDArray[np.uint8]

PDF_MAX_DPI = 300
PDF_MAX_PAGE_PT = 14_400
MAGIC = {
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
    "image/jpg": b"\xff\xd8\xff",
    "application/pdf": b"%PDF-",
}


@dataclass(frozen=True)
class Decoded:
    image: Gray
    page_count: int = 1


def _invalid(message: str) -> ServiceError:
    return ServiceError(422, ErrorCode.VALIDATION_ERROR, message)


def _flatten(img: NDArray[np.generic]) -> Gray:
    """Any OpenCV decode result → 8-bit gray; transparent pixels become paper, not black."""
    arr = np.asarray(img)
    if arr.dtype != np.uint8:
        arr = (arr / 257).astype(np.uint8)
    if arr.ndim == 2:
        return arr
    if arr.shape[2] == 4:
        alpha = arr[:, :, 3:4].astype(np.float32) / 255
        bgr = (arr[:, :, :3] * alpha + 255 * (1 - alpha)).astype(np.uint8)
        return np.asarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), dtype=np.uint8)
    return np.asarray(cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY), dtype=np.uint8)


def _decode_raster(data: bytes, max_pixels: int) -> Decoded:
    # Read the header first: the pixel cap has to hold before anything is decompressed.
    try:
        with Image.open(io.BytesIO(data)) as im:
            width, height = im.size
            im.verify()
    except Image.DecompressionBombError as exc:
        raise _invalid("Image exceeds the pixel limit.") from exc
    except Exception as exc:
        raise _invalid("The file is corrupt or could not be decoded.") from exc
    if width * height > max_pixels:
        raise _invalid("Image exceeds the pixel limit.")
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise _invalid("The file is corrupt or could not be decoded.")
    return Decoded(_flatten(img))


def _decode_pdf(data: bytes, max_dimension: int, max_pixels: int) -> Decoded:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")  # type: ignore[no-untyped-call]
    except Exception as exc:
        raise _invalid("The file is corrupt or could not be decoded.") from exc
    with doc:
        if doc.needs_pass:
            raise _invalid("Encrypted PDFs are not supported.")
        if doc.page_count < 1:
            raise _invalid("The PDF has no pages.")
        try:
            page = doc[0]
            w_pt, h_pt = float(page.rect.width), float(page.rect.height)
            if not (0 < w_pt <= PDF_MAX_PAGE_PT and 0 < h_pt <= PDF_MAX_PAGE_PT):
                raise _invalid("The PDF page size is out of range.")
            # Rasterise straight at working resolution so we never allocate past the pixel budget.
            scale = min(PDF_MAX_DPI / 72, max_dimension / max(w_pt, h_pt), math.sqrt(max_pixels / (w_pt * h_pt)))
            matrix = pymupdf.Matrix(scale, scale)  # type: ignore[no-untyped-call]
            pix = page.get_pixmap(matrix=matrix, colorspace=pymupdf.csGRAY, alpha=False)
            img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.stride)[:, : pix.width].copy()
        except ServiceError:
            raise
        except Exception as exc:
            raise _invalid("The file is corrupt or could not be decoded.") from exc
        return Decoded(img, doc.page_count)


def decode_image(data: bytes, content_type: str | None, *, max_dimension: int, max_pixels: int) -> Decoded:
    magic = MAGIC.get((content_type or "").split(";")[0].strip().lower())
    if magic is None or not data.startswith(magic):
        raise ServiceError(415, ErrorCode.UNSUPPORTED_MEDIA_TYPE, "Upload a PNG, JPG or PDF file.")
    if magic == MAGIC["application/pdf"]:
        return _decode_pdf(data, max_dimension, max_pixels)
    return _decode_raster(data, max_pixels)

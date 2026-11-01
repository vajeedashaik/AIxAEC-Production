"""Upload validation. Everything here is untrusted input."""

import hashlib
import io
import re
import threading
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import BinaryIO

import pymupdf
from aec_contracts import ErrorCode
from PIL import Image, UnidentifiedImageError

from .errors import ServiceError

CHUNK_BYTES = 1024 * 1024
MAX_PDF_PAGE_POINTS = 14_400
# extension → (canonical MIME, accepted declared MIMEs, magic prefix)
TYPES: dict[str, tuple[str, frozenset[str], bytes]] = {
    "png": ("image/png", frozenset({"image/png"}), b"\x89PNG\r\n\x1a\n"),
    "jpg": ("image/jpeg", frozenset({"image/jpeg", "image/jpg"}), b"\xff\xd8\xff"),
    "jpeg": ("image/jpeg", frozenset({"image/jpeg", "image/jpg"}), b"\xff\xd8\xff"),
    "pdf": ("application/pdf", frozenset({"application/pdf"}), b"%PDF-"),
}
_PDF_LOCK = threading.Lock()  # PyMuPDF is not thread-safe and routes run in a threadpool
pymupdf.TOOLS.mupdf_display_errors(False)


@dataclass(frozen=True)
class ValidatedUpload:
    data: bytes
    sha256: str
    extension: str
    content_type: str
    filename: str
    warnings: list[str]


def _unsupported(message: str) -> ServiceError:
    return ServiceError(415, ErrorCode.UNSUPPORTED_MEDIA_TYPE, message)


def _invalid(message: str) -> ServiceError:
    return ServiceError(422, ErrorCode.VALIDATION_ERROR, message)


def _too_large(message: str) -> ServiceError:
    return ServiceError(413, ErrorCode.PAYLOAD_TOO_LARGE, message)


def read_capped(stream: BinaryIO, limit: int) -> bytes:
    """Stops reading as soon as the limit is passed."""
    chunks, total = [], 0
    while chunk := stream.read(CHUNK_BYTES):
        total += len(chunk)
        if total > limit:
            raise _too_large(f"The file is larger than the {limit // (1024 * 1024)} MB limit.")
        chunks.append(chunk)
    return b"".join(chunks)


def sanitize_filename(name: str | None, extension: str) -> str:
    """For display only. Storage keys are always server-generated."""
    base = PurePosixPath((name or "").replace("\\", "/")).name
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip()[-255:]
    return base or f"upload.{extension}"


def _probe_image(data: bytes, extension: str, max_pixels: int) -> None:
    expected = "PNG" if extension == "png" else "JPEG"
    try:
        with Image.open(io.BytesIO(data), formats=[expected]) as image:  # reads the header only, nothing is decoded
            width, height = image.size
            if width * height > max_pixels:
                raise _too_large("The image has too many pixels.")
            image.verify()
    except Image.DecompressionBombError as exc:
        raise _too_large("The image has too many pixels.") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise _invalid("The image is corrupt or cannot be read.") from exc


def _probe_pdf(data: bytes) -> list[str]:
    with _PDF_LOCK:
        try:
            with pymupdf.open(stream=data, filetype="pdf") as doc:
                if doc.needs_pass or doc.is_encrypted:
                    raise _invalid("Password-protected PDFs are not supported.")
                pages = doc.page_count
                if pages == 0:
                    raise _invalid("The PDF has no pages.")
                rect = doc[0].rect
                if max(rect.width, rect.height) > MAX_PDF_PAGE_POINTS:
                    raise _too_large("The PDF page is too large.")
        except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
            raise _invalid("The PDF is corrupt or cannot be read.") from exc
    return [f"Only page 1 of {pages} will be processed."] if pages > 1 else []


def validate_upload(stream: BinaryIO, filename: str | None, declared_type: str | None,
                    max_bytes: int, max_pixels: int) -> ValidatedUpload:
    extension = PurePosixPath((filename or "").replace("\\", "/")).suffix.lstrip(".").lower()
    if extension not in TYPES:
        raise _unsupported("Upload a PNG, JPG or PDF file.")
    canonical, declared, magic = TYPES[extension]
    if (declared_type or "").split(";")[0].strip().lower() not in declared:
        raise _unsupported("The file type does not match the file extension.")
    data = read_capped(stream, max_bytes)
    if not data:
        raise _invalid("The file is empty.")
    if not data.startswith(magic):
        raise _unsupported("The file contents do not match its type.")
    warnings: list[str] = []
    if extension == "pdf":
        warnings = _probe_pdf(data)
    else:
        _probe_image(data, extension, max_pixels)
    return ValidatedUpload(data, hashlib.sha256(data).hexdigest(), extension, canonical,
                           sanitize_filename(filename, extension), warnings)

import io
import struct
import zlib

import cv2
import numpy as np
import pymupdf
import pytest

from app.errors import ServiceError
from app.vision.decode import decode_image
from app.vision.preprocess import measure_skew, preprocess

from .conftest import pre_and_walls, sp

LIMITS = {"max_dimension": 2400, "max_pixels": 64_000_000}


def png_bytes() -> bytes:
    return sp.to_png(sp.make_two_room_plan())


def pdf_bytes(pages: int = 1, encrypt: bool = False, width: float = 500, height: float = 300) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page(width=width, height=height)
        page.insert_image(pymupdf.Rect(0, 0, width, height), stream=png_bytes())
    kwargs = {"encryption": pymupdf.PDF_ENCRYPT_AES_256, "user_pw": "secret", "owner_pw": "owner"} if encrypt else {}
    out = io.BytesIO()
    doc.save(out, **kwargs)
    return out.getvalue()


def forged_png_header(width: int, height: int) -> bytes:
    """A PNG that claims huge dimensions: must be rejected before any pixel is decompressed."""

    def chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\0" * 16)) + chunk(b"IEND", b"")


def test_decodes_png_and_jpg() -> None:
    png = decode_image(png_bytes(), "image/png", **LIMITS)
    assert png.image.shape == (600, 1000)
    ok, jpg = cv2.imencode(".jpg", sp.make_two_room_plan())
    assert ok
    assert decode_image(jpg.tobytes(), "image/jpeg", **LIMITS).image.shape == (600, 1000)


def test_transparent_png_background_is_paper_not_black() -> None:
    bgra = np.zeros((50, 50, 4), np.uint8)  # fully transparent black, as CAD exports write it
    ok, buf = cv2.imencode(".png", bgra)
    assert ok
    assert decode_image(buf.tobytes(), "image/png", **LIMITS).image.min() == 255


def test_pdf_rasterises_page_one_within_budget() -> None:
    decoded = decode_image(pdf_bytes(pages=3), "application/pdf", max_dimension=800, max_pixels=64_000_000)
    assert decoded.page_count == 3
    assert max(decoded.image.shape) <= 800
    # Ink made it through: the plan is on the page, not a blank raster.
    assert decoded.image.min() < 50


def test_pdf_pixel_budget_caps_the_raster() -> None:
    decoded = decode_image(pdf_bytes(), "application/pdf", max_dimension=10_000, max_pixels=10_000)
    assert decoded.image.size <= 10_000 * 1.05


@pytest.mark.parametrize(
    "data,content_type,status",
    [
        (b"plain text", "text/plain", 415),
        (b"plain text", "image/png", 415),  # header lies about the type
        (b"\x89PNG\r\n\x1a\n", "application/pdf", 415),
        (b"\x89PNG\r\n\x1a\nnot really a png", "image/png", 422),
        (b"\xff\xd8\xff\xe0not really a jpg", "image/jpeg", 422),
        (b"%PDF-1.7 not really a pdf", "application/pdf", 422),
    ],
)
def test_bad_bytes_are_rejected(data: bytes, content_type: str, status: int) -> None:
    with pytest.raises(ServiceError) as err:
        decode_image(data, content_type, **LIMITS)
    assert err.value.status == status


def test_encrypted_pdf_rejected() -> None:
    with pytest.raises(ServiceError) as err:
        decode_image(pdf_bytes(encrypt=True), "application/pdf", **LIMITS)
    assert err.value.status == 422
    assert "Encrypted" in str(err.value.message)


def test_absurd_pdf_page_rejected() -> None:
    with pytest.raises(ServiceError) as err:
        decode_image(pdf_bytes(width=14_401), "application/pdf", **LIMITS)
    assert err.value.status == 422


def test_decompression_bomb_rejected_before_decoding() -> None:
    with pytest.raises(ServiceError) as err:
        decode_image(forged_png_header(30_000, 30_000), "image/png", **LIMITS)
    assert err.value.status == 422
    assert "pixel limit" in str(err.value.message)


def test_downscales_to_max_dimension() -> None:
    assert max(preprocess(sp.make_apartment_plan(), 800).gray.shape) == 800


def rotated(image: np.ndarray, degrees: float) -> np.ndarray:
    h, w = image.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), degrees, 1.0)
    return np.asarray(cv2.warpAffine(image, m, (w, h), flags=cv2.INTER_LINEAR, borderValue=255), np.uint8)


@pytest.mark.parametrize("degrees", [2.0, -3.5])
def test_deskew_recovers_rotation(degrees: float) -> None:
    pre = preprocess(rotated(sp.make_two_room_plan(), degrees), 2400)
    assert abs(abs(pre.deskew_deg) - abs(degrees)) <= 0.3
    assert abs(measure_skew(pre.binary)) <= 0.3


def test_deskewed_plan_still_yields_exact_walls() -> None:
    _, detection = pre_and_walls(rotated(sp.make_two_room_plan(), 2.0))
    assert len(detection.walls) == 5
    assert all(w.is_horizontal or w.is_vertical for w in detection.walls)


def test_small_skew_is_left_alone() -> None:
    assert preprocess(sp.make_two_room_plan(), 2400).deskew_deg == 0.0

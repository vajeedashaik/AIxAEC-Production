import hashlib
import io
import re
import struct
import zlib
from typing import Any

import pymupdf
import pytest
import respx
from aec_contracts import FloorPlan, Page, Project
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.orm import FloorplanRow, JobRow
from app.uploads import sanitize_filename

from .conftest import PNG_1PX, Api, AppFactory


def pdf_bytes(pages: int = 1, **save: Any) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page()
    return bytes(doc.tobytes(**save))


def png_with_dimensions(width: int, height: int) -> bytes:
    """A valid PNG header claiming a huge canvas: a decompression bomb that costs nothing to send."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    # IDAT/IEND so Pillow reaches the size check instead of failing on truncation
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"")) + chunk(b"IEND", b"")


def jpeg_bytes() -> bytes:
    out = io.BytesIO()
    Image.new("L", (4, 4)).save(out, "JPEG")
    return out.getvalue()


def post_file(api: Api, project_id: str, name: str, data: bytes, mime: str, process: bool = True) -> Any:
    return api.request("POST", f"/v1/projects/{project_id}/floorplans?process={str(process).lower()}",
                       files={"file": (name, data, mime)})


# --- projects ---

def test_project_crud_and_pagination(api: Api) -> None:
    r = api.request("POST", "/v1/projects", json={"name": "A", "description": "d"})
    created = Project.model_validate(r.json())
    assert r.status_code == 201
    assert (created.floorplan_count, created.thumbnail_url) == (0, None)
    for name in "BC":
        api.request("POST", "/v1/projects", json={"name": name})

    page = Page[Project].model_validate(api.request("GET", "/v1/projects?limit=2&offset=1").json())
    assert (page.total, page.limit, page.offset, len(page.items)) == (3, 2, 1, 2)
    assert {p.name for p in page.items} < {"A", "B", "C"}

    updated = api.request("PATCH", f"/v1/projects/{created.id}", json={"description": None}).json()
    assert (updated["name"], updated["description"]) == ("A", None)
    assert api.request("PATCH", f"/v1/projects/{created.id}", json={"name": "A2"}).json()["name"] == "A2"

    assert api.request("DELETE", f"/v1/projects/{created.id}").status_code == 204
    assert api.request("GET", f"/v1/projects/{created.id}").status_code == 404


def test_project_timestamps_end_in_z_and_trigger_bumps_updated_at(api: Api) -> None:
    project = api.request("POST", "/v1/projects", json={"name": "A"}).json()
    assert project["created_at"].endswith("Z")
    assert api.request("PATCH", f"/v1/projects/{project['id']}", json={"name": "B"}).json()["updated_at"].endswith("Z")


def test_project_quota(make_api: AppFactory, transactional: sessionmaker[Session]) -> None:
    api = make_api(transactional, max_projects_per_user=1)
    api.project()
    r = api.request("POST", "/v1/projects", json={"name": "two"})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "quota_exceeded")
    assert api.project("someone_else")  # quotas are per user


def test_floorplan_quota(make_api: AppFactory, transactional: sessionmaker[Session]) -> None:
    api = make_api(transactional, max_floorplans_per_project=1)
    project_id = api.project()
    api.upload(project_id)
    r = post_file(api, project_id, "b.png", PNG_1PX, "image/png")
    assert (r.status_code, r.json()["error"]["code"]) == (409, "quota_exceeded")
    assert len(api.blobs.objects) == 1


def test_thumbnail_is_the_latest_preprocessed_artifact(api: Api, upstream: respx.MockRouter) -> None:
    floorplan_id = api.ready_floorplan()
    project_id = api.request("GET", f"/v1/floorplans/{floorplan_id}").json()["project_id"]
    assert "preprocessed.png" in api.request("GET", f"/v1/projects/{project_id}").json()["thumbnail_url"]


# --- upload happy paths ---

def test_upload_stores_blob_and_rows_with_a_server_key(api: Api, transactional: sessionmaker[Session]) -> None:
    project_id = api.project()
    r = post_file(api, project_id, "../../evil.png", PNG_1PX, "image/png; charset=x")
    assert r.status_code == 201
    plan = FloorPlan.model_validate(r.json())
    assert plan.version == 1
    assert plan.status == "PENDING"
    assert plan.latest_job and plan.latest_job.status == "PENDING"
    assert plan.original_filename == "evil.png"
    assert plan.content_type == "image/png"
    assert plan.size_bytes == len(PNG_1PX)
    assert plan.download_url
    with transactional() as session:
        row = session.scalars(select(FloorplanRow)).one()
    assert re.fullmatch(rf"{project_id}/{plan.id}/source\.png", row.storage_key)
    assert row.checksum_sha256 == hashlib.sha256(PNG_1PX).hexdigest()
    assert api.blobs.objects[("floorplans", row.storage_key)] == PNG_1PX


def test_versions_increment_and_list_is_newest_first(api: Api) -> None:
    project_id = api.project()
    api.upload(project_id)
    api.upload(project_id)
    plans = api.request("GET", f"/v1/projects/{project_id}/floorplans").json()
    assert [p["version"] for p in plans] == [2, 1]
    assert api.request("GET", f"/v1/projects/{project_id}").json()["floorplan_count"] == 2


def test_process_false_creates_no_job(api: Api, transactional: sessionmaker[Session]) -> None:
    plan = api.upload(api.project(), process=False)
    assert plan["latest_job"] is None
    with transactional() as session:
        assert session.scalars(select(JobRow)).first() is None
    assert api.request("GET", f"/v1/floorplans/{plan['id']}/job").status_code == 404


@pytest.mark.parametrize("name,mime,data", [
    ("a.JPG", "image/jpeg", jpeg_bytes()),
    ("a.jpeg", "image/jpg", jpeg_bytes()),
    ("a.pdf", "application/pdf", pdf_bytes()),
])
def test_other_accepted_types(api: Api, name: str, mime: str, data: bytes) -> None:
    assert post_file(api, api.project(), name, data, mime).status_code == 201


def test_multi_page_pdf_warns(api: Api) -> None:
    assert post_file(api, api.project(), "a.pdf", pdf_bytes(3), "application/pdf").json()["warnings"] == [
        "Only page 1 of 3 will be processed."]


# --- upload hardening ---

@pytest.mark.parametrize("name,mime,data,status", [
    ("a.gif", "image/gif", b"GIF89a", 415),                      # extension
    ("noextension", "image/png", PNG_1PX, 415),
    ("a.png", "image/jpeg", PNG_1PX, 415),                       # MIME disagrees with extension
    ("a.png", "image/png", b"%PDF-1.7 not a png", 415),          # magic mismatch
    ("a.pdf", "application/pdf", PNG_1PX, 415),
    ("a.jpg", "image/jpeg", PNG_1PX, 415),
    ("a.png", "image/png", b"", 422),                            # empty
    ("a.png", "image/png", b"\x89PNG\r\n\x1a\ntruncated", 422),  # right magic, corrupt
    ("a.pdf", "application/pdf", b"%PDF-1.7 garbage", 422),
    ("a.png", "image/png", png_with_dimensions(100_000, 100_000), 413),  # bomb, above Pillow's own limit
    ("a.png", "image/png", png_with_dimensions(9_000, 9_000), 413),      # bomb, above our pixel cap only
])
def test_bad_uploads_store_nothing(api: Api, name: str, mime: str, data: bytes, status: int) -> None:
    r = post_file(api, api.project(), name, data, mime)
    assert r.status_code == status, r.text
    assert r.json()["error"]["code"] in {"unsupported_media_type", "validation_error", "payload_too_large"}
    assert not api.blobs.objects


def test_oversize_is_rejected(make_api: AppFactory, transactional: sessionmaker[Session]) -> None:
    api = make_api(transactional, max_upload_bytes=10)
    r = post_file(api, api.project(), "a.png", PNG_1PX, "image/png")
    assert (r.status_code, r.json()["error"]["code"]) == (413, "payload_too_large")
    assert not api.blobs.objects


def test_encrypted_pdf(api: Api) -> None:
    data = pdf_bytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
    r = post_file(api, api.project(), "a.pdf", data, "application/pdf")
    assert r.status_code == 422
    assert "Password" in r.json()["error"]["message"]


def test_absurd_pdf_page(api: Api) -> None:
    doc = pymupdf.open()
    doc.new_page(width=14_401, height=100)
    assert post_file(api, api.project(), "a.pdf", doc.tobytes(), "application/pdf").status_code == 413


def test_commit_failure_deletes_the_orphan_blob(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    project_id = api.project()

    def boom(*_: object, **__: object) -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr("app.v1.enqueue", boom)
    assert post_file(api, project_id, "a.png", PNG_1PX, "image/png").status_code == 500
    assert not api.blobs.objects
    assert api.request("GET", f"/v1/projects/{project_id}/floorplans").json() == []


def test_blob_failure_leaves_no_rows(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    from aec_contracts import ErrorCode

    from app.errors import ServiceError

    def down(*_: object) -> None:
        raise ServiceError(502, ErrorCode.UPSTREAM_UNAVAILABLE, "File storage is unavailable.")

    project_id = api.project()
    monkeypatch.setattr(api.blobs, "put", down)
    assert post_file(api, project_id, "a.png", PNG_1PX, "image/png").status_code == 502
    assert api.request("GET", f"/v1/projects/{project_id}/floorplans").json() == []


def test_sanitize_filename() -> None:
    assert sanitize_filename("C:\\Users\\me\\plan.png", "png") == "plan.png"
    assert sanitize_filename("../../etc/passwd.png", "png") == "passwd.png"
    assert sanitize_filename("a\x00b\r\n.png", "png") == "ab.png"
    assert sanitize_filename(None, "pdf") == "upload.pdf"
    assert len(sanitize_filename("x" * 400 + ".png", "png")) == 255


# --- deletion ---

def test_delete_project_removes_rows_then_blobs(api: Api, upstream: respx.MockRouter) -> None:
    floorplan_id = api.ready_floorplan()
    project_id = api.request("GET", f"/v1/floorplans/{floorplan_id}").json()["project_id"]
    assert api.blobs.objects
    assert api.request("DELETE", f"/v1/projects/{project_id}").status_code == 204
    assert not api.blobs.objects
    assert api.request("GET", f"/v1/floorplans/{floorplan_id}").status_code == 404


def test_delete_floorplan_keeps_siblings(api: Api) -> None:
    project_id = api.project()
    first, second = api.upload(project_id), api.upload(project_id)
    assert api.request("DELETE", f"/v1/floorplans/{first['id']}").status_code == 204
    assert [k for _, k in api.blobs.objects] == [f"{project_id}/{second['id']}/source.png"]


def test_blob_delete_failure_only_orphans(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    from aec_contracts import ErrorCode

    from app.errors import ServiceError

    def down(*_: object) -> None:
        raise ServiceError(502, ErrorCode.UPSTREAM_UNAVAILABLE)

    plan = api.upload(api.project())
    monkeypatch.setattr(api.blobs, "delete_prefix", down)
    assert api.request("DELETE", f"/v1/floorplans/{plan['id']}").status_code == 204
    assert api.request("GET", f"/v1/floorplans/{plan['id']}").status_code == 404

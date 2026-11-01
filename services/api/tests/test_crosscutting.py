"""Middleware, rate limiting, logging, and the migrations themselves."""

import logging
import os
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.main import create_app
from app.observability import JsonFormatter, redact, request_id_var
from app.orm import Base
from app.storage import SupabaseBlobStore

from .conftest import PNG_1PX, Api, AppFactory

ORIGIN = {"Origin": "http://localhost:3000"}


# --- security headers and CORS ---

def test_security_headers_on_every_response(api: Api) -> None:
    for path in ("/healthz", "/nope", "/v1/me"):
        headers = api.client.get(path).headers
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["Referrer-Policy"] == "no-referrer"
        assert headers["Cache-Control"] == "no-store"
        assert headers["X-Request-ID"]


def test_cors_only_allows_configured_origins(api: Api) -> None:
    allowed = api.client.options("/v1/me", headers={**ORIGIN, "Access-Control-Request-Method": "PATCH",
                                                    "Access-Control-Request-Headers": "authorization"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "PATCH" in allowed.headers["access-control-allow-methods"]
    assert "PUT" not in allowed.headers["access-control-allow-methods"]
    denied = api.client.get("/healthz", headers={"Origin": "https://evil.test"})
    assert "access-control-allow-origin" not in denied.headers


def test_unhandled_error_is_a_safe_500_with_cors(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_: object, **__: object) -> None:
        raise RuntimeError("secret-internal-detail")

    monkeypatch.setattr("app.v1.project_dtos", boom)
    r = api.client.get("/v1/projects", headers={**api.auth(), **ORIGIN})
    assert r.status_code == 500
    assert r.json() == {"error": {"code": "internal_error", "message": "Unexpected error.", "details": {}}}
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "secret-internal-detail" not in r.text


def test_text_postgres_cannot_store_is_422_not_500(api: Api) -> None:
    r = api.request("POST", "/v1/projects", json={"name": "bad\x00name"})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "validation_error")


# --- body limit ---

def test_declared_oversize_body_is_413_before_any_parsing(make_api: AppFactory,
                                                          transactional: sessionmaker[Session]) -> None:
    api = make_api(transactional, max_upload_bytes=10, max_audio_bytes=10)
    r = api.client.post("/v1/projects", content=b"x" * (2 * 1024 * 1024), headers=ORIGIN)
    assert (r.status_code, r.json()["error"]["code"]) == (413, "payload_too_large")
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert r.headers["X-Request-ID"]


def test_chunked_oversize_body_is_413(make_api: AppFactory, transactional: sessionmaker[Session]) -> None:
    api = make_api(transactional, max_upload_bytes=10, max_audio_bytes=10)
    project = uuid.uuid4()

    def chunks() -> Iterator[bytes]:
        for _ in range(4):
            yield b"x" * (512 * 1024)

    r = api.client.post(f"/v1/projects/{project}/floorplans", content=chunks(),
                        headers={**api.auth(), "Content-Type": "multipart/form-data; boundary=x"})
    assert (r.status_code, r.json()["error"]["code"]) == (413, "payload_too_large")


# --- rate limiting ---

def test_read_and_write_buckets_per_user(make_api: AppFactory, transactional: sessionmaker[Session],
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.ratelimit.clock", lambda: 1_000_000.0)  # one fixed window, no flake at the minute
    api = make_api(transactional, rate_limit_read_per_minute=2, rate_limit_write_per_minute=1)
    assert api.request("GET", "/v1/me").status_code == 200
    assert api.request("GET", "/v1/me").status_code == 200
    r = api.request("GET", "/v1/me")
    assert (r.status_code, r.json()["error"]["code"]) == (429, "rate_limited")
    assert 0 < int(r.headers["Retry-After"]) <= 60

    assert api.request("POST", "/v1/projects", json={"name": "a"}).status_code == 201  # separate bucket
    assert api.request("POST", "/v1/projects", json={"name": "b"}).status_code == 429
    assert api.request("GET", "/v1/me", "other_user").status_code == 200  # separate user


def test_window_resets(make_api: AppFactory, transactional: sessionmaker[Session],
                       monkeypatch: pytest.MonkeyPatch) -> None:
    now = 1_000_000.0
    monkeypatch.setattr("app.ratelimit.clock", lambda: now)
    api = make_api(transactional, rate_limit_read_per_minute=1)
    assert api.request("GET", "/v1/me").status_code == 200
    assert api.request("GET", "/v1/me").status_code == 429
    now += 60
    assert api.request("GET", "/v1/me").status_code == 200


def test_bad_tokens_are_limited_by_ip(make_api: AppFactory, transactional: sessionmaker[Session],
                                      monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.ratelimit.clock", lambda: 1_000_000.0)
    api = make_api(transactional, rate_limit_read_per_minute=2)
    statuses = [api.client.get("/v1/me", headers={"Authorization": "Bearer nope"}).status_code for _ in range(3)]
    assert statuses == [401, 401, 429]


# --- logging ---

@pytest.mark.parametrize("secret", [
    "Bearer abc.def.ghi", "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.c2ln", "sk-abcdef12345678", "token=abc123",
    "password=hunter2", "apikey=zzz",
])
def test_redaction(secret: str) -> None:
    assert secret not in redact(f"before {secret} after")
    assert "before" in redact(f"before {secret} after")


def test_json_logs_carry_request_id_and_redact(caplog: pytest.LogCaptureFixture) -> None:
    token = request_id_var.set("rid-1")
    try:
        record = logging.LogRecord("x", logging.INFO, "f", 1, "got Bearer abc.def", None, None)
        record.fields = {"user_id": "u1"}
        line = JsonFormatter("api").format(record)
    finally:
        request_id_var.reset(token)
    assert '"request_id": "rid-1"' in line
    assert '"user_id": "u1"' in line
    assert "abc.def" not in line


def test_access_log_has_user_id_and_no_token(api: Api, caplog: pytest.LogCaptureFixture) -> None:
    logging.getLogger().setLevel(logging.INFO)
    headers = api.auth()
    user = api.client.get("/v1/me", headers=headers).json()
    entry = next(r for r in caplog.records if r.getMessage() == "request" and "/v1/me" in str(r.__dict__))
    assert entry.fields["user_id"] == user["id"]  # type: ignore[attr-defined]
    assert headers["Authorization"].split()[1] not in caplog.text


# --- migrations ---

def test_rls_is_on_for_every_table_with_no_policies(engine: Engine) -> None:
    with engine.connect() as connection:
        tables = connection.execute(text(
            "select relname, relrowsecurity from pg_class c join pg_namespace n on n.oid = c.relnamespace "
            "where n.nspname = 'public' and c.relkind = 'r'")).all()
        policies = connection.execute(text("select count(*) from pg_policies where schemaname = 'public'")).scalar()
    assert {t.relname for t in tables} == set(Base.metadata.tables)
    assert all(t.relrowsecurity for t in tables)
    assert policies == 0


def test_orm_matches_the_migrations(engine: Engine) -> None:
    inspector = inspect(engine)
    for name, table in Base.metadata.tables.items():
        actual = {c["name"]: c for c in inspector.get_columns(name)}
        assert set(actual) == set(table.columns.keys()), name
        for column in table.columns:
            assert actual[column.name]["nullable"] == column.nullable, f"{name}.{column.name}"


def test_foreign_keys_are_all_indexed(engine: Engine) -> None:
    inspector = inspect(engine)
    for name in Base.metadata.tables:
        indexed = [list(i["column_names"]) for i in inspector.get_indexes(name)]
        indexed += [list(u["column_names"]) for u in inspector.get_unique_constraints(name)]
        for fk in inspector.get_foreign_keys(name):
            assert any(i[0] == fk["constrained_columns"][0] for i in indexed), f"{name}.{fk['constrained_columns']}"


def test_updated_at_triggers_fire(transactional: sessionmaker[Session]) -> None:
    with transactional() as session:
        session.execute(text("insert into users (clerk_user_id, updated_at) values ('t', '2000-01-01')"))
        session.execute(text("update users set display_name = 'x' where clerk_user_id = 't'"))
        year = session.execute(text("select extract(year from updated_at) from users")).scalar()
    assert year and year > 2000


# --- the real storage backend ---

@pytest.mark.skipif(not os.environ.get("SUPABASE_TEST"),
                    reason="opt-in: set SUPABASE_TEST=1, SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
def test_supabase_blob_store_round_trip() -> None:
    store = SupabaseBlobStore(Settings(_env_file=None))
    prefix = f"integration-test/{uuid.uuid4()}"
    for bucket, key, content_type in (("floorplans", f"{prefix}/source.png", "image/png"),
                                      ("artifacts", f"{prefix}/job/preprocessed.png", "image/png")):
        store.put(bucket, key, PNG_1PX, content_type)
        store.put(bucket, key, PNG_1PX, content_type)  # upsert
        assert store.get(bucket, key) == PNG_1PX
        assert "token=" in store.signed_urls(bucket, [key])[key]
        store.delete_prefix(bucket, f"{prefix}/")
        assert store.signed_urls(bucket, [key]) == {}


def test_blob_store_without_a_key_is_an_upstream_error() -> None:
    from app.errors import ServiceError

    store = SupabaseBlobStore(Settings(_env_file=None, environment="test"))
    with pytest.raises(ServiceError) as caught:
        store.put("floorplans", "a", b"x", "image/png")
    assert caught.value.status == 502


def test_create_app_has_no_startup_side_effects() -> None:
    assert create_app(Settings(_env_file=None, environment="test"))

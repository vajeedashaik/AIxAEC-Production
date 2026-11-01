"""Real Postgres (schema from the migrations), a fake JWKS and in-memory blobs. Downstream services are mocked by respx.

Each test session creates and drops its own database on TEST_DATABASE_URL's server, so dev data is never touched.
"""

import base64
import copy
import http.server
import json
import os
import re
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import jwt
import psycopg
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.clients import base as client_base
from app.config import Settings
from app.container import Container, build_container
from app.db import make_session_factory
from app.main import create_app

DEFAULT_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres"
MIGRATIONS = Path(__file__).parents[1] / "supabase" / "migrations"
FIXTURES = Path(__file__).parents[3] / "packages" / "contracts" / "fixtures"
ISSUER = "https://clerk.test"
AZP = "http://localhost:3000"
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
STAGE_NAMES = ["preprocess", "wall_detection", "ocr", "object_detection", "room_detection", "calibration",
               "semantic_assembly", "artifacts"]


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# --- database ---

@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    url = make_url(os.environ.get("TEST_DATABASE_URL", DEFAULT_URL))
    name = f"aec_test_{uuid.uuid4().hex[:12]}"
    plain = url.set(drivername="postgresql").render_as_string(hide_password=False)
    try:
        admin = psycopg.connect(plain, autocommit=True, connect_timeout=5)
    except psycopg.OperationalError as exc:
        pytest.fail(f"Tests need Postgres: run `supabase start` or set TEST_DATABASE_URL ({exc})", pytrace=False)
    admin.execute(f'create database "{name}"')
    test_url = url.set(database=name)
    with psycopg.connect(test_url.set(drivername="postgresql").render_as_string(hide_password=False),
                         autocommit=True) as conn:
        for migration in sorted(MIGRATIONS.glob("*.sql")):
            conn.execute(migration.read_text(encoding="utf-8").encode())
    yield test_url.render_as_string(hide_password=False)
    admin.execute(f'drop database "{name}" with (force)')
    admin.close()


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    engine = create_engine(database_url, connect_args={"prepare_threshold": None})
    yield engine
    engine.dispose()


@pytest.fixture
def transactional(engine: Engine) -> Iterator[sessionmaker[Session]]:
    """Per-test isolation: everything rolls back. One connection, so not for concurrency tests."""
    with engine.connect() as connection:
        outer = connection.begin()
        yield sessionmaker(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
        outer.rollback()


@pytest.fixture
def committed(database_url: str, engine: Engine) -> Iterator[sessionmaker[Session]]:
    """Really commits, for concurrency tests. Truncates afterwards."""
    factory = make_session_factory(database_url)
    yield factory
    factory.kw["bind"].dispose()
    with engine.begin() as connection:
        connection.execute(text("truncate users cascade"))


# --- Clerk ---

class Clerk:
    """Mints RS256 tokens and serves their JWKS over real HTTP, so PyJWKClient's caching is exercised for real."""

    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "kid-1"
        self.fetches = 0
        clerk = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                clerk.fetches += 1
                body = json.dumps(clerk.jwks()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/jwks.json"

    def jwks(self) -> dict[str, Any]:
        jwk = json.loads(RSAAlgorithm.to_jwk(self.key.public_key()))
        return {"keys": [{**jwk, "kid": self.kid, "use": "sig", "alg": "RS256"}]}

    def token(self, sub: str = "user_a", key: Any = None, kid: str | None = None,
              headers: dict[str, Any] | None = None, **claims: Any) -> str:
        now = int(time.time())
        payload = {"sub": sub, "iss": ISSUER, "azp": AZP, "iat": now, "nbf": now - 5, "exp": now + 300, **claims}
        return jwt.encode({k: v for k, v in payload.items() if v is not None}, key or self.key, algorithm="RS256",
                          headers={"kid": kid or self.kid, **(headers or {})})

    def rotate(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = f"kid-{uuid.uuid4().hex[:6]}"


@pytest.fixture(scope="session")
def clerk() -> Iterator[Clerk]:
    server = Clerk()
    yield server
    server.server.shutdown()


# --- blobs ---

@dataclass
class MemoryBlobs:
    objects: dict[tuple[str, str], bytes] = field(default_factory=dict)
    fail_get: bool = False

    def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        self.objects[(bucket, key)] = data

    def get(self, bucket: str, key: str) -> bytes:
        if self.fail_get:
            raise RuntimeError("secret-internal-detail")
        return self.objects[(bucket, key)]

    def signed_urls(self, bucket: str, keys: list[str]) -> dict[str, str]:
        return {k: f"http://blobs.test/{bucket}/{k}?token=x" for k in keys if (bucket, k) in self.objects}

    def delete_prefix(self, bucket: str, prefix: str) -> None:
        for b, k in list(self.objects):
            if b == bucket and k.startswith(prefix):
                del self.objects[(b, k)]


# --- the app ---

def make_settings(clerk: Clerk, **overrides: Any) -> Settings:
    defaults: dict[str, Any] = {
        "environment": "test", "log_level": "WARNING", "clerk_issuer": ISSUER, "clerk_jwks_url": clerk.url,
        "clerk_authorized_parties": [AZP], "vision_url": "http://vision.test", "geometry_url": "http://geometry.test",
        "language_url": "http://language.test", "rate_limit_read_per_minute": 100_000,
        "rate_limit_write_per_minute": 100_000,
    }
    return Settings(_env_file=None, **{**defaults, **overrides})


@dataclass
class Api:
    client: TestClient
    c: Container
    blobs: MemoryBlobs
    clerk: Clerk

    def auth(self, sub: str = "user_a") -> dict[str, str]:
        return {"Authorization": f"Bearer {self.clerk.token(sub)}"}

    def request(self, method: str, path: str, sub: str = "user_a", **kwargs: Any) -> httpx.Response:
        response: httpx.Response = self.client.request(method, path, headers=self.auth(sub), **kwargs)
        return response

    def project(self, sub: str = "user_a") -> str:
        r = self.request("POST", "/v1/projects", sub, json={"name": "Flat"})
        assert r.status_code == 201, r.text
        return str(r.json()["id"])

    def upload(self, project_id: str, sub: str = "user_a", process: bool = True) -> dict[str, Any]:
        r = self.request("POST", f"/v1/projects/{project_id}/floorplans?process={str(process).lower()}", sub,
                         files={"file": ("plan.png", PNG_1PX, "image/png")})
        assert r.status_code == 201, r.text
        result: dict[str, Any] = r.json()
        return result

    def run_worker(self) -> None:
        from app.worker import run_once
        assert run_once(self.c)

    def ready_floorplan(self, sub: str = "user_a") -> str:
        """Project + upload + one worker pass: HEAD is v1."""
        floorplan_id = str(self.upload(self.project(sub), sub)["id"])
        self.run_worker()
        return floorplan_id

    def edit(self, floorplan_id: str, sub: str = "user_a", **body: Any) -> httpx.Response:
        return self.request("POST", f"/v1/floorplans/{floorplan_id}/commands", sub,
                            json=body or {"instruction": "move the wall 300 mm left"})

    def head(self, floorplan_id: str) -> int | None:
        value: int | None = self.request("GET", f"/v1/floorplans/{floorplan_id}").json()["current_model_version"]
        return value


AppFactory = Callable[..., Api]


@pytest.fixture
def make_api(clerk: Clerk) -> AppFactory:
    def make(session_factory: sessionmaker[Session], **overrides: Any) -> Api:
        settings = make_settings(clerk, **overrides)
        blobs = MemoryBlobs()
        container = build_container(settings, blobs=blobs, session_factory=session_factory)
        return Api(TestClient(create_app(settings, container), raise_server_exceptions=False), container, blobs, clerk)

    return make


@pytest.fixture
def api(make_api: AppFactory, transactional: sessionmaker[Session]) -> Api:
    return make_api(transactional)


# --- downstream services ---

def analyze_result(floorplan_id: str, **overrides: Any) -> dict[str, Any]:
    model = fixture("apartment.model.json")
    model["floorplan_id"] = floorplan_id
    return {
        "status": "COMPLETED", "model": model,
        "stages": [{"name": n, "status": "ok", "duration_ms": 1, "error": None, "detail": {}} for n in STAGE_NAMES],
        "artifacts": [
            {"kind": "preprocessed", "content_type": "image/png",
             "data_base64": base64.b64encode(PNG_1PX).decode()},
            {"kind": "semantic_model", "content_type": "application/json",
             "data_base64": base64.b64encode(b"{}").decode()},
        ],
        "warnings": [], "error": None, **overrides,
    }


def floorplan_id_of(request: httpx.Request) -> str:
    found = re.search(rb'name="floorplan_id"\r\n\r\n([0-9a-f-]{36})', request.content)
    assert found
    return found.group(1).decode()


def applied(request: httpx.Request) -> httpx.Response:
    """Geometry's APPLIED answer: the input model plus one new wall."""
    body = json.loads(request.content)
    model = copy.deepcopy(body["model"])
    wall = {"id": str(uuid.uuid4()), "start": {"x": 1, "y": 1}, "end": {"x": 9, "y": 1}}
    model["walls"].append(wall)
    command = {"operation": "DELETE_WALL", "target_id": model["walls"][0]["id"]}
    return httpx.Response(200, json={"status": "APPLIED", "command": command, "model": model,
                                     "changes": {"added": [wall["id"]], "modified": [], "removed": []},
                                     "summary": "Moved wall 300 mm left."})


PARSED = {"status": "PARSED", "provider": "rules", "command": {"operation": "MOVE_WALL", "target_query": "kitchen",
                                                               "direction": "LEFT",
                                                               "distance": {"value": 300, "unit": "mm"}}}


@pytest.fixture
def upstream() -> Iterator[respx.MockRouter]:
    """Happy-path doubles for vision, geometry and language. Tests override single routes."""
    client_base_backoff = client_base.BACKOFF_SECONDS
    client_base.BACKOFF_SECONDS = 0
    envelope = fixture("api/floorplans.model.json")
    brief = {"rooms": [], "counts": envelope["summary"], "has_scale": True, "image_width": 1600, "image_height": 1200}
    with respx.mock(assert_all_called=False) as router:
        router.post("http://vision.test/v1/analyze", name="analyze").mock(
            side_effect=lambda r: httpx.Response(200, json=analyze_result(floorplan_id_of(r))))
        router.post("http://geometry.test/v1/models/brief", name="brief").respond(200, json=brief)
        router.post("http://geometry.test/v1/models/insights", name="insights").respond(200, json=envelope["insights"])
        router.post("http://geometry.test/v1/commands/execute", name="execute").mock(side_effect=applied)
        router.post("http://language.test/v1/commands/parse", name="parse").respond(200, json=PARSED)
        router.post("http://language.test/v1/rooms/classify", name="classify").mock(side_effect=_classified)
        router.post("http://language.test/v1/speech/transcribe", name="transcribe").respond(200, json={
            "text": "move the wall 300 mm left", "language": "en", "duration_ms": 900, "provider": "stub"})
        yield router
    client_base.BACKOFF_SECONDS = client_base_backoff


def _classified(request: httpx.Request) -> httpx.Response:
    labels = json.loads(request.content)["labels"]
    return httpx.Response(200, json={"results": [
        {"label": label, "room_type": "KITCHEN", "confidence": 0.9, "source": "rules"} for label in labels]})

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app

from .conftest import Api


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_healthz() -> None:
    client = TestClient(create_app(_settings(environment="test")))
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service": "api", "version": "0.1.0"}


def test_readyz_checks_the_database(api: Api) -> None:
    assert api.client.get("/readyz").status_code == 200


def test_readyz_reports_a_dead_database() -> None:
    settings = _settings(environment="test", database_url="postgresql+psycopg://x:x@127.0.0.1:1/x")
    r = TestClient(create_app(settings)).get("/readyz")
    assert (r.status_code, r.json()["error"]["code"]) == (503, "upstream_unavailable")


def test_request_id_is_echoed() -> None:
    client = TestClient(create_app(_settings(environment="test")))
    assert client.get("/healthz", headers={"X-Request-ID": "abc-123"}).headers["X-Request-ID"] == "abc-123"
    assert client.get("/healthz").headers["X-Request-ID"]


def test_unknown_route_uses_error_envelope() -> None:
    r = TestClient(create_app(_settings(environment="test"))).get("/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("overrides", [
    {},  # default internal token
    {"internal_service_token": "short", "clerk_issuer": "https://c.test"},
    {"internal_service_token": "x" * 32},  # no Clerk issuer
    {"internal_service_token": "x" * 32, "clerk_issuer": "https://c.test", "cors_origins": ["*"]},
])
def test_production_guards_refuse_unsafe_config(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _settings(environment="production", **overrides)


def test_production_accepts_safe_config() -> None:
    _settings(environment="production", internal_service_token="x" * 32, clerk_issuer="https://c.test")

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_healthz() -> None:
    client = TestClient(create_app(Settings(environment="test")))
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service": "vision", "version": "0.1.0"}
    assert client.get("/readyz").status_code == 200


def test_request_id_is_echoed() -> None:
    client = TestClient(create_app(Settings(environment="test")))
    assert client.get("/healthz", headers={"X-Request-ID": "abc-123"}).headers["X-Request-ID"] == "abc-123"
    assert client.get("/healthz").headers["X-Request-ID"]


def test_unknown_route_uses_error_envelope() -> None:
    r = TestClient(create_app(Settings(environment="test"))).get("/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_production_refuses_default_token() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(environment="production")
    Settings(environment="production", internal_service_token="x" * 32)  # type: ignore[arg-type]

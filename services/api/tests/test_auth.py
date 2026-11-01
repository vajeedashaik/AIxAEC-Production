import time

import httpx
import jwt
import pytest
import respx
from aec_contracts import Me
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr
from sqlalchemy.orm import Session, sessionmaker

from .conftest import Api, AppFactory, Clerk


def me(api: Api, token: str) -> httpx.Response:
    response: httpx.Response = api.client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    return response


def test_valid_token_provisions_once(api: Api, clerk: Clerk) -> None:
    first = Me.model_validate(me(api, clerk.token("user_1", email="A@Example.com", name="Ann")).json())
    assert (first.clerk_user_id, first.email, first.display_name) == ("user_1", "a@example.com", "Ann")
    assert Me.model_validate(me(api, clerk.token("user_1")).json()).id == first.id


@pytest.mark.parametrize("claims", [
    {"exp": int(time.time()) - 120},                  # expired past the leeway
    {"nbf": int(time.time()) + 120},                  # not valid yet
    {"iss": "https://evil.test"},
    {"iss": None},
    {"azp": "https://evil.test"},
    {"azp": None},
    {"exp": None},
    {"sub": None},
])
def test_bad_claims_are_rejected(api: Api, clerk: Clerk, claims: dict[str, object]) -> None:
    r = me(api, clerk.token(**claims))  # type: ignore[arg-type]
    assert (r.status_code, r.json()["error"]["code"]) == (401, "unauthorized")


def test_leeway_accepts_slight_clock_skew(api: Api, clerk: Clerk) -> None:
    assert me(api, clerk.token(exp=int(time.time()) - 10)).status_code == 200


@pytest.mark.parametrize("token", ["garbage", "a.b.c", "Bearer", "eyJhbGciOiJub25lIn0.e30."])
def test_malformed_tokens(api: Api, token: str) -> None:
    assert me(api, token).status_code == 401


def test_unknown_kid_and_forged_signature(api: Api, clerk: Clerk) -> None:
    assert me(api, clerk.token(kid="nope")).status_code == 401
    forged = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert me(api, clerk.token(key=forged)).status_code == 401


def test_hs256_and_none_algorithms_are_refused(api: Api, clerk: Clerk) -> None:
    claims = {"sub": "x", "iss": "https://clerk.test", "azp": "http://localhost:3000", "exp": time.time() + 60}
    hs = jwt.encode(claims, "x" * 40, algorithm="HS256", headers={"kid": clerk.kid})
    none = jwt.encode(claims, "", algorithm="none", headers={"kid": clerk.kid})
    assert me(api, hs).status_code == 401
    assert me(api, none).status_code == 401


def test_jwks_is_cached_and_refreshed_on_rotation(make_api: AppFactory, transactional: sessionmaker[Session],
                                                  clerk: Clerk) -> None:
    api = make_api(transactional)
    assert api.c.verifier.jwks
    api.c.verifier.jwks.cooldown_duration = 0
    start = clerk.fetches
    assert me(api, clerk.token()).status_code == 200
    assert me(api, clerk.token()).status_code == 200
    assert clerk.fetches == start + 1

    clerk.rotate()
    assert me(api, clerk.token()).status_code == 200
    assert clerk.fetches == start + 2


def test_unknown_kid_cannot_flood_the_jwks_endpoint(api: Api, clerk: Clerk) -> None:
    assert me(api, clerk.token()).status_code == 200
    me(api, clerk.token(kid="first-miss"))
    start = clerk.fetches
    for i in range(5):
        assert me(api, clerk.token(kid=f"nope-{i}")).status_code == 401
    assert clerk.fetches == start


def test_jwks_outage_is_503(make_api: AppFactory, transactional: sessionmaker[Session], clerk: Clerk) -> None:
    api = make_api(transactional, clerk_jwks_url="http://127.0.0.1:1/jwks.json")
    assert me(api, clerk.token()).status_code == 503


def test_no_issuer_configured_rejects_everything(make_api: AppFactory, transactional: sessionmaker[Session],
                                                 clerk: Clerk) -> None:
    api = make_api(transactional, clerk_issuer=None, clerk_jwks_url=None)
    assert me(api, clerk.token()).status_code == 401


def test_duplicate_email_does_not_merge_accounts(api: Api, clerk: Clerk) -> None:
    first = me(api, clerk.token("user_1", email="same@example.com")).json()
    second = me(api, clerk.token("user_2", email="same@example.com")).json()
    assert first["id"] != second["id"]
    assert second["email"] is None


def test_profile_falls_back_to_clerk_api_best_effort(api: Api, clerk: Clerk) -> None:
    api.c.settings.clerk_secret_key = SecretStr("sk_test_x")
    with respx.mock() as router:
        route = router.get("https://api.clerk.com/v1/users/user_9").respond(200, json={
            "primary_email_address_id": "e2", "first_name": "Bo", "last_name": None,
            "email_addresses": [{"id": "e1", "email_address": "old@x.io"}, {"id": "e2", "email_address": "bo@x.io"}],
        })
        body = me(api, clerk.token("user_9")).json()
        assert route.called
        assert (body["email"], body["display_name"]) == ("bo@x.io", "Bo")

        router.get("https://api.clerk.com/v1/users/user_10").respond(500)
        assert me(api, clerk.token("user_10")).json()["email"] is None

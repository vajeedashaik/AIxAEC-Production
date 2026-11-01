"""Offline verification of Clerk session JWTs against the JWKS."""

import logging
from typing import Any

import jwt
from aec_contracts import ErrorCode
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWTError

from .config import Settings
from .errors import ServiceError

log = logging.getLogger("api.auth")
LEEWAY_SECONDS = 30


def unauthorized() -> ServiceError:
    return ServiceError(401, ErrorCode.UNAUTHORIZED, "Sign in to continue.")


class ClerkVerifier:
    def __init__(self, settings: Settings) -> None:
        self._issuer = settings.clerk_issuer
        self._parties = settings.clerk_authorized_parties
        url = settings.clerk_jwks_url or (f"{self._issuer.rstrip('/')}/.well-known/jwks.json" if self._issuer else None)
        # PyJWKClient refreshes on an unknown kid at most once per cooldown, so bad tokens cannot flood Clerk.
        self.jwks = PyJWKClient(url, lifespan=3600, timeout=5) if url else None

    def verify(self, token: str) -> dict[str, Any]:
        if self.jwks is None or self._issuer is None:
            log.error("CLERK_ISSUER is not set, so no token can be verified")
            raise unauthorized()
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if header.get("alg") != "RS256" or not isinstance(kid, str):
                raise unauthorized()
            claims = jwt.decode(
                token, self.jwks.get_signing_key(kid).key, algorithms=["RS256"], issuer=self._issuer,
                leeway=LEEWAY_SECONDS, options={"require": ["exp", "iss", "sub"], "verify_aud": False},
            )
        except PyJWKClientConnectionError as exc:
            log.warning("JWKS fetch failed", extra={"fields": {"error": type(exc).__name__}})
            raise ServiceError(503, ErrorCode.UPSTREAM_UNAVAILABLE, "Sign-in is temporarily unavailable.") from exc
        except PyJWTError as exc:
            raise unauthorized() from exc
        if claims.get("azp") not in self._parties:
            raise unauthorized()
        return claims

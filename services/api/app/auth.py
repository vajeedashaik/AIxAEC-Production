"""get_current_user: Clerk token → users row. The user id never comes from the client."""

import logging
from typing import Annotated, Any
from urllib.parse import quote

import httpx
from aec_contracts import Me
from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .clerk import unauthorized
from .config import Settings
from .container import Container
from .errors import ServiceError
from .orm import UserRow
from .ratelimit import Bucket

log = logging.getLogger("api.auth")
CLERK_API = "https://api.clerk.com/v1"


def container(request: Request) -> Container:
    c: Container = request.app.state.container
    return c


Ctx = Annotated[Container, Depends(container)]


def _profile_from_clerk(settings: Settings, sub: str) -> tuple[str | None, str | None]:
    """Best effort: a user with no email is still a valid user."""
    if settings.clerk_secret_key is None:
        return None, None
    try:
        response = httpx.get(f"{CLERK_API}/users/{quote(sub, safe='')}", timeout=3,
                             headers={"Authorization": f"Bearer {settings.clerk_secret_key.get_secret_value()}"})
        response.raise_for_status()
        user = response.json()
        primary = user.get("primary_email_address_id")
        emails = [e.get("email_address") for e in user.get("email_addresses", []) if e.get("id") == primary]
        name = " ".join(n for n in (user.get("first_name"), user.get("last_name")) if n)
        return (emails[0] if emails else None, name or None)
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        log.warning("Clerk profile lookup failed", extra={"fields": {"error": type(exc).__name__}})
        return None, None


def _provision(session: Session, settings: Settings, sub: str, claims: dict[str, Any]) -> UserRow:
    email, name = claims.get("email"), claims.get("name")
    email, name = (email if isinstance(email, str) else None, name if isinstance(name, str) else None)
    if email is None and name is None:
        session.rollback()  # no open transaction across the Clerk call
        email, name = _profile_from_clerk(settings, sub)
    values = {"clerk_user_id": sub, "email": email.lower() if email else None, "display_name": name}
    statement = insert(UserRow).on_conflict_do_nothing(index_elements=[UserRow.clerk_user_id])
    try:
        session.execute(statement, values)
        session.commit()
    except IntegrityError:
        # The email belongs to another Clerk identity. Never merge accounts on email.
        session.rollback()
        session.execute(statement, {**values, "email": None})
        session.commit()
    return session.scalars(select(UserRow).where(UserRow.clerk_user_id == sub)).one()


def current_user(request: Request, c: Ctx, authorization: Annotated[str | None, Header()] = None) -> Me:
    bucket: Bucket = "read" if request.method in ("GET", "HEAD") else "write"
    scheme, _, token = (authorization or "").partition(" ")
    try:
        if scheme.lower() != "bearer" or not token.strip():
            raise unauthorized()
        claims = c.verifier.verify(token.strip())
    except ServiceError:
        c.limiter.check(f"ip:{request.client.host if request.client else '-'}", bucket)
        raise
    sub = claims["sub"]
    c.limiter.check(f"user:{sub}", bucket)
    with c.session_factory() as session:
        row = session.scalars(select(UserRow).where(UserRow.clerk_user_id == sub)).first()
        row = row or _provision(session, c.settings, sub, claims)
        request.state.user_id = str(row.id)
        return Me(id=row.id, clerk_user_id=row.clerk_user_id, email=row.email, display_name=row.display_name,
                  created_at=row.created_at)


CurrentUser = Annotated[Me, Depends(current_user)]

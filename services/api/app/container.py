"""Everything a request or worker needs, built once per process."""

from dataclasses import dataclass, field

from aec_contracts import Insights
from sqlalchemy.orm import Session, sessionmaker

from .clerk import ClerkVerifier
from .clients.geometry import GeometryClient
from .clients.language import LanguageClient
from .clients.vision import VisionClient
from .config import Settings
from .db import make_session_factory
from .ratelimit import RateLimiter
from .storage import BlobStore, SupabaseBlobStore


@dataclass
class Container:
    settings: Settings
    session_factory: sessionmaker[Session]
    blobs: BlobStore
    vision: VisionClient
    geometry: GeometryClient
    language: LanguageClient
    verifier: ClerkVerifier
    limiter: RateLimiter
    insights_cache: dict[tuple[object, int], Insights] = field(default_factory=dict)


def build_container(settings: Settings, database_url: str | None = None,
                    blobs: BlobStore | None = None,
                    session_factory: sessionmaker[Session] | None = None) -> Container:
    token = settings.internal_service_token.get_secret_value()
    return Container(
        settings=settings,
        session_factory=session_factory or make_session_factory(database_url or settings.database_url),
        blobs=blobs or SupabaseBlobStore(settings),
        vision=VisionClient("vision", settings.vision_url, token, timeout=180),
        geometry=GeometryClient("geometry", settings.geometry_url, token, timeout=30),
        language=LanguageClient("language", settings.language_url, token, timeout=30),
        verifier=ClerkVerifier(settings),
        limiter=RateLimiter(settings.rate_limit_read_per_minute, settings.rate_limit_write_per_minute),
    )

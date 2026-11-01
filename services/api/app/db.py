"""Engine and session factory. The schema comes from supabase/migrations, never create_all."""

from datetime import UTC, datetime

from sqlalchemy import Dialect, create_engine
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """Always UTC, so DTOs serialise with Z whatever the session time zone is."""

    impl = TIMESTAMP(timezone=True)
    cache_ok = True

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return value.astimezone(UTC) if value else None


def make_session_factory(database_url: str) -> sessionmaker[Session]:
    # prepare_threshold=None: Supabase's transaction-mode pooler cannot use prepared statements.
    engine = create_engine(database_url, pool_pre_ping=True,
                           connect_args={"prepare_threshold": None, "connect_timeout": 5})
    return sessionmaker(engine, expire_on_commit=False)

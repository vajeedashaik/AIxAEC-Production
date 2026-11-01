"""Settings from env vars (phases/shared/CONTRACTS.md §10)."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_INTERNAL_TOKEN = "dev-internal-token-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "api"
    version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"
    internal_service_token: SecretStr = SecretStr(DEFAULT_INTERNAL_TOKEN)
    database_url: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres"
    supabase_url: str = "http://127.0.0.1:54321"
    supabase_service_role_key: SecretStr | None = None
    clerk_issuer: str | None = None
    clerk_jwks_url: str | None = None  # defaults to {clerk_issuer}/.well-known/jwks.json
    clerk_authorized_parties: list[str] = ["http://localhost:3000", "http://localhost:3001"]
    clerk_secret_key: SecretStr | None = None
    vision_url: str = "http://127.0.0.1:8001"
    geometry_url: str = "http://127.0.0.1:8002"
    language_url: str = "http://127.0.0.1:8003"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]
    max_upload_bytes: int = 26_214_400
    max_audio_bytes: int = 10_485_760
    max_projects_per_user: int = 200
    max_floorplans_per_project: int = 100
    processing_max_attempts: int = 3
    processing_stale_seconds: int = 600
    worker_poll_seconds: float = 2
    rate_limit_read_per_minute: int = 300
    rate_limit_write_per_minute: int = 90

    @model_validator(mode="after")
    def _production_guards(self) -> Self:
        token = self.internal_service_token.get_secret_value()
        if self.environment == "production" and (token == DEFAULT_INTERNAL_TOKEN or len(token) < 32):
            raise ValueError("INTERNAL_SERVICE_TOKEN must be set to a non-default value of >= 32 chars in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

"""Settings from env vars (phases/shared/CONTRACTS.md §10)."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_INTERNAL_TOKEN = "dev-internal-token-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "vision"
    version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"
    internal_service_token: SecretStr = SecretStr(DEFAULT_INTERNAL_TOKEN)
    ocr_provider: Literal["auto", "stub", "tesseract", "textract"] = "auto"
    tesseract_cmd: str | None = None
    object_detector: Literal["heuristic", "none", "yolo"] = "heuristic"
    yolo_weights_path: str | None = None
    image_max_dimension: int = 2400
    max_image_pixels: int = 64_000_000
    max_upload_bytes: int = 26_214_400

    @model_validator(mode="after")
    def _production_guards(self) -> Self:
        token = self.internal_service_token.get_secret_value()
        if self.environment == "production" and (token == DEFAULT_INTERNAL_TOKEN or len(token) < 32):
            raise ValueError("INTERNAL_SERVICE_TOKEN must be set to a non-default value of >= 32 chars in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

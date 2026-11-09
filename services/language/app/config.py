"""Settings from env vars (phases/shared/CONTRACTS.md §10)."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_INTERNAL_TOKEN = "dev-internal-token-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "language"
    version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"
    internal_service_token: SecretStr = SecretStr(DEFAULT_INTERNAL_TOKEN)
    command_parser: Literal["hybrid", "rules", "llm"] = "hybrid"
    llm_base_url: str = "http://127.0.0.1:20128/v1"
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = 20
    stt_provider: Literal["whisper", "stub", "transcribe"] = "whisper"
    whisper_model: str = "base.en"
    whisper_compute_type: str = "int8"
    # AWS profile (docs/AWS_MIGRATION_PLAN.md): the defaults are the free stack
    llm_provider: Literal["openai", "bedrock"] = "openai"
    aws_region: str | None = None
    s3_bucket: str | None = None

    @model_validator(mode="after")
    def _production_guards(self) -> Self:
        token = self.internal_service_token.get_secret_value()
        if self.environment == "production" and (token == DEFAULT_INTERNAL_TOKEN or len(token) < 32):
            raise ValueError("INTERNAL_SERVICE_TOKEN must be set to a non-default value of >= 32 chars in production")
        bedrock, transcribe = self.llm_provider == "bedrock", self.stt_provider == "transcribe"
        if self.command_parser == "llm" and not (self.llm_model and (self.llm_api_key or bedrock)):
            raise ValueError("COMMAND_PARSER=llm requires LLM_MODEL and LLM_API_KEY (LLM_MODEL alone for Bedrock)")
        if (bedrock or transcribe) and not self.aws_region:
            raise ValueError("LLM_PROVIDER=bedrock and STT_PROVIDER=transcribe require AWS_REGION")
        if transcribe and not self.s3_bucket:
            raise ValueError("STT_PROVIDER=transcribe requires S3_BUCKET")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

"""Environment-only deployment configuration."""
from functools import lru_cache
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://romana:romana@localhost:5432/romana"
    telegram_bot_token: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    model_tutor: str = "openai/gpt-4.1-mini"
    model_assessor: str = "openai/gpt-4.1-mini"
    model_max_tokens: int = Field(default=1800, ge=256, le=8000)
    model_timeout_seconds: float = Field(default=45, gt=0, le=180)
    model_retries: int = Field(default=2, ge=0, le=4)


@lru_cache
def get_settings() -> Settings:
    return Settings()

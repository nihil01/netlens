from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "local"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://netlens:netlens@localhost:5432/netlens"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    auth_enabled: bool = False
    keycloak_issuer_url: AnyHttpUrl | None = None
    keycloak_audience: str = "netlens-api"

    netbox_mode: Literal["mock", "real"] = "mock"
    netbox_url: AnyHttpUrl | None = None
    netbox_token: str | None = None
    netbox_verify_ssl: bool = True

    opensearch_mode: Literal["mock", "real"] = "mock"
    opensearch_url: AnyHttpUrl | None = None
    opensearch_username: str | None = None
    opensearch_password: str | None = None
    opensearch_verify_ssl: bool = True
    opensearch_index_pattern: str = "logs-*"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
